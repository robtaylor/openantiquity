from __future__ import annotations

import errno
import gzip
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Any

import httpx
import pytest
import respx

from fieldclub.ingest.adapters.common import AdapterError
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.errors import DiskFullError
from tests.ingest.adapters.support import NoWait, fixture_bytes

HUB = "https://hub.example/api/download/v1/items/abc/geoPackage"
FILE = "https://cdn.example/exports/abc-123.gpkg"
BODY = fixture_bytes("scheduled_monuments.gpkg")
ETAG = '"0x8DF3F24BA17C343"'


class Dropping(httpx.SyncByteStream):
    """A body that sends its first `cut` bytes and then loses the connection."""

    def __init__(self, data: bytes, cut: int) -> None:
        self.data = data
        self.cut = cut

    def __iter__(self) -> Iterator[bytes]:
        yield self.data[: self.cut]
        raise httpx.ReadError("connection reset by peer")


def redirect() -> httpx.Response:
    return httpx.Response(302, headers={"Location": FILE})


def whole(etag: str = ETAG) -> httpx.Response:
    return httpx.Response(200, content=BODY, headers={"ETag": etag, "Content-Length": str(len(BODY))})


def client() -> httpx.Client:
    return httpx.Client(follow_redirects=True)


def aged(days: int) -> NoWait:
    """A `NoWait` whose clock is `days` ahead, so a copy made now has had time to grow old."""
    return NoWait(now=lambda: datetime.now(UTC) + timedelta(days=days))


@respx.mock
def test_downloads_through_the_hub_redirect(tmp_path: Path) -> None:
    respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(return_value=whole())
    result = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait())

    assert result.path.read_bytes() == BODY
    assert not result.from_cache
    assert result.size == len(BODY)
    assert not (tmp_path / "sm.gpkg.part").exists()
    assert (tmp_path / "sm.gpkg.json").is_file()


@respx.mock
def test_a_young_copy_is_reused_without_asking(tmp_path: Path) -> None:
    hub = respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(return_value=whole())
    polite = NoWait()
    download(HUB, tmp_path / "sm.gpkg", client=client(), polite=polite)
    again = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=polite, max_age=timedelta(hours=1))
    assert again.from_cache
    assert hub.call_count == 1


@respx.mock
def test_an_old_copy_is_fetched_again(tmp_path: Path) -> None:
    hub = respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(return_value=whole())
    download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    again = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=aged(2), max_age=timedelta(hours=20))
    assert not again.from_cache
    assert hub.call_count == 2


@respx.mock
def test_a_dropped_connection_resumes_where_it_stopped(tmp_path: Path) -> None:
    cut = 50_000
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                stream=Dropping(BODY, cut),
                headers={"ETag": ETAG, "Content-Length": str(len(BODY))},
            )
        assert request.headers["Range"] == f"bytes={cut}-"
        assert request.headers["If-Range"] == ETAG
        return httpx.Response(
            206,
            content=BODY[cut:],
            headers={"ETag": ETAG, "Content-Range": f"bytes {cut}-{len(BODY) - 1}/{len(BODY)}"},
        )

    respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(side_effect=serve)
    polite = NoWait()
    result = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=polite)

    assert result.path.read_bytes() == BODY
    assert len(requests) == 2
    assert polite.slept == [polite.backoff_s]


@respx.mock
def test_a_file_that_changed_meanwhile_starts_again(tmp_path: Path) -> None:
    changed = BODY[::-1]

    def serve(request: httpx.Request) -> httpx.Response:
        if "Range" not in request.headers:
            return httpx.Response(
                200, stream=Dropping(BODY, 1000), headers={"ETag": ETAG, "Content-Length": str(len(BODY))}
            )
        # If-Range didn't match, so the server sends the new file whole.
        return httpx.Response(200, content=changed, headers={"ETag": '"new"'})

    respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(side_effect=serve)
    result = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    assert result.path.read_bytes() == changed


