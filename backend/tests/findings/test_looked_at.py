"""Second looks on a line or shape: what they were given on, what an extension asks of them,
and how much of what they saw an edit must keep (Decision 0029)."""

from __future__ import annotations

import math
from typing import Any

import pytest
import shapely
import shapely.affinity
from geoalchemy2.shape import to_shape
from shapely.geometry import LineString, MultiPoint, Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from fieldclub.errors import ValidationFailedError
from fieldclub.models import Activity, Finding, Notification, Observation, User
from fieldclub.services import findings, looked_at, review, shapes
from fieldclub.vocab import Visible
from tests.findings.support import (
    API,
    LAT,
    LON,
    answer,
    changes_of,
    create,
    drawn,
    east,
    edit,
    meridian,
    outline_of,
    path,
)
from tests.helpers import ClientAs, MakeUser, error_code

NEW_PART = "look_at_new_part"
# About 111 m of latitude.
STEP = 0.001


def answered(
    db: Session, make_user: MakeUser, finding: Finding, people: int = 1, role: str = "member"
) -> list[User]:
    """`people` who see the finding exactly give it a yes."""
    helpers = [make_user(role) for _ in range(people)]
    for helper in helpers:
        answer(db, finding, helper, Visible.YES)
    db.expire_all()
    return helpers


def seen_on(finding: Finding) -> BaseGeometry:
    assert finding.looked_at is not None, f"nobody has looked at {finding.public_id}"
    return to_shape(finding.looked_at)


def same_ground(geometry: Any, expected: Any) -> bool:
    """Whether two geometries cover the same ground, to well under a millimetre."""
    return geometry.hausdorff_distance(expected) < 1e-9 and geometry.length == pytest.approx(expected.length)


def refused(db: Session, finding: Finding, finder: User, **changes: Any) -> str:
    with pytest.raises(ValidationFailedError) as caught:
        edit(db, finding, finder, **changes)
    db.rollback()
    return caught.value.code


# --------------------------------------------------------------------------
# What a second look records
# --------------------------------------------------------------------------


