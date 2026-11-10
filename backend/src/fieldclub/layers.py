"""The map layer catalogue served by `/meta`.

The catalogue is data. `VIEWS` and `OVERLAYS` are lists of the Pydantic shapes
in `schemas/meta.py`, and `build_layers()` checks them and hands them to the
API. To add a layer, append to a list here or call `add_view()` or
`add_overlay()` from the module that owns the layer.

A view of type `raster` is a tiled image. Any view can be the main layer or
the comparison layer. Overlays stack above with their own opacity.

The LIDAR views and the elevation tiles cover England only for now, from the
Environment Agency's 2022 composite DTM, so they carry its attribution.
Change it here, in one place, when another nation's elevation is added.

Every layer someone else publishes carries its attribution, licence and
reuse class, as a source does (Decision 0004). The records overlay names each
record's source in the tile, and `/meta` lists the sources. These layers have
no `sources` row: they are drawn, not indexed. The LIDAR providers are the
exception, because the elevation they publish is stored in the mirror: their
rows are written by `fieldclub.terrain.attribution.register_sources`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

from fieldclub.schemas.meta import (
    CoverageOverlay,
    DemSource,
    FindingsOverlay,
    InitialView,
    Layers,
    OpenMapTilesOverlay,
    Overlay,
    RakingView,
    RasterView,
    RecordsOverlay,
    View,
)
from fieldclub.terrain.grid import TILE_SIZE
from fieldclub.terrain.render import DEM_KIND, tile_version
from fieldclub.terrain.service import default_editions
from fieldclub.terrain.styles import DEFAULT_STYLE, MAXZOOM, MINZOOM
from fieldclub.vocab import SourceReuse

# A style id or `DEM_KIND` to the token terrain tile URLs carry.
TileVersion = Callable[[str], str]


def default_tile_version(kind: str) -> str:
    """The token before any national overview is built. `/meta` passes the terrain service's own."""
    return tile_version(kind, default_editions())


def terrain_tiles(path: str, kind: str, version: TileVersion = default_tile_version) -> str:
    """A terrain tile URL with the version token that lets the tile be cached as immutable."""
    return f"{path}/{{z}}/{{x}}/{{y}}.png?v={version(kind)}"


OGL_V3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

LIDAR_ATTRIBUTION = (
    "© Environment Agency copyright and/or database right 2022. All rights reserved. "
    f'<a href="{OGL_V3_URL}">Open Government Licence v3.0</a>'
)

OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'


class Terms(TypedDict):
    """The terms a publisher's layer is shown under."""

    licence: str
    licence_url: str
    reuse: SourceReuse


LIDAR_TERMS = Terms(licence="Open Government Licence v3.0", licence_url=OGL_V3_URL, reuse=SourceReuse.OPEN)
# OpenStreetMap's data is under the ODbL, which asks that what is made from it is shared alike.
OSM_TERMS = Terms(
    licence="Open Database License 1.0",
    licence_url="https://www.openstreetmap.org/copyright",
    reuse=SourceReuse.SHARE_ALIKE,
)

# OpenFreeMap serves OpenMapTiles-schema vector tiles with no key. The TileJSON
# and glyph URLs are the ones its "liberty" style uses
# (https://tiles.openfreemap.org/styles/liberty, checked November 2026).
OPENFREEMAP_TILEJSON = "https://tiles.openfreemap.org/planet"
OPENFREEMAP_GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf"
OPENFREEMAP_ATTRIBUTION = (
    '<a href="https://openfreemap.org">OpenFreeMap</a> '
    '<a href="https://www.openmaptiles.org/">© OpenMapTiles</a> '
    'Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
)

# Styles drawn by /tiles/lidar/{style}/{z}/{x}/{y}.png?v=: id, title, description.
LIDAR_STYLES: tuple[tuple[str, str, str], ...] = (
    (
        "composite",
        "Composite",
        "Sky-view, openness, slope and hillshade blended. Shows most earthworks with no light to aim.",
    ),
    (
        "local_relief",
        "Local relief",
        "Takes away the hills and keeps the small stuff. Best for ploughed-down features on flat ground.",
    ),
    (
        "sky_view",
        "Sky-view",
        "Ditches and hollows go dark, banks go bright. Good for enclosures and hollow ways.",
    ),
    (
        "multi_shade",
        "Multi-direction shade",
        "Three lights in red, green and blue, so nothing hides by running parallel to the sun.",
    ),
    (
        "slope",
        "Slope",
        "Steepness. Picks out the sharp edges of platforms, lynchets and quarries.",
    ),
    (
        "openness",
        "Openness",
        "How much sky each spot sees, without the light. Banks and ridges go bright, ditches dark.",
    ),
)

DEFAULT_VIEW = DEFAULT_STYLE


