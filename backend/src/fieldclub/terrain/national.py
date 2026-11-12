"""The national overview for zooms below 13, mosaicked from the 8 m copies inside our own mirror.

Defra's national 10 m composite can't be downloaded: its server cuts every
response at about 1.08 GB and ignores Range. Every mirrored 5 km tile already
holds an 8 m overview, so `Builder` lays those side by side in one COG for the
country, with its own overviews at 16 to 512 m.

The grid is fixed: 8 m pixels whose edges are multiples of 8 m from the
British National Grid's origin, and a file whose edges are multiples of
`ALIGN_M`, so every overview level is a whole number of pixels and lands on
the same global grid in every build. Each tile is read with the same windowed
read the mirror's own readers use at 8 m (`sources.paste`), so the overview
holds what a read of the mirror at 8 m gives.

A build goes through chunks of 50 km in the work directory:

1. the tiles the mirror holds are grouped by chunk;
2. a chunk that lacks some of them is read back, the missing tiles are read
   from the mirror and pasted in, and the chunk is written to a new file and
   renamed into place, with the tiles it holds in its metadata;
3. the chunks are joined by a VRT and written as one COG under a name made
   from the tiles it holds, which is uploaded beside the previous builds;
4. `national.json` is replaced to point at it.

So a build reads only tiles that no chunk holds yet, an interrupted build
resumes from the last chunk it finished, and a reader never sees a part
built file. Readers keep the previous build until their next look at
`national.json`, so the build before it is kept and older ones are removed.
The overview is replaced as a whole: the COG layout can't be updated in place.

All of England needs about 8 GB of local disk in the work directory: 4.2 GB
of chunks, kept between builds, and the 3.5 GB COG staged before it is
uploaded. One build runs at a time per work directory (a file lock) and per
bucket (`BUILD_LOCK`), and each starts by removing the staged files a killed
build left behind.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import math
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import rasterio
import rasterio.shutil
from rasterio.transform import from_origin

from fieldclub.errors import AppError, ConflictError
from fieldclub.terrain.blobs import Folder, ObjectLock
from fieldclub.terrain.catalogue import Catalogue, tile_origin
from fieldclub.terrain.cog import check_cog, creation_options
from fieldclub.terrain.mirror import Mirror
from fieldclub.terrain.sources import paste

logger = logging.getLogger(__name__)

RESOLUTION_M = 8.0
OVERVIEW_COUNT = 6
# Metres of the coarsest overview's pixel. The file's edges are multiples of it.
ALIGN_M = RESOLUTION_M * 2**OVERVIEW_COUNT
# Every level of the file, from its own 8 m to its coarsest overview.
RESOLUTIONS = tuple(RESOLUTION_M * 2**level for level in range(OVERVIEW_COUNT + 1))
CHUNK_M = 50_000
CHUNK_PX = round(CHUNK_M / RESOLUTION_M)
# Bumped when the layout or the values of a build change.
NATIONAL_FORMAT = "n1"
MANIFEST = "national.json"
BUILD_LOCK = "locks/build.lock"
_TILES_TAG = "FIELDCLUB_TILES"
_EDITION_TAG = "FIELDCLUB_EDITION"

assert CHUNK_M % RESOLUTION_M == 0, "a chunk must be a whole number of pixels"
assert 5_000 % RESOLUTION_M == 0, "a 5 km tile must be a whole number of pixels"


class BuildRunningError(ConflictError):
    code = "overview_build_running"
    message = "Another overview build is running in this work directory."


class NothingToBuildError(AppError):
    code = "overview_nothing_to_build"
    message = "The mirror holds no tiles, so there is nothing to build an overview from."


@dataclass(frozen=True)
class Manifest:
    """What `national.json` says: the current build, its file and the tiles it holds."""

    build: str
    filename: str
    # The mirror edition the tiles were read from.
    edition: str
    tiles: frozenset[str]
    created: str

    def to_json(self) -> bytes:
        body = {
            "format": NATIONAL_FORMAT,
            "build": self.build,
            "filename": self.filename,
            "edition": self.edition,
            "created": self.created,
            "resolution_m": RESOLUTION_M,
            "tiles": sorted(self.tiles),
        }
        return json.dumps(body, indent=1).encode()

    @classmethod
    def from_json(cls, data: bytes) -> Manifest | None:
        """The manifest, or None for one written in another format, which readers ignore."""
        body = json.loads(data)
        if body.get("format") != NATIONAL_FORMAT:
            return None
        assert body["filename"] == filename_for(body["build"]), (
            f"{body['filename']} isn't build {body['build']}"
        )
        return cls(
            body["build"], body["filename"], body["edition"], frozenset(body["tiles"]), body["created"]
        )


def build_id(edition: str, tiles: Iterable[str]) -> str:
    """The same tiles of the same edition always make the same build."""
    text = "/".join([NATIONAL_FORMAT, edition, ",".join(sorted(tiles))])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def filename_for(build: str) -> str:
    return f"england-{build}.tif"


# Only a name `filename_for` makes is ever pruned, so a folder set to the
# mirror's by mistake loses nothing (the settings refuse that as well).
_BUILD_FILE = re.compile(r"england-[0-9a-f]{12}\.tif")


class NationalStore:
    """The overview's folder: one COG per build and `national.json` naming the current one."""

    def __init__(self, folder: Folder) -> None:
        self.folder = folder

    def manifest(self) -> Manifest | None:
        data = self.folder.read(MANIFEST)
        return None if data is None else Manifest.from_json(data)

    def gdal_path(self, manifest: Manifest) -> str:
        return self.folder.gdal_path(manifest.filename)

    def publish(self, local: Path, manifest: Manifest) -> None:
        """Upload a build's COG, then point `national.json` at it."""
        self.folder.upload(local, manifest.filename, "image/tiff")
        self.folder.write(MANIFEST, manifest.to_json(), "application/json")

    def prune(self, keep: set[str]) -> list[str]:
        """Remove build files other than those named in `keep`. Returns what was removed.

        Any other file in the folder is left alone.
        """
        removed = [
            name for name in self.folder.names(".tif") if _BUILD_FILE.fullmatch(name) and name not in keep
        ]
        for name in removed:
            self.folder.delete(name)
        return removed

    def __repr__(self) -> str:
        return f"NationalStore({self.folder!r})"


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------


