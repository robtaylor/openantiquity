from __future__ import annotations

import gzip
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from fieldclub.ingest.adapters.common import AdapterError
from fieldclub.ingest.adapters.download import download
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
    later = NoWait(now=lambda: datetime.now(UTC) + timedelta(days=2))
    again = download(HUB, tmp_path / "sm.gpkg", client=client(), polite=later, max_age=timedelta(hours=20))
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
