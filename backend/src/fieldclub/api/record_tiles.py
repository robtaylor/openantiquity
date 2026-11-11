"""`/tiles/records/{z}/{x}/{y}.mvt`: the record index as vector tiles.

They sit outside `/api/v1` so a CDN can cache them by path.

The answer is the same for every viewer, because records carry no
sensitivity. Findings never go into tiles (Decision 0005).

As with terrain tiles, every response carries an ETag, and a tile asked for
with the current `?v=` token (`record_tiles.tile_token`, in the address
`/meta` gives) is sent as immutable, unless an ingest run is still going.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from fieldclub.api.deps import Db, IfNoneMatch, body_etag, not_modified, split_list
from fieldclub.services import record_tiles

MOUNT_AT_ROOT = True

router = APIRouter(tags=["tiles"])


@router.get(
    "/tiles/records/{z}/{x}/{y}.mvt",
    response_class=Response,
    responses={200: {"content": {record_tiles.MEDIA_TYPE: {}}, "description": "A Mapbox vector tile"}},
)
def records_tile(
    db: Db,
    z: int,
    x: int,
    y: int,
    category: Annotated[
        str | None,
        Query(max_length=200, description="Comma-separated categories, such as `designation,find`"),
    ] = None,
    v: Annotated[str | None, Query(max_length=64, description="The token from /meta")] = None,
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Counts by category on a grid below zoom 12, individual records from zoom 12 up."""
    tile = record_tiles.record_tile(db, z, x, y, split_list(category))
    version = record_tiles.tile_version(db)
    current = v is not None and v == version.token and version.settled
    headers = {
        "Cache-Control": record_tiles.IMMUTABLE_CACHE if current else record_tiles.UNVERSIONED_CACHE,
        "ETag": body_etag(tile),
    }
    return not_modified(if_none_match, headers) or Response(
        tile, media_type=record_tiles.MEDIA_TYPE, headers=headers
    )