def lidar_view(style: str, title: str, description: str) -> RasterView:
    return RasterView(
        id=style,
        title=title,
        description=description,
        group="lidar",
        tiles=[terrain_tiles(f"/tiles/lidar/{style}", style)],
        tile_size=TILE_SIZE,
        # The zoom range the terrain service serves. Below zoom 13 the tiles
        # are drawn from the national overview, from 13 to 16 from the 1 m
        # mirror. Both are the Environment Agency's 2022 composite, so one
        # attribution covers them.
        minzoom=MINZOOM,
        maxzoom=MAXZOOM,
        attribution=LIDAR_ATTRIBUTION,
        **LIDAR_TERMS,
        bounds=None,
        default=style == DEFAULT_VIEW,
    )


VIEWS: list[View] = [
    *(lidar_view(style, title, description) for style, title, description in LIDAR_STYLES),
    RakingView(
        id="raking",
        title="Raking light",
        group="lidar",
        description="Low light from a side you choose. Drag the sun round and watch faint ridges appear.",
        attribution=LIDAR_ATTRIBUTION,
        **LIDAR_TERMS,
    ),
    RasterView(
        id="osm_standard",
        title="OpenStreetMap",
        description="The standard OpenStreetMap map, for roads, paths and place names.",
        group="map",
        tiles=["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tile_size=256,
        minzoom=0,
        maxzoom=19,
        attribution=OSM_ATTRIBUTION,
        **OSM_TERMS,
        bounds=None,
        default=False,
    ),
]

DEM = DemSource(
    tiles=[terrain_tiles("/tiles/dem", DEM_KIND)],
    tile_size=TILE_SIZE,
    encoding="terrarium",
    minzoom=MINZOOM,
    maxzoom=MAXZOOM,
    attribution=LIDAR_ATTRIBUTION,
    **LIDAR_TERMS,
)

OVERLAYS: list[Overlay] = [
    OpenMapTilesOverlay(
        id="osm",
        title="OpenStreetMap",
        tilejson=OPENFREEMAP_TILEJSON,
        glyphs=OPENFREEMAP_GLYPHS,
        default_opacity=0.8,
        attribution=OPENFREEMAP_ATTRIBUTION,
        **OSM_TERMS,
    ),
    RecordsOverlay(id="records", title="Heritage records", tiles=["/tiles/records/{z}/{x}/{y}.mvt"]),
    # No tiles: findings come from GET /findings?format=geojson, because what
    # each viewer may see of a position differs (Decision 0005).
    FindingsOverlay(id="findings", title="Findings"),
    CoverageOverlay(id="coverage", title="Scan coverage"),
]

# Avebury.
INITIAL_VIEW = InitialView(center=(-1.8542, 51.4286), zoom=14)


def add_view(view: View, *, before: str | None = None) -> None:
    """Add a view to the catalogue, at the end or just before the view called `before`."""
    assert all(existing.id != view.id for existing in VIEWS), f"view {view.id!r} is already in the catalogue"
    _insert(VIEWS, view, before)


def add_overlay(overlay: Overlay, *, before: str | None = None) -> None:
    """Add an overlay to the catalogue, at the end or just before the overlay called `before`."""
    assert all(existing.id != overlay.id for existing in OVERLAYS), (
        f"overlay {overlay.id!r} is already in the catalogue"
    )
    _insert(OVERLAYS, overlay, before)


def _insert[T: (View, Overlay)](items: list[T], item: T, before: str | None) -> None:
    if before is None:
        items.append(item)
        return
    positions = [index for index, existing in enumerate(items) if existing.id == before]
    assert positions, f"no layer called {before!r} to insert before"
    items.insert(positions[0], item)


def _versioned(view: View, version: TileVersion) -> View:
    """A terrain view with the URL token `version` gives. Every other view as it is."""
    if isinstance(view, RasterView) and view.group == "lidar" and view.id in _STYLE_IDS:
        return view.model_copy(update={"tiles": [terrain_tiles(f"/tiles/lidar/{view.id}", view.id, version)]})
    return view


_STYLE_IDS = frozenset(style for style, _, _ in LIDAR_STYLES)


def build_layers(tile_version: TileVersion = default_tile_version) -> Layers:
    """The `layers` part of `/meta`, checked for the mistakes that would break the map.

    `tile_version` gives the token terrain tile URLs carry. `/meta` passes the
    terrain service's, which changes when the national overview is rebuilt.
    """
    view_ids = [view.id for view in VIEWS]
    overlay_ids = [overlay.id for overlay in OVERLAYS]
    assert len(set(view_ids)) == len(view_ids), f"duplicate view ids: {view_ids}"
    assert len(set(overlay_ids)) == len(overlay_ids), f"duplicate overlay ids: {overlay_ids}"
    defaults = [view.id for view in VIEWS if isinstance(view, RasterView) and view.default]
    assert defaults == [DEFAULT_VIEW], f"exactly one view must be the default, found {defaults}"
    views = [_versioned(view, tile_version) for view in VIEWS]
    dem = DEM.model_copy(update={"tiles": [terrain_tiles("/tiles/dem", DEM_KIND, tile_version)]})
    return Layers(views=views, dem=dem, overlays=list(OVERLAYS), initial_view=INITIAL_VIEW)
