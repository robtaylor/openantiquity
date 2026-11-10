"""Grid references: WGS84 to and from the British National Grid and the Irish Grid.

Great Britain uses the Ordnance Survey National Grid (EPSG:27700), with two
letters for the 100 km square, as in `SU 1025 6996`. The island of Ireland uses
the Irish Grid (EPSG:29903), with one letter, as in `J 338 740`. Points on the
island of Ireland get an Irish reference and everything else gets a British
one.

A reference names a square, not a point. `SU 1025 6996` is the 10 m square
whose south-west corner is 410250, 169960. Digits are always truncated, never
rounded, which is the Ordnance Survey convention.

Accuracy: pyproj uses the 7-parameter datum shift unless the OSTN15 grid file
is installed, which is good to about 2 m in Great Britain and 1 m in Ireland.
That is far finer than anything a grid reference is used for here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import NamedTuple

from pyproj import Transformer
from shapely.geometry import Point, Polygon

from fieldclub.errors import BadRequestError


class GridRefError(BadRequestError):
    """A grid reference that can't be read, or a point outside both grids."""

    code = "invalid_grid_reference"
    message = "That isn't a grid reference we can read."


class GridSystem(StrEnum):
    OSGB = "osgb"
    IRISH = "irish"


_EPSG = {GridSystem.OSGB: 27700, GridSystem.IRISH: 29903}

# Extent of each grid in metres: (width, height).
_EXTENT = {GridSystem.OSGB: (700_000, 1_300_000), GridSystem.IRISH: (500_000, 500_000)}

# The 25 letters used for grid squares. There is no I.
_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

VALID_DIGITS = (2, 4, 6, 8, 10)

# A rough outline of the island of Ireland with its offshore islands, in
# longitude and latitude. It only has to separate Ireland from Great Britain,
# so it runs down the middle of the North Channel and the Irish Sea: west of
# Kintyre, Islay, Galloway, Man, Anglesey and Pembrokeshire, east of Rathlin,
# the Copelands, the Ards and Wicklow Head.
_IRELAND = Polygon(
    [
        (-11.0, 51.2),
        (-5.8, 51.2),
        (-5.8, 53.6),
        (-5.3, 54.0),
        (-5.3, 54.85),
        (-5.7, 55.12),
        (-5.97, 55.27),
        (-5.97, 55.47),
        (-11.0, 55.47),
    ]
)

_REF_PATTERN = re.compile(r"^\s*([A-Za-z]{1,2})\s*(\d+)(?:\s+(\d+))?\s*$")


@cache
def transformer(source_epsg: int, target_epsg: int) -> Transformer:
    """A transformer between two EPSG codes, x before y. Shared: pyproj keeps its PROJ objects per thread."""
    return Transformer.from_crs(source_epsg, target_epsg, always_xy=True)


def is_lon_lat(lon: float, lat: float) -> bool:
    """Whether a longitude and latitude are a position on Earth. NaN and the infinities aren't."""
    return -180 <= lon <= 180 and -90 <= lat <= 90


def grid_system(lon: float, lat: float) -> GridSystem:
    """Irish Grid for points on the island of Ireland, British National Grid otherwise."""
    if math.isfinite(lon) and math.isfinite(lat) and _IRELAND.contains(Point(lon, lat)):
        return GridSystem.IRISH
    return GridSystem.OSGB


def to_grid(lon: float, lat: float) -> tuple[GridSystem, float, float]:
    """Easting and northing in metres on whichever grid covers the point."""
    if not is_lon_lat(lon, lat):
        raise GridRefError(f"Not a position on Earth: {lon}, {lat}.")
    system = grid_system(lon, lat)
    easting, northing = transformer(4326, _EPSG[system]).transform(lon, lat)
    width, height = _EXTENT[system]
    if not (
        math.isfinite(easting) and math.isfinite(northing) and 0 <= easting < width and 0 <= northing < height
    ):
        raise GridRefError(f"{lon:.5f}, {lat:.5f} is outside the British and Irish grids.")
    return system, easting, northing


def to_lonlat(system: GridSystem, easting: float, northing: float) -> tuple[float, float]:
    """Longitude and latitude (WGS84) of a grid position."""
    lon, lat = transformer(_EPSG[system], 4326).transform(easting, northing)
    assert math.isfinite(lon), f"{system} {easting}, {northing} did not transform"
    assert math.isfinite(lat), f"{system} {easting}, {northing} did not transform"
    return lon, lat


