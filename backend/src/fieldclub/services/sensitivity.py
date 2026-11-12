"""Location sensitivity: what position a viewer may see for a finding (Decision 0005).

A finding is `open`, `protected` or `restricted`. `visible_location` is the
only place that decides what a viewer sees, and every route that returns a
finding goes through it, exports included:

| Viewer                             | open  | protected   | restricted  |
|------------------------------------|-------|-------------|-------------|
| Signed out                         | exact | 1 km square | 1 km square |
| Member                             | exact | exact       | 1 km square |
| Finder, trusted, expert, moderator | exact | exact       | exact       |

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
  was stored. Build a `PositionGuard` for the findings it holds and the
  reader, and pass each through it.
- Don't copy an exact position into another table, a cache or a tile, even
  while the finding is open. Store `square_centre(finding)`, which is the
  same at every level, and resolve the position to show through
  `visible_location` when it is read. `activity.location` works this way.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement, and_, false, func, not_, or_, select, true
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import DataIntegrityError, ForbiddenError
from fieldclub.models import Finding, User
from fieldclub.models.common import db_point, point_lon_lat
from fieldclub.services import geo, text_positions
from fieldclub.vocab import (
    EXACT_LOCATION_ROLES,
    MODERATOR_ROLES,
    PROTECTED_CLASSES,
    TRUSTED_ROLES,
    FeatureClass,
    Role,
    Sensitivity,
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
    # The drawn outline. Always None when obscured.
    outline: BaseGeometry | None
    # `SU 1025 6996` when exact, the 1 km reference `SU 10 69` when obscured.
    grid_ref: str | None
    # The compact 1 km square, such as `SU1069`, when obscured. The frontend
    # draws this square in place of a marker.
    square: str | None
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
        outline = to_shape(finding.outline) if finding.outline is not None else None
        return VisibleLocation(
            lon=lon, lat=lat, obscured=False, outline=outline, grid_ref=finding.grid_ref, square=None
        )
    square = _square(lon, lat, finding.public_id)
    lon, lat = square.centre()
    return VisibleLocation(
        lon=lon,
        lat=lat,
        obscured=True,
        outline=None,
        grid_ref=square.format(),
        square=square.format(compact=True),
        square_ref=square,
    )


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
# finding the reader sees only as a square is held back from them, or
# coarsened. A view centred within this distance at any zoom, or a line or an
# area reaching it, says where the finding is more closely than its square.
NEAR_HIDDEN_M = 1500.0
# The grid an area near such a finding is widened to: about a kilometre each way.
AREA_GRID_LAT = 0.01
AREA_GRID_LON = 0.016
# Metres in a degree of latitude, and of longitude at the equator, near enough
# for distances of a kilometre or two.
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON = 111_320.0


def snapped_box(geometry: BaseGeometry) -> Polygon:
    """The bounding box of `geometry` widened to whole cells of the area grid.

    The box's edges are grid lines, so however a box search is narrowed it
    can't find more than the cells the shape touches. `snapped_box_sql` is
    the same in SQL.
    """
    west, south, east, north = geometry.bounds
    # Cell numbers: the first is the one the west or south edge is in, the last
    # is at least one further, so even a shape on a grid line has a whole cell.
    x0, y0 = math.floor(west / AREA_GRID_LON), math.floor(south / AREA_GRID_LAT)
    x1 = max(math.ceil(east / AREA_GRID_LON), x0 + 1)
    y1 = max(math.ceil(north / AREA_GRID_LAT), y0 + 1)
    return box(x0 * AREA_GRID_LON, y0 * AREA_GRID_LAT, x1 * AREA_GRID_LON, y1 * AREA_GRID_LAT)


def snapped_box_sql(column: Any) -> ColumnElement[Any]:
    """`snapped_box` of a geometry column, in SQL, for a box search on what a reader may see."""
    x0 = func.floor(func.ST_XMin(column) / AREA_GRID_LON)
    y0 = func.floor(func.ST_YMin(column) / AREA_GRID_LAT)
    x1 = func.greatest(func.ceil(func.ST_XMax(column) / AREA_GRID_LON), x0 + 1)
    y1 = func.greatest(func.ceil(func.ST_YMax(column) / AREA_GRID_LAT), y0 + 1)
    return func.ST_MakeEnvelope(
        x0 * AREA_GRID_LON, y0 * AREA_GRID_LAT, x1 * AREA_GRID_LON, y1 * AREA_GRID_LAT, 4326
    )


def _in_metres(geometry: BaseGeometry, lon: float, lat: float) -> BaseGeometry:
    """`geometry` in metres east and north of `lon, lat`, near enough for a kilometre or two."""
    scale = np.array([_M_PER_DEG_LON * math.cos(math.radians(lat)), _M_PER_DEG_LAT])
    origin = np.array([lon, lat])
    return shapely.transform(geometry, lambda coords: (coords - origin) * scale)


@dataclass(frozen=True)
class PositionGuard:
    """What a reader may see of what people wrote and drew beside some findings.

    `hidden` holds the exact points of the findings among them the reader
    doesn't see exactly (or, for a download, doesn't download exactly). While
    there is one, every piece of free text loses the positions written in it
    (`text`), an address that holds one is dropped (`url`), a view or a line
    that comes within `NEAR_HIDDEN_M` of one is held back (`near`), and an
    area that does is widened to whole cells of the area grid (`area`).
    Everything is left as it is for a reader who sees every finding exactly.
    """

    hidden: tuple[tuple[float, float], ...] = ()

    def text(self, value: str | None) -> str | None:
        return text_positions.redact(value) if value and self.hidden else value

    def url(self, value: str | None) -> str | None:
        return None if value and self.hidden and text_positions.holds_position(value) else value

    def near(self, geometry: BaseGeometry) -> bool:
        """Whether `geometry` comes within `NEAR_HIDDEN_M` of a finding the reader sees only as a square."""
        for lon, lat in self.hidden:
            if _in_metres(geometry, lon, lat).distance(Point(0, 0)) <= NEAR_HIDDEN_M:
                return True
        return False

    def area(self, geometry: BaseGeometry | None) -> BaseGeometry | None:
        if geometry is None or not self.near(geometry):
            return geometry
        return snapped_box(geometry)


def position_guard(
    findings: Iterable[Finding], viewer: User | None, *, download: bool = False
) -> PositionGuard:
    """The guard for what was written beside `findings`, as `viewer` may read it or download it."""
    exact = downloads_exact if download else sees_exact
    return PositionGuard(tuple(_exact_point(finding) for finding in findings if not exact(finding, viewer)))


def near_hidden_clause(viewer: User | None, geometry: Any, held: ColumnElement[bool]) -> ColumnElement[bool]:
    """SQL: whether `geometry` comes near a finding matched by `held` that `viewer` sees only as a square.

    `held` ties `Finding` to the row whose geometry this is. The distance is a
    little longer than `PositionGuard.near`'s, whose metres are approximate, so
    SQL never treats as far a shape that a response treats as near.
    """
    exact = sees_exact_clause(viewer)
    if exact is True:
        return false()
    hidden = not_(as_sql(exact))
    return (
        select(Finding.id)
        .where(
            held,
            hidden,
            func.ST_DWithin(func.geography(geometry), func.geography(Finding.location), NEAR_HIDDEN_M * 1.05),
        )
        .exists()
    )