def test_an_answer_records_the_revision_and_the_shape_it_was_given_on(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    assert finding.looked_at is None
    first, *_ = answered(db, make_user, finding)
    assert same_ground(seen_on(finding), LineString([(LON, LAT), (LON, LAT + 0.01)]))

    edit(db, finding, finder, path=meridian(0, 0.01, 0.02), path_revision=0)
    second, *_ = answered(db, make_user, finding)
    revisions = dict(db.execute(select(Observation.user_id, Observation.shape_revision)).all())
    assert revisions == {first.id: 0, second.id: 1}
    assert same_ground(seen_on(finding), LineString([(LON, LAT), (LON, LAT + 0.02)]))


def test_an_area_is_looked_at_by_its_edge_and_a_spot_by_its_point(db: Session, make_user: MakeUser) -> None:
    ring = [(LON, LAT), (LON + 0.004, LAT), (LON + 0.004, LAT + 0.004)]
    area = drawn(db, make_user(), path(*ring, closed=True))
    spot = create(db, make_user())
    answered(db, make_user, area)
    answered(db, make_user, spot)
    assert seen_on(area).geom_type == "LineString"
    assert seen_on(area).equals(outline_of(area).boundary)
    assert seen_on(spot).equals(Point(LON, LAT))


def test_an_answer_naming_a_shape_that_has_since_changed_is_refused_and_stores_nothing(
    db: Session, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    edit(db, finding, finder, path=meridian(0, 0.01, 0.3), path_revision=0)
    with pytest.raises(findings.ShapeChangedError):
        answer(db, finding, helper, Visible.YES, shape_revision=0)
    db.rollback()
    assert db.scalars(select(Observation)).all() == []
    assert finding.looked_at is None
    # Naming the shape as it is now, or naming none, as a tab opened before the change does, is answered.
    answer(db, finding, helper, Visible.YES, shape_revision=1)
    answer(db, finding, make_user(), Visible.YES)
    assert db.scalars(select(Observation.shape_revision)).all() == [1, 1]


def _zigzag(vertices: int, amplitude_m: float, spacing_m: float = 15.0) -> LineString:
    """A line north from LAT that swings `amplitude_m` east and back at every vertex."""
    k = math.cos(math.radians(LAT))
    return LineString(
        [
            (LON + (i % 2) * amplitude_m / (111_320 * k), LAT + i * spacing_m / 111_320)
            for i in range(vertices)
        ]
    )


def _apart_m(a: BaseGeometry, b: BaseGeometry) -> float:
    """The Hausdorff distance between two geometries near LAT, in metres north and east."""
    scale = [math.cos(math.radians(LAT)) * 111_320, 111_320]
    return shapely.transform(a, lambda xy: xy * scale).hausdorff_distance(
        shapely.transform(b, lambda xy: xy * scale)
    )


def test_what_is_added_is_simplified_to_5_m() -> None:
    wiggle = _zigzag(50_000, amplitude_m=2)
    kept = looked_at.grown(None, wiggle)
    assert shapely.get_num_coordinates(kept) < 100
    # Never more than 5 m from the line, measured in metres north and east.
    assert _apart_m(kept, wiggle) < 5.01


def test_looked_at_is_simplified_harder_once_it_passes_the_cap() -> None:
    saw_tooth = _zigzag(12_000, amplitude_m=30)
    assert shapely.get_num_coordinates(saw_tooth.simplify(5 / 111_320)) > looked_at.LOOKED_AT_MAX_VERTICES
    kept = looked_at.grown(None, saw_tooth)
    assert 2 <= shapely.get_num_coordinates(kept) <= looked_at.LOOKED_AT_MAX_VERTICES
    assert _apart_m(kept, saw_tooth) <= looked_at.LOOKED_AT_MAX_MOVE_M / 4
    # The cap holds as more is added beside it.
    beside = shapely.affinity.translate(saw_tooth, xoff=0.0005)
    both = looked_at.grown(kept, beside)
    assert shapely.get_num_coordinates(both) <= looked_at.LOOKED_AT_MAX_VERTICES


def test_points_and_lines_looked_at_are_all_kept() -> None:
    spot = looked_at.grown(None, Point(LON, LAT))
    moved = looked_at.grown(spot, Point(LON + 0.001, LAT))
    assert moved.equals_exact(MultiPoint([(LON, LAT), (LON + 0.001, LAT)]), 1e-9)
    drawn_later = looked_at.grown(moved, LineString([(LON, LAT + 0.01), (LON, LAT + 0.02)]))
    assert {part.geom_type for part in shapely.get_parts(drawn_later)} == {"Point", "LineString"}
    assert shapely.get_num_geometries(drawn_later) == 3


def test_nothing_empty_is_added_to_what_was_looked_at() -> None:
    with pytest.raises(AssertionError, match="empty"):
        looked_at.grown(None, LineString())
    with pytest.raises(AssertionError, match="empty"):
        looked_at.grown(Point(LON, LAT), LineString())


def test_every_revision_looked_at_stays_under_the_cap(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    smooth = [(LON + 0.002 * (i % 2), LAT + 0.004 * i) for i in range(40)]
    finding = drawn(db, finder, path(*smooth, kind="smooth"))
    shown = []
    for revision in range(4):
        answered(db, make_user, finding)
        shown.append(outline_of(finding))
        nudged = [(lon + (revision + 1) * 0.0001, lat) for lon, lat in smooth]
        edit(db, finding, finder, path=path(*nudged, kind="smooth"), path_revision=revision)
    answered(db, make_user, finding)
    shown.append(outline_of(finding))
    vertices = shapely.get_num_coordinates(seen_on(finding))
    assert 0 < vertices <= looked_at.LOOKED_AT_MAX_VERTICES
    # Each revision is simplified as it is added.
    assert vertices < shapely.get_num_coordinates(shapely.union_all(shown)) / 2
    assert _apart_m(seen_on(finding), shapely.union_all(shown)) < 5.01


# --------------------------------------------------------------------------
# Extending, and what it asks of second looks
# --------------------------------------------------------------------------


def test_an_extension_leaves_the_tier_the_score_and_every_answer_as_they_were(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding, people=3)
    before = (finding.tier, finding.confidence, finding.observation_count, finding.answers_to_next)
    weights = db.execute(select(Observation.id, Observation.role_at_answer, Observation.visible)).all()

    edit(db, finding, finder, path=meridian(0, 0.01, 0.05), path_revision=0)
    assert (finding.tier, finding.confidence, finding.observation_count, finding.answers_to_next) == before
    after = db.execute(select(Observation.id, Observation.role_at_answer, Observation.visible)).all()
    assert sorted(after) == sorted(weights)
    assert NEW_PART in finding.open_steps


def test_the_new_part_is_asked_about_above_200_m_and_no_more_once_someone_looks(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding)

    edit(db, finding, finder, path=meridian(0, 0.01, 0.01 + STEP), path_revision=0)
    assert NEW_PART not in finding.open_steps
    edit(db, finding, finder, path=meridian(0, 0.01, 0.01 + STEP, 0.01 + 2 * STEP), path_revision=1)
    # Both extensions count: about 222 m since the answer.
    assert NEW_PART in finding.open_steps
    (step,) = [s for s in findings.current_assessment(finding).next_steps if s.code == NEW_PART]
    assert step.people == 1
    part = looked_at.new_part(db, finding)
    assert part is not None
    assert part.length_m == pytest.approx(2 * 111.2, abs=1)
    assert part.view == changes_of(db, finding)[-1].added_view

    answered(db, make_user, finding)
    assert NEW_PART not in finding.open_steps
    assert looked_at.new_part(db, finding) is None


def test_a_reshape_asks_nobody_to_look_and_a_finding_nobody_answered_has_no_new_part(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    unanswered = drawn(db, finder, meridian(0, 0.01))
    edit(db, unanswered, finder, path=meridian(0, 0.01, 0.05), path_revision=0)
    assert NEW_PART not in unanswered.open_steps
    assert looked_at.new_part(db, unanswered) is None

    reshaped = drawn(db, finder, meridian(0, 0.02))
    answered(db, make_user, reshaped)
    edit(db, reshaped, finder, path=meridian(0, 0.005, 0.02, lon=east(100)), path_revision=0)
    assert [change.kind for change in changes_of(db, reshaped)] == ["reshaped"]
    assert NEW_PART not in reshaped.open_steps


def test_an_answer_taken_back_leaves_the_older_one_to_count_from(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(0, 0.01, 0.02), path_revision=0)
    (later,) = answered(db, make_user, finding)
    assert NEW_PART not in finding.open_steps
    review.delete_observation(db, finding, later)
    db.commit()
    assert NEW_PART in finding.open_steps


def test_an_extension_tells_the_followers_and_nothing_else_does(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    (helper,) = answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(0, 0.012, lon=east(100)), path_revision=0)
    edit(db, finding, finder, path=meridian(0, 0.012, 0.02, lon=east(100)), path_revision=1)

    (extended,) = db.scalars(select(Activity).where(Activity.kind == "shape_extended")).all()
    assert (extended.finding_id, extended.actor_id, extended.data) == (finding.id, finder.id, None)
    told = db.scalars(select(Notification.user_id).where(Notification.kind == "shape_extended")).all()
    # The answerer follows the finding. The finder made the change and isn't told of it.
    assert told == [helper.id]


# --------------------------------------------------------------------------
# Once looked at, most of it stays
# --------------------------------------------------------------------------


def test_an_extension_may_run_far_beyond_what_was_looked_at(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(-0.2, 0, 0.01, 0.3), path_revision=0)
    assert finding.shape_revision == 1


def test_a_line_may_be_shortened_by_a_fifth_but_not_by_half(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    fifth = drawn(db, finder, meridian(0, 0.04))
    half = drawn(db, finder, meridian(0, 0.04))
    answered(db, make_user, fifth)
    answered(db, make_user, half)
    edit(db, fifth, finder, path=meridian(0, 0.032), path_revision=0)
    assert fifth.shape_revision == 1
    assert refused(db, half, finder, path=meridian(0, 0.02), path_revision=0) == "looked_at_moved"
    assert half.shape_revision == 0


def test_two_shortenings_of_a_fifth_are_refused_at_the_second(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.04))
    answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(0, 0.032), path_revision=0)
    assert refused(db, finding, finder, path=meridian(0, 0.024), path_revision=1) == "looked_at_moved"


def test_deleting_what_was_looked_at_after_extending_elsewhere_is_refused(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(0, 0.01, 0.05), path_revision=0)
    assert refused(db, finding, finder, path=meridian(0.02, 0.05), path_revision=1) == "looked_at_moved"


def test_a_chain_of_small_moves_cant_carry_a_line_more_than_250_m(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.01))
    answered(db, make_user, finding)
    edit(db, finding, finder, path=meridian(0, 0.01, lon=east(200)), path_revision=0)
    assert refused(db, finding, finder, path=meridian(0, 0.01, lon=east(400)), path_revision=1) == (
        "looked_at_moved"
    )


def test_a_spot_moves_200_m_and_is_refused_at_300_m(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    answered(db, make_user, finding)
    edit(db, finding, finder, location=Point(east(200), LAT))
    assert refused(db, finding, finder, location=Point(east(300), LAT)) == "looked_at_moved"


def test_removing_a_shape_that_was_looked_at_is_refused(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.02))
    answered(db, make_user, finding)
    assert refused(db, finding, finder, path=None, path_revision=0) == "looked_at_moved"


def test_a_finding_nobody_looked_at_changes_freely(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.02))
    edit(db, finding, finder, path=meridian(0, 0.02, lon=east(5000)), path_revision=0)
    edit(db, finding, finder, path=None, path_revision=1)
    edit(db, finding, finder, location=Point(east(9000), LAT))
    assert finding.shape_revision == 2


def test_the_check_is_made_where_a_suggestion_would_be_applied(db: Session, make_user: MakeUser) -> None:
    """`change_shape` holds an accepted suggestion to the same rule as the finder's own edit."""
    finder, suggester = make_user(), make_user()
    finding = drawn(db, finder, meridian(0, 0.02))
    answered(db, make_user, finding)
    with pytest.raises(ValidationFailedError) as caught:
        findings.change_shape(
            db, findings.lock(db, finding), suggester, path=meridian(0, 0.02, lon=east(3000)), revision=0
        )
    assert caught.value.code == "looked_at_moved"


# --------------------------------------------------------------------------
# Second looks given before they recorded what they saw
# --------------------------------------------------------------------------


def answered_before_the_change(db: Session, make_user: MakeUser, finding: Finding) -> None:
    """A second look as one given before answers recorded a revision and before `looked_at` existed."""
    answered(db, make_user, finding)
    db.execute(update(Observation).where(Observation.finding_id == finding.id).values(shape_revision=None))
    db.execute(update(Finding).where(Finding.id == finding.id).values(looked_at=None))
    db.commit()
    db.expire_all()
    assert finding.looked_at is None


def test_a_line_answered_before_the_change_is_held_to_its_shape_as_stored(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.02))
    answered_before_the_change(db, make_user, finding)
    assert refused(db, finding, finder, path=meridian(0, 0.02, lon=east(3000)), path_revision=0) == (
        "looked_at_moved"
    )
    # Seeded from the shape before the edit, and kept from then on.
    edit(db, finding, finder, path=meridian(0, 0.02, 0.03), path_revision=0)
    assert same_ground(seen_on(finding), LineString([(LON, LAT), (LON, LAT + 0.02)]))


