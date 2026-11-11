"""Blob storage: local disk in development, a bucket with the S3 interface in production.

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
from typing import Any, Protocol, runtime_checkable

from fieldclub.config import get_settings
from fieldclub.errors import AppError, NotFoundError


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


class S3Storage:
    """Objects in a bucket with the S3 interface, such as Tigris, under an optional prefix.

    A put is one request, so an object is either whole or absent. `boto3` is
    imported on first use, so development and the tests never load it.
    """

    def __init__(self, bucket: str, prefix: str = "", *, client: Any = None) -> None:
        assert bucket, "a bucket name is required"
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    def _name(self, key: str) -> str:
        check_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = s3_client()
        return self._client

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=self._name(key),
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    def get(self, key: str) -> bytes:
        data = s3_get(self.client, self.bucket_name, self._name(key))
        if data is None:
            raise StorageNotFoundError(f"Nothing is stored under {key!r}.")
        return data

    def exists(self, key: str) -> bool:
        return s3_head(self.client, self.bucket_name, self._name(key)) is not None

    def delete(self, key: str) -> None:
        # Removing a key that isn't there succeeds in S3.
        self.client.delete_object(Bucket=self.bucket_name, Key=self._name(key))

    def url(self, key: str) -> str:
        endpoint = os.environ.get("AWS_ENDPOINT_URL_S3", "https://s3.amazonaws.com").rstrip("/")
        return f"{endpoint}/{self.bucket_name}/{self._name(key)}"


# --------------------------------------------------------------------------
# The S3 client, shared by every bucket in the process
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def s3_client() -> Any:
    """One boto3 client for the process. Clients are safe to share between threads.

    Credentials come from `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`,
    which boto3 reads itself, and the store from `AWS_ENDPOINT_URL_S3`. Fly
    sets all three when a Tigris bucket is attached; the settings refuse to
    start without them (`config.S3_ENVIRONMENT`).
    """
    from boto3.session import Session
    from botocore.config import Config

    return Session().client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL_S3") or None,
        # Tigris takes "auto". Fly's own documentation gives no region.
        region_name=os.environ.get("AWS_REGION") or "auto",
        config=Config(
            retries={"mode": "standard", "max_attempts": 4},
            connect_timeout=10,
            read_timeout=60,
            # Tile renders, fetches and uploads share it.
            max_pool_connections=32,
        ),
    )


def s3_refusal(exc: BaseException) -> int | None:
    """The HTTP status of an S3 error answer, such as 404 or 412, or None for anything else."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if isinstance(status, int):
        return status
    # A HEAD carries no body, so botocore puts the status in the code.
    code = str(response.get("Error", {}).get("Code", ""))
    return int(code) if code.isdigit() else None


def s3_get(client: Any, bucket: str, name: str) -> bytes | None:
    """The object's bytes, or None when there is none.

    One request: a miss comes back as an error, so there's no metadata fetch first.
    """
    try:
        answer = client.get_object(Bucket=bucket, Key=name)
    except Exception as exc:
        if s3_refusal(exc) == 404:
            return None
        raise
    with answer["Body"] as body:
        return bytes(body.read())


def s3_head(client: Any, bucket: str, name: str) -> dict[str, Any] | None:
    """The object's metadata, or None when there is none."""
    try:
        return client.head_object(Bucket=bucket, Key=name)
    except Exception as exc:
        if s3_refusal(exc) == 404:
            return None
        raise


@lru_cache(maxsize=16)
def get_storage(namespace: str) -> Storage:
    """The configured storage for one kind of data, such as `tiles` or `media`.

    Locally that is `var/<namespace>/`. In a bucket it is the `<namespace>/`
    prefix under `FIELDCLUB_S3_PREFIX`, in the namespace's own bucket when
    `FIELDCLUB_S3_NAMESPACE_BUCKETS` names one and in `FIELDCLUB_S3_BUCKET`
    otherwise.
    """
    check_key(namespace)
    settings = get_settings()
    if settings.storage_backend == "s3":
        assert settings.s3_bucket, "Settings guarantee a bucket when the backend is s3"
        bucket = settings.s3_namespace_buckets.get(namespace, settings.s3_bucket)
        prefix = "/".join(part for part in (settings.s3_prefix.strip("/"), namespace) if part)
        return S3Storage(bucket, prefix)
    return LocalStorage(settings.var_dir / namespace)
