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
from fieldclub.schemas.common import MAX_CURSOR_CHARS, PageParams
from fieldclub.terrain.service import Terrain, get_terrain

AppSettings = Annotated[Settings, Depends(get_settings)]
TerrainDep = Annotated[Terrain, Depends(get_terrain)]

# `limit` and `cursor` query parameters.
PageQuery = Annotated[PageParams, Query()]
# A `cursor` alone, for a list whose limits differ from `PageQuery`'s.
CursorQuery = Annotated[str | None, Query(max_length=MAX_CURSOR_CHARS)]


def private(response: Response) -> None:
    """What this response holds depends on the viewer, so no shared cache may keep it."""
    response.headers["Cache-Control"] = "private, no-cache"
    response.headers["Vary"] = "Cookie"


def split_list(value: str | None) -> list[str] | None:
    """`a,b, c` as `["a", "b", "c"]`, or None when empty."""
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


__all__ = [
    "AppSettings",
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
