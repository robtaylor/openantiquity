"""A finding drawn as a line or a shape: creating it, extending it, reshaping it, and its anchor."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from geoalchemy2.shape import to_shape
from shapely import wkt
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.db import SessionLocal
from fieldclub.errors import BadRequestError, ConflictError, ValidationFailedError
from fieldclub.models import Activity, Finding, User
from fieldclub.models.common import to_db_geometry
from fieldclub.services import findings, geo, sensitivity, shape_edits, shapes
from fieldclub.services.findings import NotFinderError
from fieldclub.vocab import ShapeChangeKind
from tests.findings.support import (
    GEOD,
    LAT,
    LON,
    K,
    changes_of,
    drawn,
    east,
    edit,
    meridian,
    outline_of,
    path,
)
from tests.helpers import MakeUser, lon_lat

# --------------------------------------------------------------------------
# Creating
# --------------------------------------------------------------------------


def test_a_line_drawn_first_takes_the_point_half_way_along_it_as_its_anchor(
    db: Session, make_user: MakeUser
) -> None:
    finding = drawn(db, make_user(), meridian(0, 0.004, 0.006, 0.02))
    # Half of 0.02 is 0.01, between the vertices at 0.006 and 0.02.
    anchor = lon_lat(finding.location)
    assert anchor == pytest.approx((LON, LAT + 0.01), abs=1e-6)
    assert finding.location_derived is True
    assert finding.grid_ref == gridref.to_gridref(*anchor)
    assert finding.title == findings.suggested_title("linear", *anchor)
    assert finding.shape_kind == "line"
    assert finding.shape_revision == 0
    assert finding.path == meridian(0, 0.004, 0.006, 0.02).to_json()
    assert outline_of(finding).equals_exact(
        LineString([(LON, LAT + d) for d in (0, 0.004, 0.006, 0.02)]), 1e-7
    )
    assert finding.outline_mid is not None
    assert finding.outline_low is not None
    _, _, metres = GEOD.inv(LON, LAT, LON, LAT + 0.02)
    assert finding.shape_length_m == pytest.approx(metres, rel=1e-6)
    # Drawing it when it was marked is no change to its shape.
    assert changes_of(db, finding) == []


def test_an_area_drawn_first_takes_its_centroid(db: Session, make_user: MakeUser) -> None:
    ring = [(LON, LAT), (LON + 0.004 / K, LAT), (LON + 0.004 / K, LAT + 0.004), (LON, LAT + 0.004)]
    finding = drawn(db, make_user(), path(*ring, closed=True))
    assert lon_lat(finding.location) == pytest.approx((LON + 0.002 / K, LAT + 0.002), abs=1e-7)
    assert finding.shape_kind == "area"
    assert isinstance(outline_of(finding), Polygon)


def test_a_placed_point_keeps_its_place_and_the_shape_must_come_within_a_kilometre(
    db: Session, make_user: MakeUser
) -> None:
    author = make_user()
    near = findings.create_finding(
        db, author, location=Point(east(900), LAT), path=meridian(0, 0.01), feature_class="linear"
    )
    assert lon_lat(near.location) == pytest.approx((east(900), LAT), abs=1e-7)
    assert near.location_derived is False
    with pytest.raises(ValidationFailedError) as far:
        findings.create_finding(
            db, author, location=Point(east(1100), LAT), path=meridian(0, 0.01), feature_class="linear"
        )
    assert far.value.code == "outline_too_far"


def test_an_outline_is_still_taken_as_an_all_corner_path(db: Session, make_user: MakeUser) -> None:
    author = make_user()
    line = LineString([(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.002, LAT)])
    finding = findings.create_finding(
        db, author, location=Point(LON, LAT), outline=line, feature_class="linear"
    )
    assert finding.path == shapes.path_from_outline(line).to_json()  # pyright: ignore[reportOptionalMemberAccess]
    assert outline_of(finding).equals_exact(line, 1e-7)
    for other in (Point(LON, LAT), line.buffer(0.001).union(Point(LON + 0.1, LAT).buffer(0.001))):
        with pytest.raises(ValidationFailedError) as refused:
            findings.create_finding(
                db, author, location=Point(LON, LAT), outline=other, feature_class="linear"
            )
        assert refused.value.code == "outline_not_a_path"
    with pytest.raises(ValidationFailedError) as both:
        findings.create_finding(
            db, author, location=Point(LON, LAT), outline=line, path=meridian(0, 0.01), feature_class="linear"
        )
    assert both.value.code == "outline_and_path"


def test_a_finding_needs_a_point_or_a_shape(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(BadRequestError) as refused:
        findings.create_finding(db, make_user(), feature_class="linear")
    assert refused.value.code == "location_required"


def test_a_shape_is_held_to_the_limits_before_the_british_isles(db: Session, make_user: MakeUser) -> None:
    author = make_user()
    with pytest.raises(geo.OutsideBritishIslesError):
        drawn(db, author, path((2.30, 48.85), (2.31, 48.86)))
    # Half in, half out.
    with pytest.raises(geo.OutsideBritishIslesError):
        drawn(db, author, path((1.40, 51.10), (1.70, 51.10)))
    huge = [(2.0, 48.5), (2.5, 48.5), (2.5, 48.9)]
    with pytest.raises(ValidationFailedError) as big:
        drawn(db, author, path(*huge, closed=True))
    assert big.value.code == "shape_too_big"


# --------------------------------------------------------------------------
# Editing
# --------------------------------------------------------------------------


def test_extending_a_line_keeps_the_anchor_the_square_and_the_grid_reference(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.006, 0.012), requested_sensitivity="restricted")
    anchor, public, grid_ref = lon_lat(finding.location), lon_lat(finding.location_public), finding.grid_ref
    length = finding.shape_length_m
    assert length is not None

    edit(db, finding, finder, path=meridian(-0.01, 0, 0.006, 0.012, 0.03), path_revision=0)
    assert lon_lat(finding.location) == anchor
    assert lon_lat(finding.location_public) == public
    assert finding.grid_ref == grid_ref
    assert finding.shape_revision == 1
    assert finding.shape_length_m is not None
    assert finding.shape_length_m > length

    (change,) = changes_of(db, finding)
    assert (change.kind, change.revision, change.user_id) == ("extended", 1, finder.id)
    assert (change.points_before, change.points_after) == (3, 5)
    assert change.length_before_m == pytest.approx(length)
    assert change.added_length_m == pytest.approx(finding.shape_length_m - length, abs=0.5)
    assert change.path_before == meridian(0, 0.006, 0.012).to_json()
    assert change.added_view is not None
    assert set(change.added_view) == {"lon", "lat", "zoom"}


def test_a_reshape_that_moves_the_line_moves_a_derived_anchor_to_the_nearest_point(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.006, 0.012))
    moved_lon = east(3000)
    edit(db, finding, finder, path=meridian(-0.02, 0.03, lon=moved_lon), path_revision=0)
    # The nearest point of the new line to the old anchor, not the new line's middle.
    assert lon_lat(finding.location) == pytest.approx((moved_lon, LAT + 0.006), abs=1e-7)
    assert finding.grid_ref == gridref.to_gridref(moved_lon, LAT + 0.006)
    assert finding.title == findings.suggested_title("linear", moved_lon, LAT + 0.006)
    assert [change.kind for change in changes_of(db, finding)] == ["reshaped"]
    # Its activity moves to the new square with it: its making, and its being made much longer.
    rows = db.execute(
        select(Activity.kind, Activity.location)
        .where(Activity.finding_id == finding.id)
        .order_by(Activity.id)
    ).all()
    assert [kind for kind, _ in rows] == ["finding_created", "shape_extended"]
    for _, location in rows:
        assert location is not None
        assert lon_lat(location) == sensitivity.square_centre(finding)
    assert (
        sensitivity.square_centre(finding) != gridref.square_1km(LON, LAT + 0.006).polygon.centroid.coords[0]
    )


def test_a_derived_anchor_stays_while_the_new_shape_passes_within_25_m(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.006, 0.012))
    anchor = lon_lat(finding.location)
    edit(db, finding, finder, path=meridian(0, 0.012, lon=east(20)), path_revision=0)
    assert lon_lat(finding.location) == anchor
    edit(db, finding, finder, path=meridian(0, 0.012, lon=east(30)), path_revision=1)
    assert lon_lat(finding.location) != anchor


def test_a_placed_anchor_never_moves_and_a_shape_drawn_away_from_it_is_refused(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = findings.create_finding(
        db, finder, location=Point(LON, LAT + 0.006), path=meridian(0, 0.012), feature_class="linear"
    )
    db.commit()
    edit(db, finding, finder, path=meridian(0, 0.012, lon=east(500)), path_revision=0)
    assert lon_lat(finding.location) == pytest.approx((LON, LAT + 0.006))
    with pytest.raises(ValidationFailedError) as far:
        edit(db, finding, finder, path=meridian(0, 0.012, lon=east(2000)), path_revision=1)
    assert far.value.code == "outline_too_far"
    db.rollback()
    # Moving the point is checked against the shape it keeps.
    with pytest.raises(ValidationFailedError) as moved:
        edit(db, finding, finder, location=Point(east(3000), LAT))
    assert moved.value.code == "outline_too_far"


def test_placing_the_point_by_hand_stops_it_following_the_shape(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.012))
    edit(db, finding, finder, location=Point(east(100), LAT + 0.003))
    assert finding.location_derived is False
    assert finding.shape_revision == 0


def test_a_stale_or_missing_revision_is_refused(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = drawn(db, finder, meridian(0, 0.012))
    edit(db, finding, finder, path=meridian(0, 0.012, 0.02), path_revision=0)
    with pytest.raises(ConflictError) as stale:
        edit(db, finding, finder, path=meridian(0, 0.012, 0.03), path_revision=0)
    assert (stale.value.status_code, stale.value.code) == (409, "shape_changed")
    db.rollback()
    with pytest.raises(ValidationFailedError) as missing:
        edit(db, finding, finder, path=meridian(0, 0.012, 0.03))
    assert missing.value.code == "path_revision_required"
    db.rollback()
    assert finding.shape_revision == 1


def test_only_the_finder_changes_a_shape(db: Session, make_user: MakeUser) -> None:
    finding = drawn(db, make_user(), meridian(0, 0.012))
    with pytest.raises(NotFinderError):
        edit(db, finding, make_user("moderator"), path=meridian(0, 0.012, 0.02), path_revision=0)


def test_drawing_closing_opening_and_removing_are_each_recorded(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = findings.create_finding(db, finder, location=Point(LON, LAT), feature_class="enclosure")
    db.commit()
    ring = [(LON, LAT), (LON + 0.002, LAT), (LON + 0.002, LAT + 0.002)]
    edit(db, finding, finder, path=path(*ring), path_revision=0)
    edit(db, finding, finder, path=path(*ring, closed=True), path_revision=1)
    assert finding.shape_kind == "area"
    edit(db, finding, finder, path=path(*ring), path_revision=2)
    # Sending the same path again changes nothing.
    edit(db, finding, finder, path=path(*ring), path_revision=3)
    edit(db, finding, finder, path=None, path_revision=3)
    assert [change.kind for change in changes_of(db, finding)] == [
        "drawn",
        "closed",
        "opened",
        "removed",
    ]
    assert finding.shape_revision == 4
    assert (finding.path, finding.outline, finding.outline_mid, finding.outline_low) == (
        None,
        None,
        None,
        None,
    )
    assert (finding.shape_kind, finding.shape_length_m) == (None, None)
    removed = changes_of(db, finding)[-1]
    assert (removed.points_before, removed.points_after, removed.length_after_m) == (3, 0, None)
    assert removed.path_before == path(*ring).to_json()


def test_an_outline_saved_before_paths_is_extended_as_an_all_corner_path(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = findings.create_finding(db, finder, location=Point(LON, LAT), feature_class="linear")
    old = LineString([(LON, LAT), (LON, LAT + 0.004)])
    finding.outline = to_db_geometry(old)
    db.commit()
    assert finding.path is None
    edit(db, finding, finder, path=meridian(0, 0.004, 0.008), path_revision=0)
    (change,) = changes_of(db, finding)
    assert change.kind == "extended"
    assert change.path_before == meridian(0, 0.004).to_json()
    assert change.length_before_m == pytest.approx(shapes.length_m(old))


def test_a_shape_change_records_whoever_made_it_and_leaves_permission_to_the_caller(
    db: Session, make_user: MakeUser
) -> None:
    """`change_shape` is what accepting someone else's suggestion will call, with them as its maker."""
    finder, suggester = make_user(), make_user()
    finding = drawn(db, finder, meridian(0, 0.006, 0.012))
    kind = shape_edits.change_shape(
        db, findings.lock(db, finding), suggester, path=meridian(0, 0.006, 0.012, 0.02), revision=0
    )
    db.commit()
    assert kind is ShapeChangeKind.EXTENDED
    (change,) = changes_of(db, finding)
    assert change.user_id == suggester.id
    assert finding.shape_revision == 1


