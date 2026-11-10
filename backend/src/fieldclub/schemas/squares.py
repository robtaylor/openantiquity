"""Shapes for scanning a square and for the coverage layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fieldclub import gridref
from fieldclub.models import SquareSurvey
from fieldclub.schemas.common import (
    ApiModel,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    RequestModel,
    geojson_geometry,
)
from fieldclub.services import squares
from fieldclub.vocab import SurveyResult


class SquareOut(ApiModel):
    """A 1 km square to scan."""

    # The compact reference, such as `SU1069`. Send it back to `PUT /squares/{square}`.
    square: str
    # The same square written for people: `SU 10 69`.
    grid_ref: str
    centre: tuple[float, float]
    # West, south, east, north in degrees: fit the map to this.
    bbox: tuple[float, float, float, float]
    geometry: GeoJSONGeometry
    # How many people have scanned it, not counting skips.
    scans: int

    @classmethod
    def build(cls, ref: gridref.GridRef, scans: int) -> SquareOut:
        polygon = ref.polygon()
        lon, lat = ref.centre()
        west, south, east, north = polygon.bounds
        geometry = geojson_geometry(polygon)
        assert geometry is not None
        return cls(
            square=squares.name(ref),
            grid_ref=ref.format(),
            centre=(round(lon, 6), round(lat, 6)),
            bbox=(round(west, 6), round(south, 6), round(east, 6), round(north, 6)),
            geometry=geometry,
            scans=scans,
        )


class SurveyIn(RequestModel):
    """Your result for a square: nothing obvious, marked something, or skipped."""

    result: SurveyResult
    # How many findings you marked in it: at least one when `marked`, otherwise none.
    findings_count: int = Field(default=0, ge=0, le=squares.MAX_FINDINGS)
    # How long you spent on it.
    seconds: int | None = Field(default=None, ge=0, le=squares.MAX_SECONDS)


class SurveyOut(ApiModel):
    square: str
    grid_ref: str
    result: SurveyResult
    findings_count: int
    seconds: int | None
    created_at: datetime

    @classmethod
    def build(cls, survey: SquareSurvey) -> SurveyOut:
        return cls(
            square=survey.square,
            grid_ref=squares.parse_square(survey.square).format(),
            result=SurveyResult(survey.result),
            findings_count=survey.findings_count,
            seconds=survey.seconds,
            created_at=survey.created_at,
        )


class CoverageProperties(BaseModel):
    square: str
    # People who scanned it, not counting skips. "Nothing obvious" counts.
    scans: int
    # People who marked something in it.
    marked: int


class CoverageFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONGeometry
    properties: CoverageProperties


class CoverageCollection(GeoJSONFeatureCollection):
    """Scanned squares in view. Squares nobody has scanned aren't listed."""

    features: list[CoverageFeature] = Field(default_factory=list)  # pyright: ignore[reportIncompatibleVariableOverride]


def coverage_feature(cell: squares.Coverage) -> CoverageFeature:
    geometry = geojson_geometry(cell.ref.polygon())
    assert geometry is not None
    square = squares.name(cell.ref)
    return CoverageFeature(
        id=square,
        geometry=geometry,
        properties=CoverageProperties(square=square, scans=cell.scans, marked=cell.marked),
    )
