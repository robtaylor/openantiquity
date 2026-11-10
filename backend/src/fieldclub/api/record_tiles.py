"""`/tiles/records/{z}/{x}/{y}.mvt`: the record index as vector tiles.

They sit outside `/api/v1` so a CDN can cache them by path.

The answer is the same for every viewer, because records carry no
sensitivity. Findings never go into tiles (Decision 0005).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response

from fieldclub.api.deps import Db
from fieldclub.api.records import split_list
from fieldclub.services import record_tiles

MOUNT_AT_ROOT = True

router = APIRouter(tags=["tiles"])

# Records change when a source is ingested, at most daily. An hour fresh and a
# day stale keeps the map quick and an ingest visible the same day.
CACHE_CONTROL = "public, max-age=3600, stale-while-revalidate=86400"


@router.get(
    "/tiles/records/{z}/{x}/{y}.mvt",
    response_class=Response,
    responses={200: {"content": {record_tiles.MEDIA_TYPE: {}}, "description": "A Mapbox vector tile"}},
)
def records_tile(
    db: Db,
    z: Annotated[int, Path(ge=0, le=record_tiles.MAX_ZOOM)],
    x: Annotated[int, Path(ge=0)],
    y: Annotated[int, Path(ge=0)],
    category: Annotated[
        str | None,
        Query(max_length=200, description="Comma-separated categories, such as `designation,find`"),
    ] = None,
) -> Response:
    """Counts by category on a grid below zoom 12, individual records from zoom 12 up."""
    tile = record_tiles.record_tile(db, z, x, y, split_list(category))
    return Response(tile, media_type=record_tiles.MEDIA_TYPE, headers={"Cache-Control": CACHE_CONTROL})
