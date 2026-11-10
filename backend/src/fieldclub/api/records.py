"""The record index: search, nearby, one record, the sources, and suggestions for a finding.

`format=geojson` on search and nearby is the export: a FeatureCollection whose
every feature carries its source key, licence, attribution and reuse class.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from fieldclub.api.deps import Db, OptionalUser
from fieldclub.schemas import records as schema
from fieldclub.schemas.common import feature_collection
from fieldclub.services import records
from fieldclub.services.records import InvalidSearchError

router = APIRouter(tags=["records"])

GEOJSON = "application/geo+json"
Format = Literal["json", "geojson"]
ListParam = Annotated[
    str | None, Query(max_length=500, description="Comma-separated values, such as `designation,monument`")
]


def split_list(value: str | None) -> list[str] | None:
    """`a,b, c` as `["a", "b", "c"]`, or None when empty."""
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """`west,south,east,north` in degrees."""
    if value is None:
        return None
    parts = value.split(",")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError:
        raise InvalidSearchError("bbox is four numbers: west,south,east,north.") from None
    return records.check_bbox((west, south, east, north))


def _geojson(results: list[records.RecordResult]) -> JSONResponse:
    return JSONResponse(
        feature_collection([schema.record_feature(result) for result in results]), media_type=GEOJSON
    )


@router.get("/records/search", response_model=schema.RecordPage)
def search_records(
    db: Db,
    q: Annotated[str | None, Query(max_length=records.MAX_QUERY_CHARS)] = None,
    source: ListParam = None,
    category: ListParam = None,
    bbox: Annotated[str | None, Query(max_length=200, description="west,south,east,north")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    format: Format = "json",
) -> schema.RecordPage | JSONResponse:
    """Records by text, source, category and area, best match first."""
    found, next_cursor = records.search(
        db,
        q,
        sources=split_list(source),
        categories=split_list(category),
        bbox=parse_bbox(bbox),
        limit=limit,
        cursor=cursor,
    )
    if format == "geojson":
        return _geojson(found)
    return schema.RecordPage(
        items=[schema.record_summary(result) for result in found], next_cursor=next_cursor
    )


@router.get("/records/nearby", response_model=schema.RecordHits)
def nearby_records(
    db: Db,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    radius: Annotated[float, Query(gt=0, le=records.MAX_RADIUS_M, description="metres")] = 1000,
    source: ListParam = None,
    category: ListParam = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    format: Format = "json",
) -> schema.RecordHits | JSONResponse:
    """Records near a point, nearest first, with the distance to each in metres."""
    found = records.nearby(
        db,
        lon,
        lat,
        radius_m=radius,
        limit=limit,
        sources=split_list(source),
        categories=split_list(category),
    )
    if format == "geojson":
        return _geojson(found)
    return schema.RecordHits(items=[schema.record_hit(result) for result in found])


@router.get("/records/{record_id}", response_model=schema.RecordOut)
def get_record(db: Db, record_id: Annotated[int, Path(ge=1, le=2**63 - 1)]) -> schema.RecordOut:
    """One record with its geometry, and its source's licence and attribution."""
    return schema.record_out(records.get_record(db, record_id))


@router.get("/sources", response_model=list[schema.SourceOut])
def list_sources(db: Db) -> list[schema.SourceOut]:
    """Every source in the index, with its licence, attribution, reuse class and record count."""
    return [schema.SourceOut.model_validate(source) for source in records.list_sources(db)]


@router.get("/findings/{public_id}/suggested-records", response_model=schema.Suggestions)
def suggested_records(
    db: Db,
    viewer: OptionalUser,
    public_id: Annotated[str, Path(max_length=32)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> schema.Suggestions:
    """Records the finding might be, near the position this viewer may see of it."""
    finding = records.load_finding(db, public_id, viewer)
    found = records.suggest_for_finding(db, finding, viewer, limit=limit)
    origin = found.origin
    return schema.Suggestions(
        origin=schema.Origin(
            lon=round(origin.lon, 6), lat=round(origin.lat, 6), obscured=origin.obscured, square=origin.square
        ),
        items=[
            schema.SuggestedRecord(
                **schema.record_hit(item.result).model_dump(), type_fit=item.type_fit, score=item.score
            )
            for item in found.items
        ],
    )
