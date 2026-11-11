"""Shapes for the record index, the geo search box and the context catalogue.

Every record leaves the API with its source key and a `source` that carries
the licence, the attribution and the reuse class (Decision 0004), so whoever
shows or copies a record has what its licence requires.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from fieldclub.schemas.common import ApiModel, GeoJSONFeature, RecordCount, geojson_geometry, to_geojson
from fieldclub.vocab import LinkShows, LiveFormat

if TYPE_CHECKING:
    from fieldclub.models import Source
    from fieldclub.services.records import RecordResult, Suggestion


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
    record_count: RecordCount
    last_ingest_at: datetime | None


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


class LinkedFinding(BaseModel):
    """A finding whose evidence links a record, as listed on the record's page.

    Only findings the viewer sees exactly are listed, so none is obscured.
    """

    public_id: str
    title: str
    feature_class: str
    tier: str
    state: str


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


class LiveSource(BaseModel):
    """A source the browser queries itself, with how to ask, how to read the answer and how to credit it."""

    key: str
    name: str
    publisher: str
    coverage: str
    endpoint: str
    # `{west}`, `{south}`, `{east}` and `{north}` (or `{lat}` and `{lon}`, or `{id}`) are filled in
    # by the browser. It carries no cap: add `limit_param` for that.
    query_pattern: str
    response_fields: str
    licence: str
    attribution: str
    link_template: str | None
    limits: str | None
    answer_format: LiveFormat
    # Dot paths inside one item of the answer to the record's identifier and
    # its name. Null where the research didn't name the field.
    id_field: str | None
    name_field: str | None
    # The query parameter that caps how many come back, and the most it takes.
    limit_param: str | None
    max_limit: int | None
    # The lowest map zoom at which to ask, so one viewport's answer stays
    # under the cap. Null for a request by record id.
    min_zoom: int | None


class LiveSources(BaseModel):
    items: list[LiveSource]


class ContextLink(BaseModel):
    key: str
    name: str
    url: str
    coverage: str
    # What the viewer shows at the place.
    shows: LinkShows
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


def _summary_fields(result: RecordResult) -> dict[str, Any]:
    """The `RecordSummary` fields of a result, for it and every shape built on it."""
    record = result.record
    return {
        "id": record.id,
        "source_key": record.source_key,
        "name": record.name,
        "category": record.category,
        "record_type": record.record_type,
        "lon": round(result.lon, 6),
        "lat": round(result.lat, 6),
        "precision_m": record.precision_m,
        "url": record.url,
        "source": source_ref(result.source),
    }


def _distance(result: RecordResult) -> float:
    assert result.distance_m is not None, "a hit is measured from somewhere"
    return round(result.distance_m, 1)


def record_summary(result: RecordResult) -> RecordSummary:
    return RecordSummary(**_summary_fields(result))


def record_hit(result: RecordResult) -> RecordHit:
    return RecordHit(**_summary_fields(result), distance_m=_distance(result))


def record_suggestion(suggestion: Suggestion) -> SuggestedRecord:
    result = suggestion.result
    return SuggestedRecord(
        **_summary_fields(result),
        distance_m=_distance(result),
        type_fit=suggestion.type_fit,
        score=suggestion.score,
    )


def record_out(result: RecordResult) -> RecordOut:
    record = result.record
    geometry = to_geojson(record.geom)
    assert geometry is not None, "records.geom is NOT NULL"
    return RecordOut(
        **_summary_fields(result),
        external_id=record.external_id,
        summary=record.summary,
        monument_types=list(record.monument_types or []),
        periods=list(record.periods or []),
        geometry=geometry,
        source_updated_at=record.source_updated_at,
        ingested_at=record.ingested_at,
    )


def record_feature(result: RecordResult) -> GeoJSONFeature:
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
    return GeoJSONFeature(id=record.id, geometry=geojson_geometry(record.geom), properties=properties)
