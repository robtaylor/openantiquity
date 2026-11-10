"""The terrain service as the API and the command line use it, built from settings.

Elevation for map tiles comes from one source per zoom level. From
`FINE_MINZOOM` (13) up it is the 1 m mirror, fetching tiles that are missing.
Below that it is the national 10 m composite. A 512-pixel tile at zoom 13
spans about 3 km of ground, so it touches at most four 5 km tiles, and at its
nominal 5.8 m pixels it reads the mirror's 4 m overview. At zoom 12 a tile
spans about 6 km and touches up to nine, each of which a cold mirror would
have to download (40 to 90 MB) before the tile could be drawn, while its
11.6 m pixels match the 10 m composite.

Point heights never fetch: they read the 1 m mirror where it already has the
tile and the 10 m composite elsewhere. A height profile reads the 1 m mirror
and fetches what it needs, within the limits below.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from fieldclub.config import Settings, get_defra_sftp_settings, get_settings
from fieldclub.errors import BadRequestError
from fieldclub.gridref import GridRefError, GridSystem, to_grid
from fieldclub.storage import Storage, get_storage
from fieldclub.terrain import sftp
from fieldclub.terrain.catalogue import Catalogue, england_catalogue
from fieldclub.terrain.cog import COG_FORMAT
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.mirror import (
    GS_SCHEME,
    Fetcher,
    LocalSourceFetcher,
    Mirror,
    SftpFetcher,
    mirror_store,
)
from fieldclub.terrain.render import TileRenderer
from fieldclub.terrain.sources import (
    CogMosaicSource,
    ElevationSource,
    file_source,
    mirror_source,
    transformer,
)
from fieldclub.terrain.styles import FINE_MINZOOM

logger = logging.getLogger(__name__)

NATIONAL_EDITION = f"england-dtm-2022-10m.{COG_FORMAT}"
NATIONAL_RESOLUTION_M = 10.0
FINE_RESOLUTION_M = 1.0

# A profile is for looking across a bank or a ditch, not across a county.
MAX_PROFILE_M = 5_000.0
MAX_PROFILE_SAMPLES = 1_000
MAX_PROFILE_VERTICES = 200


class ProfileError(BadRequestError):
    code = "invalid_profile"
    message = "That line can't be profiled."


@dataclass(frozen=True)
class Profile:
    length_m: float
    distances: list[float]
    elevations: list[float | None]
    positions: list[tuple[float, float]]
    resolution_m: float


class Terrain:
    def __init__(
        self,
        mirror: Mirror,
        national: CogMosaicSource,
        storage: Storage,
        *,
        national_exists: Callable[[], bool],
    ) -> None:
        self._national_exists = national_exists
        self.mirror = mirror
        self.fine = mirror_source(mirror)
        self.fine_mirrored = mirror_source(mirror, fetch=False)
        self.national = national
        self.renderer = TileRenderer(self.source_for_zoom, storage)

    @property
    def catalogue(self) -> Catalogue:
        return self.mirror.catalogue

    def source_for_zoom(self, zoom: int) -> ElevationSource:
        if zoom >= FINE_MINZOOM:
            return self.fine
        if self.national_available():
            return self.national
        # Until the national composite is built, low zooms show what the
        # mirror already holds, from its overviews, uncached and never fetching.
        return self.fine_mirrored

    def national_available(self) -> bool:
        return self._national_exists()

    def elevation_at(self, lon: float, lat: float) -> float | None:
        """Ground height in metres, or None where there is none. Never fetches."""
        try:
            system, easting, northing = to_grid(lon, lat)
        except GridRefError:
            return None
        if system is not GridSystem.OSGB:
            return None
        eastings, northings = np.array([easting]), np.array([northing])
        value = float(self.fine_mirrored.sample(eastings, northings, FINE_RESOLUTION_M)[0])
        if math.isnan(value):
            try:
                value = float(self.national.sample(eastings, northings, NATIONAL_RESOLUTION_M)[0])
            except ElevationUnavailableError:
                logger.info("The national composite isn't built, so %s, %s has no height", lon, lat)
                return None
        return None if math.isnan(value) else round(value, 2)

    def profile(self, coordinates: list[tuple[float, float]], samples: int) -> Profile:
        """Heights at `samples` evenly spaced points along a line of WGS84 positions."""
        if not 2 <= len(coordinates) <= MAX_PROFILE_VERTICES:
            raise ProfileError(f"A profile line needs between 2 and {MAX_PROFILE_VERTICES} points.")
        if not 2 <= samples <= MAX_PROFILE_SAMPLES:
            raise ProfileError(f"Ask for between 2 and {MAX_PROFILE_SAMPLES} samples.")
        grid_points: list[tuple[float, float]] = []
        for lon, lat in coordinates:
            try:
                system, easting, northing = to_grid(lon, lat)
            except GridRefError as exc:
                raise ProfileError(exc.message) from exc
            if system is not GridSystem.OSGB:
                raise ProfileError("Profiles are only available on the British National Grid.")
            grid_points.append((easting, northing))
        vertices = np.array(grid_points, dtype=np.float64)
        steps = np.hypot(*np.diff(vertices, axis=0).T)
        along = np.concatenate([[0.0], np.cumsum(steps)])
        length = float(along[-1])
        if length <= 0:
            raise ProfileError("A profile line must have some length.")
        if length > MAX_PROFILE_M:
            raise ProfileError(f"A profile line can be at most {MAX_PROFILE_M / 1000:g} km long.")
        distances = np.linspace(0.0, length, samples)
        eastings = np.interp(distances, along, vertices[:, 0])
        northings = np.interp(distances, along, vertices[:, 1])
        # Read no finer than the spacing, so a long line doesn't assemble a huge 1 m grid.
        resolution = max(FINE_RESOLUTION_M, length / (samples - 1))
        heights = self.fine.sample(eastings, northings, resolution)
        lons, lats = transformer(27700, 4326).transform(eastings, northings)
        return Profile(
            length_m=round(length, 2),
            distances=[round(float(d), 2) for d in distances],
            elevations=[None if math.isnan(h) else round(float(h), 2) for h in heights],
            positions=[(round(float(lo), 7), round(float(la), 7)) for lo, la in zip(lons, lats, strict=True)],
            resolution_m=_level_resolution(resolution),
        )


def _level_resolution(resolution: float) -> float:
    """The mirror level a read at `resolution` uses: 1, 2, 4 or 8 m."""
    level = 1.0
    while level * 2 <= resolution and level < 8:
        level *= 2
    return level


def build_mirror(settings: Settings, *, fetchers: list[Fetcher] | None = None) -> Mirror:
    if fetchers is None:
        fetchers = []
        source_dir = settings.terrain_path(settings.terrain_source_dir)
        if source_dir:
            fetchers.append(LocalSourceFetcher(Path(source_dir)))
        fetchers.append(SftpFetcher(lambda: sftp.defra_connector(get_defra_sftp_settings())))
    return Mirror(
        england_catalogue(),
        mirror_store(settings.terrain_path(settings.terrain_mirror)),
        fetchers,
        Path(settings.terrain_path(settings.terrain_work_dir)),
        max_fetches=settings.terrain_fetch_concurrency,
    )


def national_location(settings: Settings) -> tuple[str, Callable[[], bool]]:
    """The national composite's GDAL path, and how to tell whether it has been built."""
    location = settings.terrain_path(settings.terrain_national)
    if location.startswith(GS_SCHEME):
        # In a bucket it is built before the service is deployed.
        return "/vsigs/" + location[len(GS_SCHEME) :], lambda: True
    return location, lambda: Path(location).is_file()


def build_terrain(settings: Settings | None = None, *, storage: Storage | None = None) -> Terrain:
    settings = settings or get_settings()
    path, exists = national_location(settings)
    national = file_source(NATIONAL_EDITION, path, exists=exists)
    return Terrain(build_mirror(settings), national, storage or get_storage("tiles"), national_exists=exists)


@lru_cache(maxsize=1)
def get_terrain() -> Terrain:
    """The process's terrain service. A FastAPI dependency, so tests can override it."""
    return build_terrain()
