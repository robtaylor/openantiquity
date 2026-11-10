"""Reading the mirror onto any grid: across tile edges, at the right level, NaN for no data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from fieldclub.terrain.catalogue import SourceTile, england_catalogue
from fieldclub.terrain.cog import to_cog
from fieldclub.terrain.errors import ElevationUnavailableError, ReadTooLargeError
from fieldclub.terrain.grid import Window, tile_at
from fieldclub.terrain.mirror import Fetched, LocalMirrorStore, LocalSourceFetcher, Mirror
from fieldclub.terrain.sources import (
    ENGLAND_WGS84,
    Mosaic,
    _check_span,
    file_source,
    mirror_source,
    project_window,
)
from fieldclub.terrain.styles import elevation_buffer
from tests.terrain.fakes import FunctionSource, catalogue_of, laplacian, write_source_tile


def linear(east: np.ndarray | float, north: np.ndarray | float) -> np.ndarray:
    return np.asarray(100 + 0.01 * (np.asarray(east) - 410_000) - 0.004 * (np.asarray(north) - 165_000))


@pytest.fixture(scope="module")
def mirror(tmp_path_factory: pytest.TempPathFactory) -> Mirror:
    root = tmp_path_factory.mktemp("mirror")
    for name in ("SU16nw", "SU16ne", "SU16sw"):
        write_source_tile(root / "src", name, formula=linear)
    catalogue = catalogue_of((root / "src").glob("*.tif"))
    return Mirror(
        catalogue,
        LocalMirrorStore(root / "cogs"),
        [LocalSourceFetcher(root / "src")],
        root / "work",
        convert=lambda src, dst: to_cog(src, dst, overview_count=1),
    )


def test_heights_are_continuous_across_the_edge_between_two_tiles(mirror: Mirror) -> None:
    source = mirror_source(mirror)
    eastings = np.linspace(414_900, 415_100, 401)
    northings = np.full_like(eastings, 167_500.0)
    heights = source.sample(eastings, northings, 4.0)
    # Bilinear interpolation of a plane is exact, so only the 1 cm encoding remains.
    assert np.abs(heights - linear(eastings, northings)).max() <= 0.011
    assert mirror.has("SU16nw")
    assert mirror.has("SU16ne")


def test_no_data_where_there_is_no_tile(mirror: Mirror) -> None:
    source = mirror_source(mirror)
    # SU16se isn't in the catalogue.
    heights = source.sample(np.array([416_000.0, 414_000.0]), np.array([162_000.0, 162_000.0]), 4.0)
    assert np.isnan(heights[0])
    assert np.isfinite(heights[1])


def test_reads_use_the_coarsest_level_no_coarser_than_asked(mirror: Mirror) -> None:
    source = mirror_source(mirror)
    box = (411_000.0, 166_000.0, 414_000.0, 169_000.0)
    grid = source.grid(box, 4.0)
    assert grid is not None
    assert grid.res == 4.0
    grid = source.grid(box, 10.0)
    assert grid is not None
    assert grid.res == 8.0
    # Coarser still: whole tiles averaged down, by five.
    grid = source.grid(box, 45.0)
    assert grid is not None
    assert grid.res == 40.0
    middle = grid.sample(np.array([412_500.0]), np.array([167_500.0]))
    assert middle[0] == pytest.approx(linear(412_500.0, 167_500.0), abs=0.02)


def test_without_fetching_only_mirrored_tiles_are_read(tmp_path: Path) -> None:
    write_source_tile(tmp_path / "src", "SU16nw", formula=linear)
    catalogue = catalogue_of((tmp_path / "src").glob("*.tif"))
    mirror = Mirror(
        catalogue, LocalMirrorStore(tmp_path / "cogs"), [LocalSourceFetcher(tmp_path / "src")], tmp_path
    )
    looking = mirror_source(mirror, fetch=False)
    assert not looking.cacheable
    assert np.isnan(looking.sample(np.array([412_000.0]), np.array([167_000.0]), 4.0)[0])
    assert not mirror.has("SU16nw")


def test_a_mercator_window_reads_the_right_place(mirror: Mirror) -> None:
    to_lonlat = Transformer.from_crs(27700, 4326, always_xy=True)
    lon, lat = to_lonlat.transform(412_500, 167_500)
    x, y = tile_at(lon, lat, 15)
    window = Window.tile(15, x, y)
    heights = mirror_source(mirror).read(window.bounds, window.width, window.height)
    eastings, northings = project_window(window)
    inside = (eastings > 410_010) & (eastings < 419_990) & (northings > 160_010) & (northings < 169_990)
    assert inside.any()
    assert np.abs(heights[inside] - linear(eastings[inside], northings[inside])).max() <= 0.011


def test_the_projection_lattice_matches_exact_projection() -> None:
    to_bng = Transformer.from_crs(3857, 27700, always_xy=True)
    for zoom in (10, 13, 16):
        x, y = tile_at(-1.85, 51.43, zoom)
        window = Window.tile(zoom, x, y, 30)
        eastings, northings = project_window(window)
        xs, ys = np.meshgrid(window.x_centres(), window.y_centres())
        exact_e, exact_n = to_bng.transform(xs, ys)
        assert np.abs(eastings - exact_e).max() < 0.02
        assert np.abs(northings - exact_n).max() < 0.02


def test_a_file_source_is_unavailable_until_built(tmp_path: Path) -> None:
    missing = file_source("national", str(tmp_path / "none.tif"), exists=(tmp_path / "none.tif").is_file)
    with pytest.raises(ElevationUnavailableError):
        missing.sample(np.array([400_000.0]), np.array([200_000.0]), 10.0)


def test_a_mosaic_fills_the_first_source_gaps_from_the_next() -> None:
    first = FunctionSource(lambda xs, ys: np.where(xs < xs.mean(), 1.0, np.nan), edition="a")
    second = FunctionSource(lambda xs, ys: np.full(xs.shape, 2.0), edition="b")
    mosaic = Mosaic([first, second])
    window = Window.tile(14, 8100, 5400)
    values = mosaic.read(window.bounds, window.width, window.height)
    assert set(np.unique(values)) == {1.0, 2.0}
    assert mosaic.edition == "a+b"


def test_a_cropped_coastal_tile_sits_beside_a_whole_one(tmp_path: Path) -> None:
    write_source_tile(tmp_path / "src", "SU16nw", formula=linear)
    write_source_tile(tmp_path / "src", "SU16ne", formula=linear, width_m=1012)
    mirror = Mirror(
        catalogue_of((tmp_path / "src").glob("*.tif")),
        LocalMirrorStore(tmp_path / "cogs"),
        [LocalSourceFetcher(tmp_path / "src")],
        tmp_path / "work",
    )
    source = mirror_source(mirror)
    eastings = np.array([414_990.0, 415_010.0, 415_900.0, 416_100.0])
    northings = np.full_like(eastings, 167_500.0)
    for resolution in (4.0, 8.0, 40.0):
        heights = source.sample(eastings, northings, resolution)
        assert np.isfinite(heights[:3]).all(), resolution
        assert np.isnan(heights[3]), resolution
        assert np.abs(heights[:3] - linear(eastings[:3], northings[:3])).max() < 0.02


class RefusingFetcher:
    """A fetcher for tests that must fetch nothing."""

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        raise AssertionError(f"{tile.name} was fetched")


def england_mirror(tmp_path: Path) -> Mirror:
    return Mirror(england_catalogue(), LocalMirrorStore(tmp_path / "cogs"), [RefusingFetcher()], tmp_path)


# The box of each one's projected pixels covers part of England: the first two
# touched 167 catalogue tiles and the third 22 before reads were limited to
# England's extent. The last is the zoom 7 tile at 179.9 E on the equator,
# which failed with a grid too big to assemble.
FAR_SIDE_TILES = [(16, 65024, 32768), (13, 8128, 4096), (13, 0, 4096), (7, *tile_at(179.9, 0.0, 7))]


@pytest.mark.parametrize(("z", "x", "y"), FAR_SIDE_TILES)
def test_a_tile_on_the_far_side_of_the_world_reads_nothing_and_fetches_nothing(
    tmp_path: Path, z: int, x: int, y: int
) -> None:
    window = Window.tile(z, x, y, elevation_buffer(z))
    eastings, northings = project_window(window)
    finite = np.isfinite(eastings) & np.isfinite(northings)
    e, n = eastings[finite], northings[finite]
    # The hazard: the box of the projected pixels spans English eastings and northings.
    assert e.max() > 100_000
    assert e.min() < 660_000
    assert n.min() < 100_000
    assert n.max() > 600_000
    heights = mirror_source(england_mirror(tmp_path)).read(window.bounds, window.width, window.height)
    assert heights.shape == (window.height, window.width)
    assert np.isnan(heights).all()


def test_no_zoom_7_tile_outside_england_reads_anything(tmp_path: Path) -> None:
    source = mirror_source(england_mirror(tmp_path))
    west, south, east, north = ENGLAND_WGS84
    corners = (tile_at(west, north, 7), tile_at(east, south, 7))
    for x in range(0, 128, 3):
        for y in range(0, 128, 3):
            if corners[0][0] <= x <= corners[1][0] and corners[0][1] <= y <= corners[1][1]:
                continue
            window = Window.tile(7, x, y, elevation_buffer(7))
            assert np.isnan(source.read(window.bounds, window.width, window.height)).all(), (x, y)


def test_a_fetching_read_of_more_ground_than_a_tile_is_refused_before_any_fetch(tmp_path: Path) -> None:
    source = mirror_source(england_mirror(tmp_path))
    eastings = np.array([400_000.0, 420_000.0])
    northings = np.array([160_000.0, 180_000.0])
    with pytest.raises(ReadTooLargeError):
        source.sample(eastings, northings, 1.0)


def test_a_projection_far_larger_than_its_window_is_refused() -> None:
    window = Window.tile(13, 4070, 2720)
    eastings, northings = project_window(window)
    _check_span(window, eastings, northings)
    eastings[0, 0] += 100_000
    with pytest.raises(ReadTooLargeError):
        _check_span(window, eastings, northings)


def white_noise(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    """A different height in every 4 m cell, from -1 to 1 m, as a fixed hash of its position."""
    cells = np.floor(east / 4) * 12.9898 + np.floor(north / 4) * 78.233
    return 100 + 2 * (np.sin(cells) * 43758.5453 % 1.0) - 1


def test_detail_does_not_depend_on_where_a_pixel_falls_against_the_cells(tmp_path: Path) -> None:
    write_source_tile(tmp_path / "src", "SU16nw", formula=white_noise)
    mirror = Mirror(
        catalogue_of((tmp_path / "src").glob("*.tif")),
        LocalMirrorStore(tmp_path / "cogs"),
        [LocalSourceFetcher(tmp_path / "src")],
        tmp_path / "work",
        convert=lambda src, dst: to_cog(src, dst, overview_count=1),
    )
    to_lonlat = Transformer.from_crs(27700, 4326, always_xy=True)
    x, y = tile_at(*to_lonlat.transform(412_500, 167_500), 13)
    # Zoom 13 has 5.8 m pixels and reads the 4 m cells.
    window = Window(13, x * 512 + 100, y * 512 + 100, 300, 300)
    z = mirror_source(mirror).read(window.bounds, window.width, window.height)
    assert np.isfinite(z).all()
    eastings, northings = project_window(window)
    detail = np.abs(laplacian(z))
    fx = (eastings[1:-1, 1:-1] / 4 - 0.5) % 1
    fy = (northings[1:-1, 1:-1] / 4 - 0.5) % 1
    off_centre = np.maximum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
    on_centre = float(np.median(detail[off_centre < 0.15]))
    half_way = float(np.median(detail[(np.abs(fx - 0.5) < 0.15) & (np.abs(fy - 0.5) < 0.15)]))
    # White noise is the worst case: bilinear interpolation gave 1.8, the B-spline 1.23.
    assert on_centre / half_way < 1.4