@respx.mock
def test_waits_while_the_hub_prepares_an_export(tmp_path: Path) -> None:
    respx.get(HUB).mock(
        side_effect=[
            httpx.Response(202, json={"status": "ExportingData", "progressInPercent": 0}),
            httpx.Response(202, json={"status": "ExportingData", "progressInPercent": 60}),
            redirect(),
        ]
    )
    respx.get(FILE).mock(return_value=whole())
    polite = NoWait()
    result = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=polite)
    assert result.path.read_bytes() == BODY
    assert polite.slept == [10.0, 20.0]


@respx.mock
def test_a_long_export_wait_leaves_the_error_retries_alone(tmp_path: Path) -> None:
    exporting = httpx.Response(202, json={"status": "ExportingData"})
    respx.get(HUB).mock(side_effect=[exporting] * 5 + [httpx.Response(502), redirect()])
    respx.get(FILE).mock(return_value=whole())
    polite = NoWait(backoff_s=2)
    result = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=polite)
    assert result.path.read_bytes() == BODY
    # Five export polls with growing gaps, then the first retry's backoff.
    assert polite.slept == [10.0, 20.0, 40.0, 80.0, 120.0, 2.0]


@respx.mock
def test_gives_up_on_an_export_that_never_finishes(tmp_path: Path) -> None:
    respx.get(HUB).mock(return_value=httpx.Response(202, json={"status": "ExportingData"}))
    with pytest.raises(AdapterError, match="still preparing the export"):
        download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait(), max_wait_s=100)


@respx.mock
def test_a_short_body_is_never_renamed_into_place(tmp_path: Path) -> None:
    respx.get(HUB).mock(return_value=redirect())
    respx.get(FILE).mock(
        return_value=httpx.Response(
            200, stream=Dropping(BODY, 10), headers={"Content-Length": str(len(BODY))}
        )
    )
    # No validator, so nothing can be resumed and every attempt starts again.
    with pytest.raises(AdapterError, match="kept failing"):
        download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait(retries=2))
    assert not (tmp_path / "sm.gpkg").exists()


@respx.mock
def test_a_refusal_is_an_error(tmp_path: Path) -> None:
    respx.get(HUB).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(AdapterError, match="answered 403"):
        download(HUB, tmp_path / "sm.gpkg", client=client(), polite=NoWait())


