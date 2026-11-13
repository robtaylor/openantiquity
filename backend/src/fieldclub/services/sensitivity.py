"""Location sensitivity: what position a viewer may see for a finding (Decision 0005).

A finding is `open` or `protected`. `visible_location` is the only place
that decides what a viewer sees, and every route that returns a finding goes
through it, exports included:

| Viewer                             | open  | protected   |
|------------------------------------|-------|-------------|
| Signed out                         | exact | 1 km square |
| Member                             | exact | exact       |
| Finder, trusted, expert, moderator | exact | exact       |

Decision 0032 dropped the `restricted` level: no request can set it. The
code here still handles a finding stored at it, shown exactly only to the
table's last row and as its square to everyone else, until a later sweep
takes the level out.

Downloads are stricter (`downloads_exact`): a member's download carries a
protected finding at its square. Admins count as moderators. A banned or deleted account is treated as signed
out, whatever its role. A generalised finding is shown at the centre of its
1 km grid square, with `obscured=True` and no outline.

`findings.location_public` holds the position anyone may see: the exact point
for an open finding, the square's centre otherwise. The ORM writes it on every
insert, and on every update that changes the location or the level (see
`models.findings`). Queries on behalf of signed-out visitors filter and sort
on that column only.

Things callers must not do:

- Don't return `finding.location`, `finding.outline` or `finding.grid_ref`
  directly. Use the fields of `VisibleLocation`. The same goes for
  `finding.nation`, which comes from the exact position: use `visible_nation`.
  A finding's line or shape (`path`, `outline_mid`, `outline_low`, its kind,
  length and changes) is shape too: serve it through `visible_shape`, or for
  the map `services.shape_edits.map_shapes`, and match a box against it only
  through `visible_match_clause`.
- Don't filter or sort by `findings.location` for someone who can't see it.
  A bounding-box search over exact positions lets anyone find a protected
  site by narrowing the box. Use `location_public`.
- Don't change `sensitivity` or `location` with a Core `UPDATE`. It skips the
  ORM and leaves `location_public` behind. Use `change_sensitivity`, or set
  the attribute on a loaded `Finding`. A trigger in `models/extras.sql` refuses
  an open finding whose public position differs from its location, and a change
  from open to a higher level that leaves the public position exact.
- Don't serve free text about a finding as it was typed. Pass it through
  `visible_text`, which hides positions written in it from anyone who
  doesn't see the exact position. A search over titles matches
  `title_public` for them.
- Don't serve a web address someone attached to a finding as it was typed.
  Pass it through `visible_url`, which gives it only to those who see the
  exact position: a map link is a position, and a page's address can carry
  one in any form.
- Don't serve what people wrote or drew beside a finding, such as an
  investigation's notes, saved map views, height profiles and area, as it
  was stored. Build a `PositionGuard` for the findings it holds or has held,
  the findings near what was drawn in it (`hidden_near`), and the reader,
  and pass each through it.
- Don't copy an exact position into another table, a cache or a tile, even
  while the finding is open. Store `square_centre(finding)`, which is the
  same at every level, and resolve the position to show through
  `visible_location` when it is read. `activity.location` works this way.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import shapely
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from sqlalchemy import BigInteger, ColumnElement, and_, cast, false, func, not_, or_, select, true
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, aliased, undefer

from fieldclub import gridref
from fieldclub.errors import DataIntegrityError, ForbiddenError
from fieldclub.models import Finding, FindingShapeChange, User
from fieldclub.models.common import db_point, point_lon_lat
from fieldclub.services import geo, shapes, text_positions
from fieldclub.vocab import (
    EXACT_LOCATION_ROLES,
    MODERATOR_ROLES,
    PROTECTED_CLASSES,
    TRUSTED_ROLES,
    FeatureClass,
    Role,
    Sensitivity,
    ShapeKind,
    sensitivity_rank,
)

logger = logging.getLogger(__name__)

# Four digits of grid reference name a 1 km square.
SQUARE_DIGITS = 4

# Who may move a finding's level up, and who may move it down. The finder may
# also raise their own finding. Experts and admins count as trusted, and
# admins as moderators.
MAY_RAISE_ROLES: frozenset[Role] = TRUSTED_ROLES
MAY_LOWER_ROLES: frozenset[Role] = MODERATOR_ROLES


class SensitivityChangeForbiddenError(ForbiddenError):
    code = "sensitivity_change_forbidden"
    message = (
        "Only the finder, a trusted member or a moderator can raise a level, "
        "and only a moderator can lower one."
    )


class LowerThroughModerationError(ForbiddenError):
    code = "lower_through_moderation"
    message = "A moderator lowers a level from the moderation tools, with a reason for the log."


@dataclass(frozen=True)
class VisibleLocation:
    """A finding's position as one particular viewer may see it."""

    lon: float
    lat: float
    # True when the position has been coarsened to the middle of a 1 km square.
    obscured: bool
    # `SU 1025 6996` when exact, the 1 km reference `SU 10 69` when obscured.
    grid_ref: str | None
    # The compact 1 km square, such as `SU1069`, when obscured. The frontend
    # draws this square in place of a marker.
    square: str | None
    # `line` or `area`. Always None when obscured, and for an outline saved
    # before kinds were until the backfill fills it. The shape itself is
    # `visible_shape`'s to give.
    shape_kind: ShapeKind | None = None
    # The same square as a grid reference, when obscured.
    square_ref: gridref.GridRef | None = field(default=None, compare=False, repr=False)

    def square_polygon(self) -> Polygon | None:
        """The obscuring 1 km square in WGS84, or None when the position is exact."""
        return self.square_ref.polygon() if self.square_ref is not None else None


