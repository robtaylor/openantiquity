"""The mirror of cloud-optimised elevation tiles, filled on first use (Decision 0006, points 4 and 5).

A mirror is a folder of `<tile>.tif` COGs: a local directory in development,
`gs://bucket/prefix` in production, which GDAL reads through `/vsigs/`.

`Mirror.ensure(name)` returns the path GDAL should open for a tile, adding the
tile first if it is missing. Adding one means finding the source GeoTIFF (on
local disk if it is there, otherwise from Defra's bulk supply), converting it,
checking it and publishing it under its final name. So:

- a tile that isn't in the catalogue is answered with None, with no network call;
- however many threads, processes or machines want the same missing tile, one
  fetches it and the rest wait for it, through a lock per tile in this
  process, a file lock in the work directory across processes, and, for a
  mirror in a bucket, a lock object in the bucket across machines
  (`blobs.ObjectLock`), which is treated as abandoned once it is older than
  its `stale_after_s`;
- a partial download or conversion is never published, because only a
  complete, checked COG is moved or uploaded to the final name;
- a source file GDAL can't read, at its start or part-way through its data,
  is set aside (a local one renamed with `UNREADABLE_SUFFIX`, a download
  deleted) and the next fetcher is tried;
- a tile that couldn't be added isn't fetched again for a while: requests for
  it are answered `elevation_unavailable` at once. A tile whose every copy was
  unreadable waits `UNREADABLE_RETRY_S`, recorded in the folder under
  `failed/` so that every server sharing it waits too. One whose download
  failed waits `FETCH_RETRY_S` in this process only. `ensure(...,
  retry_failed=True)`, which the mirror command uses, tries it regardless.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fieldclub.terrain import sftp
from fieldclub.terrain.blobs import Folder, GcsFolder, LocalFolder, ObjectLock, folder
from fieldclub.terrain.catalogue import Catalogue, SourceTile, normalise_name
from fieldclub.terrain.cog import COG_FORMAT, UNREADABLE_ERRORS, to_cog
from fieldclub.terrain.errors import (
    ElevationUnavailableError,
    FetchFailedError,
    SourceUnreadableError,
    SupplyRefusedError,
)

logger = logging.getLogger(__name__)


class MirrorStore:
    """The mirror's COGs in a folder, one `<tile>.tif` each, and a lock per tile when it is shared."""

    def __init__(self, folder: Folder) -> None:
        self.folder = folder

    @property
    def shared(self) -> bool:
        """Whether other machines may fill the same mirror, so a fetch takes a lock in the folder."""
        return self.folder.shared

    @staticmethod
    def filename(name: str) -> str:
        return f"{normalise_name(name)}.tif"

    @staticmethod
    def lock_name(name: str) -> str:
        return f"locks/{normalise_name(name)}.lock"

    @staticmethod
    def failure_name(name: str) -> str:
        return f"failed/{normalise_name(name)}.json"

    def gdal_path(self, name: str) -> str:
        """What to hand GDAL to open a tile's COG."""
        return self.folder.gdal_path(self.filename(name))

    def exists(self, name: str) -> bool:
        return self.folder.exists(self.filename(name))

    def publish(self, local: Path, name: str) -> None:
        """Make a complete local COG the tile's mirror file, in one step, and remove the local copy.

        A tile already in the mirror is never replaced. In a bucket the
        writers hold permission to create objects, not to replace them, so a
        mirror file can't be overwritten or lost, and another instance that
        published the same tile first has done the job.
        """
        if not self.folder.upload(local, self.filename(name), "image/tiff", replace=False):
            logger.info("%s was already in the mirror", name)
        local.unlink()

    def names(self) -> list[str]:
        """The tiles the mirror holds."""
        return [filename.removesuffix(".tif") for filename in self.folder.names(".tif")]

    def __repr__(self) -> str:
        return f"MirrorStore({self.folder!r})"


class LocalMirrorStore(MirrorStore):
    def __init__(self, root: Path) -> None:
        super().__init__(LocalFolder(root))
        self.root = Path(root)


