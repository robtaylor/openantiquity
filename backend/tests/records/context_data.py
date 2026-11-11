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

Added here, because the work-lists hold research notes rather than words for
visitors: how each live source is credited (`LIVE_CREDITS`), and the name each
link opened at a point shows (`LINK_TITLES`). `LIVE_CHANGES` changes a
work-list's query pattern or link template where its own attribution note
asks for more than the pattern gives.
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

# The name each link opened at a point shows a visitor. The work-list names
# carry working suffixes such as "at a point". Every link for a point needs
# one here, and the other links show their work-list name.
LINK_TITLES = {
    "he-apex-viewer": "Historic England Aerial Photo Explorer",
    "trove-map-at-point": "trove.scot map",
    "britain-from-above-map": "Britain from Above",
    "ncap-air-photo-finder": "NCAP Air Photo Finder",
    "nls-explore-at-point": "National Library of Scotland maps",
    # The viewer sets LIDAR beside a choice of old maps, of which CVAT is the first offered.
    "nls-side-by-side-lidar": "National Library of Scotland LIDAR and maps, side by side",
    "google-earth-web": "Google Earth",
    "know-your-place-wilts": "Know Your Place: Wiltshire",
}


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


def _credit(
    credit: str,
    licence: str,
    homepage: str | None,
    credit_field: str | None = None,
    licence_field: str | None = None,
    preferred_credit_field: str | None = None,
) -> dict[str, Any]:
    """How a source the browser may show is credited to a visitor."""
    return {
        "shown": True,
        "credit": credit,
        "licence_label": licence,
        "homepage": homepage,
        "credit_field": credit_field,
        "licence_field": licence_field,
        "preferred_credit_field": preferred_credit_field,
    }


def _withheld(homepage: str | None) -> dict[str, Any]:
    """A source the work-list doesn't say how to credit, which the browser must not show yet."""
    return {
        "shown": False,
        "credit": None,
        "licence_label": None,
        "homepage": homepage,
        "credit_field": None,
        "licence_field": None,
        "preferred_credit_field": None,
    }


NO_LICENCE = "No licence stated"
ADS_HOME = "https://archaeologydataservice.ac.uk/"
KYP_HOME = "https://maps.bristol.gov.uk/kyp/"
HE_HOME = "https://historicengland.org.uk/"
# The parts of a credit a MediaWiki answer gives per file. Each `extmetadata`
# entry is an object whose `value` holds the text, which may carry HTML.
COMMONS_ARTIST = "imageinfo.0.extmetadata.Artist.value"
COMMONS_ATTRIBUTION = "imageinfo.0.extmetadata.Attribution.value"
COMMONS_LICENCE = "imageinfo.0.extmetadata.LicenseShortName.value"

