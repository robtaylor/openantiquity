"""Reading elevation onto a Web Mercator grid.

`ElevationSource.read(bounds_3857, width, height)` returns float32 metres with
NaN where there is no data. The bounds must lie on a zoom level's pixel grid,
which every map tile and buffered tile does.

Each output pixel is computed from its global index alone: its centre is
projected to the British National Grid, and the elevation there is bilinearly
interpolated from the mirror at one overview level per zoom. Neighbouring
tiles therefore get identical values for the pixels they share. A pixel with
any no-data neighbour is NaN, so no-data never becomes a number.

Projecting every pixel costs about 85 ms for a buffered tile, so from zoom 10
up the projection is worked out on a lattice every 16 global pixels and
interpolated between its nodes. The error that adds was measured at 1.4 cm at
zoom 10 and under 1 mm from zoom 13.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.windows import Window as RasterWindow

from fieldclub.errors import DataIntegrityError
from fieldclub.terrain.catalogue import Catalogue
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.grid import HALF_WORLD, REFERENCE_LATITUDE, Window, window_for
from fieldclub.terrain.mirror import Mirror

LATTICE_STEP = 16
LATTICE_MINZOOM = 10

_local = threading.local()


def _to_bng() -> Transformer:
    # pyproj transformers aren't safe to share between threads.
    transformer = getattr(_local, "to_bng", None)
    if transformer is None:
        transformer = _local.to_bng = Transformer.from_crs(3857, 27700, always_xy=True)
    return transformer


def project_window(window: Window) -> tuple[np.ndarray, np.ndarray]:
    """British National Grid eastings and northings of every pixel centre in a window."""
    if window.zoom < LATTICE_MINZOOM:
        xs, ys = np.meshgrid(window.x_centres(), window.y_centres())
        return _to_bng().transform(xs, ys)
    step = LATTICE_STEP
    cols = np.arange(window.col, window.col + window.width)
    rows = np.arange(window.row, window.row + window.height)
    lattice_cols = np.arange(cols[0] // step, cols[-1] // step + 2) * step
    lattice_rows = np.arange(rows[0] // step, rows[-1] // step + 2) * step
    res = window.resolution
    xs, ys = np.meshgrid(-HALF_WORLD + (lattice_cols + 0.5) * res, HALF_WORLD - (lattice_rows + 0.5) * res)
    node_e, node_n = _to_bng().transform(xs, ys)
    col_pos = (cols - lattice_cols[0]) / step
    row_pos = (rows - lattice_rows[0]) / step
    return _bilinear_nodes(node_e, col_pos, row_pos), _bilinear_nodes(node_n, col_pos, row_pos)


def _bilinear_nodes(nodes: np.ndarray, col_pos: np.ndarray, row_pos: np.ndarray) -> np.ndarray:
    c0 = np.floor(col_pos).astype(np.intp)
    r0 = np.floor(row_pos).astype(np.intp)
    wc = (col_pos - c0)[np.newaxis, :]
    wr = (row_pos - r0)[:, np.newaxis]
    top = nodes[r0][:, c0] * (1 - wc) + nodes[r0][:, c0 + 1] * wc
    bottom = nodes[r0 + 1][:, c0] * (1 - wc) + nodes[r0 + 1][:, c0 + 1] * wc
    return top * (1 - wr) + bottom * wr


@dataclass(frozen=True)
class Grid:
    """A north-up raster in British National Grid metres, NaN for no data."""

    data: np.ndarray
    west: float
    north: float
    res: float

    def sample(self, eastings: np.ndarray, northings: np.ndarray) -> np.ndarray:
        """Bilinear interpolation between pixel centres. NaN outside the grid or next to no data."""
        cols = (eastings - self.west) / self.res - 0.5
        rows = (self.north - northings) / self.res - 0.5
        c0 = np.floor(cols).astype(np.intp)
        r0 = np.floor(rows).astype(np.intp)
        wc = (cols - c0).astype(np.float32)
        wr = (rows - r0).astype(np.float32)
        height, width = self.data.shape
        inside = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < width) & (r0 + 1 < height)
        c0 = np.clip(c0, 0, max(0, width - 2))
        r0 = np.clip(r0, 0, max(0, height - 2))
        c1 = np.minimum(c0 + 1, width - 1)
        r1 = np.minimum(r0 + 1, height - 1)
        data = self.data
        top = data[r0, c0] * (1 - wc) + data[r0, c1] * wc
        bottom = data[r1, c0] * (1 - wc) + data[r1, c1] * wc
        out = top * (1 - wr) + bottom * wr
        return np.where(inside, out, np.float32(np.nan)).astype(np.float32)


class ElevationSource(Protocol):
    # What the values come from. Part of every cache key.
    edition: str
    # Whether the same edition always gives the same values, so they may be cached.
    cacheable: bool

    def read(self, bounds: tuple[float, float, float, float], width: int, height: int) -> np.ndarray:
        """Float32 metres on the Web Mercator grid of `bounds`, NaN for no data."""
        ...


def target_resolution(window: Window) -> float:
    """Ground metres per pixel at the reference latitude: the same for every tile of a zoom level."""
    return window.resolution * math.cos(math.radians(REFERENCE_LATITUDE))


class CogMosaicSource:
    """COGs laid on one grid, read at a resolution that suits the output.

    `paths_for(bbox)` names the files covering a British National Grid box.
    A read picks the coarsest of `resolutions` (in metres) that is no
    coarser than asked, and no finer than the files themselves, and reads
    each file's part of the box onto that grid in one windowed read, averaged
    down where the grid is coarser than the file. GDAL takes the nearest
    overview for that. Every resolution of the 1 m mirror divides 5 km, so
    neighbouring tiles fill neighbouring cells and nothing straddles their
    edge. A file of any size works, such as a coastal tile cropped to the land.

    `cacheable` is False for a source whose answer can change without its
    edition changing, such as the mirror read without fetching, which gains
    tiles over time.
    """

    def __init__(
        self,
        edition: str,
        paths_for: Callable[[tuple[float, float, float, float]], Sequence[str]],
        resolutions: Sequence[float],
        *,
        cacheable: bool = True,
    ) -> None:
        assert list(resolutions) == sorted(resolutions), "resolutions run from fine to coarse"
        self.edition = edition
        self.cacheable = cacheable
        self._paths_for = paths_for
        self._resolutions = tuple(resolutions)

    def read(self, bounds: tuple[float, float, float, float], width: int, height: int) -> np.ndarray:
        window = window_for(bounds, width, height)
        eastings, northings = project_window(window)
        return self.sample(eastings, northings, target_resolution(window))

    def sample(self, eastings: np.ndarray, northings: np.ndarray, resolution: float) -> np.ndarray:
        """Elevation at grid positions, read at the coarsest level no coarser than `resolution`."""
        assert eastings.shape == northings.shape, "eastings and northings must match"
        finite = np.isfinite(eastings) & np.isfinite(northings)
        if not finite.any():
            return np.full(eastings.shape, np.nan, dtype=np.float32)
        bbox = (
            float(eastings[finite].min()),
            float(northings[finite].min()),
            float(eastings[finite].max()),
            float(northings[finite].max()),
        )
        grid = self.grid(bbox, resolution)
        if grid is None:
            return np.full(eastings.shape, np.nan, dtype=np.float32)
        return grid.sample(eastings, northings)

    def grid(self, bbox: tuple[float, float, float, float], resolution: float) -> Grid | None:
        """The files' data over a box, laid on one grid. None when no file covers it."""
        paths = list(self._paths_for(bbox))
        if not paths:
            return None
        with rasterio.open(paths[0]) as first:
            base = float(first.res[0])
            origin_e, origin_n = float(first.transform.c), float(first.transform.f)
        usable = [r for r in self._resolutions if r >= base * (1 - 1e-9)] or [base]
        res = max((r for r in usable if r <= resolution * (1 + 1e-9)), default=usable[0])
        west, south, east, north = bbox
        # On the first file's grid, with a margin of two cells so bilinear always has both neighbours.
        grid_west = origin_e + math.floor((west - origin_e) / res) * res - 2 * res
        grid_north = origin_n + math.ceil((north - origin_n) / res) * res + 2 * res
        cols = math.ceil((east - grid_west) / res) + 2
        rows = math.ceil((grid_north - south) / res) + 2
        assert rows * cols <= MAX_GRID_PIXELS, f"a {rows} by {cols} grid is too big to assemble"
        data = np.full((rows, cols), np.nan, dtype=np.float32)
        for path in paths:
            _paste(path, res, data, grid_west, grid_north)
        return Grid(data, grid_west, grid_north, res)