# --------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------


def _shape_columns(db: Session) -> list[tuple]:
    return list(
        db.execute(
            select(
                Finding.id,
                func.ST_AsText(Finding.outline_mid),
                func.ST_AsText(Finding.outline_low),
                Finding.shape_kind,
                Finding.shape_length_m,
                Finding.path,
                Finding.shape_revision,
                Finding.updated_at,
            ).order_by(Finding.id)
        ).all()
    )


def test_the_backfill_fills_old_outlines_once_and_leaves_everything_else(
    db: Session, make_user: MakeUser, caplog: pytest.LogCaptureFixture
) -> None:
    finder = make_user()
    line = LineString([(LON + i * 0.0001, LAT + (i % 2) * 0.00001) for i in range(50)])
    ring = Polygon([(LON, LAT), (LON + 0.004, LAT), (LON + 0.004, LAT + 0.004), (LON, LAT + 0.004)])
    old = []
    for outline in (line, ring):
        finding = findings.create_finding(db, finder, location=Point(LON, LAT), feature_class="enclosure")
        finding.outline = to_db_geometry(outline)
        old.append(finding)
    drawn_now = drawn(db, finder, meridian(0, 0.01))
    point_only = findings.create_finding(db, finder, location=Point(LON, LAT), feature_class="enclosure")
    db.commit()
    before = {row[0]: row for row in _shape_columns(db)}

    caplog.set_level(logging.INFO, logger="fieldclub.services.shapes")
    assert shapes.main(["backfill"]) == 0
    db.expire_all()
    after = {row[0]: row for row in _shape_columns(db)}
    for finding, outline in zip(old, (line, ring), strict=True):
        _, mid, low, kind, length, path, revision, updated = after[finding.id]
        assert (kind, path, revision, updated) == (
            shapes.kind_of(outline).value,
            None,
            0,
            before[finding.id][7],
        )
        assert length == pytest.approx(shapes.length_m(outline), rel=1e-6)
        assert wkt.loads(mid).equals_exact(shapes.simplified(outline, shapes.SIMPLIFY_MID_DEG), 1e-7)
        assert wkt.loads(low).equals_exact(shapes.simplified(outline, shapes.SIMPLIFY_LOW_DEG), 1e-7)
    # A shape saved through a path, and a finding with none, are left as they were.
    assert after[drawn_now.id] == before[drawn_now.id]
    assert after[point_only.id] == before[point_only.id]
    assert "filled 2" in caplog.text

    assert shapes.main(["backfill"]) == 0
    db.expire_all()
    assert {row[0]: row for row in _shape_columns(db)} == after
    assert "filled 0" in caplog.text