def _letters_for(system: GridSystem, easting: float, northing: float) -> str:
    e100 = int(easting // 100_000)
    n100 = int(northing // 100_000)
    if system is GridSystem.IRISH:
        return _LETTERS[(4 - n100) * 5 + e100]
    # The British grid's 500 km squares are lettered from a false origin two
    # squares west and one south of the grid's own origin.
    first = (19 - n100) - (19 - n100) % 5 + (e100 + 10) // 5
    second = (19 - n100) * 5 % 25 + e100 % 5
    return _LETTERS[first] + _LETTERS[second]


def _origin_for(letters: str) -> tuple[GridSystem, int, int]:
    """The grid and the south-west corner, in metres, of a lettered 100 km square."""
    letters = letters.upper()
    if any(letter not in _LETTERS for letter in letters):
        raise GridRefError(f"'{letters}' isn't a grid square. The letter I is never used.")
    if len(letters) == 1:
        row, col = divmod(_LETTERS.index(letters), 5)
        return GridSystem.IRISH, col * 100_000, (4 - row) * 100_000
    assert len(letters) == 2, f"expected one or two letters, got {letters!r}"
    first, second = _LETTERS.index(letters[0]), _LETTERS.index(letters[1])
    e100 = ((first - 2) % 5) * 5 + second % 5
    n100 = 19 - (first // 5) * 5 - second // 5
    width, height = _EXTENT[GridSystem.OSGB]
    if not (0 <= e100 * 100_000 < width and 0 <= n100 * 100_000 < height):
        raise GridRefError(f"'{letters}' isn't a square on the British National Grid.")
    return GridSystem.OSGB, e100 * 100_000, n100 * 100_000


@dataclass(frozen=True)
class GridRef:
    """A grid square: its grid, its south-west corner in metres, and its size."""

    system: GridSystem
    easting: int
    northing: int
    precision_m: int

    def __post_init__(self) -> None:
        assert self.precision_m in (1, 10, 100, 1000, 10_000), f"odd precision {self.precision_m}"
        assert self.easting % self.precision_m == 0, "easting is not on the square's own grid"
        assert self.northing % self.precision_m == 0, "northing is not on the square's own grid"

    @property
    def digits(self) -> int:
        """Total number of digits when written out: 8 for `SU 1025 6996`."""
        return 2 * (5 - round(math.log10(self.precision_m)))

    @property
    def letters(self) -> str:
        return _letters_for(self.system, self.easting, self.northing)

    def format(self, *, compact: bool = False) -> str:
        """`SU 1025 6996`, or `SU10256996` when compact."""
        half = self.digits // 2
        east = f"{(self.easting % 100_000) // self.precision_m:0{half}d}"
        north = f"{(self.northing % 100_000) // self.precision_m:0{half}d}"
        return f"{self.letters}{east}{north}" if compact else f"{self.letters} {east} {north}"

    def __str__(self) -> str:
        return self.format()

    def at_precision(self, precision_m: int) -> GridRef:
        """The coarser square that contains this one."""
        if precision_m < self.precision_m:
            raise GridRefError(f"{self.format()} is only good to {self.precision_m} m, not {precision_m} m.")
        return GridRef(
            self.system,
            self.easting - self.easting % precision_m,
            self.northing - self.northing % precision_m,
            precision_m,
        )

    def centre(self) -> tuple[float, float]:
        """Longitude and latitude of the middle of the square."""
        half = self.precision_m / 2
        return to_lonlat(self.system, self.easting + half, self.northing + half)

    def polygon(self) -> Polygon:
        """The square in WGS84, corners running south-west, south-east, north-east, north-west."""
        size = self.precision_m
        corners = [
            (self.easting, self.northing),
            (self.easting + size, self.northing),
            (self.easting + size, self.northing + size),
            (self.easting, self.northing + size),
        ]
        return Polygon([to_lonlat(self.system, e, n) for e, n in corners])


class Square(NamedTuple):
    """A 1 km grid square: its compact reference, such as `SU1069`, and its outline in WGS84."""

    ref: str
    polygon: Polygon


def gridref_at(lon: float, lat: float, digits: int = 8) -> GridRef:
    """The grid square of a given size that contains a WGS84 position."""
    if digits not in VALID_DIGITS:
        raise GridRefError(f"A grid reference has 2, 4, 6, 8 or 10 digits, not {digits}.")
    system, easting, northing = to_grid(lon, lat)
    precision = 10 ** (5 - digits // 2)
    return GridRef(
        system, int(easting // precision) * precision, int(northing // precision) * precision, precision
    )


def to_gridref(lon: float, lat: float, digits: int = 8, *, compact: bool = False) -> str:
    """The grid reference of a WGS84 position, such as `SU 1025 6996`.

    `digits` is the total count: 8 names a 10 m square, 6 a 100 m square, 4 a
    1 km square.
    """
    return gridref_at(lon, lat, digits).format(compact=compact)


def parse_gridref(text: str) -> GridRef:
    """Read a British or Irish grid reference.

    Accepts `SU 1025 6996`, `SU10256996`, `SU16` and the Irish `J 338 740`, in
    any case and with or without spaces. A bare pair of letters is refused
    because it is far more likely to be the start of a place name.
    """
    match = _REF_PATTERN.match(text or "")
    if match is None:
        raise GridRefError()
    letters, first, second = match.groups()
    if second is None:
        if len(first) % 2:
            raise GridRefError("A grid reference needs the same number of digits east and north.")
        half = len(first) // 2
        first, second = first[:half], first[half:]
    elif len(first) != len(second):
        raise GridRefError("A grid reference needs the same number of digits east and north.")
    half = len(first)
    if not 1 <= half <= 5:
        raise GridRefError("A grid reference has between 2 and 10 digits.")
    system, origin_e, origin_n = _origin_for(letters)
    precision = 10 ** (5 - half)
    return GridRef(system, origin_e + int(first) * precision, origin_n + int(second) * precision, precision)


def try_parse_gridref(text: str) -> GridRef | None:
    """`parse_gridref`, but `None` for anything that isn't a grid reference."""
    try:
        return parse_gridref(text)
    except GridRefError:
        return None


def square_1km(lon: float, lat: float) -> Square:
    """The 1 km grid square that contains a position."""
    ref = gridref_at(lon, lat, 4)
    return Square(ref.format(compact=True), ref.polygon())


def centre_of_square(ref: str) -> tuple[float, float]:
    """Longitude and latitude of the middle of the square a reference names."""
    return parse_gridref(ref).centre()