def _exact_point(finding: Finding) -> tuple[float, float]:
    return point_lon_lat(finding.location, f"finding {finding.public_id}")


def active_viewer(viewer: User | None) -> User | None:
    """The viewer, or None when they count as signed out: a banned or deleted account does."""
    return viewer if viewer is not None and viewer.is_active else None


def sees_exact(finding: Finding, viewer: User | None) -> bool:
    """Whether `viewer` sees the exact position of `finding`. `viewer` is None for the public.

    This is the viewer table. Everything else in this module follows from it.
    """
    level = Sensitivity(finding.sensitivity)
    if level is Sensitivity.OPEN:
        return True
    active = active_viewer(viewer)
    if active is None:
        return False
    if active.has_id(finding.author_id) or Role(active.role) in EXACT_LOCATION_ROLES:
        return True
    return level is Sensitivity.PROTECTED


def downloads_exact(finding: Finding, viewer: User | None) -> bool:
    """Whether a download for `viewer` may carry the exact position of `finding`.

    Stricter than `sees_exact` (Decision 0005, rule 8): only the finder and
    trusted people (experts, moderators and admins among them) download a
    protected or restricted finding's exact position. Any member sees a
    protected one exactly on its page.
    """
    if Sensitivity(finding.sensitivity) is Sensitivity.OPEN:
        return True
    active = active_viewer(viewer)
    if active is None:
        return False
    return active.has_id(finding.author_id) or Role(active.role) in TRUSTED_ROLES


def sees_exact_clause(viewer: User | None) -> ColumnElement[bool] | bool:
    """SQL for `sees_exact(finding, viewer)`: where the viewer sees the exact position.

    A plain True when a trusted viewer sees every position exactly. It has to
    agree with `sees_exact` row for row, and a test checks every viewer
    against every level.
    """
    active = active_viewer(viewer)
    if active is None:
        return Finding.sensitivity == Sensitivity.OPEN.value
    if Role(active.role) in EXACT_LOCATION_ROLES:
        return True
    return or_(
        Finding.sensitivity.in_([Sensitivity.OPEN.value, Sensitivity.PROTECTED.value]),
        Finding.author_id == active.id,
    )


def as_sql(clause: ColumnElement[bool] | bool) -> ColumnElement[bool]:
    if isinstance(clause, bool):
        return true() if clause else false()
    return clause


