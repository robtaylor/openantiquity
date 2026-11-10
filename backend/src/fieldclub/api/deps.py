"""Everything a router usually needs, in one import.

from fieldclub.api.deps import Contributor, CurrentUser, Db, OptionalUser, PageQuery

A route that stores a contribution takes `Contributor`, which also refuses
anyone who hasn't finished the welcome step.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Response

from fieldclub.auth.deps import (
    Contributor,
    CurrentUser,
    Db,
    OptionalUser,
    current_contributor,
    current_user,
    current_user_optional,
    require_role,
)
from fieldclub.config import Settings, get_settings
from fieldclub.ratelimit import rate_limit
from fieldclub.schemas.common import PageParams
from fieldclub.terrain.service import Terrain, get_terrain

AppSettings = Annotated[Settings, Depends(get_settings)]
TerrainDep = Annotated[Terrain, Depends(get_terrain)]

# `limit` and `cursor` query parameters.
PageQuery = Annotated[PageParams, Query()]
# A `cursor` alone, for a list whose limits differ from `PageQuery`'s. Its
# length is checked with everything else about it, as `invalid_cursor`.
CursorQuery = Annotated[str | None, Query()]
# A `bbox` parameter. Read it with `schemas.common.parse_bbox`, the one rule for a box.
BBoxQuery = Annotated[str | None, Query(max_length=200, description="west,south,east,north in degrees")]


# What a response that depends on the viewer is sent with. `main.PrivateByDefaultMiddleware`
# sends it for any response that sets no cache policy of its own.
PRIVATE_CACHE = "private, no-cache"


def private(response: Response) -> None:
    """What this response holds depends on the viewer, so no shared cache may keep it."""
    response.headers["Cache-Control"] = PRIVATE_CACHE
    response.headers["Vary"] = "Cookie"


def split_list(value: str | None) -> list[str] | None:
    """`a,b, c` as `["a", "b", "c"]`, or None when empty."""
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


__all__ = [
    "PRIVATE_CACHE",
    "AppSettings",
    "BBoxQuery",
    "Contributor",
    "CurrentUser",
    "CursorQuery",
    "Db",
    "OptionalUser",
    "PageQuery",
    "TerrainDep",
    "current_contributor",
    "current_user",
    "current_user_optional",
    "private",
    "rate_limit",
    "require_role",
    "split_list",
]
