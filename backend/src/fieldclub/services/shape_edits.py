"""Changing a finding's line or shape: reading it from a request, applying it, and drawing it on the map.

`change_shape` applies a change under the finding's lock: it checks the
revision the change started from, holds the new shape to the limits in
`services.shapes` and to the British Isles, places the anchor, holds the
change to what second looks were given on (`services.looked_at`), writes
the change row and raises the revision. It doesn't decide who may make the
change. `services.findings.update_finding` checks that the finder makes it,
and reassesses and records the activity afterwards, so this module needs
nothing from `services.findings`.

`map_shapes` gives the map each finding's shape, simplified for the zoom
and cut to the box, to viewers who see it exactly.

Services flush and never commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from geoalchemy2.shape import to_shape
from shapely import wkb
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.errors import ConflictError, ValidationFailedError
from fieldclub.models import Finding, FindingShapeChange, User
from fieldclub.models.common import point_lon_lat, to_db_geometry
from fieldclub.services import geo, looked_at, sensitivity, shapes
from fieldclub.vocab import ShapeChangeKind, ShapeKind

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class PathRevisionRequiredError(ValidationFailedError):
    code = "path_revision_required"
    message = "A change to the shape says which `path_revision` it started from."


class ShapeChangedError(ConflictError):
    code = "shape_changed"
    message = "The shape was changed somewhere else. Reload the finding and make your change again."


# --------------------------------------------------------------------------
# Reading and recording a shape
# --------------------------------------------------------------------------


def shape_from_request(path: shapes.Path | None, outline: BaseGeometry | None) -> shapes.Shape | None:
    """The shape a request asks for, held to the limits.

    That is its `path`, or its `outline` read as an all-corner path.
    """
    if path is not None and outline is not None:
        raise shapes.OutlineAndPathError()
    if outline is not None:
        as_path = shapes.path_from_outline(outline)
        if as_path is None:
            raise shapes.OutlineNotAPathError()
        # Checked as a path from a request is, for points on top of each other.
        path = shapes.read_path(as_path.to_json())
    return shapes.shape_of(path) if path is not None else None


def stored_path(finding: Finding) -> shapes.Path | None:
    """`shapes.stored_path` for a finding. The outline is read only when there is no path."""
    outline = to_shape(finding.outline) if finding.path is None and finding.outline is not None else None
    return shapes.stored_path(finding.path, outline)


def shape_columns(shape: shapes.Shape | None) -> dict[str, Any]:
    """The columns that hold a shape, for a new finding or an edit. All None without one."""
    if shape is None:
        return dict.fromkeys(
            ("path", "outline", "outline_mid", "outline_low", "shape_kind", "shape_length_m")
        )
    return {
        "path": shape.path.to_json(),
        "outline": to_db_geometry(shape.geometry),
        "outline_mid": to_db_geometry(shape.mid),
        "outline_low": to_db_geometry(shape.low),
        "shape_kind": shape.kind.value,
        "shape_length_m": shape.length_m,
    }


def stored_length(finding: Finding) -> float | None:
    """The length of the finding's shape as it is stored, or None without a shape.

    An outline saved before paths that the backfill hasn't measured yet is
    measured from its geometry.
    """
    if finding.shape_length_m is not None:
        return finding.shape_length_m
    if finding.outline is None:
        return None
    return shapes.length_m(to_shape(finding.outline))


def stored_kind(finding: Finding) -> ShapeKind | None:
    """Whether the finding's shape as it is stored is a line or an area, or None without a shape.

    An outline the backfill hasn't classed yet is classed from its geometry.
    """
    if finding.shape_kind is not None:
        return ShapeKind(finding.shape_kind)
    if finding.outline is None:
        return None
    return shapes.kind_of(to_shape(finding.outline))


def _check_revision(finding: Finding, revision: int | None) -> None:
    """Refuse a change to the shape that didn't start from the shape as it is now. Hold the lock."""
    if revision is None:
        raise PathRevisionRequiredError()
    if revision != finding.shape_revision:
        raise ShapeChangedError()


def _classify(finding: Finding, old: shapes.Path | None, new: shapes.Shape | None) -> ShapeChangeKind | None:
    """`shapes.classify_change`, knowing that an old outline with no path is still a shape."""
    if old is None and finding.outline is not None:
        return ShapeChangeKind.RESHAPED if new is not None else ShapeChangeKind.REMOVED
    return shapes.classify_change(old, new.path if new is not None else None)


def _anchor_for(finding: Finding, shape: shapes.Shape | None, location: Point, *, placed: bool) -> Point:
    """Where the anchor goes when the shape changes.

    A point the finder places now, or placed before, never moves by itself:
    the shape must come within `shapes.SHAPE_MAX_GAP_M` of it. A point the
    server chose stays while the shape passes within `shapes.ANCHOR_KEEP_M`,
    so extending a line never moves it, and otherwise moves to the point of
    the new shape nearest where it was, never to the new middle, which would
    leave a trail of squares along a restricted line. Removing the shape
    leaves the point where it is.
    """
    if shape is None:
        return location
    if placed or not finding.location_derived:
        shapes.check_shape(shape.geometry, location)
        return location
    if shapes.distance_m(shape.geometry, location) <= shapes.ANCHOR_KEEP_M:
        return location
    return shapes.nearest_point(shape.geometry, location)


