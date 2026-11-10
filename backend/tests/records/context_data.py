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
    "he-heritage-gateway-near-point": "The research said a browser must check it before it goes into code.",
}

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


def _degrees(bounds: tuple[int, int, int, int] | None) -> list[float] | None:
    """British grid bounds as west, south, east, north in degrees, to 4 places."""
    if bounds is None:
        return None
    transformer = Transformer.from_crs(27700, 4326, always_xy=True)
    return [round(value, 4) for value in transformer.transform_bounds(*bounds, densify_pts=21)]


def live_sources(worklist: dict[str, Any]) -> list[dict[str, Any]]:
    unconfirmed = {entry["key"] for entry in worklist["live_unconfirmed"]}
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
