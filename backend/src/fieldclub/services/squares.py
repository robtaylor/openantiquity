"""Scan a square: hand out 1 km grid squares, keep each person's result, and count coverage.

A square is named by its compact 1 km grid reference, such as `SU1069`
(`gridref`). Only squares with 1 m elevation are handed out or recorded
(`scannable`). A 1 km square lies wholly inside one 5 km tile of the
terrain catalogue, and a square can only have elevation when its tile is
listed. That isn't enough on its own: at the coast and along the Welsh and
Scottish borders the catalogue lists partial tiles, and many of their
squares are sea or outside England, where the DTM has no data. So a square
also needs its centre inside England's boundary in `admin_areas`. A coastal
square whose centre is just offshore is lost, and one whose centre is just
inland may still be mostly sea; nothing reads the rasters to tell. Until
`admin_areas` holds England, the tile alone decides and a warning is logged.

Only `terrain.catalogue` is imported from the terrain package, because it
reads a text file and loads no raster library.

An empty square is a result. "Nothing obvious" is how the map shows that an
area was looked at and not ignored, so it counts towards coverage as much as
a square where something was marked. A skip doesn't count as a scan.

A banned account's results stop counting while the ban lasts, in coverage
and in the ranking of the next square (`counted_clause`), as its second
looks do: a few accounts could otherwise mark a stretch of country as done.
Lifting the ban counts them again.

Coverage counts each person's result as they gave it. A square somebody
marked stays marked after the finding marked there is hidden, withdrawn or
deleted, because a survey keeps only how many findings were marked, not
which. It shows no more than that somebody marked something in a public
1 km square.

Choosing the next square (`next_square`):

1. Start from the point given, or the middle of a random tile with elevation.
2. Walk outwards a ring of 5 km tiles at a time, collecting the scannable
   squares the person hasn't done and didn't ask to leave out, until there are at least
   `POOL` of them or the walk reaches `MAX_RING` tiles out.
3. Rank them by how many people have had them (skips included, so a square
   everyone skips stops being handed out first), then by distance.
4. Pick at random among the best `CHOICES`. Two people asking at the same
   place at the same moment then usually get different squares, and the
   count spreads them further as results come in.

Services flush and never commit.
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import BadRequestError, NotFoundError, ValidationFailedError
from fieldclub.models import AdminArea, SquareSurvey, User
from fieldclub.models.common import to_db_geometry
from fieldclub.services import geo, sensitivity
from fieldclub.terrain.catalogue import TILE_METRES, Catalogue, england_catalogue, tile_name_at
from fieldclub.vocab import AdminAreaKind, Nation, SurveyResult

logger = logging.getLogger(__name__)

SQUARE_METRES = 1000
SQUARES_PER_SIDE = TILE_METRES // SQUARE_METRES
# The British National Grid's extent in metres.
GRID_EAST, GRID_NORTH = 700_000, 1_300_000

POOL = 40
CHOICES = 8
# 10 tiles of 5 km: 50 km in every direction.
MAX_RING = 10

# The most squares one coverage request may span, about 50 km by 50 km.
MAX_COVERAGE_KM2 = 2500.0
# How many squares a signed-out visitor may ask to leave out.
MAX_EXCLUDE = 100
MAX_SECONDS = 24 * 3600
MAX_FINDINGS = 100

assert TILE_METRES % SQUARE_METRES == 0, "a tile holds a whole number of squares"


class InvalidSquareError(BadRequestError):
    code = "invalid_square"
    message = "A square is a 1 km grid reference with four digits, such as SU1069."


class NoElevationError(ValidationFailedError):
    code = "square_has_no_elevation"
    message = "There's no 1 m elevation for that square, so it can't be scanned."


class NoSquareError(NotFoundError):
    code = "no_square_available"
    message = "There's no square left to scan within 50 km of there."


class InvalidSurveyError(ValidationFailedError):
    code = "invalid_survey"
    message = "Mark at least one finding for a square you marked, and none for one with nothing or skipped."


class CoverageTooLargeError(BadRequestError):
    code = "bbox_too_large"
    message = f"Ask for coverage over at most {MAX_COVERAGE_KM2:g} square kilometres at a time."


# --------------------------------------------------------------------------
# Squares
# --------------------------------------------------------------------------


def parse_square(text: str) -> gridref.GridRef:
    """A 1 km square from its reference, written with or without spaces, in any case."""
    try:
        ref = gridref.parse_gridref(text)
    except gridref.GridRefError:
        raise InvalidSquareError() from None
    if ref.precision_m != SQUARE_METRES:
        raise InvalidSquareError()
    return ref


def name(ref: gridref.GridRef) -> str:
    """The stored name of a square: `SU1069`."""
    assert ref.precision_m == SQUARE_METRES, "only 1 km squares have names here"
    return ref.format(compact=True)


def has_elevation(ref: gridref.GridRef, catalogue: Catalogue) -> bool:
    """Whether the square's 5 km tile is listed. Needed for elevation, but not enough: see `scannable`."""
    if ref.system is not gridref.GridSystem.OSGB:
        return False
    return tile_name_at(ref.easting, ref.northing) in catalogue


