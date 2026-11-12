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
  when it would have no shape. `findings.change_shape` calls it, and so does
  a move of a finding with no shape.
- `new_part` is what extensions added since the newest standing second look:
  its length, which `look_at_new_part` and the page's
  `added_since_looked_m` come from, and the view that frames the newest.

Distances are measured on the grid under what was looked at, where a metre
is a metre to well under one part in a thousand across the British Isles.

`looked_at` is shape. It goes only to someone who sees the finding exactly
and may change it (`sensitivity.visible_shape`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

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
from fieldclub.models import Finding, FindingShapeChange, Observation
from fieldclub.models.common import to_db_geometry
from fieldclub.vocab import ShapeChangeKind

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
    finding.looked_at = to_db_geometry(now if before is None else shapely.union(before, now))


def _on_grid(geometry: BaseGeometry, to_grid: Transformer) -> BaseGeometry:
    def project(xy: np.ndarray) -> np.ndarray:
        x, y = to_grid.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geometry, project)


def check(finding: Finding, target: BaseGeometry) -> None:
    """Refuse an edit whose shape, or point when it has none, is `target`, if too little of `looked_at` stays.

    Every looked-at point, and at least `LOOKED_AT_MIN_KEPT` of the length of
    the looked-at lines, must lie within `LOOKED_AT_MAX_MOVE_M` of `target`.
    An area counts as all of its inside. Nothing is checked before the first
    second look.
    """
    if finding.looked_at is None:
        return
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


@dataclass(frozen=True)
class NewPart:
    """What extensions added to a line since the newest standing second look."""

    length_m: float
    # The centre and zoom that frame what the newest of them added (`shapes.added_view`).
    view: dict[str, Any] | None


def newest_look(db: Session, finding: Finding) -> int | None:
    """The `shape_revision` of the newest standing second look, or None when there is none.

    An answer given before answers recorded a revision was given before any
    change to a shape, so it counts as revision 0.
    """
    return db.scalar(
        select(func.max(func.coalesce(Observation.shape_revision, 0))).where(
            Observation.finding_id == finding.id, Observation.withdrawn_at.is_(None)
        )
    )


def new_part(db: Session, finding: Finding) -> NewPart | None:
    """What extensions added since the newest standing second look, or None when no such look is older."""
    since = newest_look(db, finding)
    if since is None or since >= finding.shape_revision:
        return None
    extensions = db.execute(
        select(FindingShapeChange.added_length_m, FindingShapeChange.added_view)
        .where(
            FindingShapeChange.finding_id == finding.id,
            FindingShapeChange.revision > since,
            FindingShapeChange.kind == ShapeChangeKind.EXTENDED.value,
        )
        .order_by(FindingShapeChange.revision)
    ).all()
    if not extensions:
        return None
    return NewPart(
        length_m=sum(length or 0.0 for length, _ in extensions),
        view=extensions[-1].added_view,
    )
