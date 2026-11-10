"""Tile rendering: seams, Terrarium encoding, no data, and the two caches."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fieldclub.storage import LocalStorage
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.grid import TILE_SIZE, TileNotFoundError, Window, tile_at
from fieldclub.terrain.render import (
    TileRenderer,
    UnknownStyleError,
    terrarium_decode,
    terrarium_encode,
    to_pixels,
    transparent_png,
)
from fieldclub.terrain.styles import STYLES, elevation_buffer
from tests.terrain.fakes import FunctionSource, rolling_hills

AVEBURY = (-1.8542, 51.4286)


def decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)))


@pytest.fixture
def source() -> FunctionSource:
    return FunctionSource(rolling_hills)


@pytest.fixture
def renderer(source: FunctionSource, tmp_path: Path) -> TileRenderer:
    return TileRenderer(lambda zoom: source, LocalStorage(tmp_path / "tiles"))


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
        (dx, dy): decode(renderer.lidar_png(style_id, zoom, x + dx, y + dy)) for dx in (0, 1) for dy in (0, 1)
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


def test_terrarium_encodes_no_data_as_sea_level() -> None:
    rgb = terrarium_encode(np.array([np.nan, 12.5], dtype=np.float32))
    assert terrarium_decode(rgb).tolist() == [0.0, 12.5]


def test_dem_tiles_are_opaque_terrarium_of_the_tile_without_its_buffer(
    renderer: TileRenderer, source: FunctionSource
) -> None:
    x, y = tile_at(*AVEBURY, 15)
    rgb = decode(renderer.dem_png(15, x, y))
    assert rgb.shape == (TILE_SIZE, TILE_SIZE, 3)
    window = Window.tile(15, x, y)
    expected = source.read(window.bounds, TILE_SIZE, TILE_SIZE)
    assert np.abs(terrarium_decode(rgb) - expected).max() <= 1 / 512 + 1e-6


# --------------------------------------------------------------------------
# No data
# --------------------------------------------------------------------------


def test_a_tile_with_no_data_is_transparent(tmp_path: Path) -> None:
    empty = FunctionSource(lambda xs, ys: np.full(xs.shape, np.nan))
    renderer = TileRenderer(lambda zoom: empty, LocalStorage(tmp_path))
    assert renderer.lidar_png("composite", 14, 8100, 5400) == transparent_png()
    image = Image.open(io.BytesIO(transparent_png()))
    assert image.size == (TILE_SIZE, TILE_SIZE)
    assert np.asarray(image)[..., -1].max() == 0
    rgb = decode(renderer.dem_png(14, 8100, 5400))
    assert (terrarium_decode(rgb) == 0).all()


def test_part_of_a_tile_with_no_data_is_transparent_and_the_rest_opaque(tmp_path: Path) -> None:
    x, y = tile_at(*AVEBURY, 15)
    window = Window.tile(15, x, y)
    middle = window.x_centres()[256]
    half = FunctionSource(lambda xs, ys: np.where(xs < middle, rolling_hills(xs, ys), np.nan))
    renderer = TileRenderer(lambda zoom: half, LocalStorage(tmp_path))
    for style_id in STYLES:
        pixels = decode(renderer.lidar_png(style_id, 15, x, y))
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
    again = TileRenderer(lambda zoom: source, LocalStorage(tmp_path / "tiles"))
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
    assert f"lidar/composite/v{style.version}/synthetic/14/{x}/{y}.png" in keys
    assert any(key.startswith("elevation/") and "/synthetic/" in key for key in keys)


def test_nothing_is_cached_when_elevation_cannot_be_read(tmp_path: Path) -> None:
    calls = []

    class Failing(FunctionSource):
        def read(self, bounds, width, height):
            calls.append(bounds)
            raise ElevationUnavailableError()

    renderer = TileRenderer(lambda zoom: Failing(rolling_hills), LocalStorage(tmp_path))
    for _ in range(2):
        with pytest.raises(ElevationUnavailableError):
            renderer.lidar_png("composite", 14, 8100, 5400)
    assert len(calls) == 2
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_an_uncacheable_source_is_never_cached(source: FunctionSource, tmp_path: Path) -> None:
    source.cacheable = False
    renderer = TileRenderer(lambda zoom: source, LocalStorage(tmp_path))
    renderer.lidar_png("slope", 14, 8100, 5400)
    renderer.lidar_png("slope", 14, 8100, 5400)
    assert len(source.reads) == 2
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


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