def _record_shape_change(
    db: Session,
    finding: Finding,
    actor: User,
    kind: ShapeChangeKind,
    old: shapes.Path | None,
    new: shapes.Shape | None,
) -> FindingShapeChange:
    """Write the change row for the revision this change makes. Call it before storing the new shape."""
    length_before = stored_length(finding)
    added_length: float | None = None
    added_view: dict[str, float] | None = None
    if kind is ShapeChangeKind.EXTENDED:
        assert old is not None, "an extension extends a path"
        assert new is not None, "an extension leaves a shape"
        assert length_before is not None, "a path that was extended was measured"
        added_length = max(0.0, new.length_m - length_before)
        added_view = shapes.added_view(old, new.path)
    row = FindingShapeChange(
        finding_id=finding.id,
        user_id=actor.id,
        revision=finding.shape_revision + 1,
        kind=kind.value,
        points_before=len(old.points) if old is not None else 0,
        points_after=len(new.path.points) if new is not None else 0,
        length_before_m=length_before,
        length_after_m=new.length_m if new is not None else None,
        added_length_m=added_length,
        added_view=added_view,
        path_before=old.to_json() if old is not None else None,
    )
    db.add(row)
    return row


# --------------------------------------------------------------------------
# Applying a change
# --------------------------------------------------------------------------


def point_parts(point: Point) -> tuple[float, float]:
    """A finding's point as longitude and latitude."""
    assert isinstance(point, Point), "a finding's location is a point"
    return point.x, point.y


def move_anchor(db: Session, finding: Finding, location: Point) -> None:
    """Put the finding's anchor at `location`. The ORM keeps `grid_ref` and the public position in step."""
    finding.location = to_db_geometry(location)
    finding.nation = geo.nation_of(db, Point(*point_parts(location)))


def change_shape(
    db: Session,
    finding: Finding,
    by: User,
    *,
    path: shapes.Path | None,
    outline: BaseGeometry | None = None,
    revision: int | None,
    placed: Point | None = None,
) -> ShapeChangeKind | None:
    """Apply a change to a finding's shape made by `by`, and say what kind it was. Hold the lock.

    This doesn't decide who may change the finding: the caller does, with
    `check_finder`. `by` is recorded as the person who made the change.

    `path` (or `outline`, read as one) replaces the whole shape, and None for
    both removes it. `revision` must be the shape's revision now. A shape
    sent unchanged changes nothing and returns None. Otherwise it is held to
    the limits and the British Isles, the anchor follows `_anchor_for` (with
    `placed`, a point placed with the change, which the shape must come near),
    the change must keep most of what second looks were given on
    (`looked_at.check`), the change row is written and the revision raised.

    Every answer stands, at the weight it was given with. The length lying
    beyond what was looked at is worked out again (`looked_at.refresh_added`).
    The caller reassesses when it changed, so the finding asks, or stops
    asking, for a look at the new part, and records `shape_extended` after
    an extension: `services.findings.update_finding` does both.
    """
    _check_revision(finding, revision)
    new_shape = shape_from_request(path, outline)
    old_path = stored_path(finding)
    kind = _classify(finding, old_path, new_shape)
    if kind is None:
        return None
    current = Point(point_lon_lat(finding.location))
    anchor = _anchor_for(finding, new_shape, placed or current, placed=placed is not None)
    if new_shape is not None:
        geo.check_in_british_isles(new_shape.geometry)
    looked_at.check(db, finding, new_shape.geometry if new_shape is not None else anchor)
    _record_shape_change(db, finding, by, kind, old_path, new_shape)
    for name, value in shape_columns(new_shape).items():
        setattr(finding, name, value)
    finding.shape_revision += 1
    if new_shape is None:
        finding.location_derived = False
    if point_parts(anchor) != point_parts(current):
        move_anchor(db, finding, anchor)
    looked_at.refresh_added(finding)
    return kind


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------

# The zooms the map asks for findings at, and the column each draws a shape
# from: `outline_low` below 13, `outline_mid` to 15, `outline` from 16. An
# outline saved before the simplified copies were is drawn whole until the
# backfill fills them.
MAP_ZOOM_MIN = 9
MAP_ZOOM_MAX = 22
MAP_ZOOM_DEFAULT = 14
# A shape is cut to the box the map asked for, widened by this, so a line
# drawn to the edge of the screen doesn't stop short of it.
MAP_CLIP_MARGIN_M = 500


def _map_shape_column(zoom: int) -> Any:
    assert MAP_ZOOM_MIN <= zoom <= MAP_ZOOM_MAX, f"zoom {zoom} is outside the map's zooms"
    if zoom < 13:
        return func.coalesce(Finding.outline_low, Finding.outline)
    if zoom <= 15:
        return func.coalesce(Finding.outline_mid, Finding.outline)
    return Finding.outline


def map_shapes(
    db: Session,
    chosen: Sequence[Finding],
    viewer: User | None,
    *,
    zoom: int,
    bbox: tuple[float, float, float, float] | None,
) -> dict[int, BaseGeometry]:
    """The shape to draw for each of `chosen` this viewer sees exactly, by finding id.

    Simplified for `zoom` and cut in the database to `bbox` widened by
    `MAP_CLIP_MARGIN_M`, so a 600 km road costs a map view only the part in
    it. A shape left empty by the cut is left out.
    """
    wanted = [f.id for f in chosen if sensitivity.sees_exact(f, viewer)]
    if not wanted:
        return {}
    column = _map_shape_column(zoom)
    if bbox is not None:
        _, south, _, north = bbox
        margin_lat = MAP_CLIP_MARGIN_M / geo.METRES_PER_DEGREE
        margin_lon = margin_lat / geo.lon_scale((south + north) / 2)
        column = func.ST_ClipByBox2D(column, func.ST_Expand(geo.envelope(bbox), margin_lon, margin_lat))
    rows = db.execute(
        select(Finding.id, func.ST_AsBinary(column)).where(
            Finding.id.in_(wanted), Finding.outline.is_not(None)
        )
    ).all()
    found = {finding_id: wkb.loads(bytes(data)) for finding_id, data in rows if data is not None}
    return {finding_id: geometry for finding_id, geometry in found.items() if not geometry.is_empty}
