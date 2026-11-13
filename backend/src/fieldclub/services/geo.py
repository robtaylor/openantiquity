"""Where a point is (in the British Isles, which nation and county, the nearest place), and boxes as SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import DataIntegrityError, ValidationFailedError
from fieldclub.models import AdminArea, Place, Source
from fieldclub.models.common import SRID
from fieldclub.vocab import AdminAreaKind, Nation

# How far out to sea a point still takes the nearest nation, in metres. The
# nations reach 2 km past the coast already. This covers the estuaries and
# bays between them, such as the Severn, the Wash and Morecambe Bay.
NEAR_NATION_M = 10_000.0
# The source that fills each kind of area, whose attribution goes with a
# nation or county shown. `admin_areas` keeps no source of its own, so the
# loaders in `ingest/reference/ons_boundaries.py` are tested against this.
AREA_SOURCES = {AdminAreaKind.NATION: "ons-countries-2025", AdminAreaKind.COUNTY: "ons-counties-2025"}


# A place is offered as the nearest only within this distance, in metres.
NEAREST_PLACE_M = 10_000.0
# Settlements, from a hamlet up: the hundreds of `places.rank` are 4 and over
# (`ingest/reference/os_open_names.py`). A hill or a wood is no name for a finding.
SETTLEMENT_RANK = 400
# How many places the index's nearest-first scan hands over to be measured on the
# sphere. Degrees of longitude are shorter than degrees of latitude, so the
# index's order is close to the true one, not the same.
_NEAREST_CANDIDATES = 16


class OutsideBritishIslesError(ValidationFailedError):
    code = "outside_british_isles"
    message = "OpenAntiquity covers Great Britain, Ireland and their islands. That position is outside them."


# A coarse outline of Great Britain, Ireland, the Isle of Man, Orkney,
# Shetland, the Hebrides and Scilly, in longitude and latitude. It runs down
# the middle of the Channel and the Strait of Dover, so Calais and the Cotentin
# are outside, and well east of the North Sea coast. The Channel Islands are
# outside because they are on neither grid, and a protected finding there
# could not be generalised to a grid square.
BRITISH_ISLES = Polygon(
    [
        (-7.0, 49.8),
        (-5.2, 49.9),
        (-3.6, 50.15),
        (-2.45, 50.45),
        (-1.3, 50.5),
        (0.3, 50.65),
        (1.0, 50.85),
        (1.45, 51.05),
        (2.0, 51.5),
        (2.0, 53.0),
        (0.5, 54.5),
        (-1.0, 57.6),
        (0.0, 61.0),
        (-9.0, 61.0),
        (-14.0, 58.0),
        (-11.0, 54.5),
        (-11.0, 51.2),
    ]
)
assert BRITISH_ISLES.is_valid, "the British Isles outline crosses itself"


def check_in_british_isles(geometry: BaseGeometry) -> None:
    """Refuse a geometry that isn't wholly inside the British Isles and on one of their grids."""
    if not BRITISH_ISLES.contains(geometry):
        raise OutsideBritishIslesError()
    for lon, lat in _corners(geometry):
        try:
            gridref.to_grid(lon, lat)
        except gridref.GridRefError:
            raise OutsideBritishIslesError() from None


def _corners(geometry: BaseGeometry) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    return [(min_lon, min_lat), (min_lon, max_lat), (max_lon, min_lat), (max_lon, max_lat)]


@dataclass(frozen=True)
class NearestPlace:
    name: str
    kind: str
    distance_m: float
    # The key of the source the place came from, whose attribution goes with it.
    source: str


