"""`GET /geo/search`: the map's search box."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from fieldclub.api.deps import Db, OptionalUser
from fieldclub.schemas.records import GeoResult, GeoResults
from fieldclub.services import records, search

router = APIRouter(tags=["geo"])


@router.get("/geo/search", response_model=GeoResults)
def geo_search(
    db: Db,
    viewer: OptionalUser,
    q: Annotated[str, Query(min_length=1, max_length=records.MAX_QUERY_CHARS)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> GeoResults:
    """A grid reference, coordinates, a finding's id, a place or a record, as places the map can fly to."""
    hits = search.geo_search(db, q, viewer, limit=limit)
    return GeoResults(
        items=[
            GeoResult(
                type=hit.type,
                label=hit.label,
                detail=hit.detail,
                lon=round(hit.lon, 6),
                lat=round(hit.lat, 6),
                bbox=[round(value, 6) for value in hit.bbox] if hit.bbox else None,
                zoom=hit.zoom,
                ref=hit.ref,
                obscured=hit.obscured,
            )
            for hit in hits
        ]
    )
