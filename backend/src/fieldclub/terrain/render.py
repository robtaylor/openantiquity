"""Map tiles from elevation: rendered styles and Terrarium elevation, through two caches.

A tile's elevation is read once, with a buffer wide enough for every style at
its zoom, and kept in `Storage` under its source's edition. Every style, and
the Terrarium tile, is made from that one array, so switching style never
reads the mirror again. Rendered PNGs are kept too, under the style's version
and the edition. Nothing is cached when elevation can't be read: an error
propagates and the next request tries again.

Tiles with no data at all are a fully transparent PNG for the styles. The
Terrarium tile has alpha 255 everywhere, as MapLibre expects, and encodes
`NODATA_ELEVATION_M` where there is no data.
"""

from __future__ import annotations

import io
import logging
import zlib
from collections.abc import Callable
from functools import cache

import numpy as np
from PIL import Image

from fieldclub.errors import NotFoundError
from fieldclub.storage import Storage, StorageNotFoundError
from fieldclub.terrain.grid import TILE_SIZE, Window, check_tile
from fieldclub.terrain.sources import ElevationSource
from fieldclub.terrain.styles import MAXZOOM, MINZOOM, STYLES, Style, elevation_buffer

logger = logging.getLogger(__name__)

# What a Terrarium tile says where there is no data: sea level, which is what
# most of England's no-data is. MapLibre needs a number for every pixel.
NODATA_ELEVATION_M = 0.0
TERRARIUM_OFFSET = 32768.0
DEM_VERSION = "1"
# Bumped when the cached elevation's layout changes.
ELEVATION_FORMAT = "e1"
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
    def __init__(self, source_for_zoom: Callable[[int], ElevationSource], storage: Storage) -> None:
        self._source_for_zoom = source_for_zoom
        self.storage = storage

    def edition(self, zoom: int) -> str:
        return self._source_for_zoom(zoom).edition

    def elevation(self, z: int, x: int, y: int) -> tuple[np.ndarray | None, Window]:
        """The tile's buffered elevation, None when it has no data, and the buffered window."""
        check_tile(z, x, y, minzoom=MINZOOM, maxzoom=MAXZOOM)
        source = self._source_for_zoom(z)
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
            return (None if empty else array), window
        if data == _EMPTY:
            return None, window
        array = _decode_array(data)
        assert array.shape == (window.height, window.width), f"cached {array.shape} for {window}"
        return array, window

    def lidar_png(self, style_id: str, z: int, x: int, y: int) -> bytes:
        found = style(style_id)
        check_tile(z, x, y, minzoom=MINZOOM, maxzoom=MAXZOOM)
        key = f"lidar/{found.id}/v{found.version}/{self.edition(z)}/{z}/{x}/{y}.png"
        return self._cached(z, key, lambda: self._render_lidar(found, z, x, y))

    def _render_lidar(self, found: Style, z: int, x: int, y: int) -> bytes:
        elevation, window = self.elevation(z, x, y)
        if elevation is None:
            return transparent_png()
        values = render_values(found, elevation, window, elevation_buffer(z))
        if not np.isfinite(values).any():
            return transparent_png()
        return to_png(to_pixels(values))

    def dem_png(self, z: int, x: int, y: int) -> bytes:
        check_tile(z, x, y, minzoom=MINZOOM, maxzoom=MAXZOOM)
        key = f"dem/v{DEM_VERSION}/{self.edition(z)}/{z}/{x}/{y}.png"
        return self._cached(z, key, lambda: self._render_dem(z, x, y))

    def _render_dem(self, z: int, x: int, y: int) -> bytes:
        elevation, _ = self.elevation(z, x, y)
        buffer = elevation_buffer(z)
        if elevation is None:
            elevation = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
        else:
            elevation = elevation[buffer : buffer + TILE_SIZE, buffer : buffer + TILE_SIZE]
        return to_png(terrarium_encode(elevation))

    def _cached(self, zoom: int, key: str, make: Callable[[], bytes]) -> bytes:
        cacheable = self._source_for_zoom(zoom).cacheable
        if cacheable:
            try:
                return self.storage.get(key)
            except StorageNotFoundError:
                pass
        data = make()
        if cacheable:
            self.storage.put(key, data, "image/png")
        return data

    def render_window(self, style_id: str, window: Window) -> np.ndarray:
        """A style over any window of a zoom level's grid, with no caching. For checks and tests."""
        found = style(style_id)
        buffer = found.buffer(window.zoom)
        grown = window.grow(buffer)
        elevation = self._source_for_zoom(window.zoom).read(grown.bounds, grown.width, grown.height)
        return render_values(found, elevation, grown, buffer)
