"""A stand-in S3 store: the part of boto3's client the code uses, and an HTTP server for GDAL.

`FakeS3` holds objects in memory and answers the way the spike on Fly.io saw
Tigris answer (Decision 0018):

- `IfNoneMatch="*"` on a put is refused with 412 when the object exists;
- `IfMatch=<etag>` on a put or a delete is refused with 412 when the
  object's ETag is another, and with 404 when there is no object;
- an object's ETag is the quoted MD5 of its bytes, as S3 gives a single-part
  upload, so two writes of the same bytes share an ETag;
- `LastModified` has whole seconds, as the HTTP header boto3 reads it from;
- a read straight after a write sees the write.

Errors are botocore's own `ClientError`, shaped as boto3 raises them.
`FakeS3.client()` hands out a client for `S3Folder`, `S3Storage` and the
mirror. `serve_for_gdal()` answers GDAL's `/vsis3/` range requests from the
same objects, through the endpoint and credentials the application is given,
so a test can follow an `s3://` path from upload to a rendered tile.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.server
import io
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from botocore.exceptions import ClientError


@dataclass
class StoredObject:
    data: bytes
    etag: str
    modified: datetime
    content_type: str | None


def etag_of(data: bytes) -> str:
    return f'"{hashlib.md5(data, usedforsecurity=False).hexdigest()}"'


def client_error(operation: str, status: int, code: str) -> ClientError:
    """What boto3 raises for an error answer. A HEAD has no body, so its code is the status."""
    response: Any = {
        "Error": {"Code": code, "Message": code},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(response, operation)


@dataclass
class FakeS3:
    objects: dict[tuple[str, str], StoredObject] = field(default_factory=dict)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    # S3 gives LastModified in whole seconds. A test of sub-second timing can ask for more.
    whole_seconds: bool = True
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Every call, as (method, object name), for tests that count requests.
    calls: list[tuple[str, str]] = field(default_factory=list)
    # Objects per page of a listing, so paging is exercised.
    page_size: int = 1000

    def client(self) -> FakeClient:
        return FakeClient(self)

    def data(self, bucket: str, name: str) -> bytes:
        return self.objects[(bucket, name)].data

    def names(self, bucket: str) -> list[str]:
        with self.lock:
            return sorted(name for (b, name) in self.objects if b == bucket)

    def put(
        self,
        bucket: str,
        name: str,
        data: bytes,
        content_type: str | None = None,
        if_none_match: str | None = None,
        if_match: str | None = None,
    ) -> StoredObject:
        with self.lock:
            self.calls.append(("put", name))
            current = self.objects.get((bucket, name))
            if if_none_match is not None:
                assert if_none_match == "*", "S3 takes only * for If-None-Match on a put"
                if current is not None:
                    raise client_error("PutObject", 412, "PreconditionFailed")
            if if_match is not None:
                if current is None:
                    raise client_error("PutObject", 404, "NoSuchKey")
                if current.etag != if_match:
                    raise client_error("PutObject", 412, "PreconditionFailed")
            modified = self.now()
            if self.whole_seconds:
                modified = modified.replace(microsecond=0)
            stored = StoredObject(data, etag_of(data), modified, content_type)
            self.objects[(bucket, name)] = stored
            return stored

    def get(self, bucket: str, name: str, method: str = "get") -> StoredObject | None:
        with self.lock:
            self.calls.append((method, name))
            return self.objects.get((bucket, name))

    def remove(self, bucket: str, name: str, if_match: str | None) -> None:
        with self.lock:
            self.calls.append(("delete", name))
            current = self.objects.get((bucket, name))
            if if_match is not None:
                if current is None:
                    raise client_error("DeleteObject", 404, "NoSuchKey")
                if current.etag != if_match:
                    raise client_error("DeleteObject", 412, "PreconditionFailed")
            # Deleting what isn't there succeeds.
            self.objects.pop((bucket, name), None)


def _read(body: bytes | BinaryIO) -> bytes:
    return bytes(body) if isinstance(body, bytes | bytearray) else body.read()


class FakeClient:
    """The boto3 S3 client calls the application makes, with boto3's names and answers."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes | BinaryIO,
        ContentType: str | None = None,
        IfNoneMatch: str | None = None,
        IfMatch: str | None = None,
    ) -> dict[str, Any]:
        stored = self.s3.put(Bucket, Key, _read(Body), ContentType, IfNoneMatch, IfMatch)
        return {"ETag": stored.etag}

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None:
        extra = ExtraArgs or {}
        assert set(extra) <= {"ContentType"}, f"unexpected upload arguments {extra}"
        self.s3.put(Bucket, Key, Path(Filename).read_bytes(), extra.get("ContentType"))

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        stored = self.s3.get(Bucket, Key)
        if stored is None:
            raise client_error("GetObject", 404, "NoSuchKey")
        return {"Body": io.BytesIO(stored.data), "ETag": stored.etag, "ContentLength": len(stored.data)}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        stored = self.s3.get(Bucket, Key, "head")
        if stored is None:
            raise client_error("HeadObject", 404, "404")
        return {
            "ContentLength": len(stored.data),
            "ETag": stored.etag,
            "LastModified": stored.modified,
            "ContentType": stored.content_type,
        }

    def delete_object(self, *, Bucket: str, Key: str, IfMatch: str | None = None) -> dict[str, Any]:
        self.s3.remove(Bucket, Key, IfMatch)
        return {}

    def list_objects_v2(
        self,
        *,
        Bucket: str,
        Prefix: str = "",
        Delimiter: str | None = None,
        ContinuationToken: str | None = None,
    ) -> dict[str, Any]:
        keys = []
        for name in self.s3.names(Bucket):
            if not name.startswith(Prefix):
                continue
            if Delimiter and Delimiter in name[len(Prefix) :]:
                continue
            keys.append(name)
        start = int(ContinuationToken or 0)
        page = keys[start : start + self.s3.page_size]
        answer: dict[str, Any] = {"Contents": [{"Key": key} for key in page]} if page else {}
        more = start + len(page) < len(keys)
        answer["IsTruncated"] = more
        if more:
            answer["NextContinuationToken"] = str(start + len(page))
        return answer


