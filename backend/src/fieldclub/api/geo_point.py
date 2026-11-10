"""`GET /geo/point`: what the map's status bar shows for the spot under the pointer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fieldclub.api.deps import Db
from fieldclub.gridref import GridRefError, to_gridref
from fieldclub.services.geo import locate
from fieldclub.terrain.service import Terrain, get_terrain

router = APIRouter(prefix="/geo", tags=["geo"])


class GeoPointOut(BaseModel):
    lon: float
    lat: float
    # Such as "SU 1025 6996", or null outside the British and Irish grids.
    grid_ref: str | None
    # A `vocab.Nation` value, or null.
    nation: str | None
    county: str | None
    # Ground height in metres, or null where there is no elevation data.
    elevation: float | None


@router.get("/point", response_model=GeoPointOut)
def point(
    db: Db,
    terrain: Annotated[Terrain, Depends(get_terrain)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
) -> GeoPointOut:
    """Grid reference, nation, county and ground height at a WGS84 position."""
    try:
        grid_ref: str | None = to_gridref(lon, lat)
    except GridRefError:
        grid_ref = None
    place = locate(db, lon, lat)
    return GeoPointOut(
        lon=lon,
        lat=lat,
        grid_ref=grid_ref,
        nation=place.nation,
        county=place.county,
        elevation=terrain.elevation_at(lon, lat),
    )