# How each live source is credited to a visitor, from the work-list's
# `licence` and `attribution` and the catalogue pages in `docs/sources/`,
# word for word where the publisher prescribes the words. The work-list's own
# `licence` and `attribution` are research notes, served as they are, and are
# not for showing. A source is withheld where the work-list doesn't settle how
# it must be credited:
#
# - The ADS asks that each record's original depositor and funder be
#   credited beside "Archaeology Data Service (distributor)". The work-list
#   lists `data.publisher[]` in the answer but doesn't say it is the
#   depositor or what each entry holds, and names no field for the funder.
#   The map mode's hits carry only an id.
# - Know Your Place credits each layer to its source HER, which the work-list
#   doesn't name per layer and no field carries. The service's
#   `copyrightText`, "Bristol City Council", is the host's, not the HER's.
# - Exmoor asks for a statement on each record that holds National Record of
#   the Historic Environment data, with the date it was provided. Nothing in
#   the answer says which records those are, nor the date.
# - Aberdeenshire's terms reserve copyright and say the records are for
#   personal research only, and its work-list entry says Scotland isn't in the
#   first release.
#
# The Historic England aerial photo footprints state no licence. The spike
# `open-site-records` chose to query them live with each record's `Copyright`
# shown, and asking Historic England for a licence is an open owner action
# (`docs/plans/owner-actions.md`), so they are shown meanwhile.
LIVE_CREDITS: dict[str, dict[str, Any]] = {
    "ads-catalogue-search": _withheld(ADS_HOME),
    "ads-catalogue-map": _withheld(ADS_HOME),
    "ads-catalogue-record": _withheld(ADS_HOME),
    "he-aerial-photos-obliques": _credit(
        "Historic England Archive", NO_LICENCE, HE_HOME, credit_field="Copyright"
    ),
    "he-aerial-photos-verticals": _credit(
        "Historic England Archive", NO_LICENCE, HE_HOME, credit_field="Copyright"
    ),
    "bristol-kyp-devon-hist-2021-v2": _withheld(KYP_HOME),
    "bristol-kyp-som-hist-2022": _withheld(KYP_HOME),
    "bristol-kyp-glo-hist-2021": _withheld(KYP_HOME),
    "bristol-kyp-wilts-her-2022-v2": _withheld(KYP_HOME),
    "bristol-kyp-banes-hist-2024": _withheld(KYP_HOME),
    "bristol-kyp-nsom-hist-2022-v2": _withheld(KYP_HOME),
    "bristol-kyp-sgc-hist-2020-v2": _withheld(KYP_HOME),
    "bristol-kyp-her-2026": _withheld(KYP_HOME),
    "bristol-kyp-worcester-city": _withheld(KYP_HOME),
    "enpa-exmoor-her": _withheld("https://www.exmoorher.co.uk/"),
    # The items' own credit. The catalogue names no home page.
    "dnpa-dartmoor-her": _credit(
        "Dartmoor National Park Authority; © Crown copyright and database rights 2026 OS AC0000823576",
        NO_LICENCE,
        None,
    ),
    "wiltshire-her-monuments": _credit(
        "Wiltshire Council Archaeology Service (Wiltshire and Swindon HER)",
        NO_LICENCE,
        "https://services.wiltshire.gov.uk/HistoryEnvRecord/Home/Index",
    ),
    # The catalogue names no home page.
    "wolverhampton-walsall-her": _credit(
        "City of Wolverhampton Council / Wolverhampton and Walsall HER", NO_LICENCE, None
    ),
    # Each record's `copyright` reads "Subject to confirmation", which is no credit.
    "cambridge-cucap-pois": _credit(
        "Cambridge University Collection of Aerial Photography",
        "No open licence",
        "https://www.cambridgeairphotos.com/",
    ),
    "wikimedia-commons-geosearch": _credit(
        "Wikimedia Commons",
        "Licensed file by file",
        "https://commons.wikimedia.org/",
        credit_field=COMMONS_ARTIST,
        licence_field=COMMONS_LICENCE,
        # "Per file, from extmetadata Artist, Attribution and LicenseShortName":
        # a file that sets its own credit line asks for that one.
        preferred_credit_field=COMMONS_ATTRIBUTION,
    ),
    # "Link to the article and state the licence". The thumbnails are licensed
    # file by file, and the answer doesn't say how.
    "wikimedia-wikipedia-geosearch": _credit("Wikipedia", "CC BY-SA 4.0", "https://en.wikipedia.org/"),
    "aberdeenshire-her": _withheld("https://her.aberdeenshire.gov.uk/"),
}

COMMONS_FILTER = "iiextmetadatafilter=LicenseShortName|Artist|AttributionRequired|LicenseUrl"
# Changes to a work-list entry's fields, each with the work-list value it replaces.
LIVE_CHANGES: dict[str, dict[str, tuple[str | None, str]]] = {
    # "Link to the article and state the licence". The work-list gives no template.
    "wikimedia-wikipedia-geosearch": {
        "link_template": (None, "https://en.wikipedia.org/wiki/{title}"),
    },
    # The credit names extmetadata `Attribution`, which the pattern didn't ask for.
    "wikimedia-commons-geosearch": {
        "query_pattern": (COMMONS_FILTER, f"{COMMONS_FILTER}|Attribution"),
    },
}


def _changed(entry: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    for field, (old, new) in LIVE_CHANGES.get(entry["key"], {}).items():
        if old is None:
            assert item[field] is None, f"{entry['key']} now has a {field} of its own"
            item[field] = new
        else:
            assert old in item[field], f"{entry['key']}'s {field} no longer holds {old!r}"
            item[field] = item[field].replace(old, new)
    return item


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
    assert readable == set(LIVE_CREDITS), "every live source the browser reads says how it is credited"
    items = []
    for entry in worklist["live"]:
        assert entry["key"] not in unconfirmed, f"{entry['key']} is both live and unconfirmed"
        if not str(entry["cors"]).lower().startswith("yes"):
            continue
        item = {
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
            **LIVE_CREDITS[entry["key"]],
        }
        items.append(_changed(entry, item))
    return items


def deep_links(worklist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = {entry["key"] for entry in worklist}
    assert set(EXCLUDED_LINKS) <= keys, "an excluded link is no longer in the work-list"
    assert set(LINK_TITLES) <= keys, "a link with a title is no longer in the work-list"
    items = []
    for entry in worklist:
        if entry["key"] in EXCLUDED_LINKS:
            continue
        template = entry["template"]
        for_point = any(mark in template for mark in POINT_PLACEHOLDERS) and "{id}" not in template
        assert not for_point or entry["key"] in LINK_TITLES, (
            f"{entry['key']} opens at a point but has no title"
        )
        items.append(
            {
                "key": entry["key"],
                "name": entry["name"],
                "title": LINK_TITLES.get(entry["key"], entry["name"]),
                "template": template,
                "coverage": entry["coverage"],
                "shows": entry["shows"],
                "placeholders_crs": (entry["placeholders_crs"] or "").split(" ")[0] or None,
                "verified": entry["verified"],
                "no_frame": entry["no_frame"],
                "for_point": for_point,
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