# About 256 MB of float32. A tile or profile never needs more than a small part of it.
MAX_GRID_PIXELS = 8192 * 8192


def _paste(path: str, res: float, data: np.ndarray, west: float, north: float) -> None:
    """Read the grid cells that lie wholly inside a file, averaging down to the grid's resolution."""
    rows, cols = data.shape
    with rasterio.open(path) as ds:
        base = float(ds.res[0])
        f_west, f_north = float(ds.transform.c), float(ds.transform.f)
        f_east, f_south = f_west + ds.width * base, f_north - ds.height * base
        eps = 1e-6
        c0 = max(0, math.ceil((f_west - west) / res - eps))
        c1 = min(cols, math.floor((f_east - west) / res + eps))
        r0 = max(0, math.ceil((north - f_north) / res - eps))
        r1 = min(rows, math.floor((north - f_south) / res + eps))
        if c1 <= c0 or r1 <= r0:
            return
        col_off = (west + c0 * res - f_west) / base
        row_off = (f_north - (north - r0 * res)) / base
        if abs(col_off - round(col_off)) > eps or abs(row_off - round(row_off)) > eps:
            raise DataIntegrityError(f"{path} isn't on the mosaic's pixel grid.")
        scale = res / base
        window = RasterWindow.from_slices(
            (round(row_off), round(row_off + (r1 - r0) * scale)),
            (round(col_off), round(col_off + (c1 - c0) * scale)),
        )
        resampling = Resampling.average if scale > 1 else Resampling.nearest
        block = ds.read(
            indexes=1, window=window, out_shape=(r1 - r0, c1 - c0), resampling=resampling, masked=True
        )
        data[r0:r1, c0:c1] = block.filled(np.nan).astype(np.float32)


