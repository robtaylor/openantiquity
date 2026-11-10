"""Shapes for the record index, the geo search box and the context catalogue.

Every record leaves the API with its source key and a `source` that carries
the licence, the attribution and the reuse class (Decision 0004), so whoever
shows or copies a record has what its licence requires.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

from fieldclub.schemas.common import ApiModel, feature, to_geojson

if TYPE_CHECKING:
    from fieldclub.models import Source
    from fieldclub.services.records import RecordResult


class SourceRef(ApiModel):
    """What a record must be shown with: who published it and under what terms."""

    key: str
    name: str
    publisher: str
    licence: str
    licence_url: str | None
    attribution: str
    reuse: str


class SourceOut(SourceRef):
    homepage: str | None
    coverage: str | None
    category: str
    access: str
    record_count: int
    last_ingest_at: datetime | None

    @field_validator("record_count", mode="before")
    @classmethod
    def _no_count_yet_is_zero(cls, value: int | None) -> int:
        return value or 0


class RecordSummary(BaseModel):
    """A record in a list: enough to show it and put it on the map."""

    id: int
    source_key: str
    name: str
    category: str
    record_type: str | None
    # A point on the record's geometry, longitude and latitude.
    lon: float
    lat: float
    # How exact the position is in metres, when the source says.
    precision_m: float | None
    url: str | None
    source: SourceRef


class RecordHit(RecordSummary):
    """A record near a point. The distance is to the nearest part of its geometry."""

    distance_m: float


class RecordOut(RecordSummary):
    """One record in full, for its page."""

    external_id: str
    summary: str | None
    monument_types: list[str]
    periods: list[str]
    geometry: dict[str, Any]
    source_updated_at: datetime | None
    ingested_at: datetime


class RecordPage(BaseModel):
    items: list[RecordSummary]
    next_cursor: str | None = None


class RecordHits(BaseModel):
    items: list[RecordHit]


class Origin(BaseModel):
    """The point suggestions were measured from: the position this viewer may see."""

    lon: float
    lat: float
    obscured: bool
    # The 1 km square, such as `SU1069`, when the position is obscured.
    square: str | None


class SuggestedRecord(RecordHit):
    # Whether the record's type matches the finding's feature class.
    type_fit: bool
    score: float


class Suggestions(BaseModel):
    origin: Origin
    items: list[SuggestedRecord]


# --------------------------------------------------------------------------
# The search box
# --------------------------------------------------------------------------

GeoResultType = Literal["gridref", "coordinates", "finding", "place", "record"]


class GeoResult(BaseModel):
    """Something the map can fly to."""

    type: GeoResultType
    label: str
    detail: str | None = None
    lon: float
    lat: float
    # West, south, east, north, when the result is an area rather than a point.
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    zoom: int
    # The finding's public id or the record's id, for opening its page.
    ref: str | None = None
    obscured: bool = False
    # For a record: its source key, licence, attribution and reuse class.
    source: SourceRef | None = None


class GeoResults(BaseModel):
    items: list[GeoResult]


# --------------------------------------------------------------------------
# Context: what the browser queries and links to by itself (Decision 0007)
# --------------------------------------------------------------------------


class LiveSourceOut(BaseModel):
    key: str
    name: str
    publisher: str
    coverage: str
    endpoint: str
    query_pattern: str
    response_fields: str
    licence: str
    attribution: str
    link_template: str | None
    limits: str | None


class LiveSources(BaseModel):
    items: list[LiveSourceOut]


class ContextLink(BaseModel):
    key: str
    name: str
    url: str
    coverage: str
    # yes, redirect_only or not_tested, as the research found it on 2026-11-10.
    verified: str
    # The publisher forbids framing, so open it in a new tab.
    no_frame: bool


class ContextLinks(BaseModel):
    grid_ref: str | None
    items: list[ContextLink]


# --------------------------------------------------------------------------
# Building the shapes from service results
# --------------------------------------------------------------------------


def source_ref(source: Source) -> SourceRef:
    return SourceRef.model_validate(source)


def record_summary(result: RecordResult) -> RecordSummary:
    record = result.record
    return RecordSummary(
        id=record.id,
        source_key=record.source_key,
        name=record.name,
        category=record.category,
        record_type=record.record_type,
        lon=round(result.lon, 6),
        lat=round(result.lat, 6),
        precision_m=record.precision_m,
        url=record.url,
        source=source_ref(result.source),
    )


def record_hit(result: RecordResult) -> RecordHit:
    assert result.distance_m is not None, "a hit is measured from somewhere"
    return RecordHit(**record_summary(result).model_dump(), distance_m=round(result.distance_m, 1))


def record_out(result: RecordResult) -> RecordOut:
    record = result.record
    geometry = to_geojson(record.geom)
    assert geometry is not None, "records.geom is NOT NULL"
    return RecordOut(
        **record_summary(result).model_dump(),
        external_id=record.external_id,
        summary=record.summary,
        monument_types=list(record.monument_types or []),
        periods=list(record.periods or []),
        geometry=geometry,
        source_updated_at=record.source_updated_at,
        ingested_at=record.ingested_at,
    )


def record_feature(result: RecordResult) -> dict[str, Any]:
    """A record as a GeoJSON Feature for export. The licence travels with every feature (Decision 0004)."""
    record, source = result.record, result.source
    properties = {
        "id": record.id,
        "source_key": record.source_key,
        "external_id": record.external_id,
        "name": record.name,
        "category": record.category,
        "record_type": record.record_type,
        "url": record.url,
        "precision_m": record.precision_m,
        "licence": source.licence,
        "licence_url": source.licence_url,
        "attribution": source.attribution,
        "reuse": source.reuse,
    }
    if result.distance_m is not None:
        properties["distance_m"] = round(result.distance_m, 1)
    return feature(record.geom, properties, record.id)
