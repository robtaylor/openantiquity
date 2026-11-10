"""Fixtures for the names group: the GB1900 gazetteer, OS Open Names and ONS boundaries.

Each fixture is cut from the live download or answer of 2026-11-10, which the
connectors and loaders cached under `var/ingest/<key>/`, so recording one
costs the publisher nothing more. To cut them again from a newer download:

    uv run python -m tests.connectors.names.support gb1900 ../var
    uv run python -m tests.connectors.names.support open-names ../var

- `gb1900.zip` keeps the complete gazetteer's layout (one UTF-16 CSV in a
  folder, beside its licence file) with every label in the box
  -1.88,51.40,-1.82,51.44 around Avebury and Silbury Hill, 221 of them, of
  which 37 name antiquities, and the first antiquity label in each of the
  other two nations.
- `open_names.zip` keeps the OS Open Names layout (headings in
  `Doc/OS_Open_Names_Header.csv`, one headless CSV per 20 km square) with
  every entry of SU06 that lies in the box -1.90,51.38,-1.78,51.46 and isn't
  a postcode or a road, ten postcodes and ten roads to be left out, and the
  populated places called Cardiff and Caerphilly, which have Welsh names,
  from ST06 and ST08.
- `ons_countries.json` and `ons_counties.json` are the ONS layers' GeoJSON
  answers, recorded by `record_ons` below with `maxAllowableOffset` so the
  polygons are simplified on the server, the nations to about 5 km and the
  counties to about 1 km, and the nations' islands under 20 square
  kilometres are left out, so the files stay small. Counties are only those touching the box
  -3.2,51.3,-1.5,51.9, from the Welsh border to Wiltshire.

Nothing in them is personal data: they are place names, map labels and
boundaries as their publishers publish them.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
import respx
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, mapping, shape

from fieldclub import http
from fieldclub.ingest.connectors import portsmouth_gb1900_gazetteer as gb1900
from fieldclub.ingest.reference import ons_boundaries, os_open_names

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"
GB1900_ZIP = FIXTURES / "gb1900.zip"
OPEN_NAMES_ZIP = FIXTURES / "open_names.zip"
ONS_COUNTRIES = FIXTURES / "ons_countries.json"
ONS_COUNTIES = FIXTURES / "ons_counties.json"

# Where the work-list keeps the research's findings, which the licence tests compare with.
WORKLIST = Path(__file__).parents[4] / "docs" / "sources" / "worklists" / "sources.json"

AVEBURY_BOX = (-1.88, 51.40, -1.82, 51.44)


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def serve_file(url: str, body: bytes) -> respx.Route:
    """`url` answering with `body`, as a download host does. Call it inside `respx.mock`."""
    return respx.get(url).mock(
        return_value=httpx.Response(
            200, content=body, headers={"Content-Length": str(len(body)), "Last-Modified": "Tue, 20 Feb 2024"}
        )
    )


def zip_with(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def _inside(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def record_gb1900(var: Path) -> None:
    source = var / "ingest" / gb1900.Gb1900Gazetteer.source.key / "GB1900_gazetteer_complete_july_2018.zip"
    with zipfile.ZipFile(source) as archive:
        licence_name = next(
            name for name in archive.namelist() if "LICENCE" in name and "__MACOSX" not in name
        )
        licence = archive.read(licence_name)
        with archive.open(gb1900.MEMBER) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-16", newline=""))
            header = next(reader)
            kept: list[list[str]] = []
            other_nations: dict[str, list[str]] = {}
            for row in reader:
                values = dict(zip(header, row, strict=True))
                lon, lat = float(values["longitude"]), float(values["latitude"])
                if _inside(lon, lat, AVEBURY_BOX):
                    kept.append(row)
                elif values["nation"] != "England" and gb1900.is_antiquity(values["final_text"]):
                    other_nations.setdefault(values["nation"], row)
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows([*kept, *other_nations.values()])
    GB1900_ZIP.write_bytes(zip_with({gb1900.MEMBER: out.getvalue().encode("utf-16"), licence_name: licence}))
    logger.info("%s: %d labels near Avebury, %d elsewhere", GB1900_ZIP.name, len(kept), len(other_nations))


def record_open_names(var: Path) -> None:
    source = var / "ingest" / os_open_names.OpenNames.source.key / "opname_csv_gb.zip"
    box = (-1.90, 51.38, -1.78, 51.46)
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(source) as archive:
        members[os_open_names.HEADER] = archive.read(os_open_names.HEADER)
        header = next(
            csv.reader(io.TextIOWrapper(io.BytesIO(members[os_open_names.HEADER]), encoding="utf-8-sig"))
        )
        to_lonlat = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
        for square in ("SU06", "ST06", "ST08"):
            text = archive.read(f"Data/{square}.csv").decode("utf-8-sig")
            rows, postcodes, roads = [], 0, 0
            for row in csv.reader(io.StringIO(text, newline="")):
                values = dict(zip(header, row, strict=True))
                if square.startswith("ST"):
                    if values["NAME1"] in ("Cardiff", "Caerphilly") and values["TYPE"] == "populatedPlace":
                        rows.append(row)
                    continue
                lon, lat = to_lonlat.transform(float(values["GEOMETRY_X"]), float(values["GEOMETRY_Y"]))
                if not _inside(lon, lat, box):
                    continue
                if values["LOCAL_TYPE"] == "Postcode":
                    if postcodes < 10:
                        rows.append(row)
                    postcodes += 1
                elif values["TYPE"] == "transportNetwork" and "Road" in values["LOCAL_TYPE"]:
                    if roads < 10:
                        rows.append(row)
                    roads += 1
                else:
                    rows.append(row)
            if rows:
                out = io.StringIO(newline="")
                csv.writer(out, lineterminator="\r\n").writerows(rows)
                members[f"Data/{square}.csv"] = out.getvalue().encode("utf-8")
    OPEN_NAMES_ZIP.write_bytes(zip_with(members))
    rows = sum(len(data.splitlines()) for name, data in members.items() if name.startswith("Data/"))
    logger.info("%s: %d rows", OPEN_NAMES_ZIP.name, rows)


def without_small_islands(collection: dict[str, Any], min_area_km2: float = 20.0) -> dict[str, Any]:
    """The GeoJSON with every part of each boundary smaller than `min_area_km2` left out.

    Scotland alone has 3,661 parts, most of them skerries, which would make
    the fixture hundreds of kilobytes.
    """
    for feature in collection["features"]:
        parts = shapely.get_parts(shape(feature["geometry"]))
        kept = [part for part in parts if ons_boundaries.to_grid(part).area >= min_area_km2 * 1e6]
        feature["geometry"] = mapping(MultiPolygon(kept))
    return collection


def record_ons() -> None:
    """Two requests to ONS's ArcGIS layers, a second apart, simplified on the server."""
    client = http.get_client()
    params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "maxAllowableOffset": "0.05",
        "geometryPrecision": "4",
    }
    countries = client.get(f"{ons_boundaries.COUNTRIES}/query", params=params)
    countries.raise_for_status()
    ONS_COUNTRIES.write_text(json.dumps(without_small_islands(countries.json())), encoding="utf-8")
    time.sleep(1)
    counties = client.get(
        f"{ons_boundaries.COUNTIES}/query",
        params=params
        | {
            "maxAllowableOffset": "0.01",
            "geometry": "-3.2,51.3,-1.5,51.9",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        },
    )
    counties.raise_for_status()
    ONS_COUNTIES.write_bytes(counties.content)
    for path in (ONS_COUNTRIES, ONS_COUNTIES):
        logger.info("%s: %d bytes", path.name, path.stat().st_size)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    what = sys.argv[1]
    if what == "gb1900":
        record_gb1900(Path(sys.argv[2]))
    elif what == "open-names":
        record_open_names(Path(sys.argv[2]))
    elif what == "ons":
        record_ons()
    else:
        raise SystemExit(f"unknown fixture {what!r}")
