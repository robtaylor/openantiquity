"""The record index: search, nearby, one record, the sources, and suggestions for a finding.

`format=geojson` on search and nearby is the export: a FeatureCollection whose
every feature carries its source key, licence, attribution and reuse class.

Search, nearby, a record and the sources are the same for every viewer, so
each is sent as publicly cacheable for a few minutes (`deps.shared`). The
findings linked to a record and the suggestions for a finding depend on the
viewer and are private.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response
from pydantic import StringConstraints

from fieldclub.api.deps import BBoxQuery, Db, OptionalUser, PageQuery, private, shared
from fieldclub.schemas import records as schema
from fieldclub.schemas.common import GeoJSONFeatureCollection, Page, parse_bbox
from fieldclub.services import findings, records, sensitivity
from fieldclub.vocab import RecordCategory, stored_class

router = APIRouter(tags=["records"])

GEOJSON = "application/geo+json"
Format = Literal["json", "geojson"]
# Repeated parameters, `source=a&source=b`, as every list filter is.
MAX_SOURCES = 100
SourceParam = Annotated[
    list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] | None,
    Query(max_length=MAX_SOURCES, description="Source keys"),
]
CategoryParam = Annotated[list[RecordCategory] | None, Query(max_length=len(RecordCategory))]


def _values(values: list[str] | list[RecordCategory] | None) -> list[str] | None:
    return [str(value) for value in dict.fromkeys(values)] if values else None


def _geojson(results: list[records.RecordResult]) -> Response:
    collection = GeoJSONFeatureCollection(features=[schema.record_feature(result) for result in results])
    exported = Response(collection.model_dump_json(), media_type=GEOJSON)
    shared(exported)
    return exported


@router.get("/records/search", response_model=schema.RecordPage)
def search_records(
    db: Db,
    response: Response,
    *,
    q: Annotated[str | None, Query(max_length=records.MAX_QUERY_CHARS)] = None,
    source: SourceParam = None,
    category: CategoryParam = None,
    bbox: BBoxQuery = None,
    page: PageQuery,
    format: Format = "json",
) -> schema.RecordPage | Response:
    """Records by text, source, category and area, best match first."""
    shared(response)
    found, next_cursor = records.search(
        db,
        q,
        sources=_values(source),
        categories=_values(category),
        bbox=parse_bbox(bbox),
        limit=page.limit,
        cursor=page.cursor,
    )
    if format == "geojson":
        return _geojson(found)
    return schema.RecordPage(
        items=[schema.record_summary(result) for result in found], next_cursor=next_cursor
    )


@router.get("/records/nearby", response_model=schema.RecordHits)
def nearby_records(
    db: Db,
    response: Response,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    radius: Annotated[float, Query(gt=0, le=records.MAX_RADIUS_M, description="metres")] = 1000,
    source: SourceParam = None,
    category: CategoryParam = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    format: Format = "json",
) -> schema.RecordHits | Response:
    """Records near a point, nearest first, with the distance to each in metres."""
    shared(response)
    found = records.nearby(
        db,
        lon,
        lat,
        radius_m=radius,
        limit=limit,
        sources=_values(source),
        categories=_values(category),
    )
    if format == "geojson":
        return _geojson(found)
    return schema.RecordHits(items=[schema.record_hit(result) for result in found])


@router.get("/records/{record_id}", response_model=schema.RecordOut)
def get_record(
    db: Db, response: Response, record_id: Annotated[int, Path(ge=1, le=2**63 - 1)]
) -> schema.RecordOut:
    """One record with its geometry, and its source's licence and attribution."""
    shared(response)
    return schema.record_out(records.get_record(db, record_id))


@router.get("/records/{record_id}/findings", response_model=Page[schema.LinkedFinding])
def record_findings(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    record_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    page: PageQuery,
) -> Page[schema.LinkedFinding]:
    """The findings linked to this record that you may see exactly, oldest first.

    Apart from the record's page, because this depends on who is asking and the page doesn't.
    """
    private(response)
    found = records.linked_findings(db, record_id, viewer, limit=page.limit, cursor=page.cursor)
    return Page[schema.LinkedFinding](
        items=[
            schema.LinkedFinding(
                public_id=finding.public_id,
                title=sensitivity.visible_text(finding, viewer, finding.title) or "",
                feature_class=stored_class(finding.feature_class),
                tier=finding.tier,
                state=finding.state,
            )
            for finding in found.findings
        ],
        next_cursor=found.next_cursor,
    )


@router.get("/sources", response_model=list[schema.SourceOut])
def list_sources(db: Db, response: Response) -> list[schema.SourceOut]:
    """Every source in the index, with its licence, attribution, reuse class and record count."""
    shared(response)
    return [schema.SourceOut.model_validate(source) for source in records.list_sources(db)]


@router.get("/findings/{public_id}/suggested-records", response_model=schema.Suggestions)
def suggested_records(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    public_id: Annotated[str, Path(max_length=32)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> schema.Suggestions:
    """Records the finding might be, near the position this viewer may see of it."""
    private(response)
    finding = findings.get_finding(db, public_id, viewer)
    found = records.suggest_for_finding(db, finding, viewer, limit=limit)
    origin = found.origin
    return schema.Suggestions(
        origin=schema.Origin(
            lon=round(origin.lon, 6), lat=round(origin.lat, 6), obscured=origin.obscured, square=origin.square
        ),
        items=[schema.record_suggestion(item) for item in found.items],
    )
