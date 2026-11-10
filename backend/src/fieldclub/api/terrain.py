"""`POST /terrain/profile` and `GET /terrain/coverage`."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from fieldclub.api.deps import BBoxQuery, TerrainDep
from fieldclub.ratelimit import rate_limit
from fieldclub.schemas.common import GeoJSONFeatureCollection, parse_bbox
from fieldclub.terrain.coverage import coverage
from fieldclub.terrain.service import MAX_PROFILE_SAMPLES, MAX_PROFILE_VERTICES

router = APIRouter(prefix="/terrain", tags=["terrain"])

Position = tuple[Annotated[float, Field(ge=-180, le=180)], Annotated[float, Field(ge=-90, le=90)]]


class LineString(BaseModel):
    type: Literal["LineString"]
    coordinates: list[Position] = Field(min_length=2, max_length=MAX_PROFILE_VERTICES)


class ProfileRequest(BaseModel):
    line: LineString
    samples: int = Field(default=200, ge=2, le=MAX_PROFILE_SAMPLES)


class ProfileSample(BaseModel):
    distance_m: float
    # Metres above Ordnance Datum Newlyn, or null where there is no data.
    elevation: float | None
    lon: float
    lat: float


class ProfileOut(BaseModel):
    length_m: float
    # The grid the heights were read from: 1 m, or coarser for long lines with few samples.
    resolution_m: float
    samples: list[ProfileSample]


@router.post(
    "/profile",
    response_model=ProfileOut,
    dependencies=[Depends(rate_limit("terrain_profile", 30, per_seconds=60))],
)
def profile(body: ProfileRequest, terrain: TerrainDep) -> ProfileOut:
    """Ground height along a line, at evenly spaced samples. Lines are at most 5 km long."""
    result = terrain.profile(list(body.line.coordinates), body.samples)
    return ProfileOut(
        length_m=result.length_m,
        resolution_m=result.resolution_m,
        samples=[
            ProfileSample(distance_m=d, elevation=h, lon=lon, lat=lat)
            for d, h, (lon, lat) in zip(result.distances, result.elevations, result.positions, strict=True)
        ],
    )


# The body is built as plain GeoJSON for speed. The model documents it for the generated client.
@router.get("/coverage", response_model=GeoJSONFeatureCollection)
def get_coverage(terrain: TerrainDep, bbox: BBoxQuery = None) -> JSONResponse:
    """The 5 km tiles that have 1 m elevation, as a GeoJSON FeatureCollection."""
    body: dict[str, Any] = coverage(terrain.catalogue, parse_bbox(bbox))
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=86400"})
