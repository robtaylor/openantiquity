"""What second looks were given on, and what has been added to a line since (Decision 0029).

Each second look records the finding's `shape_revision` when it is given
(`observations.shape_revision`), and adds the finding's shape then, an area
as its edge, or its point when it has none, to `findings.looked_at`. That
ground only grows, so the quarter an edit may take away is spent over the
finding's life, not per edit.

- `grow` adds the shape or point to `looked_at`. `review.put_observation`
  calls it when an answer is given.
- `check` refuses an edit that leaves a looked-at point, or more than a
  quarter of the length of the looked-at lines, further than
  `LOOKED_AT_MAX_MOVE_M` from the finding's new shape, or from its new point
  when it would have no shape. `shape_edits.change_shape` calls it, and so does
  a move of a finding with no shape.
- `seed` fills `looked_at` for a finding answered before it existed, from
  the shape as stored, and `backfill` does so for every such finding.
- `refresh_added` stores how much of the shape lies further than
  `LOOKED_AT_MAX_MOVE_M` from `looked_at`, as `added_since_looked_m`, and
  the view that frames it, as `added_view`. `look_at_new_part` and the
  page come from them. It is measured from the ground, not from the kind of
  each change, so a nudged end with 20 km more counts, and an extension
  later cut away doesn't.

Distances are measured on the grid under what was looked at, where a metre
is a metre to well under one part in a thousand across the British Isles.

`looked_at` is shape. It goes only to someone who sees the finding exactly
and may change it (`sensitivity.visible_shape`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import numpy as np
import shapely
from geoalchemy2.shape import to_shape
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import ValidationFailedError
from fieldclub.models import Finding, Observation
from fieldclub.models.common import to_db_geometry
from fieldclub.services import geo, shapes

logger = logging.getLogger(__name__)

# How close what was looked at must stay to the new shape, and how much of
# the length of its lines must stay that close. The owner agreed these figures.
LOOKED_AT_MAX_MOVE_M = 250
LOOKED_AT_MIN_KEPT = 0.75
# Both shapes are simplified this much, in metres, before they are compared.
# It is small beside `LOOKED_AT_MAX_MOVE_M`, and saves buffering every vertex
# of a 600 km line.
_COMPARE_TOLERANCE_M = 5.0
# Segments in a quarter circle of the buffer: about 5 m from a true circle at 250 m.
_BUFFER_QUAD_SEGS = 4
# What a second look adds is simplified this much, in metres, which is far
# inside `LOOKED_AT_MAX_MOVE_M`. A 50,000-vertex line would otherwise be
# stored, sent to the finder and buffered on each edit, once for each
# revision someone looked at.
LOOKED_AT_SIMPLIFY_M = 5.0
# The most vertices `looked_at` keeps. Past it, the whole is simplified at
# twice the tolerance, and again, until it fits. About 80 KB of geometry.
LOOKED_AT_MAX_VERTICES = 5_000
# Past this tolerance the simplification would blur the 250 m rule itself.
_SIMPLIFY_MAX_M = LOOKED_AT_MAX_MOVE_M / 4


class LookedAtMovedError(ValidationFailedError):
    code = "looked_at_moved"


def _moved(kept: float | None) -> LookedAtMovedError:
    within = f"within {LOOKED_AT_MAX_MOVE_M} m"
    if kept is None:
        said = f"A point others gave second looks on would end up more than {LOOKED_AT_MAX_MOVE_M} m away."
    else:
        said = f"Only {kept:.0%} of what others gave second looks on would stay {within}."
    return LookedAtMovedError(
        f"{said} At least three-quarters of it has to stay {within}. "
        "To start afresh somewhere else, withdraw the finding and mark it again."
    )


def _parts(geometry: BaseGeometry) -> Iterator[BaseGeometry]:
    """The single points and lines in a geometry, however it is nested."""
    for part in shapely.get_parts(geometry):
        if isinstance(part, Point | LineString):
            yield part
        else:
            yield from _parts(part)


def ground(finding: Finding) -> BaseGeometry:
    """What a second look given now is given on: the shape, an area as its edge, or the point."""
    if finding.outline is None:
        return to_shape(finding.location)
    shape = to_shape(finding.outline)
    return shape.boundary if shape.geom_type in ("Polygon", "MultiPolygon") else shape


def _simplified(geometry: BaseGeometry, metres: float) -> BaseGeometry:
    """`geometry` simplified to within `metres`, in a plane scaled for its latitude, never emptied."""
    assert not geometry.is_empty, "an empty geometry is never simplified"
    k = geo.lon_scale(geometry.representative_point().y)
    scale = np.array([k, 1.0])
    flat = shapely.transform(geometry, lambda xy: xy * scale)
    simple = flat.simplify(metres / geo.METRES_PER_DEGREE, preserve_topology=True)
    result = shapely.transform(simple, lambda xy: np.round(xy / scale, shapes.DECIMALS))
    assert not result.is_empty, "simplifying never empties what was looked at"
    return result


def grown(before: BaseGeometry | None, now: BaseGeometry) -> BaseGeometry:
    """`before` with `now` added: `now` simplified to `LOOKED_AT_SIMPLIFY_M`, and the whole kept small.

    When the union passes `LOOKED_AT_MAX_VERTICES`, it is simplified at
    twice the tolerance, and again, until it fits. Empty geometries are
    refused before any other test: an empty ring crashes GEOS
    (libgeos/geos#1604).
    """
    assert not now.is_empty, "a second look is given on something, never on an empty shape"
    assert before is None or not before.is_empty, "what was looked at is never empty"
    added = _simplified(now, LOOKED_AT_SIMPLIFY_M)
    whole = added if before is None else shapely.union(before, added)
    if whole.geom_type == "MultiLineString":
        # The union cuts lines where they meet. Join the pieces again, so fewer stay separate.
        # Only lines: merging anything with a point in it drops the point.
        whole = shapely.line_merge(whole)
    assert not whole.is_empty, "what was looked at only grows"
    tolerance = LOOKED_AT_SIMPLIFY_M
    while shapely.get_num_coordinates(whole) > LOOKED_AT_MAX_VERTICES and tolerance < _SIMPLIFY_MAX_M:
        tolerance = min(2 * tolerance, _SIMPLIFY_MAX_M)
        whole = _simplified(whole, tolerance)
    if shapely.get_num_coordinates(whole) > LOOKED_AT_MAX_VERTICES:
        # Only thousands of separate pieces, each answered, could leave it this big.
        logger.error(
            "What was looked at keeps %d vertices at %.0f m", shapely.get_num_coordinates(whole), tolerance
        )
    return whole


def grow(db: Session, finding: Finding, observation: Observation) -> None:
    """Add what `observation`, just given, was given on to the finding's `looked_at`. Hold the lock.

    A shape is fixed by its revision, so when an earlier answer saw this
    revision its shape is in `looked_at` already. A point can move without a
    new revision, so it is always added.
    """
    assert observation.shape_revision == finding.shape_revision, "the answer records the revision it saw"
    seen_before = db.scalar(
        select(func.count())
        .select_from(Observation)
        .where(
            Observation.finding_id == finding.id,
            Observation.id != observation.id,
            Observation.shape_revision == finding.shape_revision,
        )
    )
    if finding.outline is not None and finding.looked_at is not None and seen_before:
        return
    now = ground(finding)
    assert not now.is_empty, f"finding {finding.public_id} has an empty shape"
    before = to_shape(finding.looked_at) if finding.looked_at is not None else None
    finding.looked_at = to_db_geometry(grown(before, now))
    refresh_added(finding)


def has_standing_look(db: Session, finding: Finding) -> bool:
    """Whether anyone's second look on the finding stands, not taken back."""
    return bool(
        db.scalar(
            select(
                select(Observation.id)
                .where(Observation.finding_id == finding.id, Observation.withdrawn_at.is_(None))
                .exists()
            )
        )
    )


def seed(db: Session, finding: Finding) -> bool:
    """Fill `looked_at` for a finding answered before it existed, and say whether it is set. Hold the lock.

    A second look given before the deploy that brought `looked_at`, or on a
    machine still running the old version during it, left it NULL. Its
    ground is the finding's shape as stored now, before any edit, or its
    point when it has no shape: the best record there is of what was seen.
    A finding whose every second look was taken back has nothing to keep.
    """
    if finding.looked_at is not None:
        return True
    if not has_standing_look(db, finding):
        return False
    now = ground(finding)
    assert not now.is_empty, f"finding {finding.public_id} has an empty shape"
    finding.looked_at = to_db_geometry(grown(None, now))
    return True


# Findings seeded at a time, each batch in its own transaction.
BACKFILL_BATCH = 200


def backfill(db: Session, *, batch: int = BACKFILL_BATCH) -> int:
    """`seed` every finding answered before `looked_at` existed. Commits each batch, and says how many.

    Each finding is locked before it is seeded, so an edit or an answer
    committed meanwhile is seen, and a second run changes nothing.
    """
    assert batch > 0, "a batch holds a finding at least"
    standing = (
        select(Observation.id)
        .where(Observation.finding_id == Finding.id, Observation.withdrawn_at.is_(None))
        .exists()
    )
    seeded, after = 0, 0
    while ids := db.scalars(
        select(Finding.id)
        .where(Finding.id > after, Finding.looked_at.is_(None), standing)
        .order_by(Finding.id)
        .limit(batch)
    ).all():
        for finding_id in ids:
            finding = db.scalars(
                select(Finding)
                .where(Finding.id == finding_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one()
            if finding.looked_at is None and seed(db, finding):
                refresh_added(finding)
                seeded += 1
        db.commit()
        after = ids[-1]
    return seeded


def _on_grid(geometry: BaseGeometry, to_grid: Transformer) -> BaseGeometry:
    def project(xy: np.ndarray) -> np.ndarray:
        x, y = to_grid.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geometry, project)


def check(db: Session, finding: Finding, target: BaseGeometry) -> None:
    """Refuse an edit whose shape, or point when it has none, is `target`, if too little of `looked_at` stays.

    Call it before the edit is applied, under the lock. Every looked-at
    point, and at least `LOOKED_AT_MIN_KEPT` of the length of the looked-at
    lines, must lie within `LOOKED_AT_MAX_MOVE_M` of `target`. An area
    counts as all of its inside. Once `looked_at` is set it binds every
    later change, even after every answer is taken back, because it never
    shrinks. Nothing is checked while `looked_at` is null and no second look
    stands. A finding answered before `looked_at` existed is seeded first
    (`seed`), so its answers hold it too.
    """
    if not seed(db, finding):
        return
    assert finding.looked_at is not None, "a seeded finding has looked-at ground"
    looked_at = to_shape(finding.looked_at)
    assert not looked_at.is_empty, f"finding {finding.public_id} has looked at nothing"
    assert not target.is_empty, "an edit leaves a shape or a point"
    system = gridref.grid_system(*looked_at.representative_point().coords[0])
    to_grid = gridref.transformer(4326, gridref.EPSG[system])
    reach = _on_grid(target, to_grid).simplify(_COMPARE_TOLERANCE_M)
    parts = list(_parts(_on_grid(looked_at, to_grid)))
    if any(reach.distance(part) > LOOKED_AT_MAX_MOVE_M for part in parts if isinstance(part, Point)):
        raise _moved(None)
    lines = MultiLineString([part for part in parts if isinstance(part, LineString)])
    if lines.is_empty:
        return
    lines = lines.simplify(_COMPARE_TOLERANCE_M)
    assert lines.length > 0, "a looked-at line has length"
    near = reach.buffer(LOOKED_AT_MAX_MOVE_M, quad_segs=_BUFFER_QUAD_SEGS)
    kept = lines.intersection(near).length / lines.length
    if kept < LOOKED_AT_MIN_KEPT:
        raise _moved(kept)


# Less than this beyond the looked-at ground is the buffer's polygon edge, not ground anyone added.
_ADDED_MIN_M = 2 * _COMPARE_TOLERANCE_M


def _beyond(finding: Finding) -> tuple[float, tuple[float, float, float, float]] | None:
    """The length and bounds of the shape lying further than `LOOKED_AT_MAX_MOVE_M` from `looked_at`.

    The shape is a line, or an area's edge. None when nothing lies beyond.
    """
    if finding.looked_at is None or finding.outline is None:
        return None
    looked_at = to_shape(finding.looked_at)
    shape = to_shape(finding.outline)
    assert not looked_at.is_empty, f"finding {finding.public_id} has looked at nothing"
    assert not shape.is_empty, f"finding {finding.public_id} has an empty shape"
    edge = shape.boundary if shape.geom_type in ("Polygon", "MultiPolygon") else shape
    system = gridref.grid_system(*looked_at.representative_point().coords[0])
    to_grid = gridref.transformer(4326, gridref.EPSG[system])
    reach = _on_grid(looked_at, to_grid).buffer(LOOKED_AT_MAX_MOVE_M, quad_segs=_BUFFER_QUAD_SEGS)
    beyond = _on_grid(edge, to_grid).simplify(_COMPARE_TOLERANCE_M).difference(reach)
    if beyond.is_empty or beyond.length < _ADDED_MIN_M:
        return None
    back = _on_grid(beyond, gridref.transformer(gridref.EPSG[system], 4326))
    return float(beyond.length), back.bounds


def refresh_added(finding: Finding) -> bool:
    """Store `added_since_looked_m` and `added_view` from the shape and `looked_at`, and say if they changed.

    Call it whenever either changes: after a change of shape and after a
    second look grows `looked_at`.
    """
    found = _beyond(finding)
    length, view = (None, None) if found is None else (round(found[0], 1), shapes.view_of(found[1]))
    changed = (length, view) != (finding.added_since_looked_m, finding.added_view)
    finding.added_since_looked_m = length
    finding.added_view = view
    return changed
