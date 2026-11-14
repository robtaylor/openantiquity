"""Suggestions: someone else proposes a change to a marking's shape, and its keeper accepts or declines it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from fieldclub import gridref
from fieldclub.auth.accounts import delete_account
from fieldclub.models import Activity, Finding, FindingShapeChange, Notification, ShapeSuggestion, User
from fieldclub.services import findings, sensitivity, shapes, suggestions
from fieldclub.vocab import Visible
from tests.findings.support import API, LAT, LON, answer, east, meridian
from tests.helpers import ClientAs, MakeUser, error_code, lon_lat


def body_of(shape: shapes.Path) -> dict[str, Any]:
    return shape.to_json()


def line(db: Session, finder: User, *lats: float, **kwargs: Any) -> Finding:
    finding = findings.create_finding(db, finder, path=meridian(*lats), feature_class="linear", **kwargs)
    db.commit()
    return finding


def suggest(client, finding: Finding, shape: shapes.Path | dict | None, revision: int | None = 0):
    sent: dict[str, Any] = {}
    if shape is not None:
        sent["path"] = shape if isinstance(shape, dict) else body_of(shape)
    if revision is not None:
        sent["path_revision"] = revision
    return client.post(f"{API}/findings/{finding.public_id}/suggestions", json=sent)


def accept(client, finding: Finding, suggestion_id: int, revision: int = 0):
    return client.post(
        f"{API}/findings/{finding.public_id}/suggestions/{suggestion_id}/accept",
        json={"shape_revision": revision},
    )


def decline(client, finding: Finding, suggestion_id: int):
    return client.post(f"{API}/findings/{finding.public_id}/suggestions/{suggestion_id}/decline")


def withdraw(client, finding: Finding, suggestion_id: int):
    return client.delete(f"{API}/findings/{finding.public_id}/suggestions/{suggestion_id}")


def page(client, finding: Finding) -> dict[str, Any]:
    response = client.get(f"{API}/findings/{finding.public_id}")
    assert response.status_code == 200, response.text
    return response.json()


# A line about 445 m long up the meridian, and an extension of it to about 670 m.
SHORT = (0, 0.004)
LONGER = (0, 0.004, 0.006)


@pytest.fixture
def people(make_user: MakeUser) -> dict[str, User]:
    return {"finder": make_user(), "suggester": make_user(), "member": make_user()}


def test_a_suggestion_is_made_listed_and_the_keeper_told(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER))
    assert made.status_code == 201, made.text
    out = made.json()
    assert out["by"]["handle"] == people["suggester"].handle
    assert (out["base_revision"], out["behind"], out["kind"], out["state"]) == (
        0,
        False,
        "extended",
        "pending",
    )
    assert out["length_m"] == pytest.approx(shapes.shape_of(meridian(*LONGER)).length_m, abs=0.5)
    assert out["path"]["points"][-1]["lat"] == pytest.approx(LAT + 0.006)
    assert out["outline"]["type"] == "LineString"
    assert out["decided_at"] is None

    listed = page(client_as(people["member"]), finding)["location"]["shape"]["suggestions"]
    assert [s["id"] for s in listed] == [out["id"]]
    (told,) = db.scalars(select(Notification).where(Notification.kind == "shape_suggested")).all()
    assert (told.user_id, told.actor_id, told.finding_id, told.data) == (
        people["finder"].id,
        people["suggester"].id,
        finding.id,
        None,
    )


def test_an_accepted_extension_credits_the_suggester_and_tells_the_followers(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    findings.follow(db, people["member"], finding)
    db.commit()
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()

    accepted = accept(client_as(people["finder"]), finding, made["id"])
    assert accepted.status_code == 200, accepted.text
    shape = accepted.json()["location"]["shape"]
    assert shape["revision"] == 1
    assert shape["suggestions"] == []
    (change,) = shape["changes"]
    assert change["kind"] == "extended"
    assert change["suggested_by"]["handle"] == people["suggester"].handle

    row = db.scalar(select(FindingShapeChange).where(FindingShapeChange.finding_id == finding.id))
    assert row is not None
    assert row.user_id == people["suggester"].id
    stored = db.get(ShapeSuggestion, made["id"])
    assert stored is not None
    db.refresh(stored)
    assert (stored.state, stored.decided_by, stored.applied_revision) == ("accepted", people["finder"].id, 1)
    (extended,) = db.scalars(select(Activity).where(Activity.kind == "shape_extended")).all()
    assert extended.actor_id == people["suggester"].id
    told = {n.user_id for n in db.scalars(select(Notification).where(Notification.kind == "shape_extended"))}
    assert people["member"].id in told
    assert people["suggester"].id not in told
    decided = db.scalars(select(Notification).where(Notification.kind == "suggestion_decided")).all()
    assert [(n.user_id, n.actor_id, n.data) for n in decided] == [
        (people["suggester"].id, people["finder"].id, {"accepted": True})
    ]


def test_a_declined_suggestion_tells_the_suggester_and_changes_nothing(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    declined = decline(client_as(people["finder"]), finding, made["id"])
    assert declined.status_code == 200, declined.text
    assert declined.json()["state"] == "declined"
    assert declined.json()["decided_at"] is not None
    db.refresh(finding)
    assert finding.shape_revision == 0
    decided = db.scalars(select(Notification).where(Notification.kind == "suggestion_decided")).all()
    assert [n.data for n in decided] == [{"accepted": False}]
    again = decline(client_as(people["finder"]), finding, made["id"])
    assert (again.status_code, error_code(again)) == (409, "suggestion_decided")


def test_a_suggestion_behind_the_shape_is_accepted_on_the_revision_the_keeper_saw(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    findings.update_finding(
        db, findings.lock(db, finding), people["finder"], {"path": meridian(0, 0.005), "path_revision": 0}
    )
    db.commit()
    (listed,) = page(client_as(people["finder"]), finding)["location"]["shape"]["suggestions"]
    assert listed["behind"] is True

    stale = accept(client_as(people["finder"]), finding, made["id"], revision=0)
    assert (stale.status_code, error_code(stale)) == (409, "shape_changed")
    accepted = accept(client_as(people["finder"]), finding, made["id"], revision=1)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["location"]["shape"]["revision"] == 2
    db.expire_all()
    stored = db.get(Finding, finding.id)
    assert stored is not None
    assert stored.path == meridian(*LONGER).to_json(), "the keeper's later edit was replaced"
    row = db.scalar(
        select(FindingShapeChange)
        .options(undefer(FindingShapeChange.path_before))
        .where(FindingShapeChange.finding_id == finding.id, FindingShapeChange.revision == 2)
    )
    assert row is not None
    assert row.path_before == meridian(0, 0.005).to_json(), "the change keeps the edit it replaced"


def test_a_suggestion_looked_at_has_outgrown_is_refused_and_stays_pending(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = line(db, people["finder"], *SHORT)
    far = shapes.read_path({"points": [{"lon": east(2000), "lat": LAT + d, "kind": "corner"} for d in SHORT]})
    made = suggest(client_as(people["suggester"]), finding, far).json()
    answer(db, finding, make_user(), Visible.YES)

    refused = accept(client_as(people["finder"]), finding, made["id"])
    assert (refused.status_code, error_code(refused)) == (422, "looked_at_moved")
    stored = db.get(ShapeSuggestion, made["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.state == "pending"
    db.refresh(finding)
    assert finding.shape_revision == 0


def test_a_suggester_isn_t_sent_what_was_looked_at(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = line(db, people["finder"], *SHORT)
    answer(db, finding, make_user(), Visible.YES)
    suggest(client_as(people["suggester"]), finding, meridian(*LONGER))
    theirs = page(client_as(people["suggester"]), finding)
    assert theirs["location"]["shape"]["looked_at"] is None
    assert theirs["actions"]["suggest"] == {"allowed": True, "reason": None}
    assert theirs["actions"]["decide_suggestions"] == {"allowed": False, "reason": "not_keeper"}
    assert page(client_as(people["finder"]), finding)["location"]["shape"]["looked_at"] is not None


def test_twenty_pending_is_the_cap_and_one_person_holds_one(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = line(db, people["finder"], *SHORT)
    for n in range(suggestions.SUGGESTIONS_MAX_PENDING):
        made = suggest(client_as(make_user()), finding, meridian(0, 0.004, 0.005 + n * 0.0001))
        assert made.status_code == 201, made.text
    refused = suggest(client_as(people["suggester"]), finding, meridian(*LONGER))
    assert (refused.status_code, error_code(refused)) == (409, "too_many_suggestions")

    # A second one from the same person replaces their first, so it never meets the cap.
    other = line(db, people["finder"], 0.01, 0.014)
    first = suggest(client_as(people["suggester"]), other, meridian(0.01, 0.014, 0.016)).json()
    second = suggest(client_as(people["suggester"]), other, meridian(0.01, 0.014, 0.017)).json()
    listed = page(client_as(people["member"]), other)["location"]["shape"]["suggestions"]
    assert [s["id"] for s in listed] == [second["id"]]
    stored = db.get(ShapeSuggestion, first["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.state == "withdrawn"


def test_a_banned_suggester_s_pending_suggestions_leave_every_list_and_come_back(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    suggester = db.get(User, people["suggester"].id)
    assert suggester is not None
    suggester.banned_at = datetime.now(UTC)
    db.commit()

    assert page(client_as(people["member"]), finding)["location"]["shape"]["suggestions"] == []
    for refused in (
        accept(client_as(people["finder"]), finding, made["id"]),
        decline(client_as(people["finder"]), finding, made["id"]),
        withdraw(client_as(people["member"]), finding, made["id"]),
    ):
        assert (refused.status_code, error_code(refused)) == (404, "suggestion_not_found")
    # Left out of the count too: the cap counts only listed suggestions.
    with db.begin_nested():
        assert db.scalar(select(ShapeSuggestion.id).where(suggestions._pending(finding))) is None

    suggester.banned_at = None
    db.commit()
    listed = page(client_as(people["member"]), finding)["location"]["shape"]["suggestions"]
    assert [s["id"] for s in listed] == [made["id"]]


def test_accepting_a_withdrawn_finding_s_suggestion_is_refused(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    findings.withdraw_finding(db, findings.lock(db, finding), people["finder"])
    db.commit()
    refused = accept(client_as(people["finder"]), finding, made["id"])
    assert (refused.status_code, error_code(refused)) == (409, "finding_withdrawn")


def test_an_accepted_suggestion_that_moves_the_anchor_takes_its_events_to_the_new_square(
    db: Session, people: dict[str, User], client_as: ClientAs, client
) -> None:
    finding = line(db, people["finder"], *SHORT, requested_sensitivity="protected")
    old_square = gridref.gridref_at(*lon_lat(finding.location), 4)
    away = shapes.read_path(
        {"points": [{"lon": east(2500), "lat": LAT + d, "kind": "corner"} for d in SHORT]}
    )
    made = suggest(client_as(people["suggester"]), finding, away).json()
    box = ",".join(str(v) for v in old_square.polygon().bounds)
    before = client.get(f"{API}/activity", params={"bbox": box}).json()["items"]
    assert finding.public_id in str(before)

    assert accept(client_as(people["finder"]), finding, made["id"]).status_code == 200
    db.refresh(finding)
    assert gridref.gridref_at(*lon_lat(finding.location), 4) != old_square, "the anchor moved square"
    after = client.get(f"{API}/activity", params={"bbox": box})
    assert after.status_code == 200
    assert finding.public_id not in after.text
    for row in db.scalars(select(Activity).where(Activity.finding_id == finding.id)):
        assert row.location is not None
        assert lon_lat(row.location) == pytest.approx(sensitivity.square_centre(finding), abs=1e-9)


# --------------------------------------------------------------------------
# Every code in the contract
# --------------------------------------------------------------------------


def test_making_one_is_refused_with_each_code(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = line(db, people["finder"], *SHORT)
    suggester = client_as(people["suggester"])
    longer = meridian(*LONGER)

    def refused(response) -> tuple[int, str]:
        return response.status_code, error_code(response)

    assert refused(suggester.post(f"{API}/findings/NOSUCH1/suggestions", json={"path": body_of(longer)})) == (
        404,
        "finding_not_found",
    )
    assert refused(suggest(suggester, finding, longer, revision=None)) == (422, "path_revision_required")
    assert refused(suggest(suggester, finding, longer, revision=3)) == (409, "shape_changed")
    assert refused(suggest(client_as(people["finder"]), finding, longer)) == (422, "own_marking")
    assert refused(suggest(suggester, finding, meridian(*SHORT))) == (422, "suggestion_unchanged")
    too_close = {
        "points": [
            {"lon": LON, "lat": LAT, "kind": "corner"},
            {"lon": LON, "lat": LAT + 1e-7, "kind": "corner"},
        ]
    }
    assert refused(suggest(suggester, finding, too_close)) == (422, "points_too_close")
    assert refused(suggest(suggester, finding, meridian(0, 6.0))) == (422, "line_too_long")
    away = shapes.read_path(
        {"points": [{"lon": east(2000), "lat": LAT + d, "kind": "corner"} for d in SHORT]}
    )
    answer(db, finding, make_user(), Visible.YES)
    # Never `looked_at_moved` when made: that is the keeper's to meet when accepting (see below).
    assert suggest(suggester, finding, away).status_code == 201
    placed = findings.create_finding(
        db, people["finder"], location=Point(LON, LAT), path=meridian(*SHORT), feature_class="linear"
    )
    db.commit()
    assert refused(suggest(suggester, placed, away)) == (422, "outline_too_far")
    findings.withdraw_finding(db, findings.lock(db, finding), people["finder"])
    db.commit()
    assert refused(suggest(suggester, finding, longer)) == (409, "finding_withdrawn")


def test_withdrawing_accepting_and_declining_are_refused_with_each_code(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    finder, member = client_as(people["finder"]), client_as(people["member"])

    def refused(response) -> tuple[int, str]:
        return response.status_code, error_code(response)

    missing = made["id"] + 1000
    for response in (
        withdraw(member, finding, missing),
        accept(finder, finding, missing),
        decline(finder, finding, missing),
    ):
        assert refused(response) == (404, "suggestion_not_found")
    other = line(db, people["finder"], 0.01, 0.014)
    assert refused(accept(finder, other, made["id"])) == (404, "suggestion_not_found"), "not on that finding"
    assert refused(withdraw(member, finding, made["id"])) == (403, "not_suggester")
    assert refused(accept(member, finding, made["id"])) == (403, "not_keeper")
    assert refused(decline(member, finding, made["id"])) == (403, "not_keeper")
    assert refused(accept(finder, finding, made["id"], revision=4)) == (409, "shape_changed")
    assert withdraw(client_as(people["suggester"]), finding, made["id"]).status_code == 204
    assert refused(withdraw(client_as(people["suggester"]), finding, made["id"])) == (
        409,
        "suggestion_decided",
    )
    assert refused(accept(finder, finding, made["id"])) == (409, "suggestion_decided")


def test_accepting_one_too_far_from_a_point_the_finder_placed_is_refused(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = findings.create_finding(
        db, people["finder"], location=Point(LON, LAT), path=meridian(*SHORT), feature_class="linear"
    )
    db.commit()
    west = shapes.read_path(
        {"points": [{"lon": east(-150), "lat": LAT + d, "kind": "corner"} for d in LONGER]}
    )
    made = suggest(client_as(people["suggester"]), finding, west).json()
    moved = client_as(people["finder"]).patch(
        f"{API}/findings/{finding.public_id}",
        json={"location": {"type": "Point", "coordinates": [east(900), LAT]}},
    )
    assert moved.status_code == 200, moved.text
    refused = accept(client_as(people["finder"]), finding, made["id"])
    assert (refused.status_code, error_code(refused)) == (422, "outline_too_far")


def test_suggesting_is_limited_to_thirty_an_hour(
    db: Session, people: dict[str, User], app, client_for, limits_on: None
) -> None:
    findings_made = [line(db, people["finder"], n * 0.01, n * 0.01 + 0.004) for n in range(31)]
    client = client_for(app, people["suggester"])
    answers = [
        suggest(client, finding, meridian(n * 0.01, n * 0.01 + 0.004, n * 0.01 + 0.006)).status_code
        for n, finding in enumerate(findings_made)
    ]
    assert answers[:30] == [201] * 30
    assert answers[30] == 429


def test_deleting_a_suggester_withdraws_their_pending_suggestions(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    gone = db.get(User, people["suggester"].id)
    assert gone is not None
    delete_account(db, gone)
    db.commit()
    stored = db.get(ShapeSuggestion, made["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.state == "withdrawn"
    assert page(client_as(people["member"]), finding)["location"]["shape"]["suggestions"] == []


def test_an_accepted_move_takes_a_default_title_to_the_new_square_and_leaves_a_written_one(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    away = shapes.read_path(
        {"points": [{"lon": east(2500), "lat": LAT + d, "kind": "corner"} for d in SHORT]}
    )
    titled = line(db, people["finder"], *SHORT)
    written = line(db, people["finder"], 0.02, 0.024, title="The old road")
    default_before = titled.title
    assert default_before == findings.suggested_title("linear", *lon_lat(titled.location))
    for finding, shape in ((titled, away), (written, None)):
        if shape is None:
            shape = shapes.read_path(
                {"points": [{"lon": east(2500), "lat": LAT + d, "kind": "corner"} for d in (0.02, 0.024)]}
            )
        made = suggest(client_as(people["suggester"]), finding, shape).json()
        assert accept(client_as(people["finder"]), finding, made["id"]).status_code == 200
    db.expire_all()
    moved = db.get(Finding, titled.id)
    kept = db.get(Finding, written.id)
    assert moved is not None
    assert kept is not None
    assert moved.title == findings.suggested_title("linear", *lon_lat(moved.location))
    assert moved.title != default_before, "the default title names the square it moved to"
    assert kept.title == "The old road"


def test_a_suggestion_says_nothing_of_what_was_looked_at_and_the_keeper_meets_the_rule(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    """Any member may suggest, so making one can't answer yes or no about the looked-at ground.

    Decisions 0008 and 0010 keep who looked, and where, from members. The
    keeper, who may see that ground, meets the rule on accepting, with its figure.
    """
    finding = line(db, people["finder"], *SHORT)
    answer(db, finding, make_user(), Visible.YES)
    leaves_it = suggest(client_as(people["suggester"]), finding, far_line_of(2000))
    keeps_it = suggest(client_as(make_user()), finding, meridian(*LONGER))
    for made in (leaves_it, keeps_it):
        assert made.status_code == 201, made.text
        assert set(made.json()) == set(keeps_it.json())
        assert made.json()["state"] == "pending"
    refused = accept(client_as(people["finder"]), finding, leaves_it.json()["id"])
    assert (refused.status_code, error_code(refused)) == (422, "looked_at_moved")
    assert "%" in refused.json()["error"]["message"], "the keeper is told how much would stay"
    stored = db.get(ShapeSuggestion, leaves_it.json()["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.state == "pending"


def test_a_declined_suggester_s_next_suggestion_tells_the_keeper(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    first = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    assert decline(client_as(people["finder"]), finding, first["id"]).status_code == 200
    suggest(client_as(people["suggester"]), finding, meridian(0, 0.004, 0.007))
    told = db.scalars(select(Notification).where(Notification.kind == "shape_suggested")).all()
    assert len(told) == 2, "the keeper acted on the first, so the second is news"
    assert told[0].read_at is not None, "deciding marks the keeper's notification of it read"


def test_an_admin_s_put_back_of_a_longer_line_names_no_admin_to_anyone_else(
    db: Session, make_user: MakeUser, client_as: ClientAs, client
) -> None:
    """A removal is only possible on an orphaned marking, so naming the admin would say the keeper is gone."""
    finder, follower, admin = make_user(), make_user(), make_user("admin", handle="TheAdmin")
    finding = line(db, finder, *LONGER)
    findings.follow(db, follower, finding)
    findings.update_finding(
        db, findings.lock(db, finding), finder, {"path": meridian(*SHORT), "path_revision": 0}
    )
    db.commit()
    gone = db.get(User, finder.id)
    assert gone is not None
    gone.banned_at = datetime.now(UTC)
    db.commit()
    done = client_as(admin).put(
        f"{API}/mod/findings/{finding.public_id}/marking",
        json={"to_revision": 0, "shape_revision": 1, "reason": "Put back."},
    )
    assert done.status_code == 200, done.text
    assert not db.scalars(
        select(Activity).where(Activity.kind == "shape_extended", Activity.actor_id == admin.id)
    ).all()
    assert not db.scalars(select(Activity).where(Activity.actor_id == admin.id)).all()
    assert not db.scalars(select(Notification).where(Notification.actor_id == admin.id)).all()
    for reader in (client, client_as(follower), client_as(make_user())):
        for address in (f"{API}/activity", f"{API}/findings/{finding.public_id}"):
            assert "TheAdmin" not in reader.get(address).text, address
    assert "TheAdmin" not in client_as(follower).get(f"{API}/notifications").text


def far_line_of(metres: float) -> shapes.Path:
    return shapes.read_path(
        {"points": [{"lon": east(metres), "lat": LAT + d, "kind": "corner"} for d in SHORT]}
    )


def test_a_replaced_suggestion_doesn_t_tell_the_keeper_again_while_they_haven_t_read_it(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    for end in (0.006, 0.007, 0.008):
        assert suggest(client_as(people["suggester"]), finding, meridian(0, 0.004, end)).status_code == 201
    told = db.scalars(select(Notification).where(Notification.kind == "shape_suggested")).all()
    assert len(told) == 1
    told[0].read_at = datetime.now(UTC)
    db.commit()
    suggest(client_as(people["suggester"]), finding, meridian(0, 0.004, 0.009))
    assert len(db.scalars(select(Notification).where(Notification.kind == "shape_suggested")).all()) == 2


def test_a_decided_suggestion_is_not_found_by_anyone_but_its_suggester_and_the_keeper(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    decline(client_as(people["finder"]), finding, made["id"])
    stranger = client_as(people["member"])
    for response in (
        withdraw(stranger, finding, made["id"]),
        accept(stranger, finding, made["id"]),
        decline(stranger, finding, made["id"]),
    ):
        assert (response.status_code, error_code(response)) == (404, "suggestion_not_found")
    assert error_code(withdraw(client_as(people["suggester"]), finding, made["id"])) == "suggestion_decided"
    assert error_code(accept(client_as(people["finder"]), finding, made["id"])) == "suggestion_decided"


def test_a_deleted_suggester_s_pending_suggestion_is_left_out_even_if_deletion_missed_it(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    # As if the deletion crossed the suggestion: the account is deleted and the row still pending.
    gone = db.get(User, people["suggester"].id)
    assert gone is not None
    gone.deleted_at = datetime.now(UTC)
    db.commit()
    assert page(client_as(people["member"]), finding)["location"]["shape"]["suggestions"] == []
    refused = accept(client_as(people["finder"]), finding, made["id"])
    assert (refused.status_code, error_code(refused)) == (404, "suggestion_not_found")


def test_taking_a_marking_on_withdraws_the_new_keeper_s_own_suggestion(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggest(client_as(people["suggester"]), finding, meridian(*LONGER)).json()
    path = f"{API}/findings/{finding.public_id}/keeping"
    client_as(people["finder"]).put(f"{path}/offer", json={"handle": people["suggester"].handle})
    assert client_as(people["suggester"]).post(f"{path}/accept").status_code == 200
    stored = db.get(ShapeSuggestion, made["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.state == "withdrawn"
    refused = accept(client_as(people["suggester"]), finding, made["id"])
    assert error_code(refused) in ("suggestion_decided", "own_marking")
    assert not db.scalars(select(Notification).where(Notification.kind == "suggestion_decided")).all()


def test_a_keeper_can_t_accept_their_own_suggestion(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = line(db, people["finder"], *SHORT)
    made = suggestions.suggest(
        db, findings.lock(db, finding), people["suggester"], path=meridian(*LONGER), revision=0
    )
    # Made keeper by hand, past the withdrawal that taking it on makes, as a crossed request could.
    finding.keeper_id = people["suggester"].id
    db.commit()
    refused = accept(client_as(people["suggester"]), finding, made.id)
    assert (refused.status_code, error_code(refused)) == (422, "own_marking")
    decline(client_as(people["suggester"]), finding, made.id)
    assert not db.scalars(select(Notification).where(Notification.kind == "suggestion_decided")).all()
