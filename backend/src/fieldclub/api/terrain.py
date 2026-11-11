"""`POST /terrain/profile` and `GET /terrain/coverage`."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from fieldclub.api.deps import BBoxQuery, IfNoneMatch, TerrainDep, not_modified
from fieldclub.ratelimit import rate_limit
from fieldclub.schemas.common import parse_bbox
from fieldclub.terrain.coverage import coverage, coverage_edition
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
    # The level of the mirror the heights were read from, in metres: 1 m, or a
    # coarser copy (2, 4, 8, 40, 200 or 1000) for a long line with few samples.
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


class CoveragePolygonOut(BaseModel):
    type: Literal["Polygon"]
    # One ring of five WGS84 positions, longitude then latitude, closed.
    coordinates: list[list[tuple[float, float]]]


class CoveragePropertiesOut(BaseModel):
    # The 5 km tile, such as SU16nw.
    tile: str
    # The edition the elevation comes from, such as "2022 composite".
    capture: str
    resolution_m: float
    # The years the surveys behind this tile were flown, oldest first. Empty where the index has none.
    years: list[int]


class CoverageFeatureOut(BaseModel):
    type: Literal["Feature"]
    id: str
    geometry: CoveragePolygonOut
    properties: CoveragePropertiesOut


class CoverageOut(BaseModel):
    type: Literal["FeatureCollection"]
    edition: str
    features: list[CoverageFeatureOut]


# The coverage changes only with a new catalogue or new capture years, which change the ETag.
COVERAGE_CACHE = "public, max-age=3600"


@router.get("/coverage", response_model=CoverageOut)
def get_coverage(
    terrain: TerrainDep,
    bbox: BBoxQuery = None,
    if_none_match: IfNoneMatch = None,
) -> Response:
    """The 5 km tiles that have 1 m elevation, with the years they were flown, as GeoJSON."""
    box = parse_bbox(bbox)
    etag = f'"{coverage_edition(terrain.catalogue)}"'
    headers = {"Cache-Control": COVERAGE_CACHE, "ETag": etag}
    unchanged = not_modified(if_none_match, headers)
    if unchanged is not None:
        return unchanged
    body: dict[str, Any] = coverage(terrain.catalogue, box)
    return JSONResponse(body, headers=headers)
