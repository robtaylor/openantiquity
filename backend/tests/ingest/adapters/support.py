"""Shared by the adapter tests: the recorded fixtures and a `Polite` that never waits.

The fixtures in `fixtures/` were recorded from the live services on
2026-11-10 with a handful of requests each:

- `arcgis_*.json`: Historic England's NHLE FeatureServer layer 6 (scheduled
  monuments), for the box -1.865,51.41,-1.84,51.42 around Silbury Hill, two
  features a page, `geometryPrecision=6`.
- `scheduled_monuments.gpkg`: the Open Data Hub GeoPackage export of the same
  layer, cut down to eight monuments with sqlite so the rows keep their
  original bytes, including the oddly written date on list entry 1008099.
- `wfs_*`: the Welsh Government's GeoServer, `inspire-wg:Cadw_SAM`, in the box
  270000,200000,276000,206000 (EPSG:27700), two a page, sorted by RecordNumber.
- `sparql_*`: three hillforts with NHLE numbers from the Wikidata endpoint.
- `lincs.csv`: the first rows of Lincolnshire HER's monuments export.
- `itinere.ndjson`: the first three lines of the Itiner-e route segment export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fieldclub.ingest.adapters.common import Polite

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class NoWait(Polite):
    """A `Polite` that records the sleeps it would have taken instead of taking them."""

    def __init__(self, **kwargs: Any) -> None:
        self.slept: list[float] = []
        super().__init__(sleep=self.slept.append, **kwargs)


def xy(geometry: object) -> tuple[float, float]:
    """Longitude and latitude of what must be a point."""
    from shapely.geometry import Point

    assert isinstance(geometry, Point), f"expected a point, got {geometry!r}"
    return geometry.x, geometry.y