_CENTRES_IN_AREA = text(
    """
    SELECT t.i FROM admin_areas AS a,
        unnest(CAST(:lons AS float8[]), CAST(:lats AS float8[])) WITH ORDINALITY AS t(lon, lat, i)
    WHERE a.id = :area AND ST_Covers(a.geom, ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326))
    """
)


def england_area(db: Session) -> int | None:
    """The id of England's row in `admin_areas`, or None, with a warning, while it isn't there."""
    area = db.scalar(
        select(AdminArea.id).where(
            AdminArea.kind == AdminAreaKind.NATION.value, AdminArea.code == Nation.ENGLAND.value
        )
    )
    if area is None:
        logger.warning("admin_areas has no England boundary, so squares at sea or over the border count")
    return area


def centres_inside(db: Session, area: int, refs: Sequence[gridref.GridRef]) -> list[bool]:
    """Whether each square's centre is inside the boundary `area` of `admin_areas`. One query."""
    if not refs:
        return []
    half = SQUARE_METRES / 2
    lons, lats = gridref.transformer(27700, 4326).transform(
        [ref.easting + half for ref in refs], [ref.northing + half for ref in refs]
    )
    inside = set(db.scalars(_CENTRES_IN_AREA, {"lons": list(lons), "lats": list(lats), "area": area}))
    return [i in inside for i in range(1, len(refs) + 1)]


def scannable(db: Session, ref: gridref.GridRef, catalogue: Catalogue) -> bool:
    """Whether the square has 1 m elevation to scan: its tile is listed and its centre is in England."""
    if not has_elevation(ref, catalogue):
        return False
    area = england_area(db)
    return area is None or centres_inside(db, area, [ref])[0]


def _square_at(easting: int, northing: int) -> gridref.GridRef:
    return gridref.GridRef(gridref.GridSystem.OSGB, easting, northing, SQUARE_METRES)


# --------------------------------------------------------------------------
# The next square
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    ref: gridref.GridRef
    distance_m: float
    # People who have had it, skips included.
    surveys: int = 0


@dataclass(frozen=True)
class NextSquare:
    ref: gridref.GridRef
    # People who have scanned it, not counting skips.
    scans: int


def _ring(col: int, row: int, radius: int) -> Iterator[tuple[int, int]]:
    """The tile cells exactly `radius` steps from (col, row), in the chessboard sense."""
    if radius == 0:
        yield col, row
        return
    for dc in range(-radius, radius + 1):
        for dr in range(-radius, radius + 1):
            if max(abs(dc), abs(dr)) == radius:
                yield col + dc, row + dr


def _ring_squares(
    catalogue: Catalogue, col: int, row: int, radius: int, easting: float, northing: float
) -> list[Candidate]:
    found = []
    for c, r in _ring(col, row, radius):
        west, south = c * TILE_METRES, r * TILE_METRES
        if not (0 <= west < GRID_EAST and 0 <= south < GRID_NORTH):
            continue
        if tile_name_at(west, south) not in catalogue:
            continue
        for i in range(SQUARES_PER_SIDE):
            for j in range(SQUARES_PER_SIDE):
                e, n = west + i * SQUARE_METRES, south + j * SQUARE_METRES
                distance = math.hypot(e + SQUARE_METRES / 2 - easting, n + SQUARE_METRES / 2 - northing)
                found.append(Candidate(_square_at(e, n), distance))
    return found


def counted_clause() -> ColumnElement[bool]:
    """Surveys that count: those of accounts that aren't banned. See the module docstring."""
    banned = select(User.id).where(User.banned_at.is_not(None))
    return SquareSurvey.user_id.not_in(banned)


def _survey_counts(db: Session, names: Sequence[str]) -> dict[str, tuple[int, int]]:
    """For each square, how many people have had it and how many have scanned it."""
    if not names:
        return {}
    rows = db.execute(
        select(
            SquareSurvey.square,
            func.count(),
            func.count().filter(SquareSurvey.result != SurveyResult.SKIPPED.value),
        )
        .where(SquareSurvey.square.in_(names), counted_clause())
        .group_by(SquareSurvey.square)
    )
    return {square: (surveys, scans) for square, surveys, scans in rows}


def _done(db: Session, user: User | None, names: Sequence[str]) -> set[str]:
    active = sensitivity.active_viewer(user)
    if active is None or not names:
        return set()
    return set(
        db.scalars(
            select(SquareSurvey.square).where(
                SquareSurvey.user_id == active.id, SquareSurvey.square.in_(names)
            )
        )
    )


def _start(catalogue: Catalogue, near: tuple[float, float] | None, rng: random.Random) -> tuple[float, float]:
    """Where to start looking, in British National Grid metres."""
    if near is None:
        tile = rng.choice(list(catalogue))
        west, south, east, north = tile.bounds
        return (west + east) / 2, (south + north) / 2
    return gridref.transformer(4326, 27700).transform(*near)


