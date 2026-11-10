"""Web Mercator map tiles of 512 pixels, as global pixel windows.

A window is a rectangle of pixels on the global grid of one zoom level. A map
tile is the window of its 512 by 512 pixels, and a buffered tile is that
window grown by the same number of pixels on every side. Two windows that
overlap name the same pixels with the same global indices, so anything
computed per pixel from those indices agrees between them. That is what keeps
tiles seamless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from fieldclub.errors import NotFoundError

TILE_SIZE = 512
EARTH_RADIUS = 6_378_137.0
# Half the width of the Web Mercator square, in metres.
HALF_WORLD = math.pi * EARTH_RADIUS

# Kernel radii are given in metres and turned into pixels at this latitude, the
# middle of England, so that a radius in pixels is the same for every tile of a
# zoom level. Working it out per tile would let neighbouring tiles round to
# different radii and show a seam. Across England (50 to 55.8 N) the true
# radius stays within 7% of the nominal one.
REFERENCE_LATITUDE = 52.5


class TileNotFoundError(NotFoundError):
    code = "tile_not_found"
    message = "There's no such map tile."


def resolution(zoom: int) -> float:
    """Metres of Web Mercator per pixel at a zoom level."""
    return 2 * HALF_WORLD / (TILE_SIZE * 2**zoom)


def nominal_ground_resolution(zoom: int) -> float:
    """Ground metres per pixel at the reference latitude."""
    return resolution(zoom) * math.cos(math.radians(REFERENCE_LATITUDE))


def longitude_of(x: np.ndarray) -> np.ndarray:
    """Longitude in degrees of Web Mercator eastings."""
    return np.degrees(x / EARTH_RADIUS)


def latitude_of(y: np.ndarray) -> np.ndarray:
    """Latitude in degrees of Web Mercator northings."""
    return np.degrees(np.arctan(np.sinh(y / EARTH_RADIUS)))


def check_tile(z: int, x: int, y: int, *, minzoom: int = 0, maxzoom: int = 24) -> None:
    """Refuse a tile that doesn't exist, or a zoom outside the served range."""
    if not minzoom <= z <= maxzoom:
        raise TileNotFoundError(f"Zoom {z} is outside {minzoom} to {maxzoom}.", code="zoom_out_of_range")
    if not (0 <= x < 2**z and 0 <= y < 2**z):
        raise TileNotFoundError(f"There's no tile {x}, {y} at zoom {z}.")


@dataclass(frozen=True)
class Window:
    """A rectangle of pixels on the global grid of one zoom level."""

    zoom: int
    col: int
    row: int
    width: int
    height: int

    def __post_init__(self) -> None:
        assert self.width > 0, "a window needs a width"
        assert self.height > 0, "a window needs a height"

    @classmethod
    def tile(cls, z: int, x: int, y: int, buffer: int = 0) -> Window:
        assert buffer >= 0, "a buffer can't be negative"
        return cls(
            z, x * TILE_SIZE - buffer, y * TILE_SIZE - buffer, TILE_SIZE + 2 * buffer, TILE_SIZE + 2 * buffer
        )

    def grow(self, buffer: int) -> Window:
        return Window(
            self.zoom, self.col - buffer, self.row - buffer, self.width + 2 * buffer, self.height + 2 * buffer
        )

    @property
    def resolution(self) -> float:
        return resolution(self.zoom)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east, north in Web Mercator metres."""
        res = self.resolution
        west = -HALF_WORLD + self.col * res
        north = HALF_WORLD - self.row * res
        return west, north - self.height * res, west + self.width * res, north

    def x_centres(self) -> np.ndarray:
        """Eastings of pixel centres, from their global column index."""
        return (
            -HALF_WORLD
            + (np.arange(self.col, self.col + self.width, dtype=np.float64) + 0.5) * self.resolution
        )

    def y_centres(self) -> np.ndarray:
        """Northings of pixel centres, from their global row index."""
        return (
            HALF_WORLD
            - (np.arange(self.row, self.row + self.height, dtype=np.float64) + 0.5) * self.resolution
        )

    def ground_resolution(self) -> np.ndarray:
        """Ground metres per pixel for each row, as a column so it broadcasts over the window."""
        latitudes = latitude_of(self.y_centres())
        return (self.resolution * np.cos(np.radians(latitudes))).astype(np.float32)[:, np.newaxis]


def window_for(bounds: tuple[float, float, float, float], width: int, height: int) -> Window:
    """The window whose bounds these are. They must lie on a zoom level's pixel grid."""
    west, south, east, north = bounds
    zoom = round(math.log2(2 * HALF_WORLD / ((east - west) / width) / TILE_SIZE))
    res = resolution(zoom)
    col, row = (west + HALF_WORLD) / res, (HALF_WORLD - north) / res
    assert abs((east - west) / width - res) < res * 1e-9, (
        "bounds and width don't make a zoom level's resolution"
    )
    assert abs((north - south) / height - res) < res * 1e-9, (
        "bounds and height don't make a zoom level's resolution"
    )
    assert abs(col - round(col)) < 1e-6, "bounds are not on the pixel grid"
    assert abs(row - round(row)) < 1e-6, "bounds are not on the pixel grid"
    return Window(zoom, round(col), round(row), width, height)


def lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * EARTH_RADIUS
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_RADIUS
    return x, y


def tile_at(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """The column and row of the tile that contains a position."""
    x, y = lonlat_to_mercator(lon, lat)
    span = 2 * HALF_WORLD / 2**zoom
    return int((x + HALF_WORLD) // span), int((HALF_WORLD - y) // span)


def tiles_in(bbox: tuple[float, float, float, float], zoom: int) -> list[tuple[int, int]]:
    """Every tile at a zoom level that a WGS84 box (west, south, east, north) touches."""
    west, south, east, north = bbox
    x0, y0 = tile_at(west, north, zoom)
    x1, y1 = tile_at(east, south, zoom)
    last = 2**zoom - 1
    return [
        (x, y) for x in range(max(0, x0), min(last, x1) + 1) for y in range(max(0, y0), min(last, y1) + 1)
    ]
