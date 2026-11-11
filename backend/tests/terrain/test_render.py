"""Tile rendering: seams, Terrarium encoding, no data, and the two caches."""

from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fieldclub.errors import TileNotFoundError
from fieldclub.storage import LocalStorage
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.grid import TILE_SIZE, Window, nominal_ground_resolution, tile_at
from fieldclub.terrain.render import (
    DEM_KIND,
    ELEVATION_FORMAT,
    NODATA_ELEVATION_M,
    TileRenderer,
    UnknownStyleError,
    fill_near_gaps,
    terrarium_decode,
    terrarium_encode,
    tile_version,
    to_pixels,
    transparent_png,
)
from fieldclub.terrain.styles import SLRM, STYLES, elevation_buffer, local_relief_stretch
from tests.helpers import AVEBURY
from tests.terrain.fakes import FunctionSource, decode_png, rolling_hills, single_source_renderer


@pytest.fixture
def source() -> FunctionSource:
    return FunctionSource(rolling_hills)


@pytest.fixture
def renderer(source: FunctionSource, tmp_path: Path) -> TileRenderer:
    return single_source_renderer(source, LocalStorage(tmp_path / "tiles"))


# --------------------------------------------------------------------------
# Seams
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zoom", [13, 16])
@pytest.mark.parametrize("style_id", list(STYLES))
def test_adjacent_tiles_agree_with_one_window_across_their_edge(
    renderer: TileRenderer, style_id: str, zoom: int
) -> None:
    x, y = tile_at(*AVEBURY, zoom)
    tiles = {
        (dx, dy): decode_png(renderer.lidar_png(style_id, zoom, x + dx, y + dy).png)
        for dx in (0, 1)
        for dy in (0, 1)
    }
    # One window over the middle of the 2 by 2 block, covering both shared edges and the corner.
    window = Window(zoom, x * TILE_SIZE + 384, y * TILE_SIZE + 384, 256, 256)
    across = to_pixels(renderer.render_window(style_id, window))
    for (dx, dy), tile in tiles.items():
        # The part of this tile that the window covers, in window and in tile pixels.
        left, top = (x + dx) * TILE_SIZE, (y + dy) * TILE_SIZE
        c0, r0 = max(window.col, left), max(window.row, top)
        c1 = min(window.col + window.width, left + TILE_SIZE)
        r1 = min(window.row + window.height, top + TILE_SIZE)
        from_tile = tile[r0 - top : r1 - top, c0 - left : c1 - left].astype(int)
        from_window = across[r0 - window.row : r1 - window.row, c0 - window.col : c1 - window.col].astype(int)
        assert from_tile.shape == from_window.shape
        assert np.abs(from_tile - from_window).max() <= 1, f"{style_id} z{zoom} tile {dx},{dy} disagrees"


def test_the_buffer_covers_the_largest_radius_of_every_style() -> None:
    for zoom in range(7, 17):
        for style in STYLES.values():
            assert elevation_buffer(zoom) >= style.buffer(zoom)
            assert all(style.buffer(zoom) > radius.pixels(zoom) for radius in style.radii)


# --------------------------------------------------------------------------
# Terrarium
# --------------------------------------------------------------------------


def test_terrarium_round_trip_is_exact_to_a_256th_of_a_metre() -> None:
    rng = np.random.default_rng(7)
    heights = np.concatenate([rng.uniform(-100, 1400, 10_000), [0.0, -0.001, 978.59765625, 1344.9]]).astype(
        np.float32
    )
    decoded = terrarium_decode(terrarium_encode(heights))
    assert np.abs(decoded - heights.astype(np.float64)).max() <= 1 / 512 + 1e-9
    # Values on the 1/256 m grid come back exactly.
    steps = (np.arange(-2000, 2000) / 256).astype(np.float32)
    assert np.array_equal(terrarium_decode(terrarium_encode(steps)), steps.astype(np.float64))


