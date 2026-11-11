"""Records the fixtures in `fixtures/` from Historic England's live ArcGIS services.

Run from `backend/` with `uv run python -m tests.connectors.he.record_fixtures`. It makes
a few requests per source, one at a time with the project's polite delay: the layer's
metadata, then a handful of features in WGS84 at six decimal places (four for project areas) for
each query below, ordered by object id. The queries are chosen to show the quirks worked
out in the connectors' notes, such as features with no monument number. Their features are
merged into one fixture file in object id order.

The fixtures were recorded on 2026-11-10. Nothing in them is personal data: the layers hold
monument outlines, report titles and the names of designated places.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from fieldclub import http
from fieldclub.ingest.adapters.common import Polite

HOST = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services"
FIXTURES = Path(__file__).parent / "fixtures"
# Layer metadata keys the readers use. The rest is drawing instructions and bulk.
INFO_KEYS = (
    "name",
    "type",
    "geometryType",
    "objectIdField",
    "maxRecordCount",
    "fields",
    "advancedQueryCapabilities",
    "copyrightText",
)
AIM = "HE_AIM_data/FeatureServer"
STONEHENGE = "-1.84,51.16,-1.80,51.19"

# One query: where, box in WGS84 or None, how many features.
Query = tuple[str, str | None, int]
# key: (layer path, queries, other query parameters). The features of every query are merged,
# in object id order, as one page.
RECORDINGS: dict[str, tuple[str, list[Query], dict[str, str]]] = {
    "he-aim-detailed-mapping": (
        f"{AIM}/0",
        [
            ("1=1", STONEHENGE, 4),
            # Features with no monument number, which are most of the layer.
            ("HE_UID = ' NONE GIVEN' AND LAYER = 'RIDGE_AND_FURROW_AREA'", None, 2),
            ("LAYER = 'DITCH' AND PERIOD = 'MEDIEVAL\\POST MEDIEVAL'", None, 3),
            ("LAYER = 'STRUCTURE' AND PERIOD = 'SECOND WORLD WAR'", None, 2),
        ],
        {},
    ),
    "he-aim-monument-extents": (f"{AIM}/1", [("1=1", STONEHENGE, 3)], {}),
    "he-aim-project-areas": (f"{AIM}/2", [("1=1", None, 3)], {"geometryPrecision": "4"}),
    "he-heritage-at-risk-2026": (
        "HAR_2026_OTHR_WGS84/FeatureServer/0",
        [("HeritageCa IN ('Scheduled Monument','Registered Park and Garden')", "-1.9,51.4,-1.8,51.45", 6)],
        {},
    ),
    "he-research-spatial-reports": (
        "Historic_England_Research_Spatial_Reports/FeatureServer/475",
        [("1=1", "-1.9,51.4,-1.8,51.45", 8)],
        {},
    ),
    "he-de-designated-sites": (
        "Delisted/FeatureServer/0",
        [("1=1", None, 4), ("HERITAGECATEGORYDESCRIPTION = 'Scheduling'", None, 2)],
        {},
    ),
    "he-greater-london-apas": (
        "Greater_London___Archaeological_Priority_Areas/FeatureServer/0",
        [("1=1", None, 6)],
        {},
    ),
    "he-turning-the-plough-2": ("Turning_the_Plough_2_/FeatureServer/0", [("1=1", None, 6)], {}),
}


def record(key: str, polite: Polite) -> None:
    path, queries, extra = RECORDINGS[key]
    url = f"{HOST}/{path}"
    client = http.get_client()
    info = polite.request(client, "GET", url, params={"f": "json"}).json()
    features: dict[int, dict[str, Any]] = {}
    reference = None
    for where, box, count in queries:
        params: dict[str, Any] = {
            "where": where,
            "outFields": "*",
            "outSR": "4326",
            "returnGeometry": "true",
            "geometryPrecision": "6",
            "orderByFields": info["objectIdField"],
            "resultRecordCount": str(count),
            "f": "json",
        } | extra
        if box:
            params |= {
                "geometry": box,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        page = polite.request(client, "GET", f"{url}/query", params=params).json()
        reference = reference or page.get("spatialReference")
        for feature in page["features"]:
            features[feature["attributes"][info["objectIdField"]]] = feature
    fixture = {
        "recorded": "2026-11-10",
        "layer": path,
        "queries": [{"where": where, "box": box, "count": count} for where, box, count in queries],
        "info": {name: info[name] for name in INFO_KEYS if name in info},
        "spatialReference": reference,
        "features": [features[oid] for oid in sorted(features)],
    }
    (FIXTURES / f"{key}.json").write_text(json.dumps(fixture, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    polite = Polite()
    for source_key in sys.argv[1:] or RECORDINGS:
        record(source_key, polite)
