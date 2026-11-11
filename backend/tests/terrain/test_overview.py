"""Zooms below 13 read the national overview: cacheable, versioned by build, joined to zoom 13."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldclub.layers import default_tile_version
from fieldclub.terrain.blobs import LocalFolder
from fieldclub.terrain.grid import HALF_WORLD, TILE_SIZE, Window, lonlat_to_mercator, resolution, tile_at
from fieldclub.terrain.mirror import Mirror
from fieldclub.terrain.national import Builder, NationalStore
from fieldclub.terrain.overview import Overview
from fieldclub.terrain.service import Terrain, get_terrain
from fieldclub.terrain.styles import elevation_buffer
from tests.terrain.fakes import TO_LONLAT, local_mirror, local_terrain, write_source_tile

# Fifteen kilometres square: SU16nw to SU27nw.
BLOCK = (
    ("SU17nw", "SU17ne", "SU27nw"),
    ("SU17sw", "SU17se", "SU27sw"),
    ("SU16nw", "SU16ne", "SU26nw"),
)
TILES = tuple(name for row in BLOCK for name in row)
# The middle of the block.
CENTRE = TO_LONLAT.transform(417_500, 172_500)
LATER = "SU27nw"


def hills(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 120 + 25 * np.sin(east / 1500.0) * np.cos(north / 1900.0) + 0.002 * (east - 410_000)


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("overview-sources")
    for name in TILES:
        write_source_tile(folder, name, formula=hills)
    return folder


def build(mirror: Mirror, root: Path) -> None:
    Builder(mirror, NationalStore(LocalFolder(root / "national")), root / "work", threads=1).build()


@pytest.fixture
def terrain(sources: Path, tmp_path: Path) -> Terrain:
    """Every tile but `LATER` mirrored and built into the overview."""
    mirror = local_mirror(tmp_path, sources=sources)
    for name in TILES:
        if name != LATER:
            mirror.ensure(name)
    build(mirror, tmp_path)
    return local_terrain(mirror, tmp_path / "tiles", national=tmp_path / "national")


def centre_tile(zoom: int) -> tuple[int, int]:
    return tile_at(*CENTRE, zoom)


def later_tile(zoom: int) -> tuple[int, int]:
    return tile_at(*TO_LONLAT.transform(422_500, 177_500), zoom)


def test_a_low_zoom_tile_inside_the_build_is_cacheable_and_drawn_from_it(terrain: Terrain) -> None:
    x, y = centre_tile(12)
    tile = terrain.renderer.lidar_png("composite", 12, x, y)
    assert tile.cacheable
    assert tile.version == terrain.renderer.version("composite")
    assert terrain.overview.snapshot().edition.endswith(terrain.overview.snapshot().manifest.build)  # type: ignore[union-attr]
    assert list((terrain.renderer.storage.root / "lidar").rglob("*.png"))  # type: ignore[attr-defined]


def test_an_area_mirrored_since_the_build_draws_and_isnt_cached_until_the_next_build(
    terrain: Terrain, tmp_path: Path
) -> None:
    zoom = 12
    x, y = later_tile(zoom)
    snapshot = terrain.overview.snapshot()
    window = Window.tile(zoom, x, y, elevation_buffer(zoom))
    before = snapshot.read(window.bounds, window.width, window.height)
    terrain.mirror.ensure(LATER)
    after = terrain.overview.snapshot().read(window.bounds, window.width, window.height)
    assert np.isfinite(after).sum() > np.isfinite(before).sum()
    tile = terrain.renderer.lidar_png("composite", zoom, x, y)
    assert not tile.cacheable
    old_version = terrain.renderer.version("composite")
    build(terrain.mirror, tmp_path)
    rebuilt = terrain.renderer.lidar_png("composite", zoom, x, y)
    assert rebuilt.cacheable
    # The new build is a new token, so nothing cached under the old one is served for it.
    assert rebuilt.version == terrain.renderer.version("composite") != old_version
    again = terrain.overview.snapshot().read(window.bounds, window.width, window.height)
    assert np.array_equal(np.isfinite(again), np.isfinite(after))


def test_a_tile_touching_an_unmirrored_tile_is_not_cacheable(terrain: Terrain) -> None:
    x, y = later_tile(12)
    assert not terrain.renderer.lidar_png("slope", 12, x, y).cacheable


def test_neighbouring_overview_tiles_agree_on_the_pixels_they_share(terrain: Terrain) -> None:
    zoom = 11
    snapshot = terrain.overview.snapshot()
    # The pixel at the centre of the block, and two windows that overlap by 48 columns round it.
    col, row = lonlat_pixel(zoom)
    left = Window(zoom, col - 256, row - 128, 280, 256)
    right = Window(zoom, col - 24, row - 128, 280, 256)
    a = snapshot.read(left.bounds, left.width, left.height)
    b = snapshot.read(right.bounds, right.width, right.height)
    overlap_a = a[:, right.col - left.col :]
    overlap_b = b[:, : overlap_a.shape[1]]
    assert np.isfinite(overlap_a).all()
    assert np.array_equal(overlap_a, overlap_b)


def lonlat_pixel(zoom: int) -> tuple[int, int]:
    """The global pixel at the centre of the block."""
    mx, my = lonlat_to_mercator(*CENTRE)
    return int((mx + HALF_WORLD) // resolution(zoom)), int((HALF_WORLD - my) // resolution(zoom))


def test_zoom_12_from_the_overview_meets_zoom_13_from_the_mirror_without_a_step(terrain: Terrain) -> None:
    x, y = centre_tile(12)
    coarse = Window.tile(12, x, y)
    fine = Window(13, coarse.col * 2, coarse.row * 2, TILE_SIZE * 2, TILE_SIZE * 2)
    low = terrain.select(12).source.read(coarse.bounds, coarse.width, coarse.height)
    high = terrain.select(13).source.read(fine.bounds, fine.width, fine.height)
    high = high.reshape(TILE_SIZE, 2, TILE_SIZE, 2).mean(axis=(1, 3))
    both = np.isfinite(low) & np.isfinite(high)
    assert both.mean() > 0.9
    difference = np.abs(low - high)[both]
    # Hills 50 m high read at 8 m and at 4 m: the levels differ by centimetres, not by a step.
    assert float(np.median(difference)) < 0.03
    assert float(difference.max()) < 0.25


def test_point_heights_come_from_the_overview_where_the_mirror_has_no_tile(
    terrain: Terrain, sources: Path, tmp_path: Path
) -> None:
    empty = local_mirror(tmp_path / "empty", sources=sources)
    store = NationalStore(LocalFolder(tmp_path / "national"))
    elsewhere = Terrain(empty, Overview(empty, store, refresh_s=0), terrain.renderer.storage)
    lon, lat = CENTRE
    height = elsewhere.elevation_at(lon, lat)
    assert height is not None
    assert height == pytest.approx(float(hills(np.array(417_500.0), np.array(172_500.0))), abs=0.1)
    assert empty.store.names() == []


def test_a_new_build_is_seen_after_the_refresh_interval(sources: Path, tmp_path: Path) -> None:
    mirror = local_mirror(tmp_path, sources=sources)
    mirror.ensure("SU16nw")
    now = [0.0]
    overview = Overview(
        mirror, NationalStore(LocalFolder(tmp_path / "national")), refresh_s=60, clock=lambda: now[0]
    )
    unbuilt = overview.edition
    assert unbuilt.endswith("-none")
    build(mirror, tmp_path)
    assert overview.edition == unbuilt
    now[0] = 61.0
    assert overview.edition != unbuilt


def test_meta_offers_the_token_of_the_current_build(
    app: FastAPI, client: TestClient, terrain: Terrain, tmp_path: Path
) -> None:
    app.dependency_overrides[get_terrain] = lambda: terrain
    views = {view["id"]: view for view in client.get("/api/v1/meta").json()["layers"]["views"]}
    before = views["composite"]["tiles"][0]
    assert before.endswith(f"?v={terrain.renderer.version('composite')}")
    terrain.mirror.ensure(LATER)
    build(terrain.mirror, tmp_path)
    views = {view["id"]: view for view in client.get("/api/v1/meta").json()["layers"]["views"]}
    after = views["composite"]["tiles"][0]
    assert after != before
    assert after.endswith(f"?v={terrain.renderer.version('composite')}")
    dem = client.get("/api/v1/meta").json()["layers"]["dem"]["tiles"][0]
    assert dem.endswith(f"?v={terrain.renderer.version('dem')}")


def test_meta_says_whether_the_overview_is_built_and_how_much_it_holds(
    app: FastAPI, client: TestClient, terrain: Terrain
) -> None:
    app.dependency_overrides[get_terrain] = lambda: terrain
    state = client.get("/api/v1/meta").json()["terrain"]
    manifest = terrain.overview.store.manifest()
    assert manifest is not None
    assert state == {
        "fine_minzoom": 13,
        "catalogue_tiles": len(terrain.catalogue),
        "overview": {"built": True, "built_at": manifest.created, "tiles": len(manifest.tiles)},
    }
    assert 0 < state["overview"]["tiles"] < state["catalogue_tiles"]


def test_only_tiles_mirrored_since_the_build_count_against_the_fallback_cap(
    terrain: Terrain, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A cap of one: the built tiles in view must not use it up.
    overview = Overview(terrain.mirror, terrain.overview.store, refresh_s=0, max_fallback_tiles=1)
    zoom = 10
    x, y = centre_tile(zoom)
    window = Window.tile(zoom, x, y, elevation_buffer(zoom))
    snapshot = overview.snapshot()
    assert LATER in snapshot.touched(window.bounds, window.width, window.height)
    assert len(snapshot.touched(window.bounds, window.width, window.height) & snapshot.built) > 1
    before = snapshot.read(window.bounds, window.width, window.height)
    terrain.mirror.ensure(LATER)
    read_from: list[frozenset[str]] = []
    real = snapshot._mirror_source

    def spy(names: frozenset[str]) -> object:
        read_from.append(names)
        return real(names)

    monkeypatch.setattr(snapshot, "_mirror_source", spy)
    after = snapshot.read(window.bounds, window.width, window.height)
    assert np.isfinite(after).sum() > np.isfinite(before).sum()
    # The fresh tile and the built ones beside it, for the sampler's margin; not the far side of the block.
    assert read_from == [{"SU27nw", "SU17ne", "SU17se", "SU27sw"}]


class UnreadableStore(NationalStore):
    def manifest(self) -> None:
        raise RuntimeError("the bucket can't be reached")


def test_meta_still_answers_when_the_overview_cannot_be_read(
    app: FastAPI, client: TestClient, terrain: Terrain, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = UnreadableStore(LocalFolder(tmp_path / "national"))
    broken = Terrain(terrain.mirror, Overview(terrain.mirror, store), terrain.renderer.storage)
    app.dependency_overrides[get_terrain] = lambda: broken
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    views = {view["id"]: view for view in response.json()["layers"]["views"]}
    # The token of no build, so no URL it offers is served as immutable.
    assert views["composite"]["tiles"][0].endswith(f"?v={default_tile_version('composite')}")
    assert response.json()["layers"]["dem"]["tiles"][0].endswith(f"?v={default_tile_version('dem')}")
    assert "Couldn't read the overview's build" in caplog.text
    assert response.json()["terrain"]["overview"] == {"built": None, "built_at": None, "tiles": 0}
