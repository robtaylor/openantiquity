"""Where a point is (which nation and county), and boxes as SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from fieldclub.errors import DataIntegrityError
from fieldclub.models import AdminArea
from fieldclub.models.common import SRID
from fieldclub.vocab import AdminAreaKind, Nation


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


def envelope(bbox: tuple[float, float, float, float]) -> ColumnElement[Any]:
    """A west, south, east, north box in degrees as a PostGIS polygon."""
    west, south, east, north = bbox
    return func.ST_MakeEnvelope(west, south, east, north, SRID)
