"""Terrain map tiles, mounted at the root so a CDN can cache them by path.

`GET /tiles/lidar/{style}/{z}/{x}/{y}.png` is a rendered visualisation and
`GET /tiles/dem/{z}/{x}/{y}.png` is elevation in Terrarium encoding, both 512
pixels. A tile never changes once made, because its cache key carries the
style version and the data edition, so it is sent as immutable with an ETag.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from starlette.responses import Response

from fieldclub.terrain.service import Terrain, get_terrain

MOUNT_AT_ROOT = True

# Left out of the OpenAPI schema: the frontend takes tile URLs from /meta, not
# from the generated client, and the schema documents the /api/v1 API.
router = APIRouter(prefix="/tiles", tags=["tiles"], include_in_schema=False)

CACHE_CONTROL = "public, max-age=31536000, immutable"

TerrainDep = Annotated[Terrain, Depends(get_terrain)]


def _png(data: bytes, if_none_match: str | None) -> Response:
    etag = f'"{hashlib.sha256(data).hexdigest()[:32]}"'
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    if if_none_match is not None and etag in {tag.strip() for tag in if_none_match.split(",")}:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="image/png", headers=headers)


@router.get("/lidar/{style}/{z}/{x}/{y}.png", response_class=Response)
def lidar_tile(
    style: str,
    z: int,
    x: int,
    y: int,
    terrain: TerrainDep,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """A terrain visualisation. Transparent where there is no elevation."""
    return _png(terrain.renderer.lidar_png(style, z, x, y), if_none_match)


@router.get("/dem/{z}/{x}/{y}.png", response_class=Response)
def dem_tile(
    z: int,
    x: int,
    y: int,
    terrain: TerrainDep,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """Elevation in Terrarium encoding, opaque everywhere, sea level where there is no data."""
    return _png(terrain.renderer.dem_png(z, x, y), if_none_match)
