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

The layers other publishers serve to the browser come from the map-layer
work-list (`docs/sources/worklists/map-layers.json`, written up in
`docs/sources/map-layers.md`). `FROM_WORKLIST` names each one offered, by its
work-list id, and its tile address, zoom range, bounds and attribution are the
work-list's word for word (`tests/test_layers.py` holds them to it).
`LEFT_OUT` gives every other work-list entry and why it isn't offered. A
layer is offered when the work-list marks it `clean`: the research found it
usable from a browser with no key, its terms are met by a non-commercial
project (Decision 0004), and its address, terms and cross-origin answer were
all checked. The National Library of Scotland's map and air photo tilesets
are described here but held back (`AWAITING_NLS`) until NLS confirms in
writing that a public app may hot-link them, as the research advised. To
offer one, take it out of `AWAITING_NLS` and mark it `clean` in the
work-list with the reason. The views come
grouped as the layer panel shows them: LIDAR, aerial imagery, historic maps,
maps, then geology.
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
    ViewGroup,
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
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"


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
        (
            "How much of the sky each spot can see. Ditches and hollows go dark, banks and mounds stay "
            "light. Good for enclosures and old sunken tracks."
        ),
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

# --------------------------------------------------------------------------
# Layers other publishers serve, from the map-layer work-list
# --------------------------------------------------------------------------

EA_2022 = "© Environment Agency copyright and/or database right 2022. All rights reserved."
NLS_CREDIT = (
    '<a href="https://maps.nls.uk/">Reproduced with the permission of the National Library of Scotland</a>'
)
NLS_HOST = "https://mapseries-tilesets.s3.amazonaws.com"
BGS_CREDIT = "Contains British Geological Survey materials © UKRI 2026"
OGL_TERMS = Terms(licence="Open Government Licence v3.0", licence_url=OGL_V3_URL, reuse=SourceReuse.OPEN)
# NLS's copyright page: "commercial, non-commercial, educational and private purposes under the
# terms of the Creative Commons Attribution (CC-BY) licence", CC-BY 4.0 on the six-inch sheets.
NLS_TERMS = Terms(licence="CC BY 4.0", licence_url=CC_BY_4_URL, reuse=SourceReuse.OPEN)
# BGS's own terms for the 1:625,000 map, given in its service's capabilities: "made available for
# all uses - including commercial use", but not to be sold on.
BGS_625K_TERMS = Terms(
    licence="BGS 1:625k DiGMap terms: all uses, no resale",
    licence_url=(
        "https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms?service=WMS&request=GetCapabilities"
    ),
    reuse=SourceReuse.OPEN,
)


# Work-list entries described below but not offered until NLS confirms that a public app may
# hot-link its tilesets. The work-list marks each of them not `clean` for that reason.
AWAITING_NLS = frozenset(
    {
        "nls-os-air-photo-mosaics-1944-50",
        "nls-os-six-inch-1888-1913",
        "nls-os-25k-outline-1945-65",
        "nls-os-one-inch-1920s-40s",
        "nls-bartholomew-half-inch-1897-1907",
        "nls-bartholomew-half-inch-1940s",
        "nls-ten-mile-general",
    }
)


def published_view(
    worklist_id: str,
    view_id: str,
    title: str,
    description: str,
    group: ViewGroup,
    tiles: str,
    *,
    attribution: str,
    terms: Terms,
    minzoom: int = 0,
    maxzoom: int,
    bounds: tuple[float, float, float, float] | None = None,
) -> RasterView:
    """A 256-pixel layer from the work-list. `FROM_WORKLIST` records which entry it is.

    One in `AWAITING_NLS` is recorded in `HELD_BACK` instead, and `offered` leaves it out.
    """
    (HELD_BACK if worklist_id in AWAITING_NLS else FROM_WORKLIST)[worklist_id] = view_id
    return RasterView(
        id=view_id,
        title=title,
        description=description,
        group=group,
        tiles=[tiles],
        tile_size=256,
        minzoom=minzoom,
        maxzoom=maxzoom,
        attribution=attribution,
        **terms,
        bounds=bounds,
        default=False,
    )


# The work-list id of each layer offered, to the view's id.
FROM_WORKLIST: dict[str, str] = {}
# The same for the layers described but held back.
HELD_BACK: dict[str, str] = {}


def offered(views: list[View]) -> list[View]:
    """The views not held back."""
    held = set(HELD_BACK.values())
    return [view for view in views if view.id not in held]


