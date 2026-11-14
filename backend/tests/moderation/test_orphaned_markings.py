"""An admin takes back an orphaned marking's shape: the list, the earlier shapes, and putting one back."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.auth.accounts import delete_account
from fieldclub.models import Activity, Finding, ModerationAction, Observation, User
from fieldclub.services import findings, looked_at, sensitivity, shapes
from fieldclub.vocab import EvidenceKind, Visible
from tests.findings.support import API, LAT, LON, add_desk_evidence, answer, east, meridian
from tests.helpers import ClientAs, MakeUser, error_code, lon_lat
from tests.moderation.support import REASON

SHORT = (0, 0.004)


def far_line(metres: float, *lats: float) -> shapes.Path:
    return shapes.read_path(
        {"points": [{"lon": east(metres), "lat": LAT + d, "kind": "corner"} for d in (lats or SHORT)]}
    )


def put_back(client, finding: Finding, to_revision: int | None, shape_revision: int):
    return client.put(
        f"{API}/mod/findings/{finding.public_id}/marking",
        json={"to_revision": to_revision, "shape_revision": shape_revision, **REASON},
    )


def ban(db: Session, user: User) -> None:
    stored = db.get(User, user.id)
    assert stored is not None
    stored.banned_at = datetime.now(UTC)
    db.commit()


@pytest.fixture
def moved(db: Session, make_user: MakeUser) -> dict[str, Any]:
    """A line drawn, then moved 2 km east by its finder, then looked at there and given evidence."""
    finder, helper = make_user(), make_user("trusted")
    finding = findings.create_finding(
        db, finder, path=meridian(*SHORT), feature_class="linear", requested_sensitivity="protected"
    )
    db.commit()
    first_square = gridref.gridref_at(*lon_lat(finding.location), 4)
    findings.update_finding(
        db, findings.lock(db, finding), finder, {"path": far_line(2000), "path_revision": 0}
    )
    db.commit()
    answer(db, finding, helper, Visible.YES)
    add_desk_evidence(db, finding, make_user(), EvidenceKind.AERIAL)
    db.refresh(finding)
    return {"finder": finder, "finding": finding, "first_square": first_square, "admin": make_user("admin")}


def test_it_is_refused_while_the_keeper_is_active(moved: dict[str, Any], client_as: ClientAs) -> None:
    refused = put_back(client_as(moved["admin"]), moved["finding"], 0, 1)
    assert (refused.status_code, error_code(refused)) == (409, "not_orphaned")


def test_it_puts_back_an_earlier_shape_outside_what_was_looked_at_and_keeps_the_rest(
    db: Session, moved: dict[str, Any], client_as: ClientAs, client
) -> None:
    finding: Finding = moved["finding"]
    before = (finding.tier, finding.confidence, finding.observation_count, finding.evidence_count)
    assert finding.added_since_looked_m is None
    assert "look_at_new_part" not in finding.open_steps
    box = ",".join(str(v) for v in moved["first_square"].polygon().bounds)
    ban(db, moved["finder"])
    # The finder could not have done this: it leaves what was looked at.
    with pytest.raises(looked_at.LookedAtMovedError):
        findings.update_finding(
            db, findings.lock(db, finding), moved["finder"], {"path": meridian(*SHORT), "path_revision": 1}
        )
    db.rollback()

    done = put_back(client_as(moved["admin"]), finding, 0, 1)
    assert done.status_code == 200, done.text
    assert done.json()["location"]["shape"]["revision"] == 2
    db.expire_all()
    stored = db.get(Finding, finding.id)
    assert stored is not None
    assert stored.path == meridian(*SHORT).to_json()
    assert (stored.tier, stored.confidence, stored.observation_count, stored.evidence_count) == before
    assert db.scalar(select(Observation.withdrawn_at).where(Observation.finding_id == finding.id)) is None
    # Reassessed: the shape now lies beyond what was looked at, so it asks for a look there.
    assert stored.added_since_looked_m is not None
    assert stored.added_since_looked_m > 200
    assert "look_at_new_part" in stored.open_steps
    assert stored.looked_at is not None, "what was looked at is kept"
    # The anchor moved back to the first square, and the events with it.
    assert gridref.gridref_at(*lon_lat(stored.location), 4) == moved["first_square"]
    assert stored.title == findings.suggested_title("linear", *lon_lat(stored.location)), (
        "a default title follows the anchor back to its square"
    )
    assert str(moved["first_square"].format()) in stored.title
    for row in db.scalars(select(Activity).where(Activity.finding_id == finding.id)):
        assert row.location is not None
        assert lon_lat(row.location) == pytest.approx(sensitivity.square_centre(stored), abs=1e-9)
    assert finding.public_id in client.get(f"{API}/activity", params={"bbox": box}).text


def test_removing_the_shape_leaves_a_spot_and_the_events_leave_the_old_square(
    db: Session, moved: dict[str, Any], client_as: ClientAs, client
) -> None:
    finding: Finding = moved["finding"]
    ban(db, moved["finder"])
    assert put_back(client_as(moved["admin"]), finding, 0, 1).status_code == 200
    db.expire_all()
    back = db.get(Finding, finding.id)
    assert back is not None
    square = gridref.gridref_at(*lon_lat(back.location), 4)
    assert square == moved["first_square"]

    # Put the far shape back, which moves the anchor into another square, then remove it.
    assert put_back(client_as(moved["admin"]), finding, 1, 2).status_code == 200
    db.expire_all()
    there = db.get(Finding, finding.id)
    assert there is not None
    assert gridref.gridref_at(*lon_lat(there.location), 4) != square
    box = ",".join(str(v) for v in square.polygon().bounds)
    signed_out = client.get(f"{API}/activity", params={"bbox": box})
    assert signed_out.status_code == 200
    assert finding.public_id not in signed_out.text

    removed = put_back(client_as(moved["admin"]), finding, None, 3)
    assert removed.status_code == 200, removed.text
    db.expire_all()
    spot = db.get(Finding, finding.id)
    assert spot is not None
    assert (spot.path, spot.outline, spot.shape_kind) == (None, None, None)
    assert lon_lat(spot.location) == lon_lat(there.location), "removing the shape leaves the anchor"


def test_the_log_row_holds_the_revisions_and_no_shape(
    db: Session, moved: dict[str, Any], client_as: ClientAs
) -> None:
    finding: Finding = moved["finding"]
    ban(db, moved["finder"])
    put_back(client_as(moved["admin"]), finding, 0, 1)
    put_back(client_as(moved["admin"]), finding, None, 2)
    rows = db.scalars(select(ModerationAction).where(ModerationAction.action == "remove_marking")).all()
    assert [(r.target_kind, r.target_id, r.reason, r.data) for r in rows] == [
        ("finding", finding.id, REASON["reason"], {"from_revision": 1, "to_revision": 0}),
        ("finding", finding.id, REASON["reason"], {"from_revision": 2, "to_revision": None}),
    ]
    log = client_as(moved["admin"]).get(f"{API}/mod/actions").json()["items"]
    assert [entry["action"] for entry in log[:2]] == ["remove_marking", "remove_marking"]


def _dragged(db: Session, make_user: MakeUser) -> tuple[Finding, User, User]:
    """A line whose finder placed its point, dragged line and point 1.6 km east, and was banned."""
    finder, admin = make_user(), make_user("admin")
    finding = findings.create_finding(
        db, finder, location=Point(LON, LAT), path=meridian(*SHORT), feature_class="linear"
    )
    db.commit()
    findings.update_finding(
        db,
        findings.lock(db, finding),
        finder,
        {"path": far_line(900), "path_revision": 0, "location": Point(east(1600), LAT)},
    )
    db.commit()
    ban(db, finder)
    return finding, finder, admin


def test_an_earlier_shape_too_far_from_the_point_puts_the_point_on_that_shape(
    db: Session, make_user: MakeUser, client_as: ClientAs, client
) -> None:
    finding, _, admin = _dragged(db, make_user)
    dragged_square = gridref.gridref_at(*lon_lat(finding.location), 4)
    done = put_back(client_as(admin), finding, 0, 1)
    assert done.status_code == 200, done.text
    db.expire_all()
    back = db.get(Finding, finding.id)
    assert back is not None
    assert back.path == meridian(*SHORT).to_json()
    assert shapes.distance_m(shapes.shape_of(meridian(*SHORT)).geometry, Point(lon_lat(back.location))) < 1
    assert back.location_derived is True, "the server placed the point by the restored shape"
    square = gridref.gridref_at(*lon_lat(back.location), 4)
    assert square != dragged_square
    assert back.title == findings.suggested_title("linear", *lon_lat(back.location))
    for row in db.scalars(select(Activity).where(Activity.finding_id == finding.id)):
        assert row.location is not None
        assert lon_lat(row.location) == pytest.approx(sensitivity.square_centre(back), abs=1e-9)
    old_box = ",".join(str(v) for v in dragged_square.polygon().bounds)
    assert finding.public_id not in client.get(f"{API}/activity", params={"bbox": old_box}).text


def test_removing_first_then_putting_back_recovers_a_dragged_marking(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finding, _, admin = _dragged(db, make_user)
    assert put_back(client_as(admin), finding, None, 1).status_code == 200
    done = put_back(client_as(admin), finding, 0, 2)
    assert done.status_code == 200, done.text
    db.expire_all()
    back = db.get(Finding, finding.id)
    assert back is not None
    assert back.path == meridian(*SHORT).to_json()
    assert shapes.distance_m(shapes.shape_of(meridian(*SHORT)).geometry, Point(lon_lat(back.location))) < 1


def test_a_put_back_near_a_point_the_finder_placed_leaves_it_and_a_written_title_stays(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, admin = make_user(), make_user("admin")
    finding = findings.create_finding(
        db,
        finder,
        location=Point(LON, LAT),
        path=meridian(*SHORT),
        feature_class="linear",
        title="The ridge road",
    )
    db.commit()
    findings.update_finding(
        db, findings.lock(db, finding), finder, {"path": far_line(700), "path_revision": 0}
    )
    db.commit()
    ban(db, finder)
    assert put_back(client_as(admin), finding, 0, 1).status_code == 200
    db.expire_all()
    back = db.get(Finding, finding.id)
    assert back is not None
    assert lon_lat(back.location) == (LON, LAT)
    assert back.location_derived is False
    assert back.title == "The ridge road"


def test_the_refusals_come_in_their_order(
    db: Session, moved: dict[str, Any], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding: Finding = moved["finding"]
    admin = client_as(moved["admin"])
    for who in ("member", "moderator"):
        refused = put_back(client_as(make_user(who)), finding, 0, 1)
        assert (refused.status_code, error_code(refused)) == (403, "admins_only")
    assert error_code(put_back(admin, finding, 0, 7)) == "not_orphaned", (
        "orphaned is asked before the revision"
    )
    ban(db, moved["finder"])
    assert error_code(put_back(admin, finding, 0, 7)) == "shape_changed"
    for revision in (1, 5, -1):
        refused = put_back(admin, finding, revision, 1)
        assert error_code(refused) != "outline_too_far"
        assert (refused.status_code, error_code(refused)) in (
            (422, "no_such_revision"),
            (422, "validation_error"),
        )


def test_a_deleted_keeper_s_marking_is_listed_and_its_earlier_shapes_go_to_admins_alone(
    db: Session, moved: dict[str, Any], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding: Finding = moved["finding"]
    kept = findings.create_finding(db, make_user(), path=meridian(0.02, 0.024), feature_class="linear")
    db.commit()
    finder = db.get(User, moved["finder"].id)
    assert finder is not None
    delete_account(db, finder)
    db.commit()
    admin = client_as(moved["admin"])

    listed = admin.get(f"{API}/mod/markings/orphaned")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [item["finding"]["public_id"] for item in items] == [finding.public_id]
    assert kept.public_id not in listed.text
    assert items[0]["keeper_gone"] == "deleted"

    shapes_page = admin.get(f"{API}/mod/findings/{finding.public_id}/shapes")
    assert shapes_page.status_code == 200, shapes_page.text
    (change,) = shapes_page.json()["items"]
    assert (change["revision"], change["kind"], change["restorable"]) == (1, "reshaped", True)
    assert change["path_before"]["points"][0]["lon"] == pytest.approx(LON)
    for who in ("member", "moderator"):
        refused = client_as(make_user(who)).get(f"{API}/mod/findings/{finding.public_id}/shapes")
        assert (refused.status_code, error_code(refused)) == (403, "admins_only")
        assert "path_before" not in refused.text
