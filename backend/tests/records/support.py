"""Sources and records made by hand for the record index tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy.orm import Session

from fieldclub.models import Record, Source
from fieldclub.models.common import to_db_geometry

# Silbury Hill's mound, and a point on Overton Hill 2.3 km east of it.
SILBURY = (-1.8574, 51.4156)
OVERTON = (-1.8240, 51.4100)


def add_source(db: Session, key: str = "test-designations", **columns: Any) -> Source:
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
    """A stored record. Give a point as `lon, lat`, or any shape as `geom`."""
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
