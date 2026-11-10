"""Where a point is (which nation and county), and boxes as SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from fieldclub.errors import DataIntegrityError
from fieldclub.models import AdminArea, Source
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