PUBLISHED_LIDAR: list[View] = [
    published_view(
        "ea-dsp-hillshade-2022-wmts",
        "ea_hillshade",
        "Environment Agency hillshade",
        "The publisher's own grey hillshade, lit from one side. For comparing with the views above.",
        "lidar",
        "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wmts"
        "?service=WMTS&version=1.0.0&request=GetTile&layer=Lidar_Composite_Hillshade_DTM_1m"
        "&style=hillshade&tilematrixset=WebMercatorQuad&format=image/png"
        "&tilematrix={z}&tilerow={y}&tilecol={x}",
        attribution=EA_2022,
        terms=OGL_TERMS,
        minzoom=6,
        maxzoom=19,
    ),
    published_view(
        "nls-rvt-hillshade-england",
        "nls_hillshade",
        "Three-light hillshade (NLS)",
        "The National Library of Scotland's hillshade of the same survey, lit in red, green and blue.",
        "lidar",
        f"{NLS_HOST}/lidar/england/{{z}}/{{x}}/{{y}}.png",
        attribution=(
            "© Environment Agency copyright and/or database right 2022. All rights reserved. "
            "Processing by Richard Pearson using RVT, National Library of Scotland"
        ),
        terms=OGL_TERMS,
        minzoom=1,
        maxzoom=18,
        bounds=(-6.4665, 49.8506, 1.7782, 55.8782),
    ),
]

PUBLISHED_IMAGERY: list[View] = [
    published_view(
        "nls-os-air-photo-mosaics-1944-50",
        "nls_air_photos_1944",
        "Air photos, 1944 to 1950",
        "RAF photographs pieced together by the Ordnance Survey, for parts of England and Wales. "
        "Shows fields and earthworks before later ploughing.",
        "imagery",
        f"{NLS_HOST}/air-photos-10560/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        maxzoom=16,
    ),
    published_view(
        "eox-s2cloudless-2016",
        "eox_sentinel_2016",
        "Satellite, 2016",
        "A cloud-free satellite picture at 10 metres. Shows field patterns, not cropmarks or earthworks.",
        "imagery",
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
        attribution=(
            "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH "
            "(Contains modified Copernicus Sentinel data 2016)"
        ),
        terms=Terms(
            licence="Creative Commons Attribution 4.0 International",
            licence_url=CC_BY_4_URL,
            reuse=SourceReuse.OPEN,
        ),
        maxzoom=14,
    ),
]

PUBLISHED_HISTORIC: list[View] = [
    published_view(
        "nls-os-six-inch-1888-1913",
        "nls_six_inch_1888",
        "Six-inch map, 1888 to 1913",
        "Ordnance Survey maps at six inches to the mile, with antiquities lettered on them.",
        "historic",
        f"{NLS_HOST}/os/6inchsecond/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        minzoom=1,
        maxzoom=17,
    ),
    published_view(
        "nls-os-25k-outline-1945-65",
        "nls_25k_1945",
        "1:25,000 map, 1945 to 1965",
        "The post-war Ordnance Survey map at about two and a half inches to the mile.",
        "historic",
        f"{NLS_HOST}/os/25000_outline/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        minzoom=1,
        maxzoom=16,
    ),
    published_view(
        "nls-os-one-inch-1920s-40s",
        "nls_one_inch_1920s",
        "One-inch map, 1920s to 1940s",
        "Ordnance Survey maps at one inch to the mile and smaller, for finding your way across a county.",
        "historic",
        f"{NLS_HOST}/api/nls/{{z}}/{{x}}/{{y}}.jpg",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        minzoom=1,
        maxzoom=14,
    ),
    published_view(
        "nls-bartholomew-half-inch-1897-1907",
        "nls_bartholomew_1897",
        "Bartholomew half-inch, 1897 to 1907",
        "Bartholomew's coloured maps at half an inch to the mile, shaded by height.",
        "historic",
        f"{NLS_HOST}/bartholomew_great_britain/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        maxzoom=15,
    ),
    published_view(
        "nls-bartholomew-half-inch-1940s",
        "nls_bartholomew_1940s",
        "Bartholomew half-inch, 1940 to 1947",
        "The same series forty years on.",
        "historic",
        f"{NLS_HOST}/bartholomew/great_britain_1940s/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        maxzoom=14,
    ),
    published_view(
        "nls-ten-mile-general",
        "nls_ten_mile",
        "Ten-mile map, 1944 to 1957",
        "A national map at ten miles to the inch. For an overview of a region, not a site.",
        "historic",
        f"{NLS_HOST}/ten_mile/general/{{z}}/{{x}}/{{y}}.png",
        attribution=NLS_CREDIT,
        terms=NLS_TERMS,
        minzoom=1,
        maxzoom=12,
    ),
]

PUBLISHED_GEOLOGY: list[View] = [
    published_view(
        "bgs-geology-625k-bedrock",
        "bgs_bedrock_625k",
        "Bedrock geology",
        "The rock under the soil across the UK, at 1:625,000. Up to zoom 12.",
        "geology",
        "https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms?service=WMS&version=1.3.0"
        "&request=GetMap&layers=GBR_BGS_625k_BLS&styles=&format=image/png&transparent=true"
        "&crs=EPSG:3857&width=256&height=256&bbox={bbox-epsg-3857}",
        attribution=BGS_CREDIT,
        terms=BGS_625K_TERMS,
        maxzoom=12,
    ),
    published_view(
        "bgs-geology-50k-superficial",
        "bgs_superficial_50k",
        "Superficial deposits",
        "Clay, sand, gravel and peat laid over the rock, at 1:50,000, where the survey has mapped them. "
        "From zoom 13.",
        "geology",
        "https://map.bgs.ac.uk/arcgis/services/BGS_Detailed_Geology/MapServer/WMSServer?service=WMS"
        "&version=1.3.0&request=GetMap&layers=BGS.50k.Superficial.deposits&styles=&format=image/png"
        "&transparent=true&crs=EPSG:3857&width=256&height=256&bbox={bbox-epsg-3857}",
        attribution=BGS_CREDIT,
        terms=OGL_TERMS,
        minzoom=13,
        # The work-list gives none: the service draws at any scale from 1:94,495 down.
        maxzoom=20,
    ),
]