def visible_match_clause(viewer: User | None, area: ColumnElement[Any]) -> ColumnElement[bool]:
    """Findings this viewer may find in `area`: by the position they may see, or by the shape.

    A shape counts only where the viewer sees the finding exactly. Matched by
    its shape, a protected line would tell anyone else that it passes through
    the box.

    The findings whose shape crosses the box are found first, through the
    index on `outline`, as an array the outer query looks ids up in. Written
    as one more spatial test in the `OR`, the planner would sometimes give up
    the spatial indexes for a scan in date order. An outline saved before
    `shape_kind` existed matches by its point until the backfill fills it.
    """
    shaped = aliased(Finding)
    crossing = (
        select(func.array_agg(shaped.id))
        .where(shaped.shape_kind.is_not(None), func.ST_Intersects(shaped.outline, area))
        .scalar_subquery()
    )
    # Wrapped, so `= ANY` reads it as an array, not as a subquery of arrays. Empty when none cross.
    ids = func.coalesce(crossing, cast(postgresql.array([]), postgresql.ARRAY(BigInteger)))
    by_shape = and_(as_sql(sees_exact_clause(viewer)), Finding.id == func.any(ids))
    return or_(visible_position_clause(viewer, area), by_shape)


def visible_position_clause(viewer: User | None, area: ColumnElement[Any]) -> ColumnElement[bool]:
    """Findings whose position, as this viewer may see it, lies in `area`.

    A signed-out visitor is matched on `location_public` alone, which is the
    exact point for an open finding. Otherwise each branch tests one indexed
    column, so the planner can use both spatial indexes.
    """
    in_public = func.ST_Intersects(Finding.location_public, area)
    if active_viewer(viewer) is None:
        return in_public
    exact = sees_exact_clause(viewer)
    in_exact = func.ST_Intersects(Finding.location, area)
    if exact is True:
        return in_exact
    assert not isinstance(exact, bool), "only a trusted viewer sees every position exactly"
    return or_(and_(exact, in_exact), and_(not_(exact), in_public))


def _square(lon: float, lat: float, public_id: str | None) -> gridref.GridRef:
    try:
        return gridref.gridref_at(lon, lat, SQUARE_DIGITS)
    except gridref.GridRefError as exc:
        # Failing here is deliberate. Falling back to the exact position would
        # publish exactly what the level is there to protect.
        raise DataIntegrityError(
            f"Finding {public_id or '(unsaved)'} is generalised but lies outside the British and Irish grids."
        ) from exc


def public_point(
    lon: float, lat: float, level: Sensitivity | str, public_id: str | None = None
) -> tuple[float, float]:
    """The position anyone may see: exact when open, the 1 km square's centre otherwise."""
    if Sensitivity(level) is Sensitivity.OPEN:
        return lon, lat
    return _square(lon, lat, public_id).centre()


def refresh_location_public(finding: Finding) -> None:
    """Set `finding.location_public` from its location and level. The ORM calls this on save."""
    lon, lat = _exact_point(finding)
    finding.location_public = db_point(*public_point(lon, lat, finding.sensitivity, finding.public_id))


def visible_location(finding: Finding, viewer: User | None) -> VisibleLocation:
    """The position of `finding` that `viewer` may see. `viewer` is None for the public."""
    lon, lat = _exact_point(finding)
    if sees_exact(finding, viewer):
        return VisibleLocation(
            lon=lon,
            lat=lat,
            obscured=False,
            grid_ref=finding.grid_ref,
            square=None,
            shape_kind=ShapeKind(finding.shape_kind) if finding.shape_kind is not None else None,
        )
    square = _square(lon, lat, finding.public_id)
    lon, lat = square.centre()
    return VisibleLocation(
        lon=lon,
        lat=lat,
        obscured=True,
        grid_ref=square.format(),
        square=square.format(compact=True),
        square_ref=square,
    )


def _shape_kind(finding: Finding, outline: BaseGeometry | None) -> ShapeKind | None:
    """The stored kind, or for an outline saved before kinds were, the kind of `outline`."""
    if finding.shape_kind is not None:
        return ShapeKind(finding.shape_kind)
    return shapes.kind_of(outline) if outline is not None else None


@dataclass(frozen=True)
class VisibleShapeChange:
    # A `ShapeChangeKind`, or `changed` for a viewer who sees only the square.
    kind: str
    on: date
    added_length_m: float | None = None
    added_view: dict[str, Any] | None = None