def test_small_gaps_take_the_nearest_height_and_far_ones_stay_empty() -> None:
    elevation = np.full((40, 60), 120.0, dtype=np.float32)
    elevation[:, 30:] = np.nan
    elevation[10:14, 5:9] = np.nan
    filled = fill_near_gaps(elevation, 5)
    # An inland hole, such as a gap between surveys, is filled.
    assert (filled[10:14, 5:9] == 120.0).all()
    # Beyond the edge of the data, five pixels are filled and the rest stay empty.
    assert (filled[:, 30:35] == 120.0).all()
    assert np.isnan(filled[:, 36:]).all()


def test_gap_filling_agrees_between_windows_that_carry_the_reach_as_buffer() -> None:
    rng = np.random.default_rng(3)
    elevation = rng.uniform(50, 60, (120, 120)).astype(np.float32)
    elevation[rng.uniform(size=elevation.shape) < 0.3] = np.nan
    elevation[:, 70:] = np.nan
    whole = fill_near_gaps(elevation, 8)
    for top, left in ((0, 40), (30, 55), (60, 64)):
        window = elevation[top : top + 56, left : left + 56]
        part = fill_near_gaps(window, 8)[8:-8, 8:-8]
        np.testing.assert_array_equal(part, whole[top + 8 : top + 48, left + 8 : left + 48])


