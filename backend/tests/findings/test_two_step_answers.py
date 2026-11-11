"""A second look in two steps: the answer first, blind, then its detail and the reveal (Decision 0008).

The detail is asked for after the answer, never before it (docs/UI.md). An
answer sent saying that detail follows is stored and counts at once, and its
reply reveals nothing. Until the detail is added, or skipped, the reviewer is
someone who hasn't seen the answers, on every route.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.services import records, review
from fieldclub.vocab import FeatureClass, Visible
from tests.findings.support import API, answer, create
from tests.helpers import ClientAs, MakeUser, add_record, add_source, error_code, lon_lat

TITLE = "Zebra ring on the down"
OTHER_NOTE = "Narwhal tusk shadow"
# Fields of a finding's page that are about the viewer, not about what they may see of the answers.
OWN = ("my_observation", "following", "actions")


def _answered(db: Session, make_user: MakeUser) -> tuple[User, Finding]:
    """A finding someone else has answered, naming a class and leaving a note."""
    finder = make_user()
    finding = create(db, finder, feature_class=FeatureClass.HILLFORT, title=TITLE)
    answer(db, finding, make_user(), Visible.YES, feature_class=FeatureClass.MOAT, note=OTHER_NOTE)
    return finder, finding


def _path(finding: Finding) -> str:
    return f"{API}/findings/{finding.public_id}/observation"


def _page(client: TestClient, finding: Finding) -> dict[str, Any]:
    response = client.get(f"{API}/findings/{finding.public_id}")
    assert response.status_code == 200
    return response.json()


def _seen(client: TestClient, finding: Finding) -> float:
    return _page(client, finding)["assessment"]["tallies"]["seen"]


def test_an_answer_whose_detail_follows_counts_at_once_and_shows_nothing(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, finding = _answered(db, make_user)
    before = _seen(client_as(finder), finding)

    held = client_as(make_user()).put(_path(finding), json={"visible": "yes", "detail_follows": True})
    assert held.status_code == 200, held.text
    body = held.json()
    assert set(body) == {"revealed", "observation"}
    assert body["revealed"] is False
    assert body["observation"]["revealed"] is False
    assert body["observation"]["visible"] == "yes"
    for secret in (TITLE, OTHER_NOTE, "moat", "hillfort", "tier"):
        assert secret not in held.text
    assert _seen(client_as(finder), finding) == before + 1.0


def test_an_answer_whose_detail_follows_carries_only_whether_it_is_seen(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    for extra in ({"feature_class": "moat"}, {"note": "Faint"}, {"not_modern": True}, {"period": "roman"}):
        refused = client.put(_path(finding), json={"visible": "yes", "detail_follows": True, **extra})
        assert refused.status_code == 422, extra
        assert error_code(refused) == "validation_error"


def _without_own(page: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in page.items() if key not in OWN}


def test_between_the_steps_the_reviewer_learns_nothing_through_any_route(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, finding = _answered(db, make_user)
    add_record(db, add_source(db), "Moat", *lon_lat(finding.location))
    reviewer, stranger = make_user(), make_user()
    held = client_as(reviewer).put(_path(finding), json={"visible": "no", "detail_follows": True})
    assert held.status_code == 200
    # As if enough people had named it a moat, which the suggestions show to those who may see answers.
    db.refresh(finding)
    finding.community_class = FeatureClass.MOAT.value
    db.commit()
    pending, fresh = client_as(reviewer), client_as(stranger)

    # The finding's page is the one a member who hasn't answered gets, but for their own answer.
    page = _page(pending, finding)
    assert page["answers_visible"] is False
    assert page["assessment"]["tallies"] is None
    assert page["my_observation"]["revealed"] is False
    assert _without_own(page) == _without_own(_page(fresh, finding))
    assert all(step["people"] is None for step in page["assessment"]["next_steps"])
    assert OTHER_NOTE not in str(page)

    # The other answers, and the people who gave them.
    for client in (pending, fresh):
        listed = client.get(f"{API}/findings/{finding.public_id}/observations")
        assert error_code(listed) == "answer_first"
    credited = {credit["user"]["handle"] for credit in page["credits"]}
    assert credited == {finder.handle}

    # Suggested records weigh the community class only for those who may see answers.
    assert records.suggest_for_finding(db, finding, reviewer).items[0].type_fit is False
    suggested = pending.get(f"{API}/findings/{finding.public_id}/suggested-records").json()
    assert suggested == fresh.get(f"{API}/findings/{finding.public_id}/suggested-records").json()

    # Nothing in the feed, the notifications or the queue tells them more than a stranger.
    assert pending.get(f"{API}/activity").json() == fresh.get(f"{API}/activity").json()
    assert pending.get(f"{API}/notifications").json()["items"] == []
    assert pending.get(f"{API}/review/next").json()["items"] == []

    # Once they take the reveal, they see the answers like anyone who has answered.
    revealed = pending.post(f"{_path(finding)}/reveal", json={})
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["comparison"]["others"] == {"yes": 1, "unsure": 0, "no": 0}
    assert _page(pending, finding)["answers_visible"] is True
    assert pending.get(f"{API}/findings/{finding.public_id}/observations").status_code == 200
    # The reveal reassessed the finding, which put back the class the answers really give.
    db.refresh(finding)
    finding.community_class = FeatureClass.MOAT.value
    db.commit()
    assert records.suggest_for_finding(db, finding, reviewer).items[0].type_fit is True


def test_a_reviewer_who_left_between_the_steps_finishes_from_the_finding_page(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    assert client.put(_path(finding), json={"visible": "yes", "detail_follows": True}).status_code == 200
    # Sent again, as a retry would be: still held, still one answer.
    again = client.put(_path(finding), json={"visible": "yes", "detail_follows": True})
    assert again.json()["revealed"] is False
    mine = _page(client, finding)["my_observation"]
    assert (mine["visible"], mine["revealed"], mine["feature_class"]) == ("yes", False, None)

    detail = {"feature_class": "moat", "period": "roman", "not_modern": True, "note": "Ditch on the north"}
    revealed = client.post(f"{_path(finding)}/reveal", json=detail)
    assert revealed.status_code == 200, revealed.text
    body = revealed.json()
    assert body["revealed"] is True
    assert body["observation"] | detail == body["observation"]
    assert body["finding"]["title"] == TITLE
    assert body["comparison"]["matches_finder"] is False
    assert body["finding"]["answers_visible"] is True


def test_the_full_answer_sent_after_the_first_step_adds_its_detail(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    client.put(_path(finding), json={"visible": "yes", "detail_follows": True})
    refused = client.put(_path(finding), json={"visible": "no", "feature_class": "moat"})
    assert error_code(refused) == "answer_final"
    finished = client.put(_path(finding), json={"visible": "yes", "feature_class": "moat"})
    assert finished.status_code == 200
    assert finished.json()["revealed"] is True
    assert finished.json()["observation"]["feature_class"] == "moat"


def test_the_detail_is_added_once(db: Session, client_as: ClientAs, make_user: MakeUser) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    client.put(_path(finding), json={"visible": "yes", "detail_follows": True})
    assert client.post(f"{_path(finding)}/reveal", json={"feature_class": "moat"}).status_code == 200

    assert error_code(client.post(f"{_path(finding)}/reveal", json={"feature_class": "round_barrow"})) == (
        "answer_final"
    )
    assert error_code(client.post(f"{_path(finding)}/reveal", json={"explanation": "modern"})) == (
        "answer_final"
    )
    # The same again, or nothing, answers the same reveal, as a retry would need.
    assert client.post(f"{_path(finding)}/reveal", json={"feature_class": "moat"}).status_code == 200
    assert client.post(f"{_path(finding)}/reveal").status_code == 200
    # After the reveal only the note can change, as with an answer given in one step.
    changed = client.put(_path(finding), json={"visible": "yes", "feature_class": "round_barrow"})
    assert error_code(changed) == "answer_final"
    noted = {"visible": "yes", "feature_class": "moat", "note": "On reflection"}
    assert client.put(_path(finding), json=noted).json()["observation"]["note"] == "On reflection"


def test_skipping_the_detail_reveals_the_answer_as_it_was(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    client.put(_path(finding), json={"visible": "unsure", "detail_follows": True})
    skipped = client.post(f"{_path(finding)}/reveal")
    assert skipped.status_code == 200, skipped.text
    observation = skipped.json()["observation"]
    assert (observation["visible"], observation["revealed"], observation["feature_class"]) == (
        "unsure",
        True,
        None,
    )


def test_an_answer_taken_back_before_its_reveal_has_nothing_to_reveal_until_restored(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    client = client_as(make_user())
    client.put(_path(finding), json={"visible": "yes", "detail_follows": True})
    assert client.delete(_path(finding)).status_code == 204
    assert error_code(client.post(f"{_path(finding)}/reveal")) == "observation_not_found"
    assert _page(client, finding)["answers_visible"] is False
    assert error_code(client.put(_path(finding), json={"visible": "no", "detail_follows": True})) == (
        "answer_final"
    )
    restored = client.put(_path(finding), json={"visible": "yes", "detail_follows": True})
    assert restored.json()["observation"]["withdrawn"] is False
    assert client.post(f"{_path(finding)}/reveal").status_code == 200


def test_nobody_reveals_an_answer_they_have_not_given(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, finding = _answered(db, make_user)
    assert error_code(client_as(make_user()).post(f"{_path(finding)}/reveal")) == "observation_not_found"
    assert error_code(client_as(finder).post(f"{_path(finding)}/reveal")) == "observation_not_found"


def test_detail_given_in_the_second_step_counts_as_detail_given_with_the_answer(
    db: Session, make_user: MakeUser
) -> None:
    """The detail was given blind, so class agreement and the checks count it the same."""
    detail = {"feature_class": FeatureClass.HILLFORT, "not_modern": True, "not_natural": True}
    together, apart = (create(db, make_user(), feature_class=FeatureClass.HILLFORT) for _ in range(2))
    for _ in range(3):
        answer(db, together, make_user(), Visible.YES, **detail)
        reviewer = make_user()
        answer(db, apart, reviewer, Visible.YES, detail_follows=True)
        review.reveal(db, apart, reviewer, review.Detail(**detail))
        db.commit()
    db.refresh(together)
    db.refresh(apart)
    for column in ("tier", "state", "confidence", "community_class", "open_steps"):
        assert getattr(apart, column) == getattr(together, column), column
    assert apart.tier == "seen"
    one, two = together.assessment, apart.assessment
    for key in ("class_support", "class_agreement", "checks", "seen", "observers"):
        assert one[key] == two[key], key


def test_an_answer_given_in_one_step_is_revealed_at_once(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    _, finding = _answered(db, make_user)
    given = client_as(make_user()).put(_path(finding), json={"visible": "yes", "feature_class": "moat"})
    assert given.json()["revealed"] is True
    assert given.json()["observation"]["revealed"] is True
    assert given.json()["finding"]["answers_visible"] is True
