"""Folders of files the terrain service keeps: a local directory, or a prefix in a Cloud Storage bucket.

The mirror and the national overview both live in a `Folder`. GDAL reads a
file through `gdal_path` (`/vsigs/` for a bucket), and everything else goes
through the methods here, so the two kinds of folder behave the same:

- `upload` makes a complete local file visible under its name in one step, and
  checks that the size stored is the size sent;
- `create` writes a small object only if nothing is there yet, which is what
  `ObjectLock` is built on;
- `stat` and `delete_if` let a lock that has been left behind be taken over by
  exactly one of the processes that find it.

`google-cloud-storage` is imported on first use, so development and the tests
that don't touch a bucket never load it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import socket
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fieldclub.errors import DataIntegrityError
from fieldclub.storage import check_key
from fieldclub.terrain.errors import ElevationUnavailableError

logger = logging.getLogger(__name__)

GS_SCHEME = "gs://"


@dataclass(frozen=True)
class BlobInfo:
    size: int
    created: datetime
    # Changes whenever the object is replaced: a generation in a bucket, an inode and mtime locally.
    token: str


class Folder(Protocol):
    # Whether processes on other machines may share it, so cross-machine locks are needed.
    shared: bool

    def gdal_path(self, name: str) -> str: ...

    def exists(self, name: str) -> bool: ...

    def read(self, name: str) -> bytes | None:
        """The object's bytes, or None when there is none."""
        ...

    def write(self, name: str, data: bytes, content_type: str) -> None:
        """Replace the object in one step."""
        ...

    def create(self, name: str, data: bytes) -> bool:
        """Write the object only if there is none. True when this call created it."""
        ...

    def upload(self, local: Path, name: str, content_type: str, *, replace: bool = True) -> bool:
        """Make a complete local file the object, checking the stored size. The local file stays.

        With `replace=False` an object already there is kept, and the call
        answers False. Otherwise it answers True.
        """
        ...

    def names(self, suffix: str = "") -> list[str]:
        """The objects directly in the folder whose names end with `suffix`, sorted."""
        ...

    def stat(self, name: str) -> BlobInfo | None: ...

    def delete(self, name: str) -> None:
        """Remove the object. Removing one that isn't there is not an error."""
        ...

    def delete_if(self, name: str, token: str) -> bool:
        """Remove the object only if it is still the one `stat` described. True when this call removed it."""
        ...


class LocalFolder:
    shared = False

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / check_key(name)

    def gdal_path(self, name: str) -> str:
        return str(self._path(name))

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def read(self, name: str) -> bytes | None:
        try:
            return self._path(name).read_bytes()
        except FileNotFoundError:
            return None

    def write(self, name: str, data: bytes, content_type: str) -> None:
        target = self._path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.writing")
        try:
            staged.write_bytes(data)
            staged.replace(target)
        finally:
            staged.unlink(missing_ok=True)

    def create(self, name: str, data: bytes) -> bool:
        target = self._path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        return True

    def upload(self, local: Path, name: str, content_type: str, *, replace: bool = True) -> bool:
        target = self._path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = local.stat().st_size
        # A rename within one file system is atomic: a reader sees the old state or the whole file.
        staged = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.publishing")
        try:
            if local.stat().st_dev == target.parent.stat().st_dev:
                os.link(local, staged)
            else:
                shutil.copyfile(local, staged)
            if staged.stat().st_size != size:
                raise DataIntegrityError(f"{name} was stored with the wrong size.")
            if replace:
                staged.replace(target)
                return True
            # A hard link is made only if nothing has the name, so an existing file is never replaced.
            try:
                os.link(staged, target)
            except FileExistsError:
                return False
            return True
        finally:
            staged.unlink(missing_ok=True)

    def names(self, suffix: str = "") -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_file() and not path.name.startswith(".") and path.name.endswith(suffix)
        )

    def stat(self, name: str) -> BlobInfo | None:
        try:
            found = self._path(name).stat()
        except FileNotFoundError:
            return None
        return BlobInfo(
            found.st_size, datetime.fromtimestamp(found.st_mtime, UTC), f"{found.st_ino}.{found.st_mtime_ns}"
        )

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def delete_if(self, name: str, token: str) -> bool:
        info = self.stat(name)
        if info is None or info.token != token:
            return False
        self.delete(name)
        return True

    def __repr__(self) -> str:
        return f"LocalFolder({str(self.root)!r})"


