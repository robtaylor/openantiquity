"""Blob storage: local disk in development, a Cloud Storage bucket in production.

The tile caches and uploads both go through `Storage`. Keys are slash-separated
paths such as `tiles/composite/14/8107/5448.png`.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from fieldclub.config import get_settings
from fieldclub.errors import AppError, NotFoundError

if TYPE_CHECKING:
    from google.cloud.storage import Bucket


class StorageError(AppError):
    code = "storage_error"
    message = "Stored data could not be read or written."


class StorageKeyError(StorageError):
    code = "storage_key_invalid"
    message = "That isn't a valid storage key."


class StorageNotFoundError(NotFoundError):
    code = "storage_not_found"
    message = "Nothing is stored under that key."


_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def check_key(key: str) -> str:
    """Keys are relative paths of plain segments. Anything else is refused.

    That rules out `..`, absolute paths, backslashes and empty segments, so a
    key built from user input can't escape the storage root.
    """
    segments = key.split("/") if key else []
    # fullmatch, because `$` also matches just before a trailing newline.
    if not segments or len(key) > 512 or not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    return key


@runtime_checkable
class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        """Store `data` under `key`, replacing whatever was there."""
        ...

    def get(self, key: str) -> bytes:
        """The bytes under `key`. Raises `StorageNotFoundError` when there are none."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Remove `key`. Removing a key that isn't there is not an error."""
        ...

    def url(self, key: str) -> str:
        """Where the object lives: a `file://` URI locally, an `https://` URL in a bucket.

        The bucket URL only works for a browser when the object is public.
        """
        ...


class LocalStorage:
    """Files under a directory. Writes are atomic, so a reader never sees half a file."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = self.root / check_key(key)
        assert path.resolve().is_relative_to(self.root), f"{key!r} escapes the storage root"
        return path

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "wb") as tmp:
                tmp.write(data)
            Path(tmp_name).replace(path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                Path(tmp_name).unlink()
            raise

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            raise StorageNotFoundError(f"Nothing is stored under {key!r}.") from None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path(key).unlink()

    def url(self, key: str) -> str:
        return self._path(key).as_uri()


class GcsStorage:
    """Objects in a Cloud Storage bucket, under an optional prefix.

    `google-cloud-storage` is imported on first use, so development and the
    tests never load it.
    """

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        assert bucket, "a bucket name is required"
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self._client = client
        self._bucket: Bucket | None = None

    def _name(self, key: str) -> str:
        check_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            if self._client is None:
                from google.cloud import storage as gcs

                self._client = gcs.Client()
            self._bucket = self._client.bucket(self.bucket_name)
        assert self._bucket is not None
        return self._bucket

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        blob = self._get_bucket().blob(self._name(key))
        blob.upload_from_string(data, content_type=content_type or "application/octet-stream")

    def get(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        # One request: a miss comes back as NotFound, so there's no metadata fetch first.
        try:
            return self._get_bucket().blob(self._name(key)).download_as_bytes()
        except NotFound:
            raise StorageNotFoundError(f"Nothing is stored under {key!r}.") from None

    def exists(self, key: str) -> bool:
        return bool(self._get_bucket().blob(self._name(key)).exists())

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        with contextlib.suppress(NotFound):
            self._get_bucket().blob(self._name(key)).delete()

    def url(self, key: str) -> str:
        return f"https://storage.googleapis.com/{self.bucket_name}/{self._name(key)}"


@lru_cache(maxsize=16)
def get_storage(namespace: str) -> Storage:
    """The configured storage for one kind of data, such as `tiles` or `media`.

    Locally that is `var/<namespace>/`. In a bucket it is the `<namespace>/`
    prefix under `FIELDCLUB_GCS_PREFIX`.
    """
    check_key(namespace)
    settings = get_settings()
    if settings.storage_backend == "gcs":
        assert settings.gcs_bucket, "Settings guarantee a bucket when the backend is gcs"
        prefix = "/".join(part for part in (settings.gcs_prefix.strip("/"), namespace) if part)
        return GcsStorage(settings.gcs_bucket, prefix)
    return LocalStorage(settings.var_dir / namespace)