class GcsMirrorStore(MirrorStore):
    """A mirror in a Cloud Storage bucket. An upload only becomes visible once it is complete."""

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        super().__init__(GcsFolder(bucket, prefix, client=client))


def mirror_store(location: str) -> MirrorStore:
    """A store for `gs://bucket/prefix` or a local directory."""
    return MirrorStore(folder(location))


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


# How long a refused login keeps every later fetch from trying again.
REFUSAL_PAUSE = 15 * 60.0


class SftpFetcher:
    """Defra's bulk supply. The connection is set up on first use, so missing credentials only matter then.

    Sessions are kept open between tiles, at most `sessions` of them idle.
    Once the supply refuses the login or shows the wrong host key, every fetch
    for the next `refusal_pause` seconds fails at once with the same error, so
    a run over many tiles, or a busy map, doesn't send Defra a login attempt
    for each one.
    """

    def __init__(
        self,
        connector: Callable[[], sftp.Connect],
        *,
        sessions: int = 2,
        refusal_pause: float = REFUSAL_PAUSE,
        clock: Callable[[], float] = time.monotonic,
        **download_options: Any,
    ) -> None:
        self._connector = connector
        self._sessions = sessions
        self._options = download_options
        self._refusal_pause = refusal_pause
        self._clock = clock
        self._refused: tuple[float, SupplyRefusedError] | None = None
        self._pool: sftp.SessionPool | None = None
        self._guard = threading.Lock()

    def _get_pool(self) -> sftp.SessionPool:
        with self._guard:
            if self._pool is None:
                self._pool = sftp.SessionPool(self._connector(), self._sessions)
            return self._pool

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        refused = self._refused
        if refused is not None:
            at, error = refused
            if self._clock() - at < self._refusal_pause:
                raise SupplyRefusedError(error.message)
            self._refused = None
        pool = self._get_pool()
        started = time.perf_counter()
        try:
            path = sftp.download(
                pool.connect,
                tile.remote_path,
                work_dir / tile.source_filename,
                expected_size=tile.size,
                **self._options,
            )
        except SupplyRefusedError as exc:
            self._refused = (self._clock(), exc)
            raise
        logger.info(
            "Fetched %s (%.1f MB) in %.1f s", tile.name, tile.size / 1e6, time.perf_counter() - started
        )
        return Fetched(path, temporary=True)

    def close(self) -> None:
        with self._guard:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()


