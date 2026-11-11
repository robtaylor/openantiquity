"""What zooms below 13 read: the national overview, and the mirror for what was mirrored since it was built.

`Overview.snapshot()` reads `national.json` at most once a `refresh_s`, so a
rebuild reaches every server within a minute, and hands out one immutable
`OverviewSnapshot` per build. A map tile takes one snapshot and uses it for
everything it does, so its pixels, its cache key and its version token all
name the same build.

A snapshot reads the overview's COG. Where a read touches 5 km tiles the
build doesn't hold, and the mirror has some of them, the mirror's tiles in
view are read at the overview's own levels and drawn over it, so an area
mirrored since the build still draws. Such a read can change as the mirror
fills, so it isn't cacheable, and nor is a read that touches a tile neither
holds yet. A read that touches only built tiles is cacheable: its pixels
change only with the build, which changes the edition and the version token.
Only the tiles mirrored since the build and the mirrored tiles beside them
are read, because the build holds the rest. Past `max_fallback_tiles` of
them in view (a zoom of about 10 or less over a mirror filling fast) the
mirror isn't read: those tiles draw after the next build.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import numpy as np

from fieldclub.terrain.catalogue import TILE_METRES, Catalogue, tile_origin
from fieldclub.terrain.grid import nominal_ground_resolution, window_for
from fieldclub.terrain.mirror import Mirror
from fieldclub.terrain.national import NATIONAL_FORMAT, RESOLUTION_M, RESOLUTIONS, Manifest, NationalStore
from fieldclub.terrain.sources import ENGLAND_WGS84, CogMosaicSource, bng_box, choose_level

logger = logging.getLogger(__name__)

REFRESH_S = 60.0
MAX_FALLBACK_TILES = 64

Bounds = tuple[float, float, float, float]


def overview_edition(mirror_edition: str, manifest: Manifest | None) -> str:
    """What a snapshot's values come from: the mirror's edition and the build, or `none` before the first."""
    return f"{mirror_edition}.{NATIONAL_FORMAT}-{manifest.build if manifest else 'none'}"


class OverviewSnapshot:
    """The overview as one build has it. An `ElevationSource`."""

    def __init__(
        self,
        mirror: Mirror,
        manifest: Manifest | None,
        national_path: str | None,
        mirrored: Callable[[], frozenset[str]],
        *,
        max_fallback_tiles: int = MAX_FALLBACK_TILES,
    ) -> None:
        assert (manifest is None) == (national_path is None), "a build has a file, and only a build"
        self.edition = overview_edition(mirror.edition, manifest)
        self.manifest = manifest
        self.built: frozenset[str] = manifest.tiles if manifest else frozenset()
        self._mirror = mirror
        self._mirrored = mirrored
        self._max_fallback = max_fallback_tiles
        self.national: CogMosaicSource | None = None
        if national_path is not None:
            path = national_path
            self.national = CogMosaicSource(
                self.edition, lambda bbox: [path], RESOLUTIONS, extent=ENGLAND_WGS84
            )

    @property
    def catalogue(self) -> Catalogue:
        return self._mirror.catalogue

    def touched(self, bounds: Bounds, width: int, height: int) -> set[str]:
        """The catalogue tiles a read of `bounds` may draw from, with the B-spline's margin."""
        window = window_for(bounds, width, height)
        box = bng_box(window, ENGLAND_WGS84)
        if box is None:
            return set()
        margin = 3 * choose_level(RESOLUTIONS, RESOLUTION_M, nominal_ground_resolution(window.zoom))
        west, south, east, north = box
        padded = (west - margin, south - margin, east + margin, north + margin)
        return {tile.name for tile in self.catalogue.covering(padded)}

    def cacheable_for(self, bounds: Bounds, width: int, height: int) -> bool:
        return self.touched(bounds, width, height) <= self.built

    def read(self, bounds: Bounds, width: int, height: int) -> np.ndarray:
        out = (
            self.national.read(bounds, width, height)
            if self.national is not None
            else np.full((height, width), np.nan, dtype=np.float32)
        )
        touched = self.touched(bounds, width, height)
        if touched <= self.built:
            return out
        mirrored = self._mirrored()
        fresh = (mirrored & touched) - self.built
        if not fresh:
            return out
        if len(fresh) > self._max_fallback:
            logger.info("%d tiles mirrored since the build in view; they wait for the next", len(fresh))
            return out
        drawn = self._mirror_source(self._with_neighbours(fresh, mirrored)).read(bounds, width, height)
        return np.where(np.isnan(drawn), out, drawn).astype(np.float32)

    def _with_neighbours(self, fresh: frozenset[str], mirrored: frozenset[str]) -> frozenset[str]:
        """`fresh` and the mirrored tiles beside them, so the sampler has data across their edges.

        The build holds the rest of the view. Without the neighbours, a pixel
        whose 16 cells straddle a fresh tile's edge would have no data in
        either read. The sampler's margin is far less than a tile, so the
        tiles next to each fresh one are enough.
        """
        near: set[str] = set(fresh)
        for name in fresh:
            west, south = tile_origin(name)
            box = (west - 1, south - 1, west + TILE_METRES + 1, south + TILE_METRES + 1)
            near.update(tile.name for tile in self.catalogue.covering(box))
        return frozenset(near & mirrored)

    def _mirror_source(self, names: frozenset[str]) -> CogMosaicSource:
        """The mirror's tiles in `names`, read at the overview's levels, never fetching."""
        store, catalogue = self._mirror.store, self.catalogue

        def paths_for(bbox: Bounds) -> list[str]:
            return [store.gdal_path(tile.name) for tile in catalogue.covering(bbox) if tile.name in names]

        return CogMosaicSource(self.edition, paths_for, RESOLUTIONS, extent=ENGLAND_WGS84, cacheable=False)

    def sample(self, eastings: np.ndarray, northings: np.ndarray) -> np.ndarray:
        """Heights at grid positions from the build at 8 m, NaN where it has none."""
        if self.national is None:
            return np.full(eastings.shape, np.nan, dtype=np.float32)
        return self.national.sample(eastings, northings, RESOLUTION_M)