class GcsFolder:
    """A prefix in a bucket. Writes are single requests, so an object is either whole or absent."""

    shared = True

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        assert bucket, "a bucket name is required"
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self._client = client
        self._bucket: Any = None
        self._guard = threading.Lock()

    def _object(self, name: str) -> str:
        check_key(name)
        return f"{self.prefix}/{name}" if self.prefix else name

    def _get_bucket(self) -> Any:
        with self._guard:
            if self._bucket is None:
                if self._client is None:
                    from google.cloud import storage as gcs

                    self._client = gcs.Client()
                self._bucket = self._client.bucket(self.bucket_name)
            return self._bucket

    def gdal_path(self, name: str) -> str:
        return f"/vsigs/{self.bucket_name}/{self._object(name)}"

    def exists(self, name: str) -> bool:
        return bool(self._get_bucket().blob(self._object(name)).exists())

    def read(self, name: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            return bytes(self._get_bucket().blob(self._object(name)).download_as_bytes())
        except NotFound:
            return None

    def write(self, name: str, data: bytes, content_type: str) -> None:
        self._get_bucket().blob(self._object(name)).upload_from_string(data, content_type=content_type)

    def create(self, name: str, data: bytes) -> bool:
        from google.api_core.exceptions import PreconditionFailed

        blob = self._get_bucket().blob(self._object(name))
        try:
            # Generation 0 means "only if there is no live object".
            blob.upload_from_string(data, content_type="application/json", if_generation_match=0)
        except PreconditionFailed:
            return False
        return True

    def upload(self, local: Path, name: str, content_type: str, *, replace: bool = True) -> bool:
        from google.api_core.exceptions import Forbidden, PreconditionFailed

        blob = self._get_bucket().blob(self._object(name))
        size = local.stat().st_size
        # Generation 0 means "only if there is no live object".
        only_new = {} if replace else {"if_generation_match": 0}
        try:
            # The library checks the CRC32C of what arrived against the file's own.
            blob.upload_from_filename(str(local), content_type=content_type, checksum="crc32c", **only_new)
        except (PreconditionFailed, Forbidden):
            # A writer that may create objects but not replace them can be
            # refused outright, rather than told the precondition failed.
            # Either is fine once the object is there.
            if replace or not blob.exists():
                raise
            return False
        if blob.size != size:
            raise DataIntegrityError(f"{name} was stored with {blob.size} bytes, not {size}.")
        return True

    def names(self, suffix: str = "") -> list[str]:
        prefix = f"{self.prefix}/" if self.prefix else ""
        blobs = self._get_bucket().list_blobs(prefix=prefix, delimiter="/")
        return sorted(
            blob.name[len(prefix) :]
            for blob in blobs
            if blob.name.endswith(suffix) and "/" not in blob.name[len(prefix) :]
        )

    def stat(self, name: str) -> BlobInfo | None:
        blob = self._get_bucket().get_blob(self._object(name))
        if blob is None:
            return None
        return BlobInfo(int(blob.size), blob.time_created, str(blob.generation))

    def delete(self, name: str) -> None:
        from google.api_core.exceptions import NotFound

        with contextlib.suppress(NotFound):
            self._get_bucket().blob(self._object(name)).delete()

    def delete_if(self, name: str, token: str) -> bool:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        try:
            self._get_bucket().blob(self._object(name)).delete(if_generation_match=int(token))
        except (NotFound, PreconditionFailed):
            return False
        return True

    def __repr__(self) -> str:
        return f"GcsFolder('gs://{self.bucket_name}/{self.prefix}')"


def folder(location: str) -> Folder:
    """A folder for `gs://bucket/prefix` or a local directory."""
    if location.startswith(GS_SCHEME):
        bucket, _, prefix = location[len(GS_SCHEME) :].partition("/")
        return GcsFolder(bucket, prefix)
    assert "://" not in location, f"{location!r}: only local paths and gs:// are supported"
    return LocalFolder(Path(location))


# --------------------------------------------------------------------------
# A lock held in the folder itself
# --------------------------------------------------------------------------


class LockTimeoutError(ElevationUnavailableError):
    code = "elevation_busy"
    message = "Elevation for this area is being prepared. Try again shortly."


def _owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"


@dataclass
class ObjectLock:
    """A lock that is an object in a folder, so processes on different machines can share it.

    `acquire(name)` creates `<name>` only if it doesn't exist. Whoever creates
    it holds the lock until `release`. A lock older than `stale_after_s` is
    treated as abandoned by a process that died: one waiter removes it, by
    generation, and the waiters race to create it again, so exactly one wins.

    `done()` says whether the work the lock guards has been finished by
    someone else, so a waiter can stop waiting as soon as it is.
    """

    folder: Folder
    stale_after_s: float = 900.0
    wait_s: float = 120.0
    poll_s: float = 0.5
    max_poll_s: float = 5.0
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lambda: datetime.now(UTC)

    @contextlib.contextmanager
    def hold(self, name: str, done: Callable[[], bool]) -> Iterator[bool]:
        """Hold the lock on `name`, or wait until `done()`. Yields True when held, False when done."""
        owner = self.acquire(name, done)
        if owner is None:
            yield False
            return
        try:
            yield True
        finally:
            self.release(name, owner)

    def acquire(self, name: str, done: Callable[[], bool]) -> str | None:
        """The owner token once the lock is held, or None when `done()` became true while waiting."""
        owner = _owner_id()
        body = json.dumps({"owner": owner, "since": self.now().isoformat()}).encode()
        started = time.monotonic()
        wait = self.poll_s
        while True:
            if self.folder.create(name, body):
                return owner
            if self._ours(name, owner):
                # A retried create whose first attempt had in fact succeeded.
                return owner
            if done():
                return None
            info = self.folder.stat(name)
            if info is not None:
                age = (self.now() - info.created).total_seconds()
                if age > self.stale_after_s:
                    if self.folder.delete_if(name, info.token):
                        logger.warning("Took over the lock %s, abandoned %.0f s ago", name, age)
                    continue
            if time.monotonic() - started > self.wait_s:
                raise LockTimeoutError(f"Waited {self.wait_s:.0f} s for another process to finish.")
            self.sleep(wait)
            wait = min(wait * 2, self.max_poll_s)

    def _ours(self, name: str, owner: str) -> bool:
        data = self.folder.read(name)
        if data is None:
            return False
        try:
            return json.loads(data).get("owner") == owner
        except ValueError:
            return False

    def release(self, name: str, owner: str) -> None:
        info = self.folder.stat(name)
        if info is not None and self._ours(name, owner):
            self.folder.delete_if(name, info.token)