def next_square(
    db: Session,
    viewer: User | None,
    *,
    near: tuple[float, float] | None = None,
    exclude: Iterable[str] = (),
    rng: random.Random | None = None,
    catalogue: Catalogue | None = None,
) -> NextSquare:
    """A square few people have had, near `near` when given, that `viewer` hasn't done.

    `exclude` names squares to leave out as well, such as a signed-out
    visitor's drafts. See the module docstring for how the square is chosen.
    """
    rng = rng or random.SystemRandom()
    catalogue = catalogue or england_catalogue()
    left_out = set(exclude)
    easting, northing = _start(catalogue, near, rng)
    if not (math.isfinite(easting) and math.isfinite(northing)):
        raise NoSquareError()
    col, row = int(easting // TILE_METRES), int(northing // TILE_METRES)
    england = england_area(db)
    pool: list[Candidate] = []
    for radius in range(MAX_RING + 1):
        ring = [
            c
            for c in _ring_squares(catalogue, col, row, radius, easting, northing)
            if name(c.ref) not in left_out
        ]
        if england is not None:
            inside = centres_inside(db, england, [c.ref for c in ring])
            ring = [c for c, keep in zip(ring, inside, strict=True) if keep]
        names = [name(c.ref) for c in ring]
        done = _done(db, viewer, names)
        pool.extend(c for c in ring if name(c.ref) not in done)
        if len(pool) >= POOL:
            break
    if not pool:
        raise NoSquareError()
    counts = _survey_counts(db, [name(c.ref) for c in pool])
    ranked = sorted(
        (Candidate(c.ref, c.distance_m, counts.get(name(c.ref), (0, 0))[0]) for c in pool),
        key=lambda c: (c.surveys, c.distance_m),
    )
    chosen = rng.choice(ranked[:CHOICES])
    return NextSquare(chosen.ref, counts.get(name(chosen.ref), (0, 0))[1])


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


def check_result(result: SurveyResult, findings_count: int, seconds: int | None) -> None:
    if not 0 <= findings_count <= MAX_FINDINGS:
        raise InvalidSurveyError(f"Between 0 and {MAX_FINDINGS} findings, please.")
    if (result is SurveyResult.MARKED) != (findings_count > 0):
        raise InvalidSurveyError()
    if seconds is not None and not 0 <= seconds <= MAX_SECONDS:
        raise InvalidSurveyError(f"The time spent is between 0 and {MAX_SECONDS} seconds.")


def record_survey(
    db: Session,
    user: User,
    ref: gridref.GridRef,
    result: SurveyResult,
    *,
    findings_count: int = 0,
    seconds: int | None = None,
    catalogue: Catalogue | None = None,
) -> tuple[SquareSurvey, bool]:
    """Keep the person's result for a square. A second result from them replaces the first.

    Returns the row and whether it is new. Two requests at once can't make two rows.
    """
    check_result(result, findings_count, seconds)
    if not scannable(db, ref, catalogue or england_catalogue()):
        raise NoElevationError()
    values = {"result": result.value, "findings_count": findings_count, "seconds": seconds}
    statement = (
        insert(SquareSurvey)
        .values(user_id=user.id, square=name(ref), geom=to_db_geometry(ref.polygon()), **values)
        .on_conflict_do_update(index_elements=["user_id", "square"], set_=values)
        # xmax is 0 on a row this statement inserted, and set on one it updated.
        .returning(SquareSurvey.id, literal_column("xmax") == 0)
    )
    survey_id, created = db.execute(statement).one()
    survey = db.get(SquareSurvey, survey_id, populate_existing=True)
    assert survey is not None, "the row was just written"
    return survey, bool(created)


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    ref: gridref.GridRef
    # People who scanned it, not counting skips.
    scans: int
    # People who marked something in it.
    marked: int


def area_km2(bbox: tuple[float, float, float, float]) -> float:
    """Roughly how many square kilometres a box in degrees covers."""
    west, south, east, north = bbox
    middle = math.radians((south + north) / 2)
    return (east - west) * 111.32 * math.cos(middle) * (north - south) * 110.57


def coverage_query(bbox: tuple[float, float, float, float]) -> Select[str, int, int]:
    """Squares touching the box with how many people scanned and marked each. Uses the GIST index on geom."""
    scans = func.count().filter(SquareSurvey.result != SurveyResult.SKIPPED.value)
    marked = func.count().filter(SquareSurvey.result == SurveyResult.MARKED.value)
    return (
        select(SquareSurvey.square, scans, marked)
        .where(func.ST_Intersects(SquareSurvey.geom, geo.envelope(bbox)), counted_clause())
        .group_by(SquareSurvey.square)
        .having(scans > 0)
        .order_by(SquareSurvey.square)
    )


def coverage(db: Session, bbox: tuple[float, float, float, float]) -> list[Coverage]:
    """How many people have scanned each square that touches the box."""
    if area_km2(bbox) > MAX_COVERAGE_KM2:
        raise CoverageTooLargeError()
    return [
        Coverage(parse_square(square), scans, marked)
        for square, scans, marked in db.execute(coverage_query(bbox))
    ]