@dataclass(frozen=True)
class VisibleShape:
    """What a viewer may know of a finding's shape and its changes.

    Someone who sees only the square learns that the shape changed and on
    which days, and nothing of its size, kind or place. Everything else is
    None for them.
    """

    changes: tuple[VisibleShapeChange, ...]
    kind: ShapeKind | None = None
    length_m: float | None = None
    revision: int | None = None
    # West, south, east, north of the shape.
    extent: tuple[float, float, float, float] | None = None
    # The shape simplified for the page (`outline_mid`), so a long road costs a
    # phone little, or the whole of it for a download.
    outline: BaseGeometry | None = None
    # The tapped points, as `shapes.Path.to_json` writes them.
    path: dict[str, Any] | None = None
    # How much of the shape lies beyond what second looks were given on, and
    # a centre and zoom that frame it (`looked_at.refresh_added`).
    added_since_looked_m: float | None = None
    added_view: dict[str, Any] | None = None
    # What second looks were given on, for someone who may change the shape.
    looked_at: BaseGeometry | None = None


def visible_shape(
    finding: Finding,
    viewer: User | None,
    changes: Sequence[FindingShapeChange],
    *,
    may_change: bool = False,
    whole: bool = False,
) -> VisibleShape:
    """The shape of `finding` and its `changes`, oldest first, as `viewer` may know them.

    An outline saved before paths is served with the all-corner path it is
    (`shapes.stored_path`), and the kind of its geometry. `may_change` is whether the viewer may
    change the finding (`actions.edit`): only then do they get `looked_at`,
    to draw under the path while they change it. `whole` gives the whole shape
    as `outline`, for a download, in place of the page's simplified one: pass
    a download's reader only when `downloads_exact`, and None otherwise.
    """
    assert all(change.finding_id == finding.id for change in changes), "a change of another finding"
    if not sees_exact(finding, viewer):
        return VisibleShape(
            changes=tuple(
                VisibleShapeChange(kind="changed", on=change.created_at.date()) for change in changes
            )
        )
    full = to_shape(finding.outline) if finding.outline is not None else None
    shown = to_shape(finding.outline_mid) if not whole and finding.outline_mid is not None else full
    path = shapes.stored_path(finding.path, full)
    return VisibleShape(
        changes=tuple(
            VisibleShapeChange(
                kind=change.kind,
                on=change.created_at.date(),
                added_length_m=change.added_length_m,
                added_view=change.added_view,
            )
            for change in changes
        ),
        kind=_shape_kind(finding, full),
        length_m=finding.shape_length_m,
        revision=finding.shape_revision,
        extent=full.bounds if full is not None else None,
        outline=shown,
        path=path.to_json() if path is not None else None,
        added_since_looked_m=finding.added_since_looked_m,
        added_view=finding.added_view,
        looked_at=to_shape(finding.looked_at) if may_change and finding.looked_at is not None else None,
    )


def visible_view_state(finding: Finding, viewer: User | None) -> dict[str, Any]:
    """The view the finder saved, as `viewer` may have it: with its zoom only if they see it exactly.

    A finder zooms out to see a long line or a large area whole, so a low
    zoom would hint at the size of a finding the viewer sees only as a
    square. Every hidden finding loses its zoom alike, point or shape, so
    its absence says nothing either.
    """
    stored = dict(finding.view_state or {})
    if not sees_exact(finding, viewer):
        stored.pop("zoom", None)
    return stored


def visible_text(finding: Finding | None, viewer: User | None, text: str | None) -> str | None:
    """Free text about `finding` as `viewer` may read it: with every position in it hidden,
    unless they see the exact position. `finding` is None for one this viewer isn't shown
    (hidden, withdrawn or gone), whose text keeps its positions from everyone.

    A title, description, note, comment, evidence or mention is typed by a
    person, who can write a grid reference, coordinates or a three-word
    address into it (`services.text_positions`). Text written while a
    finding was open, before it was raised, is hidden the same way. Pass the
    viewer a download is for as `exports.export_location` does, so a download
    hides what its position hides.
    """
    if text is None or (finding is not None and sees_exact(finding, viewer)):
        return text
    return text_positions.redact(text)


def visible_url(
    finding: Finding | None, viewer: User | None, url: str | None, *, rebuilt: str | None = None
) -> str | None:
    """A web address someone attached to `finding`, as `viewer` may follow it.

    As stored for anyone who sees the exact position. Anyone else gets
    `rebuilt`, an address made again from an identifier alone (a video's or
    a DOI's, `unfurl.IDENTIFIER_PROVIDERS`), or nothing. An address is the
    member's own text and can say where the finding is in any form, a map
    link most of all, so it isn't judged by `text_positions` alone. `finding`
    is None for one this viewer isn't shown, whose addresses go to nobody.
    """
    if url is None or (finding is not None and sees_exact(finding, viewer)):
        return url
    # An identifier can look like a position by chance (a video id such as
    # `SU123456abc`), and then even the rebuilt address isn't given.
    return rebuilt if rebuilt is not None and not text_positions.holds_position(rebuilt) else None


