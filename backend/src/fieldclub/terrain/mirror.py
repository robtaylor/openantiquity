"""The mirror of cloud-optimised elevation tiles, filled on first use (Decision 0006, points 4 and 5).

A mirror is a folder of `<tile>.tif` COGs: a local directory in development,
`gs://bucket/prefix` in production, which GDAL reads through `/vsigs/`.

`Mirror.ensure(name)` returns the path GDAL should open for a tile, adding the
tile first if it is missing. Adding one means finding the source GeoTIFF (on
local disk if it is there, otherwise from Defra's bulk supply), converting it,
checking it and publishing it under its final name. So:

- a tile that isn't in the catalogue is answered with None, with no network call;
- however many threads or processes want the same missing tile, one fetches it
  and the rest wait for it, through a lock per tile in this process and a file
  lock in the work directory across processes;
- a partial download or conversion is never published, because only a
  complete, checked COG is moved or uploaded to the final name;
- a source file GDAL can't read is set aside (a local one renamed with
  `UNREADABLE_SUFFIX`, a download deleted) and the next fetcher is tried.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import shutil
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from rasterio.errors import RasterioError

from fieldclub.errors import DataIntegrityError
from fieldclub.terrain import sftp
from fieldclub.terrain.catalogue import Catalogue, SourceTile, normalise_name
from fieldclub.terrain.cog import COG_FORMAT, to_cog
from fieldclub.terrain.errors import ElevationUnavailableError

logger = logging.getLogger(__name__)

GS_SCHEME = "gs://"


class MirrorStore(Protocol):
    def gdal_path(self, name: str) -> str:
        """What to hand GDAL to open a tile's COG."""
        ...

    def exists(self, name: str) -> bool: ...

    def publish(self, local: Path, name: str) -> None:
        """Make a complete local COG the tile's mirror file, in one step."""
        ...

    def names(self) -> list[str]:
        """The tiles the mirror holds."""
        ...


class LocalMirrorStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / f"{normalise_name(name)}.tif"

    def gdal_path(self, name: str) -> str:
        return str(self._path(name))

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def publish(self, local: Path, name: str) -> None:
        target = self._path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        # A rename within one file system is atomic: a reader sees the old state or the whole file.
        staged = target.with_name(f".{target.name}.publishing")
        if local.stat().st_dev == target.parent.stat().st_dev:
            local.replace(staged)
        else:
            shutil.copyfile(local, staged)
            local.unlink()
        staged.replace(target)

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(path.stem for path in self.root.glob("*.tif") if not path.name.startswith("."))

    def __repr__(self) -> str:
        return f"LocalMirrorStore({str(self.root)!r})"


class GcsMirrorStore:
    """A mirror in a Cloud Storage bucket. An upload only becomes visible once it is complete."""

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        assert bucket, "a bucket name is required"
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    def _object(self, name: str) -> str:
        filename = f"{normalise_name(name)}.tif"
        return f"{self.prefix}/{filename}" if self.prefix else filename

    def _bucket(self) -> Any:
        if self._client is None:
            from google.cloud import storage as gcs

            self._client = gcs.Client()
        return self._client.bucket(self.bucket_name)

    def gdal_path(self, name: str) -> str:
        return f"/vsigs/{self.bucket_name}/{self._object(name)}"

    def exists(self, name: str) -> bool:
        return bool(self._bucket().blob(self._object(name)).exists())

    def publish(self, local: Path, name: str) -> None:
        blob = self._bucket().blob(self._object(name))
        blob.upload_from_filename(str(local), content_type="image/tiff")
        local.unlink()

    def names(self) -> list[str]:
        prefix = f"{self.prefix}/" if self.prefix else ""
        blobs = self._bucket().list_blobs(prefix=prefix, delimiter="/")
        return sorted(blob.name[len(prefix) : -len(".tif")] for blob in blobs if blob.name.endswith(".tif"))

    def __repr__(self) -> str:
        return f"GcsMirrorStore('gs://{self.bucket_name}/{self.prefix}')"


def mirror_store(location: str) -> MirrorStore:
    """A store for `gs://bucket/prefix` or a local directory."""
    if location.startswith(GS_SCHEME):
        bucket, _, prefix = location[len(GS_SCHEME) :].partition("/")
        return GcsMirrorStore(bucket, prefix)
    assert "://" not in location, f"{location!r}: only local paths and gs:// are supported"
    return LocalMirrorStore(Path(location))


@dataclass(frozen=True)
class Fetched:
    path: Path
    # True when the file was downloaded for this conversion and can go afterwards.
    temporary: bool


class Fetcher(Protocol):
    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        """The tile's complete source GeoTIFF, or None when this fetcher can't provide it."""
        ...


