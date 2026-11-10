"""Which 5 km source tiles exist, known without a network call.

England's 2022 composite DTM comes as 5,877 tiles of 5 km on the British
National Grid. A tile is named by its 10 km square and quadrant: `SU16nw`
covers eastings 410000 to 415000 and northings 165000 to 170000.
`data/england-dtm-2022.tsv` lists every tile in Defra's bulk supply with the
size of its GeoTIFF, read from the supply's listing on 2026-11-10. A tile that
isn't listed has no data, so nothing is fetched for it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from fieldclub.errors import BadRequestError
from fieldclub.gridref import GridRef, GridRefError, GridSystem, parse_gridref

TILE_METRES = 5_000
# The edition every tile of this catalogue belongs to. It is part of every cache key.
ENGLAND_EDITION = "england-dtm-2022"
# Where the supply keeps the tiles, and how each is named.
REMOTE_DIR = "composite/2022/GeoTiffs/1m/DTM"

_NAME = re.compile(r"([A-Za-z]{2})(\d)(\d)(ne|nw|se|sw)", re.IGNORECASE)
_QUADRANT_OFFSET = {"sw": (0, 0), "se": (5_000, 0), "nw": (0, 5_000), "ne": (5_000, 5_000)}


class TileNameError(BadRequestError):
    code = "invalid_tile_name"
    message = "A tile is named by its 10 km square and quadrant, such as SU16nw."


@dataclass(frozen=True)
class SourceTile:
    name: str
    # Bytes in the supply's GeoTIFF, which a download must match.
    size: int

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """West, south, east, north in British National Grid metres."""
        west, south = tile_origin(self.name)
        return west, south, west + TILE_METRES, south + TILE_METRES

    @property
    def remote_path(self) -> str:
        return f"{REMOTE_DIR}/{self.source_filename}"

    @property
    def source_filename(self) -> str:
        return f"{self.name}_DTM_1m.tif"


def normalise_name(name: str) -> str:
    """`su16NW` becomes `SU16nw`. Anything that isn't a tile name is refused."""
    match = _NAME.fullmatch(name.strip())
    if match is None:
        raise TileNameError(f"{name!r} isn't a tile name such as SU16nw.")
    letters, east, north, quadrant = match.groups()
    return f"{letters.upper()}{east}{north}{quadrant.lower()}"


def tile_origin(name: str) -> tuple[int, int]:
    """The south-west corner of a tile in British National Grid metres."""
    name = normalise_name(name)
    try:
        square = parse_gridref(name[:4])
    except GridRefError as exc:
        raise TileNameError(f"{name!r} isn't on the British National Grid.") from exc
    if square.system is not GridSystem.OSGB:
        raise TileNameError(f"{name!r} isn't on the British National Grid.")
    assert square.precision_m == 10_000, f"{name[:4]} should name a 10 km square"
    east, north = _QUADRANT_OFFSET[name[4:]]
    return square.easting + east, square.northing + north


def tile_name_at(easting: float, northing: float) -> str:
    """The name of the 5 km tile that contains a grid position."""
    west = int(easting // TILE_METRES) * TILE_METRES
    south = int(northing // TILE_METRES) * TILE_METRES
    square = GridRef(GridSystem.OSGB, west - west % 10_000, south - south % 10_000, 10_000)
    quadrant = ("n" if south % 10_000 else "s") + ("e" if west % 10_000 else "w")
    return square.format(compact=True) + quadrant


class Catalogue:
    """The tiles of one edition, by name."""

    def __init__(self, edition: str, tiles: dict[str, SourceTile]) -> None:
        assert edition, "a catalogue needs an edition"
        self.edition = edition
        self._tiles = tiles

    def get(self, name: str) -> SourceTile | None:
        return self._tiles.get(normalise_name(name))

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.get(name) is not None

    def __iter__(self) -> Iterator[SourceTile]:
        return iter(sorted(self._tiles.values(), key=lambda tile: tile.name))

    def __len__(self) -> int:
        return len(self._tiles)

    @property
    def total_bytes(self) -> int:
        return sum(tile.size for tile in self._tiles.values())

    def covering(self, bounds: tuple[float, float, float, float]) -> list[SourceTile]:
        """The listed tiles that a British National Grid box touches."""
        west, south, east, north = bounds
        assert west <= east, "west is east of east"
        assert south <= north, "south is north of north"
        found: list[SourceTile] = []
        for col in range(max(0, int(west // TILE_METRES)), int(east // TILE_METRES) + 1):
            for row in range(max(0, int(south // TILE_METRES)), int(north // TILE_METRES) + 1):
                if col * TILE_METRES >= 700_000 or row * TILE_METRES >= 1_300_000:
                    continue
                tile = self._tiles.get(tile_name_at(col * TILE_METRES, row * TILE_METRES))
                if tile is not None:
                    found.append(tile)
        return found


def parse_catalogue(edition: str, text: str) -> Catalogue:
    tiles: dict[str, SourceTile] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, size = line.partition("\t")
        assert name == normalise_name(name), f"line {number}: {name!r} isn't written as a tile name"
        assert size.isdigit(), f"line {number}: {size!r} isn't a size in bytes"
        assert int(size) > 0, f"line {number}: {name} has no bytes"
        assert name not in tiles, f"line {number}: {name} is listed twice"
        tiles[name] = SourceTile(name, int(size))
    assert tiles, f"the {edition} catalogue is empty"
    return Catalogue(edition, tiles)


@lru_cache(maxsize=1)
def england_catalogue() -> Catalogue:
    text = resources.files("fieldclub.terrain").joinpath("data/england-dtm-2022.tsv").read_text("utf-8")
    catalogue = parse_catalogue(ENGLAND_EDITION, text)
    assert len(catalogue) == 5_877, f"expected 5,877 tiles in the England catalogue, found {len(catalogue)}"
    return catalogue
