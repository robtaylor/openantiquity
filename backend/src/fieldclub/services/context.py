"""The context catalogue: live sources the browser queries itself, and deep links for a point.

Decision 0007 makes a `live` source the browser's business. The server holds
nothing from it and serves only the definition: endpoint, query pattern,
response fields, licence, attribution and link template. A `deeplink` is a
template that opens the publisher's own viewer. For a point, `links_for`
fills in every template that takes a position and covers it.

Both come from `fieldclub/data/`, which is generated from the research
work-lists by `tests/records/context_data.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from shapely.geometry import Point
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.services import geo
from fieldclub.services.records import check_point
from fieldclub.terrain.grid import lonlat_to_mercator
from fieldclub.vocab import Nation

DEFAULT_ZOOM = 15

# Which coverages show for a point in each nation. `wider` and `uk` show everywhere in the UK.
_COVERAGES: dict[str | None, frozenset[str]] = {
    Nation.ENGLAND: frozenset({"england", "gb", "uk", "wider"}),
    Nation.SCOTLAND: frozenset({"scotland", "gb", "uk", "wider"}),
    Nation.WALES: frozenset({"wales", "gb", "uk", "wider"}),
    Nation.NORTHERN_IRELAND: frozenset({"northern_ireland", "uk", "wider"}),
}


@cache
def _load(name: str) -> tuple[dict[str, Any], ...]:
    text = resources.files("fieldclub.data").joinpath(name).read_text(encoding="utf-8")
    items = json.loads(text)
    assert isinstance(items, list), f"{name} must be a list"
    assert all(isinstance(item, dict) and item.get("key") for item in items), (
        f"{name} has an item without a key"
    )
    return tuple(items)


def live_sources() -> tuple[dict[str, Any], ...]:
    """The whole catalogue, withheld sources included."""
    return _load("live_sources.json")


def shown_live_sources() -> tuple[dict[str, Any], ...]:
    """The sources the browser may query and show. A withheld one isn't served at all."""
    return tuple(item for item in live_sources() if item["shown"])


def deep_links() -> tuple[dict[str, Any], ...]:
    return _load("deep_links.json")


@dataclass(frozen=True)
class Link:
    key: str
    name: str
    title: str
    url: str
    coverage: str
    shows: str
    verified: str
    no_frame: bool


@dataclass(frozen=True)
class PointLinks:
    grid_ref: str | None
    links: list[Link]


def _coverages(db: Session, lon: float, lat: float, system: gridref.GridSystem | None) -> frozenset[str]:
    """The coverages that apply at a point.

    The nation comes from `admin_areas`. A point at sea within
    `geo.NEAR_NATION_M` of one or more nations, as in the Severn or the Wash,
    gets the viewers of each of them. Otherwise, and until that table is
    filled, a point on the British grid is taken as somewhere in Great
    Britain, so every British viewer is offered. A point on the Irish Grid is
    not taken as Northern Ireland, because the grid covers the whole island
    and that guess would offer Northern Ireland's viewers in Dublin
    (`geo.locate` refuses it for the same reason). It gets only the viewers
    that cover the wider world, like a point on neither grid.
    """
    nation = geo.locate(db, lon, lat).nation
    if nation is not None:
        return _COVERAGES[nation]
    # At sea, as in an estuary between two nations: the viewers of every nation near.
    near = geo.nations_near(db, Point(lon, lat))
    if near:
        return frozenset[str]().union(*(_COVERAGES[code] for code, _ in near))
    if system is gridref.GridSystem.OSGB:
        return frozenset({"england", "scotland", "wales", "gb", "uk", "wider"})
    return frozenset({"wider"})


Grid = tuple[gridref.GridSystem, float, float]


def _fill(link: dict[str, Any], lon: float, lat: float, zoom: int, grid: Grid | None) -> str | None:
    """The template with this point filled in, or None when it needs a grid the point isn't on."""
    values = {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": str(link["zoom"] or zoom)}
    crs = link["placeholders_crs"]
    if crs == "EPSG:27700":
        if grid is None or grid[0] != gridref.GridSystem.OSGB:
            return None
        values |= {"easting": f"{grid[1]:.0f}", "northing": f"{grid[2]:.0f}"}
    elif crs == "EPSG:3857":
        x, y = lonlat_to_mercator(lon, lat)
        values |= {"easting": f"{x:.2f}", "northing": f"{y:.2f}"}
    url = link["template"]
    for name, value in values.items():
        url = url.replace("{" + name + "}", value)
    assert "{" not in url, f"deep link {link['key']} has a placeholder left: {url}"
    return url


def _inside(bounds: list[float] | None, lon: float, lat: float) -> bool:
    return bounds is None or (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3])


def links_for(db: Session, lon: float, lat: float, zoom: int = DEFAULT_ZOOM) -> PointLinks:
    """Every deep link that opens an external viewer at this point and covers it."""
    check_point(lon, lat)
    assert 1 <= zoom <= 20, "zoom must be between 1 and 20"
    grid: Grid | None
    try:
        grid = gridref.to_grid(lon, lat)
        reference: str | None = gridref.to_gridref(lon, lat, 8)
    except gridref.GridRefError:
        grid, reference = None, None
    coverages = _coverages(db, lon, lat, grid[0] if grid else None)
    links = []
    for link in deep_links():
        applies = link["for_point"] and link["coverage"] in coverages and _inside(link["bounds"], lon, lat)
        url = _fill(link, lon, lat, zoom, grid) if applies else None
        if url is not None:
            links.append(
                Link(
                    link["key"],
                    link["name"],
                    link["title"],
                    url,
                    link["coverage"],
                    link["shows"],
                    link["verified"],
                    link["no_frame"],
                )
            )
    return PointLinks(reference, links)