def refresh_title_public(finding: Finding) -> None:
    """Set `finding.title_public`, the title a search matches for those who don't see it exactly."""
    finding.title_public = text_positions.redact(finding.title)


def visible_nation(db: Session, finding: Finding, viewer: User | None) -> str | None:
    """The nation of `finding` that `viewer` may know: from the 1 km square, when that is all they see.

    `finding.nation` comes from the exact position. For a square that meets
    two nations it would say which side of the border the finding is on, so
    a viewer who sees only the square is told the square's nation instead,
    which is None when it meets two.
    """
    seen = visible_location(finding, viewer)
    square = seen.square_polygon()
    if square is None:
        return finding.nation
    return geo.nation_of(db, square)


def square_centre(finding: Finding) -> tuple[float, float] | None:
    """Longitude and latitude of the centre of the finding's 1 km grid square.

    This is the only position that is safe to keep a copy of, because it is
    what the public sees of a generalised finding and so stays true whatever
    the finding's level becomes. It is None for a finding outside the British
    and Irish grids, which has no square: keep no position at all.
    """
    lon, lat = _exact_point(finding)
    try:
        return gridref.gridref_at(lon, lat, SQUARE_DIGITS).centre()
    except gridref.GridRefError:
        logger.debug("Finding %s is outside both grids, so it has no square", finding.public_id)
        return None


def default_sensitivity(feature_class: FeatureClass | str) -> Sensitivity:
    """The level a new finding of this class starts at."""
    return Sensitivity.PROTECTED if FeatureClass(feature_class) in PROTECTED_CLASSES else Sensitivity.OPEN


def starting_sensitivity(
    feature_class: FeatureClass | str, requested: Sensitivity | str | None, actor: User | None
) -> Sensitivity:
    """The level a new finding is saved at.

    It is the higher of the class default and `requested`. A request for a
    lower level than the class default is honoured only from a moderator,
    the same rule as `may_change_sensitivity`. Without this, a member could
    save a round barrow as open. Create services call this, then save.
    """
    floor = default_sensitivity(feature_class)
    if requested is None:
        return floor
    wanted = Sensitivity(requested)
    if sensitivity_rank(wanted) >= sensitivity_rank(floor):
        return wanted
    active = active_viewer(actor)
    if active is not None and Role(active.role) in MAY_LOWER_ROLES:
        return wanted
    return floor


def level_after_class_change(
    current: Sensitivity | str, old_class: FeatureClass | str, new_class: FeatureClass | str
) -> Sensitivity:
    """The level a finding takes when its feature class changes.

    A change to a class with a higher default raises the level to that
    default if it is below it. It never lowers a level, and a change between
    classes with the same default leaves the level alone, so a moderator's
    decision to lower one finding isn't undone by an edit. The ORM applies this
    on save (see `models.findings`).
    """
    level = Sensitivity(current)
    old_default, new_default = default_sensitivity(old_class), default_sensitivity(new_class)
    if sensitivity_rank(new_default) > max(sensitivity_rank(old_default), sensitivity_rank(level)):
        return new_default
    return level


def may_change_sensitivity(finding: Finding, actor: User | None, level: Sensitivity | str) -> bool:
    """Whether `actor` may set `finding` to `level`.

    The finder, a trusted member or a moderator may raise a level. Only a
    moderator may lower one. Setting the level it already has is allowed for
    anyone who may raise it.
    """
    active = active_viewer(actor)
    if active is None:
        return False
    role = Role(active.role)
    if sensitivity_rank(level) < sensitivity_rank(finding.sensitivity):
        return role in MAY_LOWER_ROLES
    return role in MAY_RAISE_ROLES or active.has_id(finding.author_id)


