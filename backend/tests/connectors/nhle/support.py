"""Fixtures and a mock Hub for the National Heritage List connectors.

The fixtures in `fixtures/` were recorded on 2026-11-10 from Historic England's
Open Data Hub. Each source's export was downloaded once through the connector's
own address (`hub_export_url`), politely: one request at a time, a second
apart, 202 "ExportingData" answers waited out. The download was then cut down
to a few rows with sqlite, so the rows keep their original bytes. Spatial
indexes were dropped from the cut files, and nothing else was changed.

| Fixture | Source | Rows kept |
|---|---|---|
| `listed_buildings_points.gpkg` | NHLE layer 0 | six, four near Avebury and two elsewhere |
| `listed_buildings_polygons.gpkg` | NHLE layer 3 | three with an `area_ha` and three 2.5 m placeholders |
| `bpn_points.gpkg`, `bpn_polygons.gpkg` | layers 1 and 4 | all six notices |
| `coi_points.gpkg`, `coi_polygons.gpkg` | layers 2 and 5 | three, two of them one entry in two places |
| `parks_and_gardens.gpkg` | layer 7 | the first four by list entry |
| `battlefields.gpkg` | layer 8 | the first three |
| `wreck_sites.gpkg` | layer 9 | the first three |
| `world_heritage_sites.gpkg` | layer 10 | four rows for three sites |
| `conservation_areas.gpkg` | Conservation Areas item, layer 0 | seven, two with no name |

Everything in them is published openly by Historic England. None of it is
personal data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import respx

FIXTURES = Path(__file__).parent / "fixtures"
WORKLIST = Path(__file__).parents[4] / "docs" / "sources" / "worklists" / "sources.json"
EXPORT_FILE = "https://export.example/nhle_layer.gpkg"


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def serve_export(url: str, body: bytes) -> respx.Route:
    """The Hub's 302 to a short-lived export file, and the file. Call it inside `respx.mock`."""
    respx.get(EXPORT_FILE).mock(
        return_value=httpx.Response(
            200, content=body, headers={"ETag": '"0x1"', "Content-Length": str(len(body))}
        )
    )
    return respx.get(url).mock(return_value=httpx.Response(302, headers={"Location": EXPORT_FILE}))


def changed_copy(fixture: str, destination: Path, sql: str) -> bytes:
    """The fixture after `sql` has been run against its one table, whose name is `{table}`."""
    destination.write_bytes((FIXTURES / fixture).read_bytes())
    with sqlite3.connect(destination) as conn:
        (table,) = conn.execute("SELECT table_name FROM gpkg_contents").fetchone()
        conn.executescript(sql.format(table=table))
    return destination.read_bytes()