def test_dem_tiles_fill_the_edge_of_the_data_for_the_buffer_then_sea_level(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    window = Window.tile(15, x, y)
    middle = window.x_centres()[256]
    half = FunctionSource(lambda xs, ys: np.where(xs < middle, 80.0, np.nan))
    heights = terrarium_decode(
        decode_png(single_source_renderer(half, LocalStorage(tmp_path)).dem_png(15, x, y).png)
    )
    reach = elevation_buffer(15)
    assert (heights[:, : 256 + reach] == 80.0).all()
    assert (heights[:, 256 + reach + 1 :] == 0.0).all()


def test_a_void_inside_the_data_wider_than_the_reach_draws_sea_level(tmp_path: Path) -> None:
    """A known artefact, kept visible: inland gaps such as the North York Moors' are drawn at 0 m.

    Neither source can tell them from the sea. If this starts failing, the
    render docstring, ARCHITECTURE.md and the WS2 plan entry describe it too.
    """
    x, y = tile_at(*AVEBURY, 15)
    window = Window.tile(15, x, y)
    west, east = window.x_centres()[100], window.x_centres()[400]
    moor = FunctionSource(lambda xs, ys: np.where((xs > west) & (xs < east), np.nan, 250.0))
    heights = terrarium_decode(
        decode_png(single_source_renderer(moor, LocalStorage(tmp_path), fill=moor).dem_png(15, x, y).png)
    )
    reach = elevation_buffer(15)
    assert (heights[:, : 100 + reach] == 250.0).all()
    assert NODATA_ELEVATION_M == 0.0
    assert (heights[:, 101 + reach : 400 - reach] == NODATA_ELEVATION_M).all()


def test_beyond_the_reach_dem_tiles_take_the_fill_where_it_has_data(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    window = Window.tile(15, x, y)
    middle, three_quarters = window.x_centres()[256], window.x_centres()[400]
    half = FunctionSource(lambda xs, ys: np.where(xs < middle, 80.0, np.nan))
    fill = FunctionSource(lambda xs, ys: np.where(xs < three_quarters, 75.0, np.nan), edition="overview")
    renderer = single_source_renderer(half, LocalStorage(tmp_path), fill=fill)
    tile = renderer.dem_png(15, x, y)
    heights = terrarium_decode(decode_png(tile.png))
    reach = elevation_buffer(15)
    assert (heights[:, : 256 + reach] == 80.0).all()
    assert (heights[:, 256 + reach + 1 : 400] == 75.0).all()
    # Where neither has data: sea level.
    assert (heights[:, 401:] == 0.0).all()
    assert tile.cacheable
    keys = [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.png")]
    assert keys == [f"dem/v2/{ELEVATION_FORMAT}/synthetic/overview/15/{x}/{y}.png"]


def test_a_dem_tile_the_fill_never_touches_is_keyed_without_it(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    fill = FunctionSource(lambda xs, ys: np.full(xs.shape, 1.0), edition="overview")
    fill.cacheable = False
    renderer = single_source_renderer(FunctionSource(rolling_hills), LocalStorage(tmp_path), fill=fill)
    # The fill isn't drawn from, so its edition and its cacheability don't matter.
    assert renderer.dem_png(15, x, y).cacheable
    assert fill.reads == []
    keys = [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.png")]
    assert keys == [f"dem/v2/{ELEVATION_FORMAT}/synthetic/15/{x}/{y}.png"]


def test_a_dem_tile_drawing_on_a_fill_that_is_still_filling_isnt_cached(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    fill = FunctionSource(lambda xs, ys: np.full(xs.shape, 1.0), edition="overview")
    fill.cacheable = False
    empty = FunctionSource(lambda xs, ys: np.full(xs.shape, np.nan))
    renderer = single_source_renderer(empty, LocalStorage(tmp_path), fill=fill)
    tile = renderer.dem_png(15, x, y)
    assert not tile.cacheable
    assert (terrarium_decode(decode_png(tile.png)) == 1.0).all()
    assert not list(tmp_path.rglob("*.png"))


def test_a_tile_carries_the_version_of_the_editions_it_was_drawn_from(
    renderer: TileRenderer, source: FunctionSource
) -> None:
    x, y = tile_at(*AVEBURY, 14)
    assert renderer.lidar_png("slope", 14, x, y).version == tile_version("slope", [source.edition])
    assert renderer.dem_png(14, x, y).version == tile_version(DEM_KIND, [source.edition])


def test_terrarium_encodes_no_data_as_sea_level() -> None:
    rgb = terrarium_encode(np.array([np.nan, 12.5], dtype=np.float32))
    assert terrarium_decode(rgb).tolist() == [0.0, 12.5]


def test_dem_tiles_are_opaque_terrarium_of_the_tile_without_its_buffer(
    renderer: TileRenderer, source: FunctionSource
) -> None:
    x, y = tile_at(*AVEBURY, 15)
    rgb = decode_png(renderer.dem_png(15, x, y).png)
    assert rgb.shape == (TILE_SIZE, TILE_SIZE, 3)
    window = Window.tile(15, x, y)
    expected = source.read(window.bounds, TILE_SIZE, TILE_SIZE)
    assert np.abs(terrarium_decode(rgb) - expected).max() <= 1 / 512 + 1e-6


# --------------------------------------------------------------------------
# No data
# --------------------------------------------------------------------------


def test_a_tile_with_no_data_is_transparent(tmp_path: Path) -> None:
    empty = FunctionSource(lambda xs, ys: np.full(xs.shape, np.nan))
    renderer = single_source_renderer(empty, LocalStorage(tmp_path))
    assert renderer.lidar_png("composite", 14, 8100, 5400).png == transparent_png()
    image = Image.open(io.BytesIO(transparent_png()))
    assert image.size == (TILE_SIZE, TILE_SIZE)
    assert np.asarray(image)[..., -1].max() == 0
    rgb = decode_png(renderer.dem_png(14, 8100, 5400).png)
    assert (terrarium_decode(rgb) == 0).all()


def test_part_of_a_tile_with_no_data_is_transparent_and_the_rest_opaque(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    window = Window.tile(15, x, y)
    middle = window.x_centres()[256]
    half = FunctionSource(lambda xs, ys: np.where(xs < middle, rolling_hills(xs, ys), np.nan))
    renderer = single_source_renderer(half, LocalStorage(tmp_path))
    for style_id in STYLES:
        pixels = decode_png(renderer.lidar_png(style_id, 15, x, y).png)
        alpha = pixels[..., -1]
        assert (alpha[:, 260:] == 0).all(), style_id
        assert (alpha[:, :200] == 255).all(), style_id


# --------------------------------------------------------------------------
# Caches
# --------------------------------------------------------------------------


def test_elevation_is_read_once_per_tile_for_every_style(
    renderer: TileRenderer, source: FunctionSource
) -> None:
    x, y = tile_at(*AVEBURY, 14)
    for style_id in STYLES:
        renderer.lidar_png(style_id, 14, x, y)
    renderer.dem_png(14, x, y)
    assert len(source.reads) == 1


def test_a_cached_tile_is_served_without_reading_elevation(
    source: FunctionSource, renderer: TileRenderer, tmp_path: Path
) -> None:
    x, y = tile_at(*AVEBURY, 14)
    first = renderer.lidar_png("slope", 14, x, y)
    again = single_source_renderer(source, LocalStorage(tmp_path / "tiles"))
    assert again.lidar_png("slope", 14, x, y) == first
    assert len(source.reads) == 1


def test_cache_keys_carry_the_style_version_and_edition(renderer: TileRenderer, tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 14)
    renderer.lidar_png("composite", 14, x, y)
    keys = {
        path.relative_to(tmp_path / "tiles").as_posix()
        for path in (tmp_path / "tiles").rglob("*")
        if path.is_file()
    }
    style = STYLES["composite"]
    assert f"lidar/composite/v{style.version}/{ELEVATION_FORMAT}/synthetic/14/{x}/{y}.png" in keys
    assert any(key.startswith("elevation/") and "/synthetic/" in key for key in keys)


def test_nothing_is_cached_when_elevation_cannot_be_read(tmp_path: Path) -> None:
    calls = []

    class Failing(FunctionSource):
        def read(self, bounds, width, height):
            calls.append(bounds)
            raise ElevationUnavailableError()

    renderer = single_source_renderer(Failing(rolling_hills), LocalStorage(tmp_path))
    for _ in range(2):
        with pytest.raises(ElevationUnavailableError):
            renderer.lidar_png("composite", 14, 8100, 5400)
    assert len(calls) == 2
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_a_tile_says_whether_its_source_may_be_cached(renderer: TileRenderer) -> None:
    x, y = tile_at(*AVEBURY, 14)
    assert renderer.lidar_png("slope", 14, x, y).cacheable
    assert renderer.lidar_png("slope", 14, x, y).cacheable
    assert renderer.dem_png(14, x, y).cacheable


def test_an_uncacheable_source_is_never_cached(source: FunctionSource, tmp_path: Path) -> None:
    source.cacheable = False
    renderer = single_source_renderer(source, LocalStorage(tmp_path))
    assert not renderer.lidar_png("slope", 14, 8100, 5400).cacheable
    assert not renderer.dem_png(14, 8100, 5400).cacheable
    assert len(source.reads) == 2
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_the_local_relief_stretch_widens_with_the_ground_its_radius_covers() -> None:
    # 2 m at RVT's 10 m radius, so the contrast stays steady when the pixel floor grows the radius.
    for zoom in range(7, 17):
        radius_m = SLRM.pixels(zoom) * nominal_ground_resolution(zoom)
        assert local_relief_stretch(zoom) == pytest.approx(2.0 * radius_m / 10.0)
    assert local_relief_stretch(16) == pytest.approx(2.0, rel=0.05)
    assert local_relief_stretch(11) > 6 * local_relief_stretch(16)


def test_the_tile_version_changes_with_style_version_format_and_editions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tile_version("composite", ["a", "b"])
    assert base == tile_version("composite", ["a", "b"])
    assert len({base, tile_version("slope", ["a", "b"]), tile_version(DEM_KIND, ["a", "b"])}) == 3
    assert tile_version("composite", ["a", "c"]) != base
    monkeypatch.setattr("fieldclub.terrain.render.ELEVATION_FORMAT", "e-next")
    assert tile_version("composite", ["a", "b"]) != base
    monkeypatch.undo()
    monkeypatch.setitem(STYLES, "composite", replace(STYLES["composite"], version="next"))
    assert tile_version("composite", ["a", "b"]) != base


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_unknown_styles_and_tiles_are_refused(renderer: TileRenderer) -> None:
    with pytest.raises(UnknownStyleError):
        renderer.lidar_png("hillshade_rainbow", 14, 0, 0)
    with pytest.raises(TileNotFoundError) as zoom:
        renderer.lidar_png("composite", 17, 0, 0)
    assert zoom.value.code == "zoom_out_of_range"
    with pytest.raises(TileNotFoundError):
        renderer.dem_png(14, 2**14, 0)
    with pytest.raises(TileNotFoundError):
        renderer.dem_png(14, 0, -1)