def change_sensitivity(db: Session, finding: Finding, actor: User, level: Sensitivity | str) -> Finding:
    """Set a finding's level and its public position, or raise `SensitivityChangeForbiddenError`.

    The caller commits.
    """
    level = Sensitivity(level)
    if not may_change_sensitivity(finding, actor, level):
        raise SensitivityChangeForbiddenError()
    if finding.sensitivity != level.value:
        # The before_update listener in `models.findings` moves the public position on this flush.
        finding.sensitivity = level.value
        db.flush()
    return finding


def raise_sensitivity(db: Session, finding: Finding, actor: User, level: Sensitivity | str) -> Finding:
    """Raise a finding's level, or keep it: what `PUT /findings/{public_id}/sensitivity` does.

    Lowering a level is a moderator's decision, so it goes through
    `services.moderation.set_sensitivity`, which logs it with a reason. A
    moderator who asks for a lower level here gets `LowerThroughModerationError`,
    anyone else `SensitivityChangeForbiddenError`. The caller commits.
    """
    level = Sensitivity(level)
    active = active_viewer(actor)
    if (
        active is not None
        and Role(active.role) in MAY_LOWER_ROLES
        and sensitivity_rank(level) < sensitivity_rank(finding.sensitivity)
    ):
        raise LowerThroughModerationError()
    return change_sensitivity(db, finding, actor, level)


# --------------------------------------------------------------------------
# What people wrote and drew beside a finding
# --------------------------------------------------------------------------

# A saved map view, a height profile or an area that comes this close to a
# finding the reader sees only as a square is held back from them, or shown
# as whole squares. A view centred within this distance at any zoom, or a
# line or an area reaching it, says where the finding is more closely than
# its square.
NEAR_HIDDEN_M = 1500.0
# How far, in degrees, a finding may be from a shape and still be within
# `NEAR_HIDDEN_M` of it, generously: a cheap first test the index can answer.
NEAR_HIDDEN_DEGREES = 0.05
# Metres in a degree of latitude, near enough for distances of a kilometre or
# two. A degree of longitude is `geo.METRES_PER_DEGREE` at the equator.
_M_PER_DEG_LAT = 110_574.0
assert NEAR_HIDDEN_DEGREES * geo.METRES_PER_DEGREE * geo.lon_scale(61.5) > NEAR_HIDDEN_M * 1.05, (
    "the first test must take in everything near, as far north as the grids go"
)
# An area more than this many squares round is shown as the bounding box of
# its squares' corners, which still holds every square whole, in place of an
# outline with a corner every kilometre.
_COVER_EDGE_MAX = 2000


def square_cover(geometry: BaseGeometry) -> Polygon | None:
    """The whole 1 km grid squares that `geometry`'s bounding box on the grid covers, in WGS84.

    The grid is the one under the shape's middle, the same grid a finding
    there is generalised on. Every square of that grid the shape touches is
    inside the result whole, and nothing else is, so set beside a finding's
    public square it never says more than the square: it holds all of it or
    none. Each kilometre along the edge is a corner of the outline, so the
    squares on the edge share their edges with it exactly. None when the
    shape is off both grids.
    """
    lon, lat = geometry.representative_point().coords[0]
    system = gridref.grid_system(lon, lat)
    to_grid = gridref.transformer(4326, gridref.EPSG[system])
    coords = shapely.get_coordinates(geometry)
    xs, ys = (np.asarray(values) for values in to_grid.transform(coords[:, 0], coords[:, 1]))
    if not (np.isfinite(xs).all() and np.isfinite(ys).all()):
        return None
    step = 1000
    west, south = math.floor(xs.min() / step), math.floor(ys.min() / step)
    east = max(math.ceil(xs.max() / step), west + 1)
    north = max(math.ceil(ys.max() / step), south + 1)
    edge = [(x, south) for x in range(west, east)]
    edge += [(east, y) for y in range(south, north)]
    edge += [(x, north) for x in range(east, west, -1)]
    edge += [(west, y) for y in range(north, south, -1)]
    to_lon_lat = gridref.transformer(gridref.EPSG[system], 4326)
    corners = np.asarray(edge, dtype=float) * step
    lons, lats = to_lon_lat.transform(corners[:, 0], corners[:, 1])
    cover = Polygon(zip(lons, lats, strict=True))
    if len(edge) > _COVER_EDGE_MAX:
        # The box round every corner on the edge still holds every square whole.
        cover = box(*cover.bounds)
    return cover if cover.is_valid and not cover.is_empty else None


