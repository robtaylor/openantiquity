"""`GET /geo/point`: what the map's status bar shows for the spot under the pointer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from fieldclub.api.deps import Db, TerrainDep
from fieldclub.gridref import GridRefError, to_gridref
from fieldclub.models import Source
from fieldclub.schemas.records import SourceRef, source_ref
from fieldclub.services.geo import locality_sources, locate, nearest_place

router = APIRouter(prefix="/geo", tags=["geo"])


class NearbyPlace(BaseModel):
    """The nearest settlement in the gazetteer, for a suggested title such as "Enclosure near Avebury"."""

    name: str
    # The gazetteer's kind, such as Village or Town.
    kind: str
    # Metres, to the nearest metre.
    distance_m: float
    # The gazetteer's source, whose attribution goes with the name. Null if it isn't in the index.
    source: SourceRef | None


class GeoPoint(BaseModel):
    lon: float
    lat: float
    # Such as "SU 1025 6996", or null outside the British and Irish grids.
    grid_ref: str | None
    # A `vocab.Nation` value, or null.
    nation: str | None
    county: str | None
    # Ground height in metres, or null where there is no elevation data.
    elevation: float | None
    # The boundary sources that gave the nation and county, whose attribution goes with them.
    sources: list[SourceRef]
    # The nearest settlement within 10 km, or null.
    place: NearbyPlace | None


def _nearby(db: Db, lon: float, lat: float) -> NearbyPlace | None:
    near = nearest_place(db, lon, lat)
    if near is None:
        return None
    source = db.get(Source, near.source)
    return NearbyPlace(
        name=near.name,
        kind=near.kind,
        distance_m=round(near.distance_m),
        source=source_ref(source) if source is not None else None,
    )


@router.get("/point", response_model=GeoPoint)
def point(
    db: Db,
    terrain: TerrainDep,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
) -> GeoPoint:
    """Grid reference, nation, county, ground height and the nearest settlement at a WGS84 position."""
    try:
        grid_ref: str | None = to_gridref(lon, lat)
    except GridRefError:
        grid_ref = None
    place = locate(db, lon, lat)
    return GeoPoint(
        lon=lon,
        lat=lat,
        grid_ref=grid_ref,
        nation=place.nation,
        county=place.county,
        elevation=terrain.elevation_at(lon, lat),
        sources=[source_ref(source) for source in locality_sources(db, place)],
        place=_nearby(db, lon, lat),
    )