class LocalSourceFetcher:
    """Source tiles already on disk, exactly as Defra supplies them."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        path = self.root / tile.source_filename
        if not path.is_file():
            return None
        if path.stat().st_size != tile.size:
            logger.warning(
                "%s is %d bytes, not the %d listed; ignoring it", path, path.stat().st_size, tile.size
            )
            return None
        return Fetched(path, temporary=False)


class SftpFetcher:
    """Defra's bulk supply. The connection is set up on first use, so missing credentials only matter then."""

    def __init__(self, connector: Callable[[], sftp.Connect], **download_options: Any) -> None:
        self._connector = connector
        self._options = download_options

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        connect = self._connector()
        started = time.perf_counter()
        path = sftp.download(
            connect,
            tile.remote_path,
            work_dir / tile.source_filename,
            expected_size=tile.size,
            **self._options,
        )
        logger.info(
            "Fetched %s (%.1f MB) in %.1f s", tile.name, tile.size / 1e6, time.perf_counter() - started
        )
        return Fetched(path, temporary=True)


# Added to the name of a source file on disk that GDAL couldn't read, so it isn't offered again.
UNREADABLE_SUFFIX = ".unreadable"


def _set_aside(fetched: Fetched) -> None:
    """Rename an unreadable file on disk. A temporary download is deleted by `Mirror._add` instead."""
    if fetched.temporary:
        return
    aside = fetched.path.with_name(fetched.path.name + UNREADABLE_SUFFIX)
    fetched.path.replace(aside)
    logger.warning("Moved the unreadable %s aside to %s", fetched.path, aside)


class Mirror:
    def __init__(
        self,
        catalogue: Catalogue,
        store: MirrorStore,
        fetchers: Sequence[Fetcher],
        work_dir: Path,
        *,
        max_fetches: int = 2,
        convert: Callable[[Path, Path], object] = to_cog,
    ) -> None:
        assert max_fetches >= 1, "at least one fetch must be allowed"
        self.catalogue = catalogue
        self.store = store
        self.fetchers = list(fetchers)
        self.work_dir = Path(work_dir)
        self._convert = convert
        self._fetch_slots = threading.BoundedSemaphore(max_fetches)
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        # Tiles once seen in the store. A mirror file is never removed, so this
        # saves asking a bucket again for every read.
        self._present: set[str] = set()

    @property
    def edition(self) -> str:
        """The catalogue's edition and the mirror's encoding: what a cached tile was made from."""
        return f"{self.catalogue.edition}.{COG_FORMAT}"

    def has(self, name: str) -> bool:
        """Whether the mirror holds a tile now, without adding it."""
        name = normalise_name(name)
        if name in self._present:
            return True
        if self.store.exists(name):
            self._present.add(name)
            return True
        return False

    def path(self, name: str) -> str | None:
        """The tile's GDAL path if the mirror holds it, without adding it."""
        return self.store.gdal_path(name) if self.has(name) else None

    def ensure(self, name: str) -> str | None:
        """The tile's GDAL path, adding it to the mirror first if needed. None when no such tile exists."""
        tile = self.catalogue.get(name)
        if tile is None:
            return None
        if self.has(tile.name):
            return self.store.gdal_path(tile.name)
        with self._tile_lock(tile.name):
            # Whoever held the lock before us may have added it.
            if not self.has(tile.name):
                self._add(tile)
        assert self.has(tile.name), f"{tile.name} should be in the mirror now"
        return self.store.gdal_path(tile.name)

    def _add(self, tile: SourceTile) -> None:
        """Convert and publish the tile from the first source that has a readable copy."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        staged = self.work_dir / f"{tile.name}.cog.tif"
        unreadable = 0
        for fetcher in self.fetchers:
            with self._fetch_slots:
                fetched = fetcher.fetch(tile, self.work_dir)
            if fetched is None:
                continue
            started = time.perf_counter()
            try:
                try:
                    self._convert(fetched.path, staged)
                except (RasterioError, DataIntegrityError) as exc:
                    # The right size but not a raster GDAL can read: try the next source.
                    logger.warning("%s from %s can't be read (%s)", tile.name, fetched.path, exc)
                    unreadable += 1
                    _set_aside(fetched)
                    continue
                self.store.publish(staged, tile.name)
            finally:
                staged.unlink(missing_ok=True)
                if fetched.temporary:
                    fetched.path.unlink(missing_ok=True)
            self._present.add(tile.name)
            logger.info("Added %s to the mirror in %.1f s", tile.name, time.perf_counter() - started)
            return
        if unreadable:
            raise DataIntegrityError(f"Every copy of {tile.name} that could be found was unreadable.")
        raise ElevationUnavailableError(f"No source could provide {tile.name}.")

    @contextlib.contextmanager
    def _tile_lock(self, name: str) -> Iterator[None]:
        with self._guard:
            lock = self._locks.setdefault(name, threading.Lock())
        with lock:
            locks = self.work_dir / "locks"
            locks.mkdir(parents=True, exist_ok=True)
            with (locks / f"{name}.lock").open("w") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
