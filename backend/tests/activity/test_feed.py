"""GET /activity: the public feed, its filters, and what it leaves out."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.auth import accounts
from fieldclub.models import Activity
from fieldclub.services import activity, findings, sensitivity
from fieldclub.vocab import ActivityKind, AgeBand, Visibility, Visible
from tests.activity.support import API, add_map, comment, investigation, items
from tests.findings.support import answer, create
from tests.helpers import ClientAs, MakeUser, error_code, lon_lat

# A protected barrow away from the 1 km square's centre, and that centre.
BARROW = (-1.836214, 51.416382)


def feed(client: TestClient, **params: Any) -> list[dict]:
    return items(client.get(f"{API}/activity", params=params))


def test_newest_first_and_paged(db: Session, make_user: MakeUser, client: TestClient) -> None:
    finder = make_user(handle="Finder")
    finding = create(db, finder, title="Ditched enclosure")
    for _ in range(3):
        comment(db, finding, finder)

    response = client.get(f"{API}/activity", params={"limit": 2})
    assert response.headers["cache-control"] == "private, no-cache"
    first = response.json()
    assert [item["kind"] for item in first["items"]] == ["comment_added", "comment_added"]
    rest = client.get(f"{API}/activity", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [item["kind"] for item in rest["items"]] == ["comment_added", "finding_created"]
    assert rest["next_cursor"] is None
    ids = [item["id"] for item in first["items"] + rest["items"]]
    assert ids == sorted(ids, reverse=True)

    created = rest["items"][-1]
    assert created["actor"] == {
        "handle": "Finder",
        "display_name": "Finder",
        "role": "member",
        "avatar_url": None,
    }
    assert created["finding"]["public_id"] == finding.public_id
    assert created["finding"]["title"] == "Ditched enclosure"
    assert created["finding"]["location"]["obscured"] is False
    assert created["investigation"] is None
    assert error_code(client.get(f"{API}/activity", params={"cursor": "nonsense"})) == "invalid_cursor"


def test_details_carry_what_changed_and_nothing_more(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    finder, one, two = make_user(), make_user(), make_user()
    finding = create(db, finder)
    evidence_id = add_map(db, finding, one, url="https://maps.example/view?lat=51.428637&lon=-1.854173")
    answer(db, finding, one, Visible.YES)
    answer(db, finding, two, Visible.YES)

    by_kind = {item["kind"]: item for item in feed(client)}
    assert by_kind["tier_changed"]["details"]["tier_from"] == "spotted"
    assert by_kind["tier_changed"]["details"]["tier_to"] == "seen"
    assert by_kind["evidence_added"]["details"]["evidence_id"] == evidence_id
    assert by_kind["evidence_added"]["details"]["evidence_kind"] == "historic_map"
    # The evidence link is never in the feed: it can hold a position.
    assert "maps.example" not in client.get(f"{API}/activity").text
    # A second look and the tier change it caused name nobody (Decision 0008).
    assert by_kind["observation_added"]["actor"] is None
    assert by_kind["tier_changed"]["actor"] is None
    assert set(by_kind["observation_added"]["details"].values()) == {None}


def test_filters(db: Session, make_user: MakeUser, client: TestClient) -> None:
    ann, bob = make_user(handle="Ann"), make_user(handle="Bob")
    near = create(db, ann)
    far = create(db, bob, lon=-2.5, lat=53.0)
    comment(db, near, bob)
    # Making a public investigation records investigation_published itself.
    survey = investigation(db, ann)

    assert {item["kind"] for item in feed(client, kind="comment_added")} == {"comment_added"}
    two_kinds = feed(client, kind=["comment_added", "investigation_published"])
    assert {item["kind"] for item in two_kinds} == {"comment_added", "investigation_published"}
    assert {item["finding"]["public_id"] for item in feed(client, finding=near.public_id.lower())} == {
        near.public_id
    }
    assert [item["kind"] for item in feed(client, person="bob")] == ["comment_added", "finding_created"]
    assert [item["investigation"]["public_id"] for item in feed(client, investigation=survey.public_id)] == [
        survey.public_id
    ]
    in_box = feed(client, bbox="-1.9,51.4,-1.8,51.45")
    assert {item["finding"]["public_id"] for item in in_box} == {near.public_id}
    assert far.public_id not in client.get(f"{API}/activity", params={"bbox": "-1.9,51.4,-1.8,51.45"}).text


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"bbox": "1,2,3"}, "invalid_bbox"),
        ({"bbox": "3,2,1,4"}, "invalid_bbox"),
        ({"person": "Nobody"}, "user_not_found"),
        ({"finding": "ZZZZZZ"}, "finding_not_found"),
        ({"finding": "!"}, "finding_not_found"),
        ({"investigation": "ZZZZZZ"}, "investigation_not_found"),
        ({"kind": "made_up"}, "validation_error"),
        ({"limit": 201}, "validation_error"),
    ],
)
def test_bad_filters(client: TestClient, db: Session, params: dict, code: str) -> None:
    assert error_code(client.get(f"{API}/activity", params=params)) == code


def test_a_box_matches_the_square_and_never_narrows_to_the_spot(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    finder = make_user()
    barrow = create(db, finder, lon=BARROW[0], lat=BARROW[1], feature_class="round_barrow")
    assert barrow.sensitivity == "protected"
    lon, lat = BARROW
    tiny = f"{lon - 0.0002},{lat - 0.0002},{lon + 0.0002},{lat + 0.0002}"
    centre = sensitivity.square_centre(barrow)
    assert centre is not None
    around_centre = f"{centre[0] - 0.0002},{centre[1] - 0.0002},{centre[0] + 0.0002},{centre[1] + 0.0002}"

    for viewer in (client, client_as(make_user()), client_as(finder)):
        # The same answer for everyone: the box is matched against the square's centre.
        assert feed(viewer, bbox=tiny) == []
        assert [item["finding"]["public_id"] for item in feed(viewer, bbox=around_centre)] == [
            barrow.public_id
        ]

    public = feed(client, bbox=around_centre)[0]["finding"]["location"]
    assert public["obscured"] is True
    assert public["square"] == gridref.gridref_at(lon, lat, 4).format(compact=True)
    assert (public["lon"], public["lat"]) == pytest.approx(centre, abs=1e-6)
    member = feed(client_as(make_user()), bbox=around_centre)[0]["finding"]["location"]
    assert member["obscured"] is False
    assert (member["lon"], member["lat"]) == pytest.approx(BARROW, abs=1e-6)


def test_moving_a_finding_moves_its_activity(db: Session, make_user: MakeUser, client: TestClient) -> None:
    finder = make_user()
    finding = create(db, finder)
    comment(db, finding, finder)
    findings.update_finding(db, findings.lock(db, finding), finder, {"location": Point(-2.5, 53.0)})
    db.commit()
    moved = sensitivity.square_centre(finding)
    for row in db.scalars(select(Activity)):
        assert row.location is not None
        assert lon_lat(row.location) == pytest.approx(moved)
    assert len(feed(client, bbox="-2.6,52.9,-2.4,53.1")) == 2
    assert feed(client, bbox="-1.9,51.4,-1.8,51.45") == []


def test_hidden_and_withdrawn_findings_leave_the_feed(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    finder, other = make_user(), make_user()
    hidden = create(db, finder, title="Hidden")
    withdrawn = create(db, finder, title="Withdrawn")
    shown = create(db, other, title="Shown")
    hidden.hidden_at = datetime.now(UTC)
    db.commit()
    findings.withdraw_finding(db, findings.lock(db, withdrawn), finder)
    db.commit()

    for viewer in (client, client_as(other), client_as(make_user("trusted"))):
        assert {item["finding"]["title"] for item in feed(viewer)} == {"Shown"}
        assert (
            error_code(viewer.get(f"{API}/activity", params={"finding": hidden.public_id}))
            == "finding_not_found"
        )
    # Those who may see a hidden finding see its events: its finder and moderators.
    for viewer in (client_as(finder), client_as(make_user("moderator"))):
        assert {item["finding"]["title"] for item in feed(viewer)} == {"Shown", "Hidden"}
    assert shown.public_id


def test_only_public_investigations_appear(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    owner = make_user()
    for visibility in Visibility:
        made = investigation(db, owner, visibility)
        if visibility is not Visibility.PUBLIC:
            # The service records the event only for a public one. A stray row for any other
            # must still never show.
            activity.record(db, ActivityKind.INVESTIGATION_PUBLISHED, owner, investigation=made)
            db.commit()
            for viewer in (client, client_as(owner), client_as(make_user("moderator"))):
                response = viewer.get(f"{API}/activity", params={"investigation": made.public_id})
                assert error_code(response) == "investigation_not_found"
    for viewer in (client, client_as(owner), client_as(make_user("moderator"))):
        assert [item["investigation"]["title"] for item in feed(viewer)] == ["A public survey"]


def test_banned_actors_vanish_and_deleted_ones_are_nobody(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    banned, leaver, finder = make_user(handle="Banned"), make_user(handle="Leaver"), make_user()
    finding = create(db, finder)
    comment(db, finding, banned)
    comment(db, finding, leaver)
    banned.banned_at = datetime.now(UTC)
    accounts.delete_account(db, leaver)
    db.commit()

    listed = feed(client, kind="comment_added")
    assert len(listed) == 1
    assert listed[0]["actor"] is None
    assert "Banned" not in client.get(f"{API}/activity").text
    assert "Leaver" not in client.get(f"{API}/activity").text
    assert error_code(client.get(f"{API}/activity", params={"person": "Banned"})) == "user_not_found"
    assert error_code(client.get(f"{API}/activity", params={"person": "Leaver"})) == "user_not_found"


def test_deleted_comments_and_evidence_leave_the_feed(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    comment_id = comment(db, finding, helper)
    evidence_id = add_map(db, finding, helper)
    assert {item["kind"] for item in feed(client)} >= {"comment_added", "evidence_added"}

    findings.delete_comment(db, comment_id, helper)
    findings.delete_evidence(db, evidence_id, helper)
    db.commit()
    kinds = {item["kind"] for item in feed(client)}
    assert "comment_added" not in kinds
    assert "evidence_added" not in kinds


def test_a_16_to_17_actor_shows_only_their_handle(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    young = make_user(
        handle="YoungDigger",
        display_name="Real Name",
        avatar_url="https://provider.example/face.png",
        age_band=AgeBand.AGE_16_17.value,
    )
    create(db, young)
    actor = feed(client)[0]["actor"]
    assert actor == {
        "handle": "YoungDigger",
        "display_name": "YoungDigger",
        "role": "member",
        "avatar_url": None,
    }
    assert "Real Name" not in client.get(f"{API}/activity").text