# --------------------------------------------------------------------------
# GDAL's side: /vsis3/ range requests, path-style
# --------------------------------------------------------------------------


def _handler(s3: FakeS3) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self, with_body: bool) -> None:
            # Path-style, as AWS_VIRTUAL_HOSTING=FALSE asks for: /bucket/key.
            bucket, _, name = self.path.lstrip("/").partition("/")
            # GDAL signs every request with the credentials it was given.
            assert self.headers.get("Authorization", "").startswith("AWS4-HMAC-SHA256"), "unsigned"
            stored = s3.objects.get((bucket, name.partition("?")[0]))
            if stored is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = stored.data
            asked = self.headers.get("Range")
            if asked:
                first, _, last = asked.removeprefix("bytes=").partition("-")
                start, end = int(first), min(int(last or len(data) - 1), len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                data = data[start : end + 1]
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("ETag", stored.etag)
            self.send_header("Last-Modified", format_datetime(stored.modified, usegmt=True))
            self.end_headers()
            if with_body:
                self.wfile.write(data)

        def do_GET(self) -> None:
            self._answer(True)

        def do_HEAD(self) -> None:
            self._answer(False)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


class QuickServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # HTTPServer looks up the host's fully qualified name here, which can take half a minute.
        http.server.socketserver.TCPServer.server_bind(self)  # type: ignore[attr-defined]
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


# What Fly sets on an app with a Tigris bucket attached, with made-up credentials.
FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "tid_test",
    "AWS_SECRET_ACCESS_KEY": "tsec_test",
    "AWS_REGION": "auto",
}


@contextlib.contextmanager
def serve_for_gdal(s3: FakeS3, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve `s3`'s objects on a local endpoint, set as Fly would set it, for the rest of the block.

    Only the platform's variables are set here. The S3 folders made inside
    the block turn them into GDAL's options themselves.
    """
    server = QuickServer(("127.0.0.1", 0), _handler(s3))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    for name, value in {**FAKE_CREDENTIALS, "AWS_ENDPOINT_URL_S3": endpoint}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()