def _old_outline(db: Session, finder: Any, outline: BaseGeometry) -> Finding:
    """A finding with an outline saved before paths: no path, no simplified copies, no kind or length."""
    finding = findings.create_finding(db, finder, location=Point(LON, LAT), feature_class="enclosure")
    finding.outline = to_db_geometry(outline)
    db.commit()
    return finding


def test_the_backfill_leaves_alone_a_shape_edited_while_it_ran(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    finder = make_user()
    old = _old_outline(db, finder, LineString([(LON, LAT), (LON, LAT + 0.01)]))
    new_path = meridian(0, 0.01, 0.03)
    simplify = shapes.simplified
    edited: list[bool] = []

    def edit_meanwhile(geometry: BaseGeometry, tolerance: float) -> BaseGeometry:
        """The finder saves a new shape after the backfill read the old one, and before it writes."""
        if not edited:
            edited.append(True)
            with SessionLocal() as other:
                finding = findings.lock(other, other.get_one(Finding, old.id))
                findings.update_finding(
                    other,
                    finding,
                    other.get_one(User, finder.id),
                    {
                        "path": new_path,
                        "path_revision": 0,
                    },
                )
                other.commit()
        return simplify(geometry, tolerance)

    monkeypatch.setattr(shapes, "simplified", edit_meanwhile)
    assert shapes.backfill(db) == 0
    assert edited == [True]
    db.expire_all()
    fresh = shapes.shape_of(new_path)
    assert old.shape_revision == 1
    assert old.shape_length_m == pytest.approx(fresh.length_m)
    assert old.outline_mid is not None
    assert to_shape(old.outline_mid).equals_exact(fresh.mid, 1e-7)


def test_the_backfill_logs_an_empty_outline_and_goes_on(
    db: Session, make_user: MakeUser, caplog: pytest.LogCaptureFixture
) -> None:
    finder = make_user()
    empty = _old_outline(db, finder, LineString([(LON, LAT), (LON, LAT + 0.01)]))
    db.execute(
        update(Finding)
        .where(Finding.id == empty.id)
        .values(outline=func.ST_GeomFromText("LINESTRING EMPTY", 4326))
    )
    db.commit()
    good = _old_outline(db, finder, LineString([(LON, LAT), (LON, LAT + 0.01)]))
    caplog.set_level(logging.WARNING, logger="fieldclub.services.shapes")
    assert shapes.backfill(db) == 1
    db.expire_all()
    assert good.shape_kind == "line"
    assert empty.shape_kind is None
    assert f"Finding {empty.id} has an empty outline" in caplog.text
    # Nothing is left to fill but the empty one, which is passed over again.
    assert shapes.backfill(db) == 0
