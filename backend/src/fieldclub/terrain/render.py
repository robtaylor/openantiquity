"""Map tiles from elevation: rendered styles and Terrarium elevation, through two caches.

A tile's elevation is read once, with a buffer wide enough for every style at
its zoom, and kept in `Storage` under its source's edition. Every style, and
the Terrarium tile, is made from that one array, so switching style never
reads the mirror again. Rendered PNGs are kept too, under the style's version
and the edition. Nothing is cached when elevation can't be read: an error
propagates and the next request tries again.

Tiles with no data at all are a fully transparent PNG for the styles. The
Terrarium tile has alpha 255 everywhere, as MapLibre expects. A gap in the
data no wider than twice the tile's buffer takes the height of the nearest
pixel with data, and anything further from data encodes `NODATA_ELEVATION_M`.

Every key carries `ELEVATION_FORMAT`, so a change to how elevation is read
(`sources.py`, the projection lattice, the sampler) renews every tile, and a
style's `version`, so a change to a style renews its tiles. `tile_version`
folds both, with the editions, into the token the tile URLs carry.
`tests/terrain/test_versions.py` fails when pixels change and these don't.
"""

from __future__ import annotations

import hashlib
import io
import logging
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from fieldclub.errors import NotFoundError
from fieldclub.storage import Storage, StorageNotFoundError
from fieldclub.terrain.grid import TILE_SIZE, Window, check_tile
from fieldclub.terrain.sources import ElevationSource
from fieldclub.terrain.styles import MAXZOOM, MINZOOM, STYLES, Style, elevation_buffer

logger = logging.getLogger(__name__)

# What a Terrarium tile says far from any data: sea level, which is what
# most of England's no-data is. MapLibre needs a number for every pixel.
NODATA_ELEVATION_M = 0.0
TERRARIUM_OFFSET = 32768.0
DEM_VERSION = "2"
# Bumped when the cached elevation's layout or values change: e2 is the B-spline sampler.
ELEVATION_FORMAT = "e2"
DEM_KIND = "dem"
_EMPTY = b"empty"
_PNG_LEVEL = 6


class UnknownStyleError(NotFoundError):
    code = "unknown_style"
    message = "There's no such terrain style."


def terrarium_encode(elevation: np.ndarray) -> np.ndarray:
    """Metres to Terrarium RGB, rounded to the nearest 1/256 m. NaN becomes `NODATA_ELEVATION_M`."""
    values = np.where(np.isfinite(elevation), elevation, NODATA_ELEVATION_M).astype(np.float64)
    steps = np.clip(np.round((values + TERRARIUM_OFFSET) * 256), 0, 2**24 - 1).astype(np.uint32)
    rgb = np.stack([(steps >> 16) & 255, (steps >> 8) & 255, steps & 255], axis=-1)
    return rgb.astype(np.uint8)


def fill_near_gaps(elevation: np.ndarray, reach: int) -> np.ndarray:
    """No-data within `reach` pixels of data takes the nearest data's height. The rest stays NaN.

    Every pixel with data within `reach` of a tile pixel lies in the tile's
    buffered window when `reach` is no more than the buffer, so neighbouring
    tiles fill a shared gap alike.
    """
    gaps = ~np.isfinite(elevation)
    if not gaps.any() or gaps.all():
        return elevation
    found = distance_transform_edt(gaps, return_indices=True)
    assert isinstance(found, tuple), "distance_transform_edt returns distances and indices"
    distance, (rows, cols) = found
    filled = elevation[rows, cols]
    return np.where(gaps & (distance > reach), np.float32(np.nan), filled).astype(np.float32)


def terrarium_decode(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float64)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - TERRARIUM_OFFSET


def to_png(pixels: np.ndarray) -> bytes:
    """A PNG of uint8 pixels: greyscale, grey and alpha, RGB or RGBA by the last axis."""
    assert pixels.dtype == np.uint8, f"expected uint8 pixels, got {pixels.dtype}"
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG", compress_level=_PNG_LEVEL)
    return buffer.getvalue()


def to_pixels(values: np.ndarray) -> np.ndarray:
    """Rendered values from 0 to 1 as uint8, with an alpha channel only where some pixels have no data."""
    grey = values.ndim == 2
    valid = np.isfinite(values) if grey else np.isfinite(values).all(axis=-1)
    scaled = np.round(np.nan_to_num(np.clip(values, 0, 1), nan=0.0) * 255).astype(np.uint8)
    if valid.all():
        return scaled
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    channels = [scaled] if grey else [scaled[..., band] for band in range(scaled.shape[-1])]
    return np.stack([*channels, alpha], axis=-1)


@cache
def transparent_png() -> bytes:
    return to_png(np.zeros((TILE_SIZE, TILE_SIZE, 2), dtype=np.uint8))


