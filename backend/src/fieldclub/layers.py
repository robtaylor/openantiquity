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

Not done yet: the OpenStreetMap raster view, the OpenFreeMap overlay and the
LIDAR providers have no `sources` row, so `/meta` lists them under `layers`
with their attribution but not under `sources`. When docs/DATA_SOURCES.md
lands, seed those rows from one idempotent function, with their licence and
reuse class, and have each layer here name its source by key.
"""

from __future__ import annotations

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

TILE_SIZE = 512
LIDAR_MINZOOM = 7
LIDAR_MAXZOOM = 16

OGL_V3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

LIDAR_ATTRIBUTION = (
    "© Environment Agency copyright and/or database right 2022. All rights reserved. "
    f'<a href="{OGL_V3_URL}">Open Government Licence v3.0</a>'
)

OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

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

# Styles drawn by /tiles/lidar/{style}/{z}/{x}/{y}.png: id, title, description.
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
        "Sixteen light directions at once, so nothing hides by running parallel to the sun.",
    ),
    (
        "slope",
        "Slope",
        "Steepness. Picks out the sharp edges of platforms, lynchets and quarries.",
    ),
)

DEFAULT_VIEW = "composite"


def lidar_view(style: str, title: str, description: str) -> RasterView:
    return RasterView(
        id=style,
        title=title,
        description=description,
        group="lidar",
        tiles=[f"/tiles/lidar/{style}/{{z}}/{{x}}/{{y}}.png"],
        tile_size=TILE_SIZE,
        minzoom=LIDAR_MINZOOM,
        maxzoom=LIDAR_MAXZOOM,
        attribution=LIDAR_ATTRIBUTION,
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
        bounds=None,
        default=False,
    ),
]

DEM = DemSource(
    tiles=["/tiles/dem/{z}/{x}/{y}.png"],
    tile_size=TILE_SIZE,
    encoding="terrarium",
    minzoom=LIDAR_MINZOOM,
    maxzoom=LIDAR_MAXZOOM,
    attribution=LIDAR_ATTRIBUTION,
)

OVERLAYS: list[Overlay] = [
    OpenMapTilesOverlay(
        id="osm",
        title="OpenStreetMap",
        tilejson=OPENFREEMAP_TILEJSON,
        glyphs=OPENFREEMAP_GLYPHS,
        default_opacity=0.8,
        attribution=OPENFREEMAP_ATTRIBUTION,
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


def build_layers() -> Layers:
    """The `layers` part of `/meta`, checked for the mistakes that would break the map."""
    view_ids = [view.id for view in VIEWS]
    overlay_ids = [overlay.id for overlay in OVERLAYS]
    assert len(set(view_ids)) == len(view_ids), f"duplicate view ids: {view_ids}"
    assert len(set(overlay_ids)) == len(overlay_ids), f"duplicate overlay ids: {overlay_ids}"
    defaults = [view.id for view in VIEWS if isinstance(view, RasterView) and view.default]
    assert defaults == [DEFAULT_VIEW], f"exactly one view must be the default, found {defaults}"
    return Layers(views=list(VIEWS), dem=DEM, overlays=list(OVERLAYS), initial_view=INITIAL_VIEW)
