"""Scan a square: hand out 1 km grid squares, keep each person's result, and count coverage.

A square is named by its compact 1 km grid reference, such as `SU1069`
(`gridref`). Only squares with 1 m elevation are handed out or recorded.
A 1 km square lies wholly inside one 5 km tile of the terrain catalogue,
so a square has elevation exactly when its tile is listed. Only
`terrain.catalogue` is imported from the terrain package, because it reads a
text file and loads no raster library.

An empty square is a result. "Nothing obvious" is how the map shows that an
area was looked at and not ignored, so it counts towards coverage as much as
a square where something was marked. A skip doesn't count as a scan.

Choosing the next square (`next_square`):

1. Start from the point given, or the middle of a random tile with elevation.
2. Walk outwards a ring of 5 km tiles at a time, collecting the squares the
   person hasn't done and didn't ask to leave out, until there are at least
   `POOL` of them or the walk reaches `MAX_RING` tiles out.
3. Rank them by how many people have had them (skips included, so a square
   everyone skips stops being handed out first), then by distance.
4. Pick at random among the best `CHOICES`. Two people asking at the same
   place at the same moment then usually get different squares, and the
   count spreads them further as results come in.

Services flush and never commit.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import BadRequestError, NotFoundError, ValidationFailedError
from fieldclub.models import SquareSurvey, User
from fieldclub.models.common import to_db_geometry
from fieldclub.services import geo, sensitivity
from fieldclub.terrain.catalogue import TILE_METRES, Catalogue, england_catalogue, tile_name_at
from fieldclub.vocab import SurveyResult

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
    if ref.system is not gridref.GridSystem.OSGB:
        return False
    return tile_name_at(ref.easting, ref.northing) in catalogue


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
        .where(SquareSurvey.square.in_(names))
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
    pool: list[Candidate] = []
    for radius in range(MAX_RING + 1):
        ring = [
            c
            for c in _ring_squares(catalogue, col, row, radius, easting, northing)
            if name(c.ref) not in left_out
        ]
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
    if not has_elevation(ref, catalogue or england_catalogue()):
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
        .where(func.ST_Intersects(SquareSurvey.geom, geo.envelope(bbox)))
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
