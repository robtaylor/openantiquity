"""Small helpers and fixture types shared by many test files. Import by full path."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.config import CLIENT_HEADER, CLIENT_HEADER_VALUE, Settings
from fieldclub.models import Finding, User
from fieldclub.models.common import point_lon_lat as lon_lat

# TestClient talks https so that Secure session cookies are sent back.
BASE_URL = "https://testserver"
# The header the web app sends with every request.
WEB = {CLIENT_HEADER: CLIENT_HEADER_VALUE}

# The types of the factory fixtures in `tests/conftest.py`.
MakeUser = Callable[..., User]
MakeFinding = Callable[..., Finding]
ClientAs = Callable[[User], TestClient]
ClientFor = Callable[..., TestClient]

__all__ = [
    "BASE_URL",
    "WEB",
    "ClientAs",
    "ClientFor",
    "MakeFinding",
    "MakeUser",
    "count",
    "error_code",
    "lon_lat",
    "nested",
    "settings",
]


class _JsonResponse(Protocol):
    def json(self, **kwargs: Any) -> Any: ...


def error_code(response: _JsonResponse) -> str:
    """The `error.code` of an error response."""
    return response.json()["error"]["code"]


def count(db: Session, model: type) -> int:
    """How many rows the table behind `model` holds."""
    return db.scalar(select(func.count()).select_from(model)) or 0


def nested(depth: int, leaf: Any = 1) -> Any:
    """`leaf` inside `depth` levels of dict, so `nested(2)` is `{"a": {"a": 1}}`."""
    value = leaf
    for _ in range(depth):
        value = {"a": value}
    return value


def settings(**values: object) -> Settings:
    """Settings from `values` and the environment, ignoring any `.env` file."""
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]