def _in_metres(geometry: BaseGeometry, lon: float, lat: float) -> BaseGeometry:
    """`geometry` in metres east and north of `lon, lat`, near enough for a kilometre or two."""
    scale = np.array([geo.METRES_PER_DEGREE * geo.lon_scale(lat), _M_PER_DEG_LAT])
    origin = np.array([lon, lat])
    return shapely.transform(geometry, lambda coords: (coords - origin) * scale)


def _near_shape(geometry: BaseGeometry, shape: BaseGeometry) -> bool:
    """Whether `geometry` comes within `NEAR_HIDDEN_M` of `shape`, which may be a 600 km line.

    Only the part of `shape` round `geometry` is measured, in metres about
    the middle of `geometry`, where a degree's metres are close to true.
    """
    west, south, east, north = geometry.bounds
    piece = shapely.clip_by_rect(
        shape,
        west - NEAR_HIDDEN_DEGREES,
        south - NEAR_HIDDEN_DEGREES,
        east + NEAR_HIDDEN_DEGREES,
        north + NEAR_HIDDEN_DEGREES,
    )
    if piece.is_empty:
        return False
    lon, lat = (west + east) / 2, (south + north) / 2
    return _in_metres(geometry, lon, lat).distance(_in_metres(piece, lon, lat)) <= NEAR_HIDDEN_M


@dataclass(frozen=True)
class PositionGuard:
    """What a reader may see of what people wrote and drew beside some findings.

    `hidden` holds the exact points of the findings the reader doesn't see
    exactly (or, for a download, doesn't download exactly) that the writing
    is about: those an investigation holds or has held, and those near
    anything drawn in it. `hidden_shapes` holds the lines and areas of those
    that have one (Decision 0030). While there is one, every piece of free
    text loses the positions written in it (`text`), an address is given
    only when it is rebuilt from an identifier (`url`), a view or a line
    that comes within `NEAR_HIDDEN_M` of one's point or shape is held back
    (`near`), and an area that does is shown as the whole grid squares it
    covers (`area`). What the reader added themselves is theirs to see
    (`for_item`). Everything is left as it is for a reader who sees every
    finding exactly.
    """

    hidden: tuple[tuple[float, float], ...] = ()
    # The reader, whose own items are shown to them as they made them.
    reader_id: int | None = None
    hidden_shapes: tuple[BaseGeometry, ...] = ()

    def __post_init__(self) -> None:
        assert len(self.hidden_shapes) <= len(self.hidden), "every hidden shape is a hidden finding's"

    def for_item(self, added_by: int) -> PositionGuard:
        """The guard for an item added by `added_by`: none when the reader added it."""
        return PositionGuard() if self.reader_id is not None and self.reader_id == added_by else self

    def text(self, value: str | None) -> str | None:
        return text_positions.redact(value) if value and self.hidden else value

    def url(self, value: str | None, *, rebuilt: str | None = None) -> str | None:
        """An address as `visible_url` gives it: as stored when nothing is hidden, else only `rebuilt`."""
        if not value or not self.hidden:
            return value
        return rebuilt if rebuilt is not None and not text_positions.holds_position(rebuilt) else None

    def near(self, geometry: BaseGeometry) -> bool:
        """Whether `geometry` comes within `NEAR_HIDDEN_M` of a finding the reader sees only as a square.

        Near its point, or anywhere along its line or area.
        """
        for lon, lat in self.hidden:
            if _in_metres(geometry, lon, lat).distance(Point(0, 0)) <= NEAR_HIDDEN_M:
                return True
        return any(_near_shape(geometry, shape) for shape in self.hidden_shapes)

    def area(self, geometry: BaseGeometry | None, squares: BaseGeometry | None) -> BaseGeometry | None:
        """The area as drawn, or its `square_cover` when it comes near a hidden finding.

        None when the squares aren't on the grid each nearby finding is
        generalised on, which only a shape at the edge of both grids can be.
        """
        if geometry is None or not self.near(geometry):
            return geometry
        system = gridref.grid_system(*geometry.representative_point().coords[0])
        if squares is None or any(gridref.grid_system(lon, lat) is not system for lon, lat in self.hidden):
            return None
        return squares