class Overview:
    """The current build, looked up at most once a `refresh_s`."""

    def __init__(
        self,
        mirror: Mirror,
        store: NationalStore,
        *,
        refresh_s: float = REFRESH_S,
        max_fallback_tiles: int = MAX_FALLBACK_TILES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.mirror = mirror
        self.store = store
        self.refresh_s = refresh_s
        self._max_fallback = max_fallback_tiles
        self._clock = clock
        self._guard = threading.Lock()
        self._snapshot: OverviewSnapshot | None = None
        self._checked = -float("inf")
        self._mirrored: frozenset[str] = frozenset()
        self._listed = -float("inf")

    def snapshot(self) -> OverviewSnapshot:
        with self._guard:
            if self._snapshot is not None and self._clock() - self._checked < self.refresh_s:
                return self._snapshot
            try:
                manifest = self.store.manifest()
            except Exception:
                if self._snapshot is None:
                    raise
                # A bucket that can't be read this minute keeps the build already in use.
                logger.exception(
                    "Couldn't read the overview's manifest; keeping build %s", self._snapshot.edition
                )
                self._checked = self._clock()
                return self._snapshot
            self._checked = self._clock()
            if self._snapshot is None or self._snapshot.manifest != manifest:
                path = self.store.gdal_path(manifest) if manifest else None
                self._snapshot = OverviewSnapshot(
                    self.mirror, manifest, path, self._mirror_names, max_fallback_tiles=self._max_fallback
                )
                logger.info("The overview is now %s", self._snapshot.edition)
            return self._snapshot

    @property
    def edition(self) -> str:
        return self.snapshot().edition

    def mirrored(self) -> frozenset[str]:
        """The tiles the mirror holds, listed at most once a `refresh_s`."""
        return self._mirror_names()

    def _mirror_names(self) -> frozenset[str]:
        """The tiles the mirror holds, listed at most once a `refresh_s`."""
        with self._guard:
            if self._clock() - self._listed >= self.refresh_s:
                self._mirrored = frozenset(self.mirror.store.names())
                self._listed = self._clock()
            return self._mirrored