def nearest_place(
    db: Session, lon: float, lat: float, *, within_m: float = NEAREST_PLACE_M
) -> NearestPlace | None:
    """The settlement in `places` nearest a WGS84 position, within `within_m`, or None."""
    assert within_m > 0, "a distance must be positive"
    here = func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID)
    distance = func.ST_Distance(func.Geography(Place.geom), func.Geography(here))
    candidates = (
        select(Place.name, Place.kind, Place.source, distance.label("distance"))
        .where(Place.rank >= SETTLEMENT_RANK)
        .order_by(Place.geom.op("<->")(here))
        .limit(_NEAREST_CANDIDATES)
        .subquery()
    )
    row = db.execute(
        select(candidates)
        .where(candidates.c.distance <= within_m)
        .order_by(candidates.c.distance, candidates.c.name)
        .limit(1)
    ).first()
    if row is None:
        return None
    return NearestPlace(name=row.name, kind=row.kind, distance_m=float(row.distance), source=row.source)


@dataclass(frozen=True)
class Locality:
    # A `vocab.Nation` value, or None when the point is in no known nation.
    nation: str | None
    # The county's name, or None when no county boundary covers the point.
    county: str | None


def locate(db: Session, lon: float, lat: float) -> Locality:
    """The nation and county that contain a WGS84 position.

    Both come from `admin_areas` and from nowhere else. A point that no
    nation boundary covers has no nation. There is deliberately no guess from
    the grid a point falls on: the Irish Grid covers the whole island, so that
    guess would label Dublin and Cork as Northern Ireland and show them its
    field-visit notices.
    """
    here = func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID)
    rows = db.execute(
        select(AdminArea.kind, AdminArea.code, AdminArea.name)
        .where(func.ST_Covers(AdminArea.geom, here))
        # Where boundaries overlap, the smaller area is the more specific one.
        .order_by(func.ST_Area(AdminArea.geom), AdminArea.id)
    ).all()

    nation: str | None = None
    county: str | None = None
    for kind, code, name in rows:
        if kind == AdminAreaKind.NATION and nation is None:
            if code not in Nation:
                raise DataIntegrityError(
                    f"admin_areas has a nation with code {code!r}, which is not a known nation."
                )
            nation = code
        elif kind == AdminAreaKind.COUNTY and county is None:
            county = name
    return Locality(nation=nation, county=county)


def locality_sources(db: Session, locality: Locality) -> list[Source]:
    """The sources of the boundaries that gave a locality its nation and county."""
    found = ((AdminAreaKind.NATION, locality.nation), (AdminAreaKind.COUNTY, locality.county))
    keys = [AREA_SOURCES[kind] for kind, value in found if value is not None]
    if not keys:
        return []
    return list(db.scalars(select(Source).where(Source.key.in_(keys)).order_by(Source.key)))


def nations_near(db: Session, area: BaseGeometry, within_m: float = NEAR_NATION_M) -> list[tuple[str, float]]:
    """The nations within `within_m` metres of a WGS84 geometry, nearest first, with their distances.

    A nation the geometry meets is 0 m away. Like `locate`, this reads `admin_areas` only.
    """
    assert within_m >= 0, "a distance can't be negative"
    shape = func.Geography(func.ST_GeomFromText(area.wkt, SRID))
    boundary = func.Geography(AdminArea.geom)
    distance = func.ST_Distance(boundary, shape)
    rows = db.execute(
        select(AdminArea.code, distance)
        .where(AdminArea.kind == AdminAreaKind.NATION.value, func.ST_DWithin(boundary, shape, within_m))
        .order_by(distance, AdminArea.code)
    ).all()
    return [(code, float(metres)) for code, metres in rows]


def nation_of(db: Session, area: BaseGeometry) -> str | None:
    """The one nation a WGS84 geometry lies in, or None when it meets two, or none is near.

    A geometry wholly at sea takes the nearest nation within `NEAR_NATION_M`.
    A finding's 1 km square that meets two nations gives None, so the nation
    shown to someone who sees only the square never says which side of the
    border the finding is on.
    """
    near = nations_near(db, area)
    meeting = [code for code, metres in near if metres == 0]
    if meeting:
        return meeting[0] if len(meeting) == 1 else None
    return near[0][0] if near else None


def envelope(bbox: tuple[float, float, float, float]) -> ColumnElement[Any]:
    """A west, south, east, north box in degrees as a PostGIS polygon."""
    west, south, east, north = bbox
    return func.ST_MakeEnvelope(west, south, east, north, SRID)