def exact_clause(viewer: User | None, *, download: bool = False) -> ColumnElement[bool] | bool:
    """SQL for `sees_exact`, or for `downloads_exact` when `download`."""
    if not download:
        return sees_exact_clause(viewer)
    active = active_viewer(viewer)
    if active is None:
        return Finding.sensitivity == Sensitivity.OPEN.value
    if Role(active.role) in TRUSTED_ROLES:
        return True
    return or_(Finding.sensitivity == Sensitivity.OPEN.value, Finding.author_id == active.id)


def hidden_near(
    db: Session, viewer: User | None, shapes: Iterable[BaseGeometry], *, download: bool = False
) -> list[Finding]:
    """Findings `viewer` doesn't see exactly (or download exactly) that may lie near any of `shapes`.

    Near by their point, or by their line or area.

    A first test, generous by `NEAR_HIDDEN_DEGREES`, whatever investigation
    or none holds them: `PositionGuard.near` decides. Their shapes are
    loaded with them, since the guard measures to them.

    A finding a moderator has hidden is left out. Nobody this guard works
    for can see it at all, so holding back what is drawn near it would say
    that something is there, and how near (Decision 0032).
    """
    exact = exact_clause(viewer, download=download)
    collected = [shape for shape in shapes if not shape.is_empty]
    if exact is True or not collected:
        return []
    everything = func.ST_GeomFromText(shapely.GeometryCollection(collected).wkt, 4326)
    return list(
        db.scalars(
            select(Finding)
            .options(undefer(Finding.outline))
            .where(
                not_(as_sql(exact)),
                Finding.hidden_at.is_(None),
                or_(
                    func.ST_DWithin(Finding.location, everything, NEAR_HIDDEN_DEGREES),
                    func.ST_DWithin(Finding.outline, everything, NEAR_HIDDEN_DEGREES),
                ),
            )
        )
    )


def position_guard(
    findings: Iterable[Finding],
    viewer: User | None,
    *,
    download: bool = False,
    near: Iterable[Finding] = (),
    shapes: Iterable[BaseGeometry] = (),
) -> PositionGuard:
    """The guard for what was written beside `findings`, as `viewer` may read it or download it.

    `near` are findings from `hidden_near` for `shapes`, what was drawn: each
    counts when it is within `NEAR_HIDDEN_M` of one of them. The reader's own
    items are shown to them as made, except in a download.
    """
    exact = downloads_exact if download else sees_exact
    hidden = {finding.id: finding for finding in findings if not exact(finding, viewer)}
    drawn = shapely.GeometryCollection(list(shapes))
    for finding in near:
        if finding.id in hidden or exact(finding, viewer) or drawn.is_empty:
            continue
        if _guard_for([finding]).near(drawn):
            hidden[finding.id] = finding
    # A download keeps the stricter rule even for the reader's own items: a member's own view of a
    # protected finding is still that finding's exact position (Decision 0005, rule 8).
    active = active_viewer(viewer) if not download else None
    return _guard_for(list(hidden.values()), active.id if active is not None else None)


def _guard_for(hidden: Sequence[Finding], reader_id: int | None = None) -> PositionGuard:
    """The guard for `hidden`, findings the reader may not see exactly: their points and their shapes."""
    return PositionGuard(
        tuple(_exact_point(finding) for finding in hidden),
        reader_id,
        tuple(to_shape(finding.outline) for finding in hidden if finding.outline is not None),
    )


def near_hidden_clause(viewer: User | None, geometry: Any) -> ColumnElement[bool]:
    """SQL: whether `geometry` comes near a finding that `viewer` sees only as a square.

    The distance is a little longer than `PositionGuard.near`'s, whose metres
    are approximate, so SQL never treats as far a shape that a response
    treats as near. A finding a moderator has hidden is left out, as in
    `hidden_near`.
    """
    exact = sees_exact_clause(viewer)
    if exact is True:
        return false()

    def within(column: Any) -> ColumnElement[bool]:
        return and_(
            func.ST_DWithin(column, geometry, NEAR_HIDDEN_DEGREES),
            func.ST_DWithin(func.geography(geometry), func.geography(column), NEAR_HIDDEN_M * 1.05),
        )

    # Near its point, or anywhere along its line or area (Decision 0030).
    return (
        select(Finding.id)
        .where(
            not_(as_sql(exact)),
            Finding.hidden_at.is_(None),
            or_(within(Finding.location), within(Finding.outline)),
        )
        .exists()
    )
