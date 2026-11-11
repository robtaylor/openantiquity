"""The terrain service as the API and the command line use it, built from settings.

Elevation for map tiles comes from one source per zoom level. From
`FINE_MINZOOM` (13) up it is the 1 m mirror, fetching tiles that are missing.
Below that it is the national overview (`overview.py`), built from the
mirror's own 8 m copies. A 512-pixel tile at zoom 13 spans about 3 km of
ground, so it touches at most four 5 km tiles, and at its nominal 5.8 m
pixels it reads the mirror's 4 m overview. At zoom 12 a tile spans about 6 km
and touches up to nine, each of which a cold mirror would have to download
(40 to 90 MB) before the tile could be drawn, while its 11.6 m pixels match
the overview's 8 m.

Point heights never fetch: they read the 1 m mirror where it already has the
tile and the overview elsewhere. A height profile reads the 1 m mirror and
fetches what it needs, within the limits below.
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
from fieldclub.gridref import GridRefError, GridSystem, to_grid, transformer
from fieldclub.storage import Storage, get_storage
from fieldclub.terrain import sftp
from fieldclub.terrain.blobs import ObjectLock, folder
from fieldclub.terrain.catalogue import Catalogue, england_catalogue
from fieldclub.terrain.cog import COG_FORMAT
from fieldclub.terrain.mirror import Fetcher, LocalSourceFetcher, Mirror, SftpFetcher, mirror_store
from fieldclub.terrain.national import NationalStore
from fieldclub.terrain.overview import Overview, overview_edition
from fieldclub.terrain.render import Selection, TileRenderer, tile_version
from fieldclub.terrain.sources import mirror_source
from fieldclub.terrain.styles import FINE_MINZOOM

logger = logging.getLogger(__name__)

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
    def __init__(self, mirror: Mirror, overview: Overview, storage: Storage) -> None:
        self.mirror = mirror
        self.fine = mirror_source(mirror)
        self.fine_mirrored = mirror_source(mirror, fetch=False)
        self.overview = overview
        self.renderer = TileRenderer(self.select, storage, editions=self.editions)

    @property
    def catalogue(self) -> Catalogue:
        return self.mirror.catalogue

    def editions(self) -> tuple[str, str]:
        """What the tiles are drawn from now: the 1 m mirror and the overview's current build."""
        return self.fine.edition, self.overview.edition

    def url_versions(self) -> Callable[[str], str]:
        """The tokens `/meta` puts in tile URLs, from the editions read once.

        When the overview's manifest can't be read (a bucket error, or a
        malformed `national.json` before any build was ever read), the tokens
        are those of no build, so `/meta` still answers and no URL it offers is
        sent as immutable.
        """
        try:
            editions = self.editions()
        except Exception:
            logger.exception(
                "Couldn't read the overview's build; /meta offers tile URLs that aren't immutable"
            )
            editions = default_editions()
        return lambda kind: tile_version(kind, editions)

    def select(self, zoom: int) -> Selection:
        snapshot = self.overview.snapshot()
        editions = (self.fine.edition, snapshot.edition)
        if zoom >= FINE_MINZOOM:
            return Selection(self.fine, snapshot, editions)
        return Selection(snapshot, None, editions)

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
            value = float(self.overview.snapshot().sample(eastings, northings)[0])
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
        heights, used = self.fine.sample_level(eastings, northings, resolution)
        lons, lats = transformer(27700, 4326).transform(eastings, northings)
        return Profile(
            length_m=round(length, 2),
            distances=[round(float(d), 2) for d in distances],
            elevations=[None if math.isnan(h) else round(float(h), 2) for h in heights],
            positions=[(round(float(lo), 7), round(float(la), 7)) for lo, la in zip(lons, lats, strict=True)],
            resolution_m=used,
        )


def build_mirror(settings: Settings, *, fetchers: list[Fetcher] | None = None) -> Mirror:
    if fetchers is None:
        fetchers = []
        source_dir = settings.terrain_path(settings.terrain_source_dir)
        if source_dir:
            fetchers.append(LocalSourceFetcher(Path(source_dir)))
        fetchers.append(
            SftpFetcher(
                lambda: sftp.defra_connector(get_defra_sftp_settings()),
                sessions=settings.terrain_fetch_concurrency,
            )
        )
    store = mirror_store(settings.terrain_path(settings.terrain_mirror))
    return Mirror(
        england_catalogue(),
        store,
        fetchers,
        Path(settings.terrain_path(settings.terrain_work_dir)),
        max_fetches=settings.terrain_fetch_concurrency,
        lock=ObjectLock(
            store.folder, stale_after_s=settings.terrain_lock_stale_s, wait_s=settings.terrain_lock_wait_s
        ),
    )


def national_store(settings: Settings) -> NationalStore:
    return NationalStore(folder(settings.terrain_path(settings.terrain_national)))


def build_terrain(settings: Settings | None = None, *, storage: Storage | None = None) -> Terrain:
    settings = settings or get_settings()
    mirror = build_mirror(settings)
    return Terrain(mirror, Overview(mirror, national_store(settings)), storage or get_storage("tiles"))


@lru_cache(maxsize=1)
def get_terrain() -> Terrain:
    """The process's terrain service. A FastAPI dependency, so tests can override it."""
    return build_terrain()


def default_editions() -> tuple[str, str]:
    """The editions before any overview is built, for a tile URL made without a terrain service."""
    mirror_edition = f"{england_catalogue().edition}.{COG_FORMAT}"
    return mirror_edition, overview_edition(mirror_edition, None)
