"""Places, fixtures and a second source for the record index tests.

`add_source` and `add_record` are in `tests.helpers`.
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import respx
from shapely.geometry import Point
from sqlalchemy.orm import Session

from fieldclub.ingest.connectors.he_nhle_scheduled_monuments import HUB_EXPORT
from fieldclub.models import Source
from tests.helpers import add_source
from tests.ingest.adapters.support import FIXTURES

# Silbury Hill's mound, and a point on Overton Hill 2.3 km east of it.
SILBURY = (-1.8574, 51.4156)
OVERTON = (-1.8240, 51.4100)
# Silbury Hill as an area rather than a point, about 100 m across.
SILBURY_MOUND = Point(*SILBURY).buffer(0.001)

# Eight scheduled monuments cut from the Open Data Hub export of 2026-11-10.
MONUMENTS_GPKG = FIXTURES / "scheduled_monuments.gpkg"
EXPORT_FILE = "https://export.example/National_Heritage_List_for_England_NHLE_v02_VIEW_1.gpkg"


def serve_hub(body: bytes) -> respx.Route:
    """The Hub's 302 to a short-lived export file, and the file. Call it inside `respx.mock`."""
    respx.get(EXPORT_FILE).mock(
        return_value=httpx.Response(
            200, content=body, headers={"ETag": '"0x1"', "Content-Length": str(len(body))}
        )
    )
    return respx.get(HUB_EXPORT).mock(return_value=httpx.Response(302, headers={"Location": EXPORT_FILE}))


def tile_of(lon: float, lat: float, z: int) -> tuple[int, int]:
    """The Web Mercator tile holding a point."""
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def add_finds_source(db: Session, **columns: Any) -> Source:
    """A second source, of finds, whose records may not be reused commercially."""
    values: dict[str, Any] = {"name": "Test finds", "category": "find", "reuse": "non_commercial"} | columns
    return add_source(db, "test-finds", **values)