def test_a_spot_answered_before_the_change_is_held_to_its_point(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    answered_before_the_change(db, make_user, finding)
    assert refused(db, finding, finder, location=Point(east(300), LAT)) == "looked_at_moved"
    edit(db, finding, finder, location=Point(east(200), LAT))
    assert seen_on(finding).equals(Point(LON, LAT))


def test_a_finding_whose_only_look_was_taken_back_isnt_held(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.02))
    answered_before_the_change(db, make_user, finding)
    db.execute(update(Observation).values(withdrawn_at=func.now()))
    db.commit()
    edit(db, finding, finder, path=meridian(0, 0.02, lon=east(3000)), path_revision=0)
    assert finding.looked_at is None


def _looked_at_by_id(db: Session) -> dict[int, str | None]:
    return dict(db.execute(select(Finding.id, func.ST_AsText(Finding.looked_at))).all())


def test_the_backfill_seeds_what_was_looked_at_once(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    line, spot, unanswered, taken_back = (
        drawn(db, finder, meridian(0, 0.02)),
        create(db, finder),
        drawn(db, finder, meridian(0, 0.01)),
        create(db, finder),
    )
    for finding in (line, spot, taken_back):
        answered_before_the_change(db, make_user, finding)
    db.execute(
        update(Observation).where(Observation.finding_id == taken_back.id).values(withdrawn_at=func.now())
    )
    seen_now = drawn(db, finder, meridian(0, 0.03))
    answered(db, make_user, seen_now)
    db.commit()
    before = _looked_at_by_id(db)

    assert shapes.main(["backfill"]) == 0
    db.expire_all()
    after = _looked_at_by_id(db)
    assert same_ground(seen_on(line), LineString([(LON, LAT), (LON, LAT + 0.02)]))
    assert seen_on(spot).equals(Point(LON, LAT))
    assert after[unanswered.id] is None
    assert after[taken_back.id] is None
    assert after[seen_now.id] == before[seen_now.id]

    assert shapes.main(["backfill"]) == 0
    db.expire_all()
    assert _looked_at_by_id(db) == after


# --------------------------------------------------------------------------
# Over HTTP
# --------------------------------------------------------------------------


def _line(client_as: ClientAs, finder: User, *, sensitivity: str = "open") -> str:
    made = client_as(finder).post(
        f"{API}/findings",
        json={
            "feature_class": "linear",
            "sensitivity": sensitivity,
            "path": {"points": [{"lon": LON, "lat": LAT + d, "kind": "corner"} for d in (0, 0.01)]},
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["public_id"]


def _extend(client_as: ClientAs, finder: User, public_id: str, revision: int, *offsets: float) -> Any:
    return client_as(finder).patch(
        f"{API}/findings/{public_id}",
        json={
            "path": {"points": [{"lon": LON, "lat": LAT + d, "kind": "corner"} for d in offsets]},
            "path_revision": revision,
        },
    )


def test_the_page_says_what_was_added_since_the_last_look_to_exact_viewers_only(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    public_id = _line(client_as, finder, sensitivity="restricted")
    finding = findings.get_finding(db, public_id, finder)
    answered(db, make_user, finding, role="trusted")
    assert _extend(client_as, finder, public_id, 0, 0, 0.01, 0.03).status_code == 200

    own = client_as(finder).get(f"{API}/findings/{public_id}").json()
    assert own["location"]["shape"]["added_since_looked_m"] == pytest.approx(2224, abs=5)
    assert NEW_PART in [step["code"] for step in own["assessment"]["next_steps"]]

    # A member sees a restricted finding only as its square.
    square = client_as(make_user()).get(f"{API}/findings/{public_id}").json()
    assert square["location"]["shape"]["added_since_looked_m"] is None
    assert square["location"]["shape"]["looked_at"] is None
    assert NEW_PART not in [step["code"] for step in square["assessment"]["next_steps"]]


def test_a_viewer_who_hasnt_answered_learns_no_count_of_answers(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    public_id = _line(client_as, finder)
    answered(db, make_user, findings.get_finding(db, public_id, finder), people=2)
    assert _extend(client_as, finder, public_id, 0, 0, 0.01, 0.03).status_code == 200

    page = client_as(make_user()).get(f"{API}/findings/{public_id}").json()
    assert page["answers_visible"] is False
    assert page["assessment"]["tallies"] is None
    assert page["location"]["shape"]["added_since_looked_m"] == pytest.approx(2224, abs=5)
    for step in page["assessment"]["next_steps"]:
        assert (step["people"], step["weight_needed"]) == (None, None), step


def test_looked_at_goes_only_to_the_one_who_may_change_the_finding(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    public_id = _line(client_as, finder)
    unseen = client_as(finder).get(f"{API}/findings/{public_id}").json()
    assert unseen["location"]["shape"]["looked_at"] is None
    answered(db, make_user, findings.get_finding(db, public_id, finder))
    own = client_as(finder).get(f"{API}/findings/{public_id}").json()
    assert own["actions"]["edit"]["allowed"] is True
    assert own["location"]["shape"]["looked_at"]["type"] == "LineString"
    for other in (make_user(), make_user("moderator")):
        page = client_as(other).get(f"{API}/findings/{public_id}").json()
        assert page["actions"]["edit"]["allowed"] is False
        assert page["location"]["shape"]["looked_at"] is None


def test_an_edit_that_moves_what_was_looked_at_is_refused_with_its_code(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    public_id = _line(client_as, finder)
    answered(db, make_user, findings.get_finding(db, public_id, finder))
    moved = _extend(client_as, finder, public_id, 0, 0.02, 0.03)
    assert (moved.status_code, error_code(moved)) == (422, "looked_at_moved")
    message = moved.json()["error"]["message"]
    assert "0%" in message
    assert "three-quarters" in message
    assert "withdraw the finding and mark it again" in message


def test_help_wanted_and_the_queue_frame_the_new_part(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    public_id = _line(client_as, finder)
    answered(db, make_user, findings.get_finding(db, public_id, finder))
    assert _extend(client_as, finder, public_id, 0, 0, 0.01, 0.03).status_code == 200
    finding = findings.get_finding(db, public_id, finder)
    view = changes_of(db, finding)[-1].added_view
    assert view is not None

    reviewer = client_as(make_user())
    groups = reviewer.get(f"{API}/review/tasks", params={"code": NEW_PART}).json()["groups"]
    (task,) = [item for item in groups[0]["items"] if item["public_id"] == public_id]
    assert (task["place"]["lon"], task["place"]["lat"]) == pytest.approx((view["lon"], view["lat"]))
    assert task["view_state"]["zoom"] == view["zoom"]
    assert (task["step"], task["finding"], task["place"]["outline"]) == (None, None, None)

    cards = reviewer.get(f"{API}/review/next", params={"limit": 50}).json()["items"]
    (card,) = [card for card in cards if card["public_id"] == public_id]
    assert (card["place"]["lon"], card["place"]["lat"]) == pytest.approx((view["lon"], view["lat"]))
    assert card["view_state"]["zoom"] == view["zoom"]


def test_an_answer_over_http_names_the_shape_it_was_given_on(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    public_id = _line(client_as, finder)
    reviewer = client_as(helper)
    cards = reviewer.get(f"{API}/review/next", params={"limit": 50}).json()["items"]
    (card,) = [card for card in cards if card["public_id"] == public_id]
    assert card["shape_revision"] == 0
    groups = reviewer.get(f"{API}/review/tasks").json()["groups"]
    tasks = [item for group in groups for item in group["items"] if item["public_id"] == public_id]
    assert tasks
    assert {task["shape_revision"] for task in tasks} == {0}

    assert _extend(client_as, finder, public_id, 0, 0, 0.01, 0.03).status_code == 200
    stale = reviewer.put(
        f"{API}/findings/{public_id}/observation", json={"visible": "yes", "shape_revision": 0}
    )
    assert (stale.status_code, error_code(stale)) == (409, "shape_changed")
    assert db.scalars(select(Observation)).all() == []
    fresh = reviewer.put(
        f"{API}/findings/{public_id}/observation", json={"visible": "yes", "shape_revision": 1}
    )
    assert fresh.status_code == 200, fresh.text
    unnamed = client_as(make_user()).put(f"{API}/findings/{public_id}/observation", json={"visible": "yes"})
    assert unnamed.status_code == 200, unnamed.text
