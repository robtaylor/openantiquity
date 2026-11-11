"""The layer catalogue has the documented shape and can be extended."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from fieldclub import layers
from fieldclub.schemas.meta import CoverageOverlay, RakingView, RasterView
from fieldclub.terrain.render import tile_version
from fieldclub.terrain.service import default_editions
from fieldclub.vocab import SourceReuse


@pytest.fixture
def restore_catalogue() -> Iterator[None]:
    views, overlays = list(layers.VIEWS), list(layers.OVERLAYS)
    yield
    layers.VIEWS[:] = views
    layers.OVERLAYS[:] = overlays


def dump() -> dict:
    return layers.build_layers().model_dump(mode="json")


def test_views_in_order() -> None:
    assert [view["id"] for view in dump()["views"]] == [
        "composite",
        "local_relief",
        "sky_view",
        "multi_shade",
        "slope",
        "openness",
        "raking",
        "ea_hillshade",
        "nls_hillshade",
        "nls_air_photos_1944",
        "eox_sentinel_2016",
        "nls_six_inch_1888",
        "nls_25k_1945",
        "nls_one_inch_1920s",
        "nls_bartholomew_1897",
        "nls_bartholomew_1940s",
        "nls_ten_mile",
        "osm_standard",
        "bgs_bedrock_625k",
        "bgs_superficial_50k",
    ]


def test_views_come_grouped_as_the_layer_panel_shows_them() -> None:
    groups = [view["group"] for view in dump()["views"]]
    order = ["lidar", "imagery", "historic", "map", "geology"]
    assert groups == sorted(groups, key=order.index)


WORKLIST = Path(__file__).resolve().parents[2] / "docs" / "sources" / "worklists" / "map-layers.json"


@pytest.fixture(scope="module")
def worklist() -> dict[str, dict]:
    return {entry["id"]: entry for entry in json.loads(WORKLIST.read_text(encoding="utf-8"))}


def test_every_work_list_layer_is_offered_or_left_out_with_a_reason(worklist: dict[str, dict]) -> None:
    offered, left_out = set(layers.FROM_WORKLIST), set(layers.LEFT_OUT)
    assert not offered & left_out
    assert offered | left_out == set(worklist)
    assert all(reason.strip() for reason in layers.LEFT_OUT.values())


def test_a_published_layer_is_the_work_lists_word_for_word(worklist: dict[str, dict]) -> None:
    views = {view.id: view for view in layers.build_layers().views}
    for worklist_id, view_id in layers.FROM_WORKLIST.items():
        entry, view = worklist[worklist_id], views[view_id]
        assert isinstance(view, RasterView), view_id
        assert entry["key_required"] is False, worklist_id
        assert entry["cors"].startswith("yes"), worklist_id
        assert entry["group"] == view.group, worklist_id
        assert view.tiles == entry["source"]["tiles"], worklist_id
        assert view.tile_size == entry["source"]["tileSize"], worklist_id
        assert view.attribution == entry["attribution"], worklist_id
        assert view.maxzoom == (entry["maxzoom"] or view.maxzoom), worklist_id
        assert view.minzoom == (entry["minzoom"] or 0), worklist_id
        assert view.bounds == (tuple(entry["bounds"]) if entry["bounds"] else None), worklist_id
        assert view.licence_url.startswith("https://"), worklist_id
        assert view.reuse in (SourceReuse.OPEN, SourceReuse.SHARE_ALIKE, SourceReuse.NON_COMMERCIAL)


def test_composite_matches_the_documented_shape_exactly() -> None:
    composite = dump()["views"][0]
    assert list(composite) == [
        "id",
        "title",
        "description",
        "group",
        "type",
        "tiles",
        "tile_size",
        "minzoom",
        "maxzoom",
        "attribution",
        "licence",
        "licence_url",
        "reuse",
        "bounds",
        "default",
    ]
    assert composite == {
        "id": "composite",
        "title": "Composite",
        "description": composite["description"],
        "group": "lidar",
        "type": "raster",
        "tiles": [
            f"/tiles/lidar/composite/{{z}}/{{x}}/{{y}}.png?v={tile_version('composite', default_editions())}"
        ],
        "tile_size": 512,
        "minzoom": 7,
        "maxzoom": 16,
        "attribution": composite["attribution"],
        "licence": "Open Government Licence v3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "reuse": "open",
        "bounds": None,
        "default": True,
    }
    assert composite["description"]
    assert "Open Government Licence" in composite["attribution"]


def test_lidar_raster_views_are_served_by_the_lidar_tile_endpoint() -> None:
    views = {view["id"]: view for view in dump()["views"]}
    for style in ("composite", "local_relief", "sky_view", "multi_shade", "slope", "openness"):
        view = views[style]
        assert view["type"] == "raster"
        assert view["group"] == "lidar"
        version = tile_version(style, default_editions())
        assert view["tiles"] == [f"/tiles/lidar/{style}/{{z}}/{{x}}/{{y}}.png?v={version}"]
        assert view["tile_size"] == 512
        assert view["default"] is (style == "composite")


def test_exactly_one_view_is_the_default() -> None:
    assert [view["id"] for view in dump()["views"] if view.get("default")] == ["composite"]


def test_raking_view_has_only_the_documented_keys() -> None:
    raking = next(view for view in dump()["views"] if view["id"] == "raking")
    assert set(raking) == {
        "id",
        "title",
        "group",
        "type",
        "description",
        "attribution",
        "licence",
        "licence_url",
        "reuse",
    }
    assert (raking["title"], raking["group"], raking["type"]) == ("Raking light", "lidar", "raking")


def test_openstreetmap_standard_is_a_raster_view_in_the_map_group() -> None:
    osm = next(view for view in dump()["views"] if view["id"] == "osm_standard")
    assert (osm["group"], osm["type"], osm["tile_size"]) == ("map", "raster", 256)
    assert osm["tiles"] == ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]
    assert "OpenStreetMap" in osm["attribution"]
    assert osm["default"] is False


def test_dem_source() -> None:
    dem = dump()["dem"]
    assert dem == {
        "tiles": [f"/tiles/dem/{{z}}/{{x}}/{{y}}.png?v={tile_version('dem', default_editions())}"],
        "tile_size": 512,
        "encoding": "terrarium",
        "minzoom": 7,
        "maxzoom": 16,
        "attribution": dem["attribution"],
        "licence": "Open Government Licence v3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "reuse": "open",
    }
    assert dem["attribution"]


def test_overlays() -> None:
    overlays = dump()["overlays"]
    assert [overlay["id"] for overlay in overlays] == ["osm", "records", "findings", "coverage"]
    osm, records, findings, coverage = overlays
    assert osm == {
        "id": "osm",
        "title": "OpenStreetMap",
        "type": "openmaptiles",
        "tilejson": "https://tiles.openfreemap.org/planet",
        "glyphs": "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
        "default_opacity": 0.8,
        "attribution": osm["attribution"],
        "licence": "Open Database License 1.0",
        "licence_url": "https://www.openstreetmap.org/copyright",
        "reuse": "share_alike",
    }
    assert "OpenStreetMap" in osm["attribution"]
    assert "OpenMapTiles" in osm["attribution"]
    assert records == {
        "id": "records",
        "title": "Heritage records",
        "type": "records",
        "tiles": ["/tiles/records/{z}/{x}/{y}.mvt"],
    }
    # Findings reach the map through GET /findings?format=geojson, because the
    # answer depends on who is looking. A tile would be cached for everyone.
    assert findings == {"id": "findings", "title": "Findings", "type": "findings"}
    assert coverage == {"id": "coverage", "title": "Scan coverage", "type": "coverage"}


def test_initial_view_is_avebury() -> None:
    view = dump()["initial_view"]
    assert view == {"center": [-1.8542, 51.4286], "zoom": 14}
    assert isinstance(view["zoom"], int), "a whole zoom is written as 14, not 14.0"


def test_layers_can_be_appended(restore_catalogue: None) -> None:
    layers.add_view(
        RasterView(
            id="os_six_inch",
            title="OS six-inch, 1888 to 1913",
            description="Ordnance Survey six-inch maps.",
            group="historic",
            tiles=["https://maps.example/{z}/{x}/{y}.png"],
            tile_size=256,
            minzoom=1,
            maxzoom=17,
            attribution="National Library of Scotland",
            licence="CC BY 4.0",
            licence_url="https://creativecommons.org/licenses/by/4.0/",
            reuse=SourceReuse.OPEN,
            bounds=(-8.7, 49.8, 1.8, 60.9),
        )
    )
    layers.add_overlay(CoverageOverlay(id="coverage_mine", title="My scans"), before="coverage")
    result = dump()
    assert result["views"][-1]["id"] == "os_six_inch"
    assert result["views"][-1]["bounds"] == [-8.7, 49.8, 1.8, 60.9]
    assert [overlay["id"] for overlay in result["overlays"]][-2:] == ["coverage_mine", "coverage"]


def test_duplicate_ids_are_refused(restore_catalogue: None) -> None:
    with pytest.raises(AssertionError, match="already in the catalogue"):
        layers.add_view(
            RakingView(
                id="raking",
                title="Again",
                group="lidar",
                description="x",
                attribution="y",
                **layers.LIDAR_TERMS,
            ),
        )
    with pytest.raises(AssertionError, match="already in the catalogue"):
        layers.add_overlay(CoverageOverlay(id="coverage", title="Again"))


def test_a_second_default_view_is_caught(restore_catalogue: None) -> None:
    layers.VIEWS.append(layers.lidar_view("composite", "Clone", "x").model_copy(update={"id": "clone"}))
    with pytest.raises(AssertionError, match="exactly one view must be the default"):
        layers.build_layers()


ENGLAND_LIDAR = "© Environment Agency copyright and/or database right 2022. All rights reserved."


def test_lidar_attribution_is_the_environment_agency_wording_under_ogl() -> None:
    assert layers.LIDAR_ATTRIBUTION.startswith(f"{ENGLAND_LIDAR} ")
    assert ">Open Government Licence v3.0</a>" in layers.LIDAR_ATTRIBUTION
    assert (
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        in layers.LIDAR_ATTRIBUTION
    )
    catalogue = dump()
    # Field Club's own: the comparison layers others publish carry their own credit.
    lidar = [
        view
        for view in catalogue["views"]
        if view["group"] == "lidar" and view["id"] not in layers.FROM_WORKLIST.values()
    ]
    assert len(lidar) == 7
    assert {view["attribution"] for view in lidar} == {layers.LIDAR_ATTRIBUTION}
    assert catalogue["dem"]["attribution"] == layers.LIDAR_ATTRIBUTION
    for other in ("Natural Resources Wales", "Scottish Government", "DfI"):
        assert other not in layers.LIDAR_ATTRIBUTION


def test_every_layer_from_someone_else_names_its_licence_and_reuse_class() -> None:
    """As every source does (Decision 0004). Records and findings carry theirs per feature and in /meta."""
    layers = dump()
    third_party = [*layers["views"], layers["dem"], *(o for o in layers["overlays"] if "attribution" in o)]
    assert len(third_party) == len(layers["views"]) + 2
    for layer in third_party:
        assert layer["attribution"], layer
        assert layer["licence"], layer
        assert layer["licence_url"].startswith("https://"), layer
        assert layer["reuse"] in {reuse.value for reuse in SourceReuse}, layer