# Added to the name of a source file on disk that GDAL couldn't read, so it isn't offered again.
UNREADABLE_SUFFIX = ".unreadable"
# How long a tile isn't fetched again after every copy of it was unreadable: a
# corrupt file upstream is rarely replaced within the day, and each try
# downloads 40 to 90 MB.
UNREADABLE_RETRY_S = 6 * 3600.0
# How long one process waits before fetching a tile again after its download failed.
FETCH_RETRY_S = 300.0


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
        lock: ObjectLock | None = None,
        unreadable_retry_s: float = UNREADABLE_RETRY_S,
        fetch_retry_s: float = FETCH_RETRY_S,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        assert max_fetches >= 1, "at least one fetch must be allowed"
        self.catalogue = catalogue
        self.store = store
        self.fetchers = list(fetchers)
        self.work_dir = Path(work_dir)
        self._convert = convert
        # Shared folders get a lock in the folder, so two machines never fetch the same tile.
        self._shared_lock = (lock or ObjectLock(store.folder)) if store.shared else None
        self._fetch_slots = threading.BoundedSemaphore(max_fetches)
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        # Tiles once seen in the store. A mirror file is never removed, so this
        # saves asking a bucket again for every read.
        self._present: set[str] = set()
        self._unreadable_retry_s = unreadable_retry_s
        self._fetch_retry_s = fetch_retry_s
        self._clock = clock
        self._now = now
        # Tiles this process failed to add, with the `clock` time before which they aren't tried again.
        self._failed: dict[str, float] = {}

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

    def ensure(self, name: str, *, retry_failed: bool = False) -> str | None:
        """The tile's GDAL path, adding it to the mirror first if needed. None when no such tile exists.

        A tile that failed recently is refused without a fetch unless `retry_failed`.
        """
        tile = self.catalogue.get(name)
        if tile is None:
            return None
        if self.has(tile.name):
            return self.store.gdal_path(tile.name)
        if not retry_failed:
            self._refuse_if_failed(tile.name)
        with self._tile_lock(tile.name):
            # Whoever held the lock before us may have added it.
            if not self.has(tile.name):
                self._add_once(tile)
        assert self.has(tile.name), f"{tile.name} should be in the mirror now"
        return self.store.gdal_path(tile.name)

    def refuse_if_failed(self, name: str) -> None:
        """Raise `ElevationUnavailableError` for a tile that couldn't be added lately, as `ensure` would."""
        self._refuse_if_failed(normalise_name(name))

    def _refuse_if_failed(self, name: str) -> None:
        """Raise `ElevationUnavailableError` when this process or the folder says the tile failed lately."""
        until = self._failed.get(name)
        if until is not None and self._clock() < until:
            raise ElevationUnavailableError(f"{name} couldn't be added a short while ago.")
        since = self._failed_since(name)
        if since is not None:
            age = (self._now() - since).total_seconds()
            if age < self._unreadable_retry_s:
                self._failed[name] = self._clock() + self._unreadable_retry_s - age
                raise ElevationUnavailableError(f"Every copy of {name} was unreadable when last fetched.")

    def _failed_since(self, name: str) -> datetime | None:
        """When the folder's record says every copy of the tile was found unreadable, if it has one."""
        data = self.store.folder.read(self.store.failure_name(name))
        if data is None:
            return None
        try:
            return datetime.fromisoformat(json.loads(data)["since"])
        except (ValueError, KeyError, TypeError):
            logger.warning("Ignoring the malformed failure record of %s", name)
            return None

    def _record_failure(self, name: str, exc: SourceUnreadableError | FetchFailedError) -> None:
        unreadable = isinstance(exc, SourceUnreadableError)
        wait = self._unreadable_retry_s if unreadable else self._fetch_retry_s
        self._failed[name] = self._clock() + wait
        if unreadable:
            body = json.dumps({"tile": name, "since": self._now().isoformat(), "code": exc.code})
            self.store.folder.write(self.store.failure_name(name), body.encode(), "application/json")
        logger.warning("Not fetching %s again for %.0f s", name, wait)

    def _add_once(self, tile: SourceTile) -> None:
        """Add the tile, under the folder's lock when other machines share the mirror."""
        try:
            if self._shared_lock is None:
                self._add(tile)
            else:
                lock_name = self.store.lock_name(tile.name)
                with self._shared_lock.hold(lock_name, done=lambda: self.has(tile.name)) as held:
                    # Not held means another machine added it while this one waited.
                    if held and not self.has(tile.name):
                        self._add(tile)
        except SupplyRefusedError:
            # The supply refused us, not this tile: `SftpFetcher` pauses every fetch instead.
            raise
        except (SourceUnreadableError, FetchFailedError) as exc:
            self._record_failure(tile.name, exc)
            raise
        self._failed.pop(tile.name, None)

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
                except UNREADABLE_ERRORS as exc:
                    # The right size but not a raster GDAL can read: try the next source.
                    logger.warning(
                        "%s from %s can't be read (%s: %s)", tile.name, fetched.path, type(exc).__name__, exc
                    )
                    unreadable += 1
                    _set_aside(fetched)
                    continue
                self.store.publish(staged, tile.name)
                self.store.folder.delete(self.store.failure_name(tile.name))
            finally:
                staged.unlink(missing_ok=True)
                if fetched.temporary:
                    fetched.path.unlink(missing_ok=True)
            self._present.add(tile.name)
            logger.info("Added %s to the mirror in %.1f s", tile.name, time.perf_counter() - started)
            return
        if unreadable:
            raise SourceUnreadableError(f"Every copy of {tile.name} that could be found was unreadable.")
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
