"""`infra/jobs/cache_lifecycle.py` gives the tile cache bucket its expiry rule.

The script is run for real, with boto3, against a stand-in S3 endpoint on
127.0.0.1 that keeps one lifecycle configuration per bucket and records each
request.
"""

from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

import pytest

from tests.fake_s3 import QuickServer

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "infra" / "jobs" / "cache_lifecycle.py"
BUCKET = "openantiquity-cache"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


@dataclass
class Store:
    lifecycle: dict[str, bytes] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)


def _handler(store: Store) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _answer(self, status: int, body: bytes = b"") -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _bucket(self) -> str | None:
            path, _, query = self.path.partition("?")
            store.requests.append((self.command, self.path))
            return path.strip("/") if query.startswith("lifecycle") else None

        def do_PUT(self) -> None:
            bucket = self._bucket()
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if bucket is None:
                self._answer(400)
                return
            store.lifecycle[bucket] = body
            self._answer(200)

        def do_GET(self) -> None:
            bucket = self._bucket()
            if bucket is None:
                self._answer(400)
            elif bucket in store.lifecycle:
                self._answer(200, store.lifecycle[bucket])
            else:
                code = b"<Error><Code>NoSuchLifecycleConfiguration</Code><Message>none</Message></Error>"
                self._answer(404, code)

    return Handler


@pytest.fixture
def store() -> Iterator[tuple[Store, str]]:
    held = Store()
    server = QuickServer(("127.0.0.1", 0), _handler(held))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield held, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def run(endpoint: str, *args: str, prefix: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("FIELDCLUB_", "AWS_", "FLY_")) and name != "DATABASE_URL"
    }
    env |= {
        "FIELDCLUB_ENV_FILE": "",
        "FIELDCLUB_STORAGE_BACKEND": "s3",
        "FIELDCLUB_S3_BUCKET": BUCKET,
        "FIELDCLUB_S3_PREFIX": prefix,
        "AWS_ACCESS_KEY_ID": "tid_test",
        "AWS_SECRET_ACCESS_KEY": "tsec_test",
        "AWS_ENDPOINT_URL_S3": endpoint,
        "AWS_REGION": "auto",
    }
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=120, check=False)


def rules(store: Store) -> list[dict[str, str]]:
    root = ElementTree.fromstring(store.lifecycle[BUCKET])
    return [
        {
            "id": rule.findtext(f"{NS}ID", ""),
            "status": rule.findtext(f"{NS}Status", ""),
            "prefix": rule.findtext(f"{NS}Filter/{NS}Prefix", ""),
            "days": rule.findtext(f"{NS}Expiration/{NS}Days", ""),
        }
        for rule in root.iter(f"{NS}Rule")
    ]


def test_tiles_expire_after_180_days(store: tuple[Store, str]) -> None:
    held, endpoint = store

    result = run(endpoint)

    assert result.returncode == 0, result.stderr
    assert rules(held) == [{"id": "tiles-180-days", "status": "Enabled", "prefix": "tiles/", "days": "180"}]
    assert BUCKET in result.stdout


def test_the_rule_follows_the_storage_prefix(store: tuple[Store, str]) -> None:
    held, endpoint = store

    assert run(endpoint, prefix="/staging/").returncode == 0

    assert [rule["prefix"] for rule in rules(held)] == ["staging/tiles/"]


def test_running_it_twice_leaves_the_same_rules(store: tuple[Store, str]) -> None:
    held, endpoint = store
    assert run(endpoint).returncode == 0
    first = held.lifecycle[BUCKET]

    assert run(endpoint).returncode == 0

    assert held.lifecycle[BUCKET] == first


def test_check_reads_without_writing_and_fails_when_the_rules_are_missing(store: tuple[Store, str]) -> None:
    held, endpoint = store

    missing = run(endpoint, "--check")

    assert missing.returncode == 1
    assert all(method == "GET" for method, _ in held.requests)

    assert run(endpoint).returncode == 0
    assert run(endpoint, "--check").returncode == 0


def test_the_credentials_are_never_printed(store: tuple[Store, str]) -> None:
    _, endpoint = store

    result = run(endpoint)

    assert "tsec_test" not in result.stdout + result.stderr
