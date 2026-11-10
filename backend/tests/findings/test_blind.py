"""Second looks are blind (Decision 0008).

Nothing in a review card, a help-wanted task for a second look, or the page
of a finding someone hasn't answered reveals the finder's claim (on a card)
or anyone's answers (anywhere), including through counts, ordering or error
messages.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.vocab import FeatureClass, Period, Visible
from tests.findings.support import API, answer, create
from tests.helpers import ClientAs, MakeFinding, MakeUser, error_code

# Words that appear only in the finder's claim or in other people's answers.
CLAIM = {"title": "Zebra ring on the down", "description": "Quokka-shaped bank", "period": Period.ROMAN}
ANSWER_NOTE = "Narwhal tusk shadow"
CARD_KEYS = {"public_id", "place", "view_state"}
PLACE_KEYS = {"lon", "lat", "grid_ref"}
VIEW_KEYS = {"layer", "zoom", "bearing", "pitch", "sun_azimuth", "sun_altitude", "exaggeration"}


def _claimed(db: Session, finder: User, **kwargs) -> Finding:
    return create(
        db,
        finder,
        feature_class=kwargs.pop("feature_class", FeatureClass.HILLFORT),
        title=kwargs.pop("title", CLAIM["title"]),
        description=CLAIM["description"],
        period=CLAIM["period"],
        view_state={"layer": "slope", "zoom": 16, "sun_azimuth": 300},
        **kwargs,
    )


def _no_claim_or_answers(text: str) -> None:
    for secret in (CLAIM["title"], CLAIM["description"], "roman", "hillfort", "moat", ANSWER_NOTE, "spotted"):
        assert secret not in text, f"{secret!r} is visible"


def test_a_card_has_the_place_and_view_and_nothing_else(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper, reviewer = make_user(), make_user(), make_user()
    finding = _claimed(db, finder)
    answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.MOAT, note=ANSWER_NOTE)

    response = client_as(reviewer).get(f"{API}/review/next")
    assert response.status_code == 200
    (card,) = response.json()["items"]
    assert set(card) == CARD_KEYS
    assert set(card["place"]) == PLACE_KEYS
    assert set(card["view_state"]) == VIEW_KEYS
    assert card["view_state"]["sun_azimuth"] == 300
    _no_claim_or_answers(response.text)
    for word in ('"tier"', '"state"', "confidence", "count", "observ", "seen", "class", "title"):
        assert word not in response.text, f"{word} appears on a card"


def test_a_view_cannot_smuggle_anything_onto_a_card(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding(
        view_state={"layer": "slope", "note": "it's a hillfort", "zoom": "very", "pitch": 40}
    )
    from fieldclub.services import findings

    findings.reassess(db, findings.lock(db, finding), None)
    db.commit()
    (card,) = client_as(make_user()).get(f"{API}/review/next").json()["items"]
    assert card["view_state"] == {**dict.fromkeys(VIEW_KEYS), "layer": "slope", "pitch": 40}


def test_the_queue_puts_findings_one_answer_from_moving_up_first_whatever_they_claim(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper, reviewer = make_user(), make_user(), make_user()
    start = datetime(2026, 11, 1, tzinfo=UTC)
    made = []
    for n, (feature_class, title) in enumerate(
        [(FeatureClass.HILLFORT, "Aardvark"), (FeatureClass.UNKNOWN, "Zulu"), (FeatureClass.MOAT, "Mmm")]
    ):
        with time_machine.travel(start + timedelta(hours=n), tick=False):
            made.append(_claimed(db, finder, feature_class=feature_class, title=title))
    # The newest one gets one "yes", so one more answer would lift it to Seen.
    answer(db, made[2], helper)
    assert [f.answers_to_next for f in made] == [2, 2, 1]

    order = [card["public_id"] for card in client_as(reviewer).get(f"{API}/review/next").json()["items"]]
    assert order == [made[2].public_id, made[0].public_id, made[1].public_id]

    # Swapping the claims changes nothing.
    made[0].feature_class, made[1].feature_class = made[1].feature_class, made[0].feature_class
    made[0].title, made[1].title = "Zulu", "Aardvark"
    db.commit()
    again = [card["public_id"] for card in client_as(reviewer).get(f"{API}/review/next").json()["items"]]
    assert again == order


def test_the_queue_leaves_out_your_own_findings_and_ones_you_have_answered(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    you, other = make_user(), make_user()
    yours = _claimed(db, you)
    answered = _claimed(db, other)
    waiting = _claimed(db, other)
    answer(db, answered, you, Visible.NO)
    offered = {card["public_id"] for card in client_as(you).get(f"{API}/review/next").json()["items"]}
    assert offered == {waiting.public_id}
    assert yours.public_id not in offered


def test_the_queue_prefers_nearby_findings_and_pages(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, reviewer = make_user(), make_user()
    far = _claimed(db, finder, lon=-3.0, lat=54.4)  # the Lake District
    near = [_claimed(db, finder, lon=-1.85 + 0.01 * n, lat=51.43) for n in range(3)]
    client = client_as(reviewer)
    first = client.get(f"{API}/review/next", params={"lon": -1.85, "lat": 51.43, "limit": 2}).json()
    assert [c["public_id"] for c in first["items"]] == [near[0].public_id, near[1].public_id]
    rest = client.get(
        f"{API}/review/next", params={"lon": -1.85, "lat": 51.43, "limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [c["public_id"] for c in rest["items"]] == [near[2].public_id, far.public_id]
    assert rest["next_cursor"] is None
    assert error_code(client.get(f"{API}/review/next", params={"lon": -1.85})) == "invalid_point"
    assert error_code(client.get(f"{API}/review/next", params={"cursor": "nope"})) == "invalid_cursor"


def test_a_page_hides_answers_until_you_have_given_yours(
    db: Session, client, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper, reviewer = make_user(), make_user(), make_user()
    finding = _claimed(db, finder)
    answer(db, finding, helper, Visible.NO, feature_class=FeatureClass.MOAT, note=ANSWER_NOTE)
    path = f"{API}/findings/{finding.public_id}"

    for viewer in (client, client_as(reviewer)):
        page = viewer.get(path)
        body = page.json()
        # The claim is on the page, where it's discussed.
        assert body["title"] == CLAIM["title"]
        assert body["answers_visible"] is False
        assert body["assessment"]["tallies"] is None
        assert {c["kind"] for c in body["credits"]} == {"spotted", "answered"}
        for secret in (
            ANSWER_NOTE,
            "moat",
            "could_not_see",
            "observation_count",
            "unseen",
            "community_class",
        ):
            assert secret not in page.text
        refused = viewer.get(f"{path}/observations")
        assert refused.status_code in (401, 403)
    refused = client_as(reviewer).get(f"{path}/observations")
    assert error_code(refused) == "answer_first"
    assert not any(ch.isdigit() for ch in refused.json()["error"]["message"])

    # The finder sees everything without answering.
    as_finder = client_as(finder).get(path).json()
    assert as_finder["answers_visible"] is True
    assert as_finder["assessment"]["tallies"]["unseen"] == 1.0
    assert "could_not_see" in {c["kind"] for c in as_finder["credits"]}

    # Once you've answered, you see the others.
    reveal = client_as(reviewer).put(
        f"{path}/observation", json={"visible": "yes", "feature_class": "hillfort"}
    )
    assert reveal.status_code == 200
    seen = client_as(reviewer).get(path).json()
    assert seen["answers_visible"] is True
    assert seen["my_observation"]["visible"] == "yes"
    answers = client_as(reviewer).get(f"{path}/observations").json()["items"]
    assert {a["note"] for a in answers} == {ANSWER_NOTE, None}

    # Taking your answer back hides them again.
    assert client_as(reviewer).delete(f"{path}/observation").status_code == 204
    assert client_as(reviewer).get(path).json()["assessment"]["tallies"] is None


def test_the_reveal_shows_the_finding_in_full_and_how_your_answer_compares(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, first, second = make_user(), make_user(), make_user()
    finding = _claimed(db, finder)
    answer(db, finding, first, Visible.YES, feature_class=FeatureClass.HILLFORT)
    response = client_as(second).put(
        f"{API}/findings/{finding.public_id}/observation", json={"visible": "yes", "feature_class": "moat"}
    )
    body = response.json()
    assert (body["tier_before"], body["tier_after"], body["moved_up"]) == ("spotted", "seen", True)
    assert body["comparison"] == {
        "finder_class": "hillfort",
        # Two of the three named a hillfort, which is the two-thirds agreement needed.
        "community_class": "hillfort",
        "matches_finder": False,
        "others": {"yes": 1, "unsure": 0, "no": 0},
    }
    assert body["finding"]["title"] == CLAIM["title"]
    assert body["finding"]["answers_visible"] is True
    assert body["observation"]["feature_class"] == "moat"


@pytest.mark.parametrize(
    ("who", "code"),
    [("finder", "own_finding"), ("member", "location_hidden")],
)
def test_refusals_say_nothing_about_answers(
    db: Session, client_as: ClientAs, make_user: MakeUser, who: str, code: str
) -> None:
    finder, helper = make_user(), make_user("trusted")
    finding = _claimed(db, finder, requested_sensitivity="restricted")
    answer(db, finding, helper, Visible.NO, feature_class=FeatureClass.MOAT, note=ANSWER_NOTE)
    viewer = finder if who == "finder" else make_user()
    response = client_as(viewer).put(
        f"{API}/findings/{finding.public_id}/observation", json={"visible": "yes"}
    )
    assert response.status_code == 403
    assert error_code(response) == code
    _no_claim_or_answers(response.text)
    assert not any(ch.isdigit() for ch in response.text)


def test_help_wanted_tasks_for_second_looks_are_blind(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper, reviewer = make_user(), make_user(), make_user()
    finding = _claimed(db, finder)
    answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.MOAT, note=ANSWER_NOTE)
    response = client_as(reviewer).get(f"{API}/review/tasks", params={"code": "need_observers"})
    (group,) = response.json()["groups"]
    (task,) = group["items"]
    assert (task["public_id"], task["step"], task["finding"]) == (finding.public_id, None, None)
    _no_claim_or_answers(response.text)
    assert "people" not in response.text
    assert "prompt" not in response.text


def test_lists_and_the_map_carry_no_tallies(db: Session, client, make_user: MakeUser) -> None:
    finding = _claimed(db, make_user())
    answer(db, finding, make_user(), Visible.NO, feature_class=FeatureClass.MOAT, note=ANSWER_NOTE)
    for params in ({}, {"format": "geojson"}):
        text = client.get(f"{API}/findings", params=params).text
        for secret in (ANSWER_NOTE, "moat", "observation_count", "unseen", "community_class", "tallies"):
            assert secret not in text
