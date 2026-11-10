"""A fake Cloud Storage: the part of the Python client the terrain service uses, and an HTTP server for GDAL.

`FakeGcs` holds objects in memory with generations and creation times, and
honours `if_generation_match` the way the real service does, including 0 for
"only if absent". `FakeGcs.client()` hands out a client for `GcsFolder`,
`GcsStorage` and the mirror. `serve_for_gdal()` answers GDAL's `/vsigs/`
range requests from the same objects, so a test can follow a `gs://` path
from upload to a rendered tile.
"""

from __future__ import annotations

import contextlib
import http.server
import itertools
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed


@dataclass
class StoredObject:
    data: bytes
    generation: int
    created: datetime
    content_type: str | None


@dataclass
class FakeGcs:
    objects: dict[tuple[str, str], StoredObject] = field(default_factory=dict)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Every call, as (method, object name), for tests that count requests.
    calls: list[tuple[str, str]] = field(default_factory=list)
    # What a write that may not replace an object gets when one is there. A
    # writer that may create objects but not replace them can be refused
    # outright (`Forbidden`) instead.
    refusal: type[Exception] = PreconditionFailed
    _generations: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def client(self) -> FakeClient:
        return FakeClient(self)

    def data(self, bucket: str, name: str) -> bytes:
        return self.objects[(bucket, name)].data

    def names(self, bucket: str) -> list[str]:
        with self.lock:
            return sorted(name for (b, name) in self.objects if b == bucket)

    def _record(self, method: str, name: str) -> None:
        self.calls.append((method, name))

    def put(
        self, bucket: str, name: str, data: bytes, content_type: str | None, if_generation_match: int | None
    ) -> StoredObject:
        with self.lock:
            self._record("put", name)
            current = self.objects.get((bucket, name))
            if if_generation_match is not None:
                live = current.generation if current else 0
                if live != if_generation_match:
                    refusal = self.refusal if if_generation_match == 0 else PreconditionFailed
                    raise refusal(f"{name}: generation {live}, not {if_generation_match}")
            stored = StoredObject(data, next(self._generations), self.now(), content_type)
            self.objects[(bucket, name)] = stored
            return stored

    def get(self, bucket: str, name: str) -> StoredObject | None:
        with self.lock:
            self._record("get", name)
            return self.objects.get((bucket, name))

    def remove(self, bucket: str, name: str, if_generation_match: int | None) -> None:
        with self.lock:
            self._record("delete", name)
            current = self.objects.get((bucket, name))
            if current is None:
                raise NotFound(name)
            if if_generation_match is not None and current.generation != if_generation_match:
                raise PreconditionFailed(f"{name}: generation {current.generation}")
            del self.objects[(bucket, name)]


class FakeClient:
    def __init__(self, gcs: FakeGcs) -> None:
        self.gcs = gcs

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(self.gcs, name)


class FakeBucket:
    def __init__(self, gcs: FakeGcs, name: str) -> None:
        self.gcs = gcs
        self.name = name

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self.gcs, self.name, name)

    def get_blob(self, name: str) -> FakeBlob | None:
        stored = self.gcs.get(self.name, name)
        if stored is None:
            return None
        blob = FakeBlob(self.gcs, self.name, name)
        blob._load(stored)
        return blob

    def list_blobs(self, prefix: str = "", delimiter: str | None = None) -> list[SimpleNamespace]:
        found = []
        for name in self.gcs.names(self.name):
            if not name.startswith(prefix):
                continue
            if delimiter and delimiter in name[len(prefix) :]:
                continue
            found.append(SimpleNamespace(name=name))
        return found


class FakeBlob:
    def __init__(self, gcs: FakeGcs, bucket: str, name: str) -> None:
        self.gcs = gcs
        self.bucket_name = bucket
        self.name = name
        self.size: int | None = None
        self.generation: int | None = None
        self.time_created: datetime | None = None

    def _load(self, stored: StoredObject) -> None:
        self.size = len(stored.data)
        self.generation = stored.generation
        self.time_created = stored.created

    def exists(self) -> bool:
        return self.gcs.get(self.bucket_name, self.name) is not None

    def upload_from_string(
        self,
        data: bytes | str,
        content_type: str = "text/plain",
        if_generation_match: int | None = None,
        **_: Any,
    ) -> None:
        raw = data.encode() if isinstance(data, str) else bytes(data)
        self._load(self.gcs.put(self.bucket_name, self.name, raw, content_type, if_generation_match))

    def upload_from_filename(
        self,
        filename: str,
        content_type: str | None = None,
        if_generation_match: int | None = None,
        checksum: str | None = "auto",
        **_: Any,
    ) -> None:
        data = Path(filename).read_bytes()
        self._load(self.gcs.put(self.bucket_name, self.name, data, content_type, if_generation_match))

    def download_as_bytes(self, **_: Any) -> bytes:
        stored = self.gcs.get(self.bucket_name, self.name)
        if stored is None:
            raise NotFound(self.name)
        return stored.data

    def delete(self, if_generation_match: int | None = None, **_: Any) -> None:
        self.gcs.remove(self.bucket_name, self.name, if_generation_match)


# --------------------------------------------------------------------------
# GDAL's side: /vsigs/ range requests
# --------------------------------------------------------------------------


def _handler(gcs: FakeGcs) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self, with_body: bool) -> None:
            bucket, _, name = self.path.lstrip("/").partition("/")
            stored = gcs.objects.get((bucket, name.partition("?")[0]))
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


class _QuickServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # HTTPServer looks up the host's fully qualified name here, which can take half a minute.
        http.server.socketserver.TCPServer.server_bind(self)  # type: ignore[attr-defined]
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@contextlib.contextmanager
def serve_for_gdal(gcs: FakeGcs, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point GDAL's `/vsigs/` at a local server holding `gcs`'s objects, for the rest of the block."""
    server = _QuickServer(("127.0.0.1", 0), _handler(gcs))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/"
    # Read by GDAL from the environment when a /vsigs/ file is opened, in any thread.
    monkeypatch.setenv("CPL_GS_ENDPOINT", endpoint)
    monkeypatch.setenv("GS_NO_SIGN_REQUEST", "YES")
    monkeypatch.setenv("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()
