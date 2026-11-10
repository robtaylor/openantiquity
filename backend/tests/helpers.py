"""Small helpers and fixture types shared by many test files. Import by full path."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Point, box
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.config import CLIENT_HEADER, CLIENT_HEADER_VALUE, Settings
from fieldclub.models import AdminArea, Finding, Record, Source, User
from fieldclub.models.common import point_lon_lat as lon_lat
from fieldclub.models.common import to_db_geometry

# TestClient talks https so that Secure session cookies are sent back.
BASE_URL = "https://testserver"
# The header the web app sends with every request.
WEB = {CLIENT_HEADER: CLIENT_HEADER_VALUE}
# The henge at Avebury, where `make_finding` puts a finding by default.
AVEBURY = (-1.8542, 51.4286)

# The types of the factory fixtures in `tests/conftest.py`.
MakeUser = Callable[..., User]
MakeFinding = Callable[..., Finding]
ClientAs = Callable[[User], TestClient]
ClientFor = Callable[..., TestClient]

__all__ = [
    "AVEBURY",
    "BASE_URL",
    "WEB",
    "ClientAs",
    "ClientFor",
    "MakeFinding",
    "MakeUser",
    "add_record",
    "add_source",
    "admin_area",
    "count",
    "error_code",
    "lon_lat",
    "nested",
    "run_fresh",
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


def run_fresh(code: str) -> None:
    """Run Python `code` in a new interpreter, for what can only be seen before anything is imported."""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]


# --------------------------------------------------------------------------
# Rows made by hand
# --------------------------------------------------------------------------


def add_source(db: Session, key: str = "test-designations", **columns: Any) -> Source:
    """A flushed, enabled source of open designations. Any `Source` column can be passed."""
    values: dict[str, Any] = {
        "name": "Test designations",
        "publisher": "The test suite",
        "licence": "Open Government Licence v3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "attribution": "© The test suite 2026",
        "reuse": "open",
        "category": "designation",
        "access": "bulk",
        "enabled": True,
    } | columns
    source = Source(key=key, **values)
    db.add(source)
    db.flush()
    return source


def add_record(
    db: Session,
    source: Source,
    name: str,
    lon: float | None = None,
    lat: float | None = None,
    *,
    geom: BaseGeometry | None = None,
    external_id: str | None = None,
    **columns: Any,
) -> Record:
    """A flushed record. Give a point as `lon, lat`, or any shape as `geom`."""
    if geom is None:
        assert lon is not None, "give lon and lat, or geom"
        assert lat is not None, "give lon and lat, or geom"
        geom = Point(lon, lat)
    record = Record(
        source_key=source.key,
        external_id=external_id or f"{source.key}-{name}",
        name=name,
        category=columns.pop("category", source.category),
        geom=to_db_geometry(geom),
        centroid=to_db_geometry(geom.point_on_surface()),
        ingested_at=columns.pop("ingested_at", datetime(2026, 11, 10, tzinfo=UTC)),
        **columns,
    )
    db.add(record)
    db.flush()
    return record


def admin_area(kind: str, code: str, name: str, *boxes: tuple[float, float, float, float]) -> AdminArea:
    """An unsaved nation or county made of west, south, east, north boxes in degrees."""
    return AdminArea(
        kind=kind, code=code, name=name, geom=to_db_geometry(MultiPolygon([box(*b) for b in boxes]))
    )