def _encode_array(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    return zlib.compress(buffer.getvalue(), 1)


def _decode_array(data: bytes) -> np.ndarray:
    return np.load(io.BytesIO(zlib.decompress(data)), allow_pickle=False)


def tile_version(kind: str, editions: Sequence[str]) -> str:
    """The token a tile URL carries: it changes whenever a tile of this kind could.

    `kind` is a style id or `DEM_KIND`. A response is immutable only for a URL
    with the current token.
    """
    version = DEM_VERSION if kind == DEM_KIND else style(kind).version
    parts = [kind, version, ELEVATION_FORMAT, *editions]
    return hashlib.sha256("/".join(parts).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class RenderedTile:
    png: bytes
    # False when the same URL may draw differently later, so it mustn't be cached for long.
    cacheable: bool


def style(style_id: str) -> Style:
    found = STYLES.get(style_id)
    if found is None:
        raise UnknownStyleError(f"There's no terrain style called {style_id!r}.")
    return found


def render_values(style: Style, elevation: np.ndarray, window: Window, crop: int) -> np.ndarray:
    """A style's values from 0 to 1 over a buffered window, cropped by `crop` pixels on each side."""
    assert style.buffer(window.zoom) <= crop, f"{style.id} needs a buffer of {style.buffer(window.zoom)}"
    values = style.render(elevation, window.ground_resolution(), window.zoom)
    return values[crop : values.shape[0] - crop, crop : values.shape[1] - crop]


class TileRenderer:
    def __init__(
        self,
        source_for_zoom: Callable[[int], ElevationSource],
        storage: Storage,
        *,
        editions: Sequence[str],
    ) -> None:
        """`editions` lists every edition `source_for_zoom` may return, for `tile_version`."""
        assert editions, "a renderer draws from at least one edition"
        self._source_for_zoom = source_for_zoom
        self.storage = storage
        self.editions = tuple(editions)

    def version(self, kind: str) -> str:
        return tile_version(kind, self.editions)

    def _source(self, z: int, x: int, y: int) -> ElevationSource:
        """The source of a valid tile, resolved once per request."""
        check_tile(z, x, y, minzoom=MINZOOM, maxzoom=MAXZOOM)
        source = self._source_for_zoom(z)
        assert source.edition in self.editions, f"{source.edition} isn't one of {self.editions}"
        return source

    def _elevation(
        self, source: ElevationSource, z: int, x: int, y: int
    ) -> tuple[np.ndarray | None, Window, int]:
        """The tile's buffered elevation, None when it has no data, the buffered window and the buffer."""
        buffer = elevation_buffer(z)
        window = Window.tile(z, x, y, buffer)
        key = f"elevation/{ELEVATION_FORMAT}/{source.edition}/b{buffer}/{z}/{x}/{y}.npy.z"
        try:
            data = self.storage.get(key) if source.cacheable else None
        except StorageNotFoundError:
            data = None
        if data is None:
            array = source.read(window.bounds, window.width, window.height)
            assert array.shape == (window.height, window.width), f"read {array.shape} for {window}"
            empty = not np.isfinite(array).any()
            if source.cacheable:
                self.storage.put(key, _EMPTY if empty else _encode_array(array), "application/octet-stream")
            return (None if empty else array), window, buffer
        if data == _EMPTY:
            return None, window, buffer
        array = _decode_array(data)
        assert array.shape == (window.height, window.width), f"cached {array.shape} for {window}"
        return array, window, buffer

    def lidar_png(self, style_id: str, z: int, x: int, y: int) -> RenderedTile:
        found = style(style_id)
        source = self._source(z, x, y)
        key = f"lidar/{found.id}/v{found.version}/{ELEVATION_FORMAT}/{source.edition}/{z}/{x}/{y}.png"
        return self._cached(source, key, lambda: self._render_lidar(found, source, z, x, y))

    def _render_lidar(self, found: Style, source: ElevationSource, z: int, x: int, y: int) -> bytes:
        elevation, window, buffer = self._elevation(source, z, x, y)
        if elevation is None:
            return transparent_png()
        values = render_values(found, elevation, window, buffer)
        if not np.isfinite(values).any():
            return transparent_png()
        return to_png(to_pixels(values))

    def dem_png(self, z: int, x: int, y: int) -> RenderedTile:
        source = self._source(z, x, y)
        key = f"dem/v{DEM_VERSION}/{ELEVATION_FORMAT}/{source.edition}/{z}/{x}/{y}.png"
        return self._cached(source, key, lambda: self._render_dem(source, z, x, y))

    def _render_dem(self, source: ElevationSource, z: int, x: int, y: int) -> bytes:
        elevation, _, buffer = self._elevation(source, z, x, y)
        if elevation is None:
            elevation = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
        else:
            elevation = fill_near_gaps(elevation, buffer)
            elevation = elevation[buffer : buffer + TILE_SIZE, buffer : buffer + TILE_SIZE]
        return to_png(terrarium_encode(elevation))

    def _cached(self, source: ElevationSource, key: str, make: Callable[[], bytes]) -> RenderedTile:
        cacheable = source.cacheable
        if cacheable:
            try:
                return RenderedTile(self.storage.get(key), cacheable=True)
            except StorageNotFoundError:
                pass
        data = make()
        if cacheable:
            self.storage.put(key, data, "image/png")
        return RenderedTile(data, cacheable=cacheable)

    def render_window(self, style_id: str, window: Window) -> np.ndarray:
        """A style over any window of a zoom level's grid, with no caching. For checks and tests."""
        found = style(style_id)
        buffer = found.buffer(window.zoom)
        grown = window.grow(buffer)
        elevation = self._source_for_zoom(window.zoom).read(grown.bounds, grown.width, grown.height)
        return render_values(found, elevation, grown, buffer)
