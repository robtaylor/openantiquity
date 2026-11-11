"""A pretend ArcGIS server for Historic England's layers, answering from the recorded fixtures.

The fixtures in `fixtures/` were recorded from the live FeatureServers on 2026-11-10 by
`record_fixtures.py`, which says how: the layer's metadata, and one page of features in
WGS84 at six decimal places (four for project areas), ordered by object id, chosen by the
`where` and box it lists. Each fixture file holds the layer metadata (`info`) and those
features. `RecordedLayer` answers metadata, count and paged queries from them the way the
live server does, including the box filter, so a connector runs through the real adapter,
the real runner and a real database, and no test calls the service.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import respx
from pyproj import Transformer
from shapely.geometry import box

from fieldclub.ingest.adapters.arcgis import esri_geometry

FIXTURES = Path(__file__).parent / "fixtures"
WORKLIST = Path(__file__).parents[4] / "docs" / "sources" / "worklists" / "sources.json"
HOST = "services-eu1.arcgis.com"


GRID = Transformer.from_crs(4326, 27700, always_xy=True)


def on_grid(geometry: dict[str, Any] | None, decimals: int) -> dict[str, Any] | None:
    """An Esri geometry recorded in WGS84 as outSR=27700 gives it, rounded as geometryPrecision does."""
    if geometry is None:
        return None

    def move(point: list[float]) -> list[float]:
        east, north = GRID.transform(point[0], point[1])
        return [round(east, decimals), round(north, decimals)]

    if "x" in geometry:
        east, north = move([geometry["x"], geometry["y"]])
        return {"x": east, "y": north}
    for key in ("rings", "paths"):
        if key in geometry:
            return {key: [[move(point) for point in part] for part in geometry[key]]}
    raise AssertionError(f"unknown Esri geometry {sorted(geometry)}")


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def fixture(key: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))


class RecordedLayer:
    """Answers like the layer a fixture was recorded from. `queries` lists what was asked."""

    def __init__(self, key: str, *, count_adds: int = 0) -> None:
        self.recorded = fixture(key)
        self.info = copy.deepcopy(self.recorded["info"])
        self.features: list[dict[str, Any]] = self.recorded["features"]
        # Makes the count promise more than the pages hold, as a layer that is cut short does.
        self.count_adds = count_adds
        self.queries: list[dict[str, str]] = []

    def inside(self, bbox: str | None) -> list[dict[str, Any]]:
        if bbox is None:
            return self.features
        west, south, east, north = (float(part) for part in bbox.split(","))
        area = box(west, south, east, north)
        found = []
        for feature in self.features:
            geometry = esri_geometry(feature["geometry"])
            if geometry is not None and area.intersects(geometry):
                found.append(feature)
        return found

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        assert params.pop("f") == "json"
        if not request.url.path.endswith("/query"):
            return httpx.Response(200, json=self.info)
        self.queries.append(params)
        matching = self.inside(params.get("geometry"))
        if params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": len(matching) + self.count_adds})
        offset = int(params.get("resultOffset", "0"))
        size = int(params["resultRecordCount"])
        page = matching[offset : offset + size]
        if params["outSR"] == "27700":
            decimals = int(params["geometryPrecision"])
            page = [{**item, "geometry": on_grid(item["geometry"], decimals)} for item in page]
            reference = {"wkid": 27700, "latestWkid": 27700}
        else:
            assert params["outSR"] == "4326", "connectors ask for WGS84 or the British National Grid"
            reference = self.recorded["spatialReference"]
        return httpx.Response(200, json={"spatialReference": reference, "features": page})


def serve(key: str, **kwargs: Any) -> RecordedLayer:
    """Serve the fixture for `key`. Call it inside `respx.mock`."""
    layer = RecordedLayer(key, **kwargs)
    respx.route(host=HOST).mock(side_effect=layer)
    return layer
