"""Folders of files the terrain service keeps: a local directory, or a prefix in an S3 bucket.

The mirror and the national overview both live in a `Folder`. GDAL reads a
file through `gdal_path` (`/vsis3/` for a bucket), and everything else goes
through the methods here, so the two kinds of folder behave the same:

- `upload` makes a complete local file visible under its name in one step, and
  checks that the size stored is the size sent;
- `create` writes a small object only if nothing is there yet, which is what
  `ObjectLock` is built on;
- `stat` and `delete_if` let a lock that has been left behind be taken over by
  exactly one of the processes that find it, and `replace_if` lets its holder
  refresh it without overwriting a lock someone else has taken since.

`boto3` is imported on first use, so development and the tests that don't
touch a bucket never load it.
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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from fieldclub.config import S3_SCHEME
from fieldclub.errors import DataIntegrityError
from fieldclub.storage import StorageError, check_key, s3_client, s3_get, s3_head, s3_refusal
from fieldclub.terrain.errors import ElevationUnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlobInfo:
    size: int
    created: datetime
    # Changes whenever the object is replaced with other bytes: an ETag in a
    # bucket, an inode and mtime locally. A bucket gives two writes of the same
    # bytes the same ETag, so a writer that relies on a token writes unique bytes.
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

    def replace_if(self, name: str, data: bytes, token: str) -> bool:
        """Replace the object only if it is still the one `stat` described. True when this replaced it."""
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

    def replace_if(self, name: str, data: bytes, token: str) -> bool:
        # Not atomic, which is enough: a local folder isn't shared between machines.
        info = self.stat(name)
        if info is None or info.token != token:
            return False
        self.write(name, data, "application/json")
        return True

    def __repr__(self) -> str:
        return f"LocalFolder({str(self.root)!r})"


class S3Folder:
    """A prefix in a bucket with the S3 interface. A put is one request, so an object is whole or absent.

    The three conditional writes are S3's own preconditions, which the spike
    on Fly.io proved Tigris honours (Decision 0018): `If-None-Match: *` to
    create, and `If-Match` with the ETag `stat` gave to replace or delete. A
    refused one answers 412. An ETag comes from an object's bytes, so two
    writes of the same bytes share one: `ObjectLock` makes every write it
    relies on a token for unique.
    """

    shared = True

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        assert bucket, "a bucket name is required"
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self._client = client
        configure_gdal_for_s3()

    def _object(self, name: str) -> str:
        check_key(name)
        return f"{self.prefix}/{name}" if self.prefix else name

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = s3_client()
        return self._client

    def _put(self, name: str, body: Any, content_type: str, **condition: str) -> bool:
        """Put one object. False when the store refused `condition`, or the object has gone."""
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=self._object(name),
                Body=body,
                ContentType=content_type,
                **condition,
            )
        except Exception as exc:
            # 409 is S3's answer to a conditional write racing another on the
            # same object; the caller looks again, as after a 412. A missing
            # bucket is an error (`s3_refusal`).
            if condition and s3_refusal(exc) in (404, 409, 412):
                return False
            raise
        return True

    def gdal_path(self, name: str) -> str:
        return f"/vsis3/{self.bucket_name}/{self._object(name)}"

    def exists(self, name: str) -> bool:
        return s3_head(self.client, self.bucket_name, self._object(name)) is not None

    def read(self, name: str) -> bytes | None:
        return s3_get(self.client, self.bucket_name, self._object(name))

    def write(self, name: str, data: bytes, content_type: str) -> None:
        self._put(name, data, content_type)

    def create(self, name: str, data: bytes) -> bool:
        return self._put(name, data, "application/json", IfNoneMatch="*")

    def upload(self, local: Path, name: str, content_type: str, *, replace: bool = True) -> bool:
        size = local.stat().st_size
        if replace:
            # A managed upload, in parts for a large file such as the national overview.
            self.client.upload_file(
                str(local), self.bucket_name, self._object(name), ExtraArgs={"ContentType": content_type}
            )
        else:
            # One request, so the precondition the spike measured is the one
            # that applies. A mirror tile is tens of megabytes.
            with local.open("rb") as body:
                if not self._put(name, body, content_type, IfNoneMatch="*"):
                    if not self.exists(name):
                        # A 409: another conditional write to it is under way.
                        raise StorageError(f"The store refused to create {name}, and holds none yet.")
                    return False
        stored = s3_head(self.client, self.bucket_name, self._object(name))
        if stored is None or stored["ContentLength"] != size:
            got = None if stored is None else stored["ContentLength"]
            raise DataIntegrityError(f"{name} was stored with {got} bytes, not {size}.")
        return True

    def names(self, suffix: str = "") -> list[str]:
        prefix = f"{self.prefix}/" if self.prefix else ""
        found: list[str] = []
        page: dict[str, Any] = {"Bucket": self.bucket_name, "Prefix": prefix, "Delimiter": "/"}
        while True:
            answer = self.client.list_objects_v2(**page)
            found.extend(
                item["Key"][len(prefix) :]
                for item in answer.get("Contents", [])
                if item["Key"].endswith(suffix) and "/" not in item["Key"][len(prefix) :]
            )
            if not answer.get("IsTruncated"):
                return sorted(found)
            page["ContinuationToken"] = answer["NextContinuationToken"]

    def stat(self, name: str) -> BlobInfo | None:
        found = s3_head(self.client, self.bucket_name, self._object(name))
        if found is None:
            return None
        return BlobInfo(int(found["ContentLength"]), found["LastModified"], str(found["ETag"]))

    def delete(self, name: str) -> None:
        # Removing an object that isn't there succeeds in S3.
        self.client.delete_object(Bucket=self.bucket_name, Key=self._object(name))

    def delete_if(self, name: str, token: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=self._object(name), IfMatch=token)
        except Exception as exc:
            if s3_refusal(exc) in (404, 409, 412):
                return False
            raise
        return True

    def replace_if(self, name: str, data: bytes, token: str) -> bool:
        return self._put(name, data, "application/json", IfMatch=token)

    def __repr__(self) -> str:
        return f"S3Folder('{S3_SCHEME}{self.bucket_name}/{self.prefix}')"


def gdal_s3_options(environ: Mapping[str, str]) -> dict[str, str]:
    """GDAL's options for `/vsis3/` to reach the store at `AWS_ENDPOINT_URL_S3`. None of them is a secret.

    GDAL reads the credentials from the environment itself. It is given the
    endpoint's host, with HTTPS as the address says, and path-style requests,
    which is how the spike on Fly.io read tiles from Tigris. Empty when no
    endpoint is set, so GDAL keeps its own defaults for AWS.
    """
    endpoint = environ.get("AWS_ENDPOINT_URL_S3", "")
    if not endpoint:
        return {}
    parsed = urlsplit(endpoint)
    assert parsed.scheme in ("http", "https"), f"{endpoint!r} isn't an http(s) address"
    assert parsed.netloc, f"{endpoint!r} has no host"
    assert parsed.path in ("", "/"), f"{endpoint!r}: GDAL can't be given an endpoint with a path"
    return {
        "AWS_S3_ENDPOINT": parsed.netloc,
        "AWS_HTTPS": "YES" if parsed.scheme == "https" else "NO",
        "AWS_VIRTUAL_HOSTING": "FALSE",
    }


def configure_gdal_for_s3() -> None:
    """Set `gdal_s3_options` for every thread in the process. Safe to call again."""
    from rasterio.env import set_gdal_config

    for key, value in gdal_s3_options(os.environ).items():
        set_gdal_config(key, value)


def folder(location: str) -> Folder:
    """A folder for `s3://bucket/prefix` or a local directory."""
    if location.startswith(S3_SCHEME):
        bucket, _, prefix = location[len(S3_SCHEME) :].partition("/")
        return S3Folder(bucket, prefix)
    assert "://" not in location, f"{location!r}: only local paths and {S3_SCHEME} are supported"
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
    it holds the lock until `release`. `hold` rewrites the object every
    `heartbeat_s` (a quarter of `stale_after_s` by default) while the work
    runs, so the object's age is the time since its holder last showed it was
    alive, however long the work takes. A lock older than `stale_after_s` is
    treated as abandoned by a process that died: one waiter removes it, by
    its token, and the waiters race to create it again, so exactly one wins.
    Every write of the lock has bytes of its own, so its token in a bucket
    (an ETag, made from the bytes) changes with every write.
    Keep `stale_after_s` below `wait_s`, so a waiter outlasts a lock left by a
    crash.

    `done()` says whether the work the lock guards has been finished by
    someone else, so a waiter can stop waiting as soon as it is.
    """

    folder: Folder
    stale_after_s: float = 90.0
    wait_s: float = 120.0
    heartbeat_s: float | None = None
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
        stop = threading.Event()
        beat = threading.Thread(
            target=self._beat, args=(name, owner, stop), name=f"heartbeat {name}", daemon=True
        )
        beat.start()
        try:
            yield True
        finally:
            stop.set()
            beat.join()
            self.release(name, owner)

    def _body(self, owner: str) -> bytes:
        # `write` makes every write's bytes unique, and so its ETag in a
        # bucket. Otherwise a refresh in the same instant as the last one, or
        # with a clock that stood still, would keep the token a waiter saw,
        # and that waiter could then remove a lock whose holder is alive.
        return json.dumps(
            {"owner": owner, "since": self.now().isoformat(), "write": uuid.uuid4().hex}
        ).encode()

    def _beat(self, name: str, owner: str, stop: threading.Event) -> None:
        interval = self.heartbeat_s if self.heartbeat_s is not None else self.stale_after_s / 4
        assert 0 < interval < self.stale_after_s, "a heartbeat must come before the lock goes stale"
        while not stop.wait(interval):
            try:
                if not self.refresh(name, owner):
                    logger.warning("The lock %s is no longer ours; another process may take over", name)
                    return
            except Exception:
                # A bucket that can't be reached this time; the next beat tries again.
                logger.exception("Couldn't refresh the lock %s", name)

    def refresh(self, name: str, owner: str, attempts: int = 3) -> bool:
        """Rewrite a held lock so it is young again. False only when it is no longer ours."""
        assert attempts >= 1, "a refresh tries at least once"
        for _ in range(attempts):
            info = self.folder.stat(name)
            if info is None or not self._ours(name, owner):
                return False
            body = self._body(owner)
            if self.folder.replace_if(name, body, info.token):
                return True
            # A retried write whose first attempt had in fact succeeded is
            # refused by its own new token. Its unique bytes say it was ours.
            if self.folder.read(name) == body:
                return True
            # Refused, yet the lock may still be ours: S3 answers 409 when
            # another conditional write to the object, such as a waiter's
            # create, was under way. The next look says which it is.
            self.sleep(self.poll_s)
        logger.warning("The lock %s is still ours but couldn't be refreshed; the next beat tries again", name)
        return True

    def acquire(self, name: str, done: Callable[[], bool]) -> str | None:
        """The owner token once the lock is held, or None when `done()` became true while waiting."""
        owner = _owner_id()
        body = self._body(owner)
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
