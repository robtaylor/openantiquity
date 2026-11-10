"""A stand-in for an ArcGIS server that answers from a recorded fixture, and what the land tests share.

The fixtures in `fixtures/` were recorded from the live services on 2026-11-10,
a handful of requests each with a second between them, as the `recorded` text in
each says. A fixture holds, for every layer, the metadata the reader relies on
(`name`, `geometryType`, `objectIdField`, `maxRecordCount`, the fields and
whether the layer pages) and the features as the server gave them with
`outSR=4326`, so the geometry is in WGS84.

`RecordedService` answers the reader's requests the way the server does:
a count, a page by offset ordered by object id, and the filters the connectors
use, a box and a `MonUID IN (...)` list. Nothing in these tests calls a live service.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import respx
import shapely
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest.adapters.arcgis import esri_geometry
from fieldclub.ingest.adapters.common import Polite
from fieldclub.models import Record
from tests.ingest.adapters.support import NoWait

FIXTURES = Path(__file__).parent / "fixtures"
WORKLIST = Path(__file__).parents[4] / "docs" / "sources" / "worklists" / "sources.json"
OID_TYPE = "esriFieldTypeOID"


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def no_wait() -> Polite:
    """A `Polite` that doesn't wait, for a connector's `polite` attribute."""
    return NoWait()


class RecordedService:
    """Serves the layers of one fixture. `fixture` may be changed before a test runs it.

    `short_offset_pages` makes a page asked for by offset come back with one feature, though
    more remain, and `phantom_ids` adds object ids that no feature has to a layer's id list.
    Together they are what York's area layer does: it is a view of every kind of shape, so
    its offsets count rows the layer then hides.
    """

    def __init__(self, name: str) -> None:
        self.fixture: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        self.queries: list[dict[str, str]] = []
        self.short_offset_pages = False
        self.phantom_ids: dict[str, list[int]] = {}

    @property
    def layers(self) -> dict[str, dict[str, Any]]:
        return self.fixture["layers"]

    def mount(self, host: str) -> respx.Route:
        """Route every request to `host` here. Call it inside `respx.mock`."""
        return respx.route(host=host).mock(side_effect=self)

    def oid_field(self, layer: dict[str, Any]) -> str:
        info = layer["info"]
        return str(
            info.get("objectIdField") or next(f["name"] for f in info["fields"] if f["type"] == OID_TYPE)
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        assert params.pop("f") == "json"
        parts = request.url.path.rstrip("/").split("/")
        is_query = parts[-1] == "query"
        number = parts[-2] if is_query else parts[-1]
        layer = self.layers[number]
        if not is_query:
            return httpx.Response(200, json=layer["info"])
        self.queries.append(params)
        oid = self.oid_field(layer)
        found = sorted(self.matching(layer, params, oid), key=lambda feature: feature["attributes"][oid])
        if params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": len(found)})
        if params.get("returnIdsOnly") == "true":
            ids = [feature["attributes"][oid] for feature in found] + self.phantom_ids.get(number, [])
            return httpx.Response(200, json={"objectIdFieldName": oid, "objectIds": sorted(ids)})
        assert params["outSR"] == "4326"
        offset = int(params.get("resultOffset", 0))
        size = int(params.get("resultRecordCount", len(found)))
        page = found[offset : offset + size]
        if "resultOffset" in params and self.short_offset_pages:
            page = page[:1]
        body = {
            "spatialReference": {"wkid": 4326, "latestWkid": 4326},
            "features": page,
            "exceededTransferLimit": offset + size < len(found),
        }
        return httpx.Response(200, json=body)

    @staticmethod
    def matching(layer: dict[str, Any], params: dict[str, str], oid: str) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = layer["features"]
        where = params["where"]
        # A range of object ids, as the reader asks for one: (<where>) AND OID >= 3 AND OID <= 9.
        ranged = re.fullmatch(rf"\((.*)\) AND {oid} >= (\d+) AND {oid} <= (\d+)", where)
        if ranged:
            low, high = int(ranged.group(2)), int(ranged.group(3))
            inner = RecordedService.matching(layer, params | {"where": ranged.group(1)}, oid)
            return [f for f in inner if low <= f["attributes"][oid] <= high]
        if where != "1=1":
            match = re.fullmatch(r"MonUID IN \((.*)\)", where)
            assert match, f"the recorded service does not understand {where!r}"
            wanted = set(re.findall(r"'([^']+)'", match.group(1)))
            features = [f for f in features if f["attributes"]["MonUID"] in wanted]
        if "geometry" in params:
            assert params["geometryType"] == "esriGeometryEnvelope"
            assert params["inSR"] == "4326"
            west, south, east, north = (float(value) for value in params["geometry"].split(","))
            area = box(west, south, east, north)
            features = [f for f in features if shapely.intersects(esri_geometry(f["geometry"]), area)]
        return features


def rows(db: Session) -> list[tuple[Any, ...]]:
    """Every stored record, without the columns a run is expected to change."""
    db.expire_all()
    found = db.scalars(select(Record).order_by(Record.source_key, Record.external_id)).all()
    return [
        (
            record.id,
            record.source_key,
            record.external_id,
            record.name,
            record.category,
            record.record_type,
            record.monument_types,
            record.periods,
            record.summary,
            record.url,
            record.precision_m,
            record.source_updated_at,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in found
    ]