@respx.mock
def test_a_compressed_body_is_saved_decompressed(tmp_path: Path) -> None:
    """ArcGIS sends GeoJSON gzipped, with the compressed length, which can't be the file's length."""
    packed = gzip.compress(BODY)
    respx.get(FILE).mock(
        return_value=httpx.Response(
            200,
            content=packed,
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(packed)), "ETag": ETAG},
        )
    )
    result = download(FILE, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    assert result.path.read_bytes() == BODY
    assert result.size == len(BODY)


@respx.mock
def test_an_old_copy_makes_way_before_the_new_one_is_asked_for(tmp_path: Path) -> None:
    """A refresh needs room for one copy of a file, not two."""
    dest = tmp_path / "sm.gpkg"
    newer = BODY[::-1]
    there_when_asked: list[bool] = []

    def serve(request: httpx.Request) -> httpx.Response:
        there_when_asked.append(dest.exists() or (tmp_path / "sm.gpkg.json").exists())
        return whole() if len(there_when_asked) == 1 else httpx.Response(200, content=newer)

    respx.get(FILE).mock(side_effect=serve)
    download(FILE, dest, client=client(), polite=NoWait())
    download(FILE, dest, client=client(), polite=aged(2), max_age=timedelta(hours=20))

    assert there_when_asked == [False, False]
    assert dest.read_bytes() == newer


@respx.mock
def test_an_old_copy_is_gone_though_the_fetch_then_fails(tmp_path: Path) -> None:
    """Nothing reads a copy past its `max_age`: a failed fetch raises, and no caller falls back to it."""
    dest = tmp_path / "sm.gpkg"
    respx.get(FILE).mock(side_effect=[whole(), httpx.Response(403, text="Forbidden")])
    download(FILE, dest, client=client(), polite=NoWait())
    with pytest.raises(AdapterError, match="answered 403"):
        download(FILE, dest, client=client(), polite=aged(2), max_age=timedelta(hours=20))
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_an_old_copy_goes_and_a_partial_file_beside_it_is_resumed(tmp_path: Path) -> None:
    """What the hourly machine's volume held on 2026-11-24: last week's file and most of this week's."""
    dest = tmp_path / "sm.gpkg"
    part = tmp_path / "sm.gpkg.part"
    cut = 50_000
    week_ago = datetime.now(UTC) - timedelta(days=8)
    dest.write_bytes(b"last week's")
    (tmp_path / "sm.gpkg.json").write_text(json.dumps({"fetched_at": week_ago.isoformat()}), encoding="utf-8")
    part.write_bytes(BODY[:cut])
    (tmp_path / "sm.gpkg.part.json").write_text(
        json.dumps({"validator": ETAG, "total": len(BODY)}), encoding="utf-8"
    )

    def rest(request: httpx.Request) -> httpx.Response:
        assert not dest.exists()
        assert request.headers["Range"] == f"bytes={cut}-"
        assert request.headers["If-Range"] == ETAG
        return httpx.Response(
            206,
            content=BODY[cut:],
            headers={"ETag": ETAG, "Content-Range": f"bytes {cut}-{len(BODY) - 1}/{len(BODY)}"},
        )

    respx.get(FILE).mock(side_effect=rest)
    result = download(FILE, dest, client=client(), polite=NoWait(), max_age=timedelta(days=7))
    assert result.path.read_bytes() == BODY
    assert not part.exists()


class FailingAfter:
    """A file that takes `room` bytes and then fails every write with `error`: ENOSPC is a full disk."""

    def __init__(self, real: IO[bytes], room: int, error: int) -> None:
        self.real = real
        self.room = room
        self.error = error

    def __enter__(self) -> FailingAfter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.real.close()

    def write(self, data: bytes) -> int:
        fits = data[: self.room]
        self.room -= self.real.write(fits)
        if len(fits) < len(data):
            raise OSError(self.error, os.strerror(self.error), self.real.name)
        return len(data)


def fail_writes(monkeypatch: pytest.MonkeyPatch, *, after: int, error: int) -> None:
    """Open every `.part` file as a `FailingAfter`."""
    really_open = Path.open

    def opened(self: Path, *args: Any, **kwargs: Any) -> Any:
        real = really_open(self, *args, **kwargs)
        return FailingAfter(real, after, error) if self.name.endswith(".part") else real

    monkeypatch.setattr(Path, "open", opened)


@respx.mock
def test_a_full_disk_removes_the_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial file left on a full disk leaves no room for any other source's download."""
    room = 30_000
    fail_writes(monkeypatch, after=room, error=errno.ENOSPC)
    respx.get(FILE).mock(return_value=whole())
    with pytest.raises(DiskFullError, match=rf"sm\.gpkg.*{room} bytes of {len(BODY)}"):
        download(FILE, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_a_disk_that_fills_at_the_last_note_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole file without its note would be thrown away and fetched again by the next run."""
    really_write = Path.write_text

    def write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name == "sm.gpkg.json":
            self.touch()
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), str(self))
        return really_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)
    respx.get(FILE).mock(return_value=whole())
    with pytest.raises(DiskFullError, match=rf"sm\.gpkg.*{len(BODY)} bytes of {len(BODY)}"):
        download(FILE, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_another_fault_in_writing_keeps_the_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a full disk costs the bytes already fetched: after any other fault they can be resumed."""
    kept = 30_000
    fail_writes(monkeypatch, after=kept, error=errno.EIO)
    respx.get(FILE).mock(return_value=whole())
    with pytest.raises(OSError, match=r"sm\.gpkg\.part") as raised:
        download(FILE, tmp_path / "sm.gpkg", client=client(), polite=NoWait())
    assert raised.value.errno == errno.EIO
    assert (tmp_path / "sm.gpkg.part").stat().st_size == kept
