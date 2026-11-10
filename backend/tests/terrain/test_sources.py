"""Reading the mirror onto any grid: across tile edges, at the right level, NaN for no data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from fieldclub.terrain.cog import to_cog
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.grid import Window, tile_at
from fieldclub.terrain.mirror import LocalMirrorStore, LocalSourceFetcher, Mirror
from fieldclub.terrain.sources import Mosaic, file_source, mirror_source, project_window
from tests.terrain.fakes import FunctionSource, catalogue_of, write_source_tile


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
    missing = file_source("national", str(tmp_path / "none.tif"), exists=lambda path: Path(path).is_file())
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
