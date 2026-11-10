"""Everything a router usually needs, in one import.

from fieldclub.api.deps import Contributor, CurrentUser, Db, OptionalUser, PageQuery

A route that stores a contribution takes `Contributor`, which also refuses
anyone who hasn't finished the welcome step.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

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

AppSettings = Annotated[Settings, Depends(get_settings)]

# `limit` and `cursor` query parameters.
PageQuery = Annotated[PageParams, Query()]

__all__ = [
    "AppSettings",
    "Contributor",
    "CurrentUser",
    "Db",
    "OptionalUser",
    "PageQuery",
    "current_contributor",
    "current_user",
    "current_user_optional",
    "rate_limit",
    "require_role",
]