# Metres. Each divides 5 km, so 5 km tiles never share a cell.
MIRROR_RESOLUTIONS = (1.0, 2.0, 4.0, 8.0, 40.0, 200.0, 1000.0)
# The national composite's own 10 m and its overviews.
NATIONAL_RESOLUTIONS = tuple(10.0 * 2**k for k in range(10))


def mirror_source(mirror: Mirror, *, fetch: bool = True) -> CogMosaicSource:
    """The 1 m mosaic over a mirror. With `fetch` off, tiles not yet mirrored read as no data."""
    catalogue: Catalogue = mirror.catalogue

    def paths_for(bbox: tuple[float, float, float, float]) -> list[str]:
        tiles = catalogue.covering(bbox)
        found = [mirror.ensure(tile.name) if fetch else mirror.path(tile.name) for tile in tiles]
        return [path for path in found if path is not None]

    return CogMosaicSource(mirror.edition, paths_for, MIRROR_RESOLUTIONS, cacheable=fetch)


def file_source(edition: str, path: str, *, exists: Callable[[str], bool]) -> CogMosaicSource:
    """The national 10 m composite as one COG. Unavailable until the file exists."""

    def paths_for(bbox: tuple[float, float, float, float]) -> list[str]:
        if not exists(path):
            raise ElevationUnavailableError(f"{edition} isn't built yet: {path} doesn't exist.")
        return [path]

    return CogMosaicSource(edition, paths_for, NATIONAL_RESOLUTIONS)


class Mosaic:
    """Sources in priority order. Each one fills the gaps the ones before it left."""

    def __init__(self, sources: Sequence[ElevationSource]) -> None:
        assert sources, "a mosaic needs at least one source"
        self.sources = list(sources)
        self.edition = "+".join(source.edition for source in self.sources)
        self.cacheable = all(source.cacheable for source in self.sources)

    def read(self, bounds: tuple[float, float, float, float], width: int, height: int) -> np.ndarray:
        out = self.sources[0].read(bounds, width, height)
        for source in self.sources[1:]:
            gaps = np.isnan(out)
            if not gaps.any():
                break
            out = np.where(gaps, source.read(bounds, width, height), out)
        return out