def chunk_of(tile: str) -> tuple[int, int]:
    """The column and row of the 50 km chunk a tile falls in."""
    west, south = tile_origin(tile)
    return west // CHUNK_M, south // CHUNK_M


def chunk_path(folder: Path, chunk: tuple[int, int]) -> Path:
    return folder / f"{chunk[0]:02d}-{chunk[1]:02d}.tif"


def _chunk_origin(chunk: tuple[int, int]) -> tuple[float, float]:
    """West and north edges of a chunk."""
    return float(chunk[0] * CHUNK_M), float((chunk[1] + 1) * CHUNK_M)


def read_chunk(path: Path, edition: str) -> tuple[np.ndarray, set[str]]:
    """A chunk's pixels and the tiles it holds, or empty if it is missing or of another edition."""
    if path.is_file():
        with rasterio.open(path) as ds:
            tags = ds.tags()
            if tags.get(_EDITION_TAG) == edition:
                tiles = set(filter(None, tags.get(_TILES_TAG, "").split(",")))
                return ds.read(1), tiles
            logger.info(
                "%s is of edition %s, not %s; starting it again", path, tags.get(_EDITION_TAG), edition
            )
    return np.full((CHUNK_PX, CHUNK_PX), np.nan, dtype=np.float32), set()


def write_chunk(path: Path, chunk: tuple[int, int], data: np.ndarray, tiles: set[str], edition: str) -> None:
    """Write a chunk to a new file and rename it into place, so a chunk on disk is always whole."""
    assert data.shape == (CHUNK_PX, CHUNK_PX), f"a chunk is {CHUNK_PX} pixels square, not {data.shape}"
    west, north = _chunk_origin(chunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp.tif")
    try:
        with rasterio.open(
            staged,
            "w",
            driver="GTiff",
            width=CHUNK_PX,
            height=CHUNK_PX,
            count=1,
            dtype="float32",
            crs="EPSG:27700",
            transform=from_origin(west, north, RESOLUTION_M, RESOLUTION_M),
            nodata=float("nan"),
            tiled=True,
            blockxsize=512,
            blockysize=512,
            # Lossless: the build's COG is the one lossy step.
            compress="ZSTD",
            predictor=3,
            BIGTIFF="IF_SAFER",
        ) as out:
            out.write(data, 1)
            out.update_tags(**{_TILES_TAG: ",".join(sorted(tiles)), _EDITION_TAG: edition})
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def vrt_of(chunks: dict[tuple[int, int], Path]) -> str:
    """A VRT laying the chunks on one grid whose edges are multiples of `ALIGN_M`."""
    assert chunks, "a VRT needs at least one chunk"
    wests = [_chunk_origin(chunk)[0] for chunk in chunks]
    norths = [_chunk_origin(chunk)[1] for chunk in chunks]
    west = math.floor(min(wests) / ALIGN_M) * ALIGN_M
    north = math.ceil(max(norths) / ALIGN_M) * ALIGN_M
    east = math.ceil((max(wests) + CHUNK_M) / ALIGN_M) * ALIGN_M
    south = math.floor((min(norths) - CHUNK_M) / ALIGN_M) * ALIGN_M
    width, height = round((east - west) / RESOLUTION_M), round((north - south) / RESOLUTION_M)
    sources = []
    for chunk, path in sorted(chunks.items()):
        chunk_west, chunk_north = _chunk_origin(chunk)
        x_off = round((chunk_west - west) / RESOLUTION_M)
        y_off = round((north - chunk_north) / RESOLUTION_M)
        sources.append(
            "<SimpleSource>"
            f'<SourceFilename relativeToVRT="0">{escape(str(path))}</SourceFilename>'
            "<SourceBand>1</SourceBand>"
            f'<SrcRect xOff="0" yOff="0" xSize="{CHUNK_PX}" ySize="{CHUNK_PX}"/>'
            f'<DstRect xOff="{x_off}" yOff="{y_off}" xSize="{CHUNK_PX}" ySize="{CHUNK_PX}"/>'
            "</SimpleSource>"
        )
    return (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">'
        "<SRS>EPSG:27700</SRS>"
        f"<GeoTransform>{west}, {RESOLUTION_M}, 0, {north}, 0, {-RESOLUTION_M}</GeoTransform>"
        '<VRTRasterBand dataType="Float32" band="1"><NoDataValue>nan</NoDataValue>'
        + "".join(sources)
        + "</VRTRasterBand></VRTDataset>"
    )


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildReport:
    build: str
    # Tiles read from the mirror by this run.
    read: int
    tiles: int
    bytes: int
    seconds: float
    up_to_date: bool


Progress = Callable[[int, int, str], None]


class Builder:
    def __init__(
        self,
        mirror: Mirror,
        store: NationalStore,
        work_dir: Path,
        *,
        workers: int = 4,
        threads: int | str = "ALL_CPUS",
        on_progress: Progress | None = None,
        lock: ObjectLock | None = None,
    ) -> None:
        assert workers >= 1, "a build needs at least one worker"
        self.mirror = mirror
        self.store = store
        self.work_dir = Path(work_dir)
        self.chunks_dir = self.work_dir / "national" / "chunks"
        self.workers = workers
        self.threads = threads
        self.on_progress = on_progress
        self._lock = lock or ObjectLock(store.folder, wait_s=0)

    @property
    def catalogue(self) -> Catalogue:
        return self.mirror.catalogue

    def build(self) -> BuildReport:
        with self._local_lock():
            self._remove_leftovers()
            if not self.store.folder.shared:
                return self._build()
            # Two builds into one bucket would each publish over the other.
            with self._lock.hold(BUILD_LOCK, done=lambda: False):
                return self._build()

    @contextlib.contextmanager
    def _local_lock(self) -> Iterator[None]:
        """Refuse a second build in the same work directory, which would share its chunks and staged files."""
        folder = self.work_dir / "national"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "build.lock").open("w") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BuildRunningError() from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _remove_leftovers(self) -> None:
        """Remove the staged COG, VRT and chunk files of a build that was killed, which can be gigabytes."""
        folder = self.work_dir / "national"
        for leftover in [*folder.glob("england-*.tif.tmp*"), *self.chunks_dir.glob(".*.tmp.tif")]:
            logger.info("Removing %s, left by a build that didn't finish", leftover)
            leftover.unlink(missing_ok=True)

    def _build(self) -> BuildReport:
        started = time.monotonic()
        edition = self.mirror.edition
        tiles = sorted(name for name in self.mirror.store.names() if name in self.catalogue)
        build = build_id(edition, tiles)
        current = self.store.manifest()
        if current is not None and current.build == build:
            return BuildReport(build, 0, len(tiles), 0, time.monotonic() - started, up_to_date=True)
        if not tiles:
            raise NothingToBuildError()
        by_chunk: dict[tuple[int, int], set[str]] = defaultdict(set)
        for name in tiles:
            by_chunk[chunk_of(name)].add(name)
        total = len(by_chunk)
        read = 0
        chunks: dict[tuple[int, int], Path] = {}
        for done, (chunk, wanted) in enumerate(sorted(by_chunk.items()), start=1):
            path = chunk_path(self.chunks_dir, chunk)
            read += self._update_chunk(path, chunk, wanted, edition)
            chunks[chunk] = path
            if self.on_progress is not None:
                self.on_progress(done, total, f"chunk {path.stem}")
        staged = self.work_dir / "national" / f"{filename_for(build)}.tmp"
        try:
            self._write_cog(chunks, staged)
            size = staged.stat().st_size
            manifest = Manifest(build, filename_for(build), edition, frozenset(tiles), _now())
            self.store.publish(staged, manifest)
        finally:
            staged.unlink(missing_ok=True)
        keep = {manifest.filename} | ({current.filename} if current else set())
        removed = self.store.prune(keep)
        if removed:
            logger.info("Removed the older overview builds %s", ", ".join(removed))
        logger.info(
            "Built overview %s from %d tiles (%d read) in %.0f s",
            build,
            len(tiles),
            read,
            time.monotonic() - started,
        )
        return BuildReport(build, read, len(tiles), size, time.monotonic() - started, up_to_date=False)

    def _update_chunk(self, path: Path, chunk: tuple[int, int], wanted: set[str], edition: str) -> int:
        """Bring a chunk up to `wanted`. Returns how many tiles were read from the mirror."""
        data, held = read_chunk(path, edition)
        missing = sorted(wanted - held)
        if not missing:
            return 0
        west, north = _chunk_origin(chunk)

        def add(name: str) -> None:
            with rasterio.open(self.mirror.store.gdal_path(name)) as ds:
                # Each tile fills its own cells, so the threads never write the same pixel.
                paste(ds, RESOLUTION_M, data, west, north)

        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="overview") as pool:
            list(pool.map(add, missing))
        write_chunk(path, chunk, data, held | set(missing), edition)
        return len(missing)

    def _write_cog(self, chunks: dict[tuple[int, int], Path], dest: Path) -> None:
        vrt = dest.with_name(dest.name + ".vrt")
        vrt.write_text(vrt_of(chunks))
        try:
            options = creation_options(overview_count=OVERVIEW_COUNT, threads=self.threads)
            # Blocks with no data at all (most of the sea) aren't written.
            options["SPARSE_OK"] = True
            rasterio.shutil.copy(str(vrt), str(dest), **options)
        finally:
            vrt.unlink(missing_ok=True)
        summary = check_cog(dest)
        assert len(summary.overviews) == OVERVIEW_COUNT, f"{dest} has overviews {summary.overviews}"
        assert summary.transform.a == RESOLUTION_M, f"{dest} has {summary.transform.a} m pixels"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