# Every other entry of the work-list, and why it isn't offered.
_NOT_THIS_RELEASE = "Covers {} only, which isn't in the first release (England)."
_NLS_NOT_OFFERED = "NLS doesn't list this tileset as offered for reuse: ask NLS before hot-linking it."
_BRITISH_LIBRARY = "The British Library's permission is needed before a public app shows it."
_AWAITING_NLS = (
    "Awaiting NLS's written confirmation that a public app may hot-link its tilesets, "
    "which the research advised getting before launch."
)
_SCOTLAND = (
    _NOT_THIS_RELEASE.format("Scotland")
    + " The reports also disagreed on its cross-origin headers, and the phase licences weren't checked."
)
LEFT_OUT: dict[str, str] = {
    **dict.fromkeys(sorted(AWAITING_NLS), _AWAITING_NLS),
    "ea-dsp-hillshade-2022-wms": "The same hillshade as the WMTS layer offered, through a slower interface.",
    "ea-imageserver-2025-multidirectional": (
        "An on-demand image service at 0.5 to 2 s a tile, which the research said to keep off the hot path "
        "until Defra confirms third-party use."
    ),
    "nls-rvt-hillshade-wales": _NOT_THIS_RELEASE.format("Wales")
    + " Its licence is recorded inconsistently ('Not Specified' on the tile catalogue).",
    **{f"nls-rvt-hillshade-scotland-phase{phase}": _SCOTLAND for phase in (1, 2, 3, 4, 5, 6)},
    "nls-rvt-hillshade-scotland-hebrides": _SCOTLAND,
    "nls-cvat-england": _NLS_NOT_OFFERED,
    "nls-terrarium-england-wales": _NLS_NOT_OFFERED,
    "mapterhorn-terrarium": "Its data licence was still to be resolved, and it is too coarse for earthworks.",
    "aws-terrarium": "The research didn't check its licence or what data it mixes.",
    "srsp-scotland-phase4-dtm-colour": _NOT_THIS_RELEASE.format("Scotland")
    + " A colour ramp in which earthworks don't show.",
    "daera-ni-coastal-dtm-relief": _NOT_THIS_RELEASE.format("the Northern Ireland coast")
    + " Its tile size was assumed, not recorded.",
    "esri-world-imagery": "Esri's terms expect an ArcGIS account, which Field Club doesn't have.",
    "esri-wayback-43291": "Esri's terms expect an ArcGIS account, which Field Club doesn't have.",
    "eox-s2cloudless-2025": (
        "The research recorded no attribution for the 2018 and later layers: "
        "the line it gives names 2016 data."
    ),
    "nls-os-six-inch-first-scotland": _NOT_THIS_RELEASE.format("Scotland"),
    "nls-os-six-inch-first-wiltshire": (
        "One county's tileset of about 56. The others, and every county's bounds, weren't recorded."
    ),
    "nls-os-25-inch-wiltshire": (
        "One county's tileset of about 56, and its terms are documented only on one sheet's page."
    ),
    "nls-roy-military-survey-lowlands": _BRITISH_LIBRARY,
    "nls-roy-military-survey-highlands": _BRITISH_LIBRARY,
    "maptiler-nls-os-25k-1937-61": "Needs a MapTiler key, and wasn't tested with one.",
    "hes-designations-scheduled-monuments-export": _NOT_THIS_RELEASE.format("Scotland")
    + " Not a tile cache: the research recommended serving our own vector tiles instead.",
    "dmw-cadw-scheduled-monuments-wms": _NOT_THIS_RELEASE.format("Wales")
    + " Its attribution needs the date the data was received.",
    "opendomesday-places-vector": "A private server whose owner asks not to be hot-linked without asking.",
    "openfreemap-planet": "Offered as the `osm` overlay.",
    "osm-standard-raster": (
        "Offered as the `osm_standard` view, for development: "
        "the tile policy rules it out as a production dependency."
    ),
    "eox-osm-overlay": "A sparse raster fallback for the `osm` overlay, which is offered and shows far more.",
    "os-maps-api-outdoor": "Needs an Ordnance Survey key, and wasn't tested with one.",
    "mra-coal-mine-entries": "Its attribution wasn't recorded and the one tile fetched was probably blank.",
    "cranfield-soilscapes": "Its licence for this service wasn't confirmed.",
}


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
    *offered(PUBLISHED_LIDAR),
    *offered(PUBLISHED_IMAGERY),
    *offered(PUBLISHED_HISTORIC),
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
    *offered(PUBLISHED_GEOLOGY),
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
