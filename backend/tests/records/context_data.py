"""Builds `fieldclub/data/live_sources.json` and `deep_links.json` from the research work-lists.

    uv run python -m tests.records.context_data     # rewrite both files

The work-lists in `docs/sources/worklists/` are the record of what the
research found. The package carries a trimmed copy, so the API doesn't read
the docs tree at run time. `test_context.py` checks the copies still match
what this builds.

Left out on purpose:

- every entry under `live_unconfirmed`, whose cross-origin access was never
  confirmed, and the `non_record` entries,
- any live entry whose `cors` doesn't start with "yes", because the browser
  couldn't read it,
- the deep links in `EXCLUDED_LINKS`, with the reason for each.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyproj import Transformer

REPO = Path(__file__).resolve().parents[3]
WORKLISTS = REPO / "docs" / "sources" / "worklists"
DATA = REPO / "backend" / "src" / "fieldclub" / "data"

EXCLUDED_LINKS = {
    "he-nhle-legacy-list": "A redirect host marked for server-side link checks, not for people.",
    "canmore-legacy-site": "A redirect host marked for server-side link checks, not for people.",
    "he-heritage-gateway-near-point": "The research said a browser must check it before it goes into code.",
    "old-maps-online": "The pattern came from memory, and the research said to check it in a browser first.",
}
# Phrases in a work-list note that mean a link isn't for people yet. A link
# whose note has one must be in EXCLUDED_LINKS, which `test_context.py` checks.
NOT_FOR_PEOPLE = ("from memory", "server-side link checks", "before it goes into code")

# The zoom a template's `{zoom}` takes when it isn't a web-map zoom level.
FIXED_ZOOM = {
    # The third value of `coords` looked like a zoom in the archived samples, which used 5.
    "trove-map-at-point": 5,
    # An index from 0 to 9 into the viewer's own list of resolutions. 7 is not verified.
    "britain-from-above-map": 7,
}

# Where a viewer covers only part of its coverage, as the research gave it on
# the British grid: west, south, east, north in metres.
LINK_GRID_BOUNDS = {
    # The Wiltshire edition of Know Your Place.
    "know-your-place-wilts": (374_000, 115_000, 436_500, 201_000),
}

POINT_PLACEHOLDERS = ("{lat}", "{lon}", "{easting}", "{northing}")


# How the browser reads each live source, taken from the work-list entry:
# the format of the answer and its fields from `response_shape` and the
# gotchas that list the fields, and the cap and its largest value from the
# query pattern and `limits`. A field is None where the work-list doesn't
# name it, so the browser falls back to showing the source's name. Field
# names are dot paths inside one item: a GeoJSON feature's `properties`, an
# ADS hit, or a MediaWiki page.
#
# The lowest zoom keeps one viewport's answer under the cap. At MapLibre
# zoom 13 a 1440 by 900 pixel viewport is about 8 by 5 km at English
# latitudes. The densest layers here hold under 10 records a square
# kilometre (the Wiltshire HER's 25,432 points over 3,485 km², 468,176
# obliques over England), so a few hundred come back, under every cap of
# 1,000 or more. Sources with a smaller cap, or that search a fixed radius,
# start at zoom 14, a quarter of that area. That doesn't keep the ADS
# catalogue search under its cap of 50: its work-list gotcha counted 900 hits
# in about 15 km², so a zoom-14 viewport holds several hundred. The browser
# pages it with `page` past the first 50, and its `min_zoom` only bounds how
# many pages that takes. The ADS map search answers any
# viewport with a grid beyond 500 hits, so it is asked from zoom 10. A
# request by record id has no zoom and no cap.
GEOJSON = "geojson"
ARCGIS = ("resultRecordCount", 1000)
ARCGIS_2000 = ("resultRecordCount", 2000)
NO_CAP: tuple[str | None, int | None] = (None, None)


def _reading(
    answer_format: str,
    id_field: str | None,
    name_field: str | None,
    cap: tuple[str | None, int | None],
    min_zoom: int | None = 13,
) -> dict[str, Any]:
    limit_param, max_limit = cap
    return {
        "answer_format": answer_format,
        "id_field": id_field,
        "name_field": name_field,
        "limit_param": limit_param,
        "max_limit": max_limit,
        "min_zoom": min_zoom,
    }


LIVE_READING: dict[str, dict[str, Any]] = {
    # "50 per page, 10,000-result window"; size is clamped to 50.
    "ads-catalogue-search": _reading("ads_search", "id", "data.title.text", ("size", 50), min_zoom=14),
    # Up to 500 trimmed marker hits, or a grid: the hits' fields aren't listed beyond the id.
    "ads-catalogue-map": _reading("ads_map", "id", None, NO_CAP, min_zoom=10),
    "ads-catalogue-record": _reading("ads_record", "id", "data.title.text", NO_CAP, min_zoom=None),
    # 2,000 per page on the 20260529 services. The record link is built from `Filename`. No name field.
    "he-aerial-photos-obliques": _reading(GEOJSON, "Filename", None, ARCGIS_2000),
    "he-aerial-photos-verticals": _reading(GEOJSON, "Filename", None, ARCGIS_2000),
    # Know Your Place: "maxRecordCount 1000 or 2000 per service", so 1,000.
    "bristol-kyp-devon-hist-2021-v2": _reading(GEOJSON, "MONUMENT_UID", "NAME", ARCGIS),
    "bristol-kyp-som-hist-2022": _reading(GEOJSON, "PRN", "NAME", ARCGIS),
    # "Fields: not recorded."
    "bristol-kyp-glo-hist-2021": _reading(GEOJSON, None, None, ARCGIS),
    # "Fields: adds DESCRIPTION, SUMMARY and SOURCES", to fields the entry doesn't name.
    "bristol-kyp-wilts-her-2022-v2": _reading(GEOJSON, None, None, ARCGIS),
    "bristol-kyp-banes-hist-2024": _reading(GEOJSON, "PRN", "NAME", ARCGIS),
    "bristol-kyp-nsom-hist-2022-v2": _reading(GEOJSON, "MonUID", None, ARCGIS),
    "bristol-kyp-sgc-hist-2020-v2": _reading(GEOJSON, "PRN", None, ARCGIS),
    "bristol-kyp-her-2026": _reading(GEOJSON, "PRN", None, ARCGIS),
    "bristol-kyp-worcester-city": _reading(GEOJSON, "MonUID", None, ARCGIS),
    "enpa-exmoor-her": _reading(GEOJSON, "MonUID", "Name", ARCGIS_2000),
    "dnpa-dartmoor-her": _reading(GEOJSON, "monuid", "name", ARCGIS_2000),
    "wiltshire-her-monuments": _reading(GEOJSON, "MonUID", "Name", ARCGIS),
    "wolverhampton-walsall-her": _reading(GEOJSON, "MonUID", "Name", ARCGIS_2000),
    # "limit=250 used by the site's own map". The `size=200` left in the pattern is the site's too.
    "cambridge-cucap-pois": _reading(GEOJSON, "id", "name", ("limit", 250), min_zoom=14),
    # A 1 km radius round the point. `ggslimit` is at most 500.
    "wikimedia-commons-geosearch": _reading(
        "mediawiki_query", "title", "title", ("ggslimit", 500), min_zoom=14
    ),
    # A 0.5 by 1.0 degree box was 'toobig'. A zoom 12 viewport is about 16 by 10 km.
    "wikimedia-wikipedia-geosearch": _reading(
        "mediawiki_query", "title", "title", ("ggslimit", 500), min_zoom=12
    ),
    # "maxRecordCount 1000-2000", so 1,000.
    "aberdeenshire-her": _reading(GEOJSON, "HER_Refere", "Name", ARCGIS),
}


def _degrees(bounds: tuple[int, int, int, int] | None) -> list[float] | None:
    """British grid bounds as west, south, east, north in degrees, to 4 places."""
    if bounds is None:
        return None
    transformer = Transformer.from_crs(27700, 4326, always_xy=True)
    return [round(value, 4) for value in transformer.transform_bounds(*bounds, densify_pts=21)]


def live_sources(worklist: dict[str, Any]) -> list[dict[str, Any]]:
    unconfirmed = {entry["key"] for entry in worklist["live_unconfirmed"]}
    readable = {entry["key"] for entry in worklist["live"] if str(entry["cors"]).lower().startswith("yes")}
    assert readable == set(LIVE_READING), "every live source the browser reads says how to read it"
    items = []
    for entry in worklist["live"]:
        assert entry["key"] not in unconfirmed, f"{entry['key']} is both live and unconfirmed"
        if not str(entry["cors"]).lower().startswith("yes"):
            continue
        items.append(
            {
                "key": entry["key"],
                "name": entry["name"],
                "publisher": entry["publisher"],
                "coverage": entry["coverage"],
                "endpoint": entry["endpoint"],
                "query_pattern": entry["query_pattern"],
                "response_fields": entry["response_shape"],
                "licence": entry["licence"],
                "attribution": entry["attribution"],
                "link_template": entry["record_link_template"],
                "limits": entry["limits"],
                **LIVE_READING[entry["key"]],
            }
        )
    return items


def deep_links(worklist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = {entry["key"] for entry in worklist}
    assert set(EXCLUDED_LINKS) <= keys, "an excluded link is no longer in the work-list"
    items = []
    for entry in worklist:
        if entry["key"] in EXCLUDED_LINKS:
            continue
        template = entry["template"]
        items.append(
            {
                "key": entry["key"],
                "name": entry["name"],
                "template": template,
                "coverage": entry["coverage"],
                "shows": entry["shows"],
                "placeholders_crs": (entry["placeholders_crs"] or "").split(" ")[0] or None,
                "verified": entry["verified"],
                "no_frame": entry["no_frame"],
                "for_point": any(mark in template for mark in POINT_PLACEHOLDERS) and "{id}" not in template,
                "zoom": FIXED_ZOOM.get(entry["key"]),
                "bounds": _degrees(LINK_GRID_BOUNDS.get(entry["key"])),
            }
        )
    return items


def build() -> dict[str, list[dict[str, Any]]]:
    sources = json.loads((WORKLISTS / "sources.json").read_text(encoding="utf-8"))
    links = json.loads((WORKLISTS / "deep-links.json").read_text(encoding="utf-8"))
    return {"live_sources.json": live_sources(sources), "deep_links.json": deep_links(links)}


def render(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    for name, items in build().items():
        (DATA / name).write_text(render(items), encoding="utf-8")


if __name__ == "__main__":
    main()
