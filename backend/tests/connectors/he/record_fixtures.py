"""Records the fixtures in `fixtures/` from Historic England's live ArcGIS services.

Run from `backend/` with `uv run python -m tests.connectors.he.record_fixtures`. It makes
a few requests per source, one at a time with the project's polite delay: the layer's
metadata, then a handful of features in WGS84 at six decimal places (four for project areas) for
each query below, ordered by object id. The queries are chosen to show the quirks worked
out in the connectors' notes, such as features with no monument number. Their features are
merged into one fixture file in object id order.

`he-aim-detailed-mapping.gpkg` is cut from the Hub's GeoPackage export instead: run
`uv run python -m tests.connectors.he.record_fixtures --cut-detailed-mapping <export path>`.

The fixtures were recorded on 2026-11-10. Nothing in them is personal data: the layers hold
monument outlines, report titles and the names of designated places.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

from fieldclub import http
from fieldclub.ingest.adapters import ogr
from fieldclub.ingest.adapters.common import Polite, bbox_from_wgs84

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


# What `he-aim-detailed-mapping.gpkg` keeps of the export: a few features for each of these queries (a
# `where` and a WGS84 box). Bell barrows at Stonehenge; ridge and furrow with no monument number; medieval
# and post-medieval ditches; a Second World War structure; two features whose type, period and evidence
# are all "NO MONUMENT RECORD"; and one with a mangled term, `POND70449`.
DETAILED_QUERIES: list[tuple[str | None, tuple[float, float, float, float] | None, int]] = [
    ("HE_UID <> ' NONE GIVEN'", (-1.84, 51.16, -1.80, 51.19), 4),
    ("HE_UID = ' NONE GIVEN' AND LAYER = 'RIDGE_AND_FURROW_AREA'", None, 2),
    ("LAYER = 'DITCH' AND PERIOD = 'MEDIEVAL\\POST MEDIEVAL'", None, 2),
    ("LAYER = 'STRUCTURE' AND PERIOD = 'SECOND WORLD WAR'", None, 2),
    ("MONUMENT_TYPE LIKE '%NO MONUMENT RECORD%'", None, 2),
    ("MONUMENT_TYPE LIKE '%POND70449%'", None, 1),
]


def cut_detailed_mapping(export: Path) -> None:
    """Writes `he-aim-detailed-mapping.gpkg` from the Hub's 4.7 GB GeoPackage export of layer 0.

    The export is downloaded by running the connector (`uv run fieldclub-ingest run
    he-aim-detailed-mapping`), which keeps it at `var/ingest/he-aim-detailed-mapping/detailed-mapping.gpkg`.
    The features' values and geometry are copied as they are, in EPSG:27700. This makes no requests.
    """
    geometries: list[Any] = []
    columns: list[list[Any]] | None = None
    names: list[str] = []
    crs = ""
    for where, box, count in DETAILED_QUERIES:
        meta, _, geometry, fields = ogr.read(
            str(export),
            where=where,
            bbox=bbox_from_wgs84(box, "EPSG:27700") if box else None,
            max_features=count,
            return_fids=True,
        )
        names, crs = list(meta["fields"]), meta["crs"]
        geometries.extend(geometry)
        columns = (
            [list(old) + list(new) for old, new in zip(columns, fields, strict=True)]
            if columns
            else [list(f) for f in fields]
        )
    assert columns is not None
    target = FIXTURES / "he-aim-detailed-mapping.gpkg"
    target.unlink(missing_ok=True)
    ogr.write(
        str(target),
        np.array(geometries, dtype=object),
        [np.array(column, dtype=object) for column in columns],
        names,
        layer="Detailed_Mapping",
        driver="GPKG",
        geometry_type="MultiPolygon Z",
        crs=crs,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    polite = Polite()
    if sys.argv[1:2] == ["--cut-detailed-mapping"]:
        cut_detailed_mapping(Path(sys.argv[2]))
        sys.exit()
    for source_key in sys.argv[1:] or RECORDINGS:
        record(source_key, polite)
