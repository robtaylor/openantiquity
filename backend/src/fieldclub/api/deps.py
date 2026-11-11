"""Everything a router usually needs, in one import.

from fieldclub.api.deps import Contributor, CurrentUser, Db, OptionalUser, PageQuery

A route that stores a contribution takes `Contributor`, which also refuses
anyone who hasn't finished the welcome step.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, Query, Response

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
# The `If-None-Match` header a cached copy is checked with, for `not_modified`.
IfNoneMatch = Annotated[str | None, Header()]


# What a response that depends on the viewer is sent with. `main.PrivateByDefaultMiddleware`
# sends it for any response that sets no cache policy of its own.
PRIVATE_CACHE = "private, no-cache"


# What a read that is the same for every viewer is sent with, when a few
# minutes' delay in what it shows does no harm.
SHARED_CACHE = "public, max-age=300"


def shared(response: Response) -> None:
    """This response is the same for every viewer, so any cache may keep it for a few minutes."""
    response.headers["Cache-Control"] = SHARED_CACHE


def private(response: Response) -> None:
    """What this response holds depends on the viewer, so no shared cache may keep it."""
    response.headers["Cache-Control"] = PRIVATE_CACHE
    response.headers["Vary"] = "Cookie"


def body_etag(body: bytes) -> str:
    """A strong ETag for a response body: a hash of its bytes."""
    return f'"{hashlib.sha256(body).hexdigest()[:32]}"'


def not_modified(if_none_match: str | None, headers: dict[str, str]) -> Response | None:
    """An empty 304 with `headers` when `If-None-Match` names their ETag, so the copy held is current.

    None when the body has to be sent. `headers` carries the ETag and the cache
    policy, which a 304 repeats so a cache keeps both.
    """
    assert "ETag" in headers, "a 304 is only for a response with an ETag"
    if if_none_match is None:
        return None
    if headers["ETag"] not in {tag.strip() for tag in if_none_match.split(",")}:
        return None
    return Response(status_code=304, headers=headers)


def split_list(value: str | None) -> list[str] | None:
    """`a,b, c` as `["a", "b", "c"]`, or None when empty."""
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


__all__ = [
    "PRIVATE_CACHE",
    "SHARED_CACHE",
    "AppSettings",
    "BBoxQuery",
    "Contributor",
    "CurrentUser",
    "CursorQuery",
    "Db",
    "IfNoneMatch",
    "OptionalUser",
    "PageQuery",
    "TerrainDep",
    "body_etag",
    "current_contributor",
    "current_user",
    "current_user_optional",
    "not_modified",
    "private",
    "rate_limit",
    "require_role",
    "shared",
    "split_list",
]
