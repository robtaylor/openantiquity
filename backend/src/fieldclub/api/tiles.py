"""Terrain map tiles, mounted at the root so a CDN can cache them by path.

`GET /tiles/lidar/{style}/{z}/{x}/{y}.png` is a rendered visualisation and
`GET /tiles/dem/{z}/{x}/{y}.png` is elevation in Terrarium encoding, both 512
pixels. Every response carries an ETag.

The URLs in `/meta` carry `?v=`, a token of the style version, the elevation
format and the data editions (`render.tile_version`). A tile asked for with
the current token is sent as immutable, because anything that could change
it changes the token. Without the token, or with an old one, it is cached
for an hour. A tile drawn from a source that is still filling, such as the
mirror's overviews before the national composite exists, is never immutable:
it is sent `no-cache`, so a browser asks again and gets a 304 until it changes.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from starlette.responses import Response

from fieldclub.terrain.render import DEM_KIND, RenderedTile
from fieldclub.terrain.service import Terrain, get_terrain

MOUNT_AT_ROOT = True

# Left out of the OpenAPI schema: the frontend takes tile URLs from /meta, not
# from the generated client, and the schema documents the /api/v1 API.
router = APIRouter(prefix="/tiles", tags=["tiles"], include_in_schema=False)

IMMUTABLE = "public, max-age=31536000, immutable"
UNVERSIONED = "public, max-age=3600"
CHANGING = "no-cache"

TerrainDep = Annotated[Terrain, Depends(get_terrain)]
VersionParam = Annotated[str | None, Query(alias="v")]
IfNoneMatch = Annotated[str | None, Header()]


def cache_control(tile: RenderedTile, asked: str | None, current: str) -> str:
    if not tile.cacheable:
        return CHANGING
    return IMMUTABLE if asked == current else UNVERSIONED


def _png(tile: RenderedTile, cache: str, if_none_match: str | None) -> Response:
    etag = f'"{hashlib.sha256(tile.png).hexdigest()[:32]}"'
    headers = {"Cache-Control": cache, "ETag": etag}
    if if_none_match is not None and etag in {tag.strip() for tag in if_none_match.split(",")}:
        return Response(status_code=304, headers=headers)
    return Response(tile.png, media_type="image/png", headers=headers)


@router.get("/lidar/{style}/{z}/{x}/{y}.png", response_class=Response)
def lidar_tile(
    style: str,
    z: int,
    x: int,
    y: int,
    terrain: TerrainDep,
    v: VersionParam = None,
    if_none_match: IfNoneMatch = None,
) -> Response:
    """A terrain visualisation. Transparent where there is no elevation."""
    tile = terrain.renderer.lidar_png(style, z, x, y)
    return _png(tile, cache_control(tile, v, terrain.renderer.version(style)), if_none_match)


@router.get("/dem/{z}/{x}/{y}.png", response_class=Response)
def dem_tile(
    z: int,
    x: int,
    y: int,
    terrain: TerrainDep,
    v: VersionParam = None,
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Elevation in Terrarium encoding, opaque everywhere, sea level far from any data."""
    tile = terrain.renderer.dem_png(z, x, y)
    return _png(tile, cache_control(tile, v, terrain.renderer.version(DEM_KIND)), if_none_match)
