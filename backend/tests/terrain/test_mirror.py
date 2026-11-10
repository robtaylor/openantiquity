"""The mirror: filled on first use, once per tile, and never serving a partial file."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
import rasterio
from google.api_core.exceptions import Forbidden, PreconditionFailed

from fieldclub.config import DefraSftpSettings
from fieldclub.errors import DataIntegrityError
from fieldclub.terrain.blobs import GcsFolder, LocalFolder
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.cog import check_cog
from fieldclub.terrain.errors import CredentialsMissingError, ElevationUnavailableError, SupplyRefusedError
from fieldclub.terrain.mirror import (
    Fetched,
    GcsMirrorStore,
    LocalMirrorStore,
    LocalSourceFetcher,
    Mirror,
    SftpFetcher,
    mirror_store,
)
from fieldclub.terrain.sftp import defra_connector
from tests.terrain.fakes import FakeServer, catalogue_of, local_mirror, small_cog, write_source_tile
from tests.terrain.gcs import FakeGcs


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("sources")
    for name in ("SU16nw", "SU16ne"):
        write_source_tile(folder, name)
    return folder


class SpyFetcher:
    """Hands out a source file slowly and counts how often it was asked."""

    def __init__(self, folder: Path, delay: float = 0.0) -> None:
        self.inner = LocalSourceFetcher(folder)
        self.delay = delay
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        with self.lock:
            self.calls.append(tile.name)
        time.sleep(self.delay)
        return self.inner.fetch(tile, work_dir)


def make_mirror(sources: Path, tmp_path: Path, fetchers: list[Any]) -> Mirror:
    return local_mirror(tmp_path, sources=sources, extra=["SU17sw"], fetchers=fetchers)


def test_a_local_source_tile_is_converted_into_the_mirror(sources: Path, tmp_path: Path) -> None:
    mirror = make_mirror(sources, tmp_path, [LocalSourceFetcher(sources)])
    assert not mirror.has("SU16nw")
    path = mirror.ensure("su16NW")
    assert path is not None
    assert path == str(tmp_path / "cogs" / "SU16nw.tif")
    summary = check_cog(path)
    assert summary.overviews == [2]
    assert summary.compression in {"lerc_zstd", "zstd"}
    with rasterio.open(path) as cog, rasterio.open(sources / "SU16nw_DTM_1m.tif") as source:
        assert cog.transform == source.transform
        assert abs(cog.read(1) - source.read(1)).max() <= 0.0101
    # The source on disk is the developer's and stays where it was.
    assert (sources / "SU16nw_DTM_1m.tif").is_file()
    assert mirror.store.names() == ["SU16nw"]


def test_a_tile_that_is_not_in_the_catalogue_is_empty_without_a_fetch(sources: Path, tmp_path: Path) -> None:
    spy = SpyFetcher(sources)
    mirror = make_mirror(sources, tmp_path, [spy])
    assert mirror.ensure("SV00sw") is None
    assert spy.calls == []


def test_twenty_threads_asking_for_one_missing_tile_cause_one_fetch(sources: Path, tmp_path: Path) -> None:
    spy = SpyFetcher(sources, delay=0.2)
    mirror = make_mirror(sources, tmp_path, [spy])
    barrier = threading.Barrier(20)
    results: list[str | None] = []

    def ask() -> None:
        barrier.wait()
        results.append(mirror.ensure("SU16nw"))

    threads = [threading.Thread(target=ask) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert spy.calls == ["SU16nw"]
    assert results == [str(tmp_path / "cogs" / "SU16nw.tif")] * 20


def test_a_failed_conversion_publishes_nothing_and_the_next_request_tries_again(
    sources: Path, tmp_path: Path
) -> None:
    def broken(src: Path, dst: Path) -> None:
        dst.write_bytes(b"half a file")
        raise OSError("disk full")

    catalogue = catalogue_of(sources.glob("*.tif"))
    store = LocalMirrorStore(tmp_path / "mirror")
    mirror = Mirror(catalogue, store, [LocalSourceFetcher(sources)], tmp_path / "work", convert=broken)
    with pytest.raises(OSError, match="disk full"):
        mirror.ensure("SU16nw")
    assert not mirror.has("SU16nw")
    assert store.names() == []
    assert not list((tmp_path / "work").glob("*.tif"))
    fixed = Mirror(catalogue, store, [LocalSourceFetcher(sources)], tmp_path / "work", convert=small_cog())
    assert fixed.ensure("SU16nw") is not None


def test_a_tile_no_source_can_provide_is_unavailable(sources: Path, tmp_path: Path) -> None:
    mirror = make_mirror(sources, tmp_path, [LocalSourceFetcher(sources)])
    with pytest.raises(ElevationUnavailableError):
        mirror.ensure("SU17sw")


def test_missing_credentials_are_a_clear_error_when_a_fetch_is_needed(sources: Path, tmp_path: Path) -> None:
    no_credentials = DefraSftpSettings(defra_sftp_host=None, defra_sftp_user=None, defra_sftp_password=None)
    fetcher = SftpFetcher(lambda: defra_connector(no_credentials))
    mirror = make_mirror(sources, tmp_path, [LocalSourceFetcher(sources), fetcher])
    # A tile on disk needs no credentials.
    assert mirror.ensure("SU16nw") is not None
    with pytest.raises(CredentialsMissingError) as raised:
        mirror.ensure("SU17sw")
    assert "DEFRA_SFTP_HOST" in raised.value.message
    assert not mirror.has("SU17sw")


def test_a_tile_is_fetched_from_the_bulk_supply_and_the_download_removed(
    sources: Path, tmp_path: Path
) -> None:
    source = sources / "SU16ne_DTM_1m.tif"
    server = FakeServer({SourceTile("SU16ne", 0).remote_path: source.read_bytes()})
    mirror = make_mirror(sources, tmp_path, [SftpFetcher(lambda: server.connect, window=1024 * 1024)])
    path = mirror.ensure("SU16ne")
    assert path is not None
    check_cog(path)
    assert server.connections == 1
    assert list((tmp_path / "work").glob("*.tif*")) == []


def test_mirror_locations() -> None:
    local = mirror_store("/data/mirror")
    assert isinstance(local.folder, LocalFolder)
    assert not local.shared
    assert local.gdal_path("SU16nw") == "/data/mirror/SU16nw.tif"
    bucket = mirror_store("gs://fieldclub-lidar/england/dtm-2022")
    assert isinstance(bucket.folder, GcsFolder)
    assert bucket.shared
    assert bucket.gdal_path("su16nw") == "/vsigs/fieldclub-lidar/england/dtm-2022/SU16nw.tif"
    assert bucket.lock_name("su16nw") == "locks/SU16nw.lock"


def test_a_bucket_mirror_uploads_whole_files_under_its_prefix(tmp_path: Path) -> None:
    gcs = FakeGcs()
    store = GcsMirrorStore("lidar", "england", client=gcs.client())
    assert store.shared
    local = tmp_path / "SU16nw.cog.tif"
    local.write_bytes(b"cog")
    assert not store.exists("SU16nw")
    store.publish(local, "SU16nw")
    assert gcs.names("lidar") == ["england/SU16nw.tif"]
    assert gcs.data("lidar", "england/SU16nw.tif") == b"cog"
    assert store.exists("SU16nw")
    assert store.names() == ["SU16nw"]
    assert not local.exists()


@pytest.mark.parametrize("refusal", [PreconditionFailed, Forbidden])
def test_a_bucket_mirror_never_replaces_a_tile_another_instance_published(
    tmp_path: Path, refusal: type[Exception]
) -> None:
    gcs = FakeGcs(refusal=refusal)
    store = GcsMirrorStore("lidar", "england", client=gcs.client())
    first, second = tmp_path / "first.tif", tmp_path / "second.tif"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    store.publish(first, "SU16nw")
    # The writers may create objects but not replace them, so a second upload must ask not to.
    store.publish(second, "SU16nw")
    assert gcs.names("lidar") == ["england/SU16nw.tif"]
    assert gcs.data("lidar", "england/SU16nw.tif") == b"first"
    assert not second.exists()


def test_a_local_mirror_never_replaces_a_tile_either(tmp_path: Path) -> None:
    store = mirror_store(str(tmp_path / "mirror"))
    first, second = tmp_path / "first.tif", tmp_path / "second.tif"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    store.publish(first, "SU16nw")
    store.publish(second, "SU16nw")
    assert (tmp_path / "mirror" / "SU16nw.tif").read_bytes() == b"first"
    assert not second.exists()
    assert [path.name for path in (tmp_path / "mirror").iterdir()] == ["SU16nw.tif"]


def test_a_refused_upload_of_a_new_tile_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gcs = FakeGcs()

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise Forbidden("no permission")

    monkeypatch.setattr(gcs, "put", refuse)
    store = GcsMirrorStore("lidar", "england", client=gcs.client())
    local = tmp_path / "SU16nw.cog.tif"
    local.write_bytes(b"cog")
    with pytest.raises(Forbidden):
        store.publish(local, "SU16nw")


class RefusingConnector:
    """A bulk supply that refuses every login, counting the attempts."""

    def __init__(self) -> None:
        self.attempts = 0

    def connect(self) -> Any:
        self.attempts += 1
        raise SupplyRefusedError("Defra's bulk supply rejected the user name or password.")


def test_a_refused_login_pauses_every_later_fetch(sources: Path, tmp_path: Path) -> None:
    supply = RefusingConnector()
    now = [1000.0]
    fetcher = SftpFetcher(lambda: supply.connect, refusal_pause=600, clock=lambda: now[0])
    tile = SourceTile("SU17sw", 1_000)
    for _ in range(3):
        with pytest.raises(SupplyRefusedError, match="user name or password"):
            fetcher.fetch(tile, tmp_path)
    assert supply.attempts == 1
    now[0] += 601
    with pytest.raises(SupplyRefusedError):
        fetcher.fetch(tile, tmp_path)
    assert supply.attempts == 2


def corrupt_copy(sources: Path, folder: Path, name: str) -> Path:
    """A file of the real source's size that isn't a GeoTIFF."""
    real = sources / f"{name}_DTM_1m.tif"
    folder.mkdir(parents=True, exist_ok=True)
    bad = folder / real.name
    bad.write_bytes(b"\0" * real.stat().st_size)
    return bad


def test_an_unreadable_source_on_disk_is_set_aside_and_the_bulk_supply_tried(
    sources: Path, tmp_path: Path
) -> None:
    bad = corrupt_copy(sources, tmp_path / "local", "SU16ne")
    good = (sources / "SU16ne_DTM_1m.tif").read_bytes()
    server = FakeServer({SourceTile("SU16ne", 0).remote_path: good})
    fetchers = [LocalSourceFetcher(bad.parent), SftpFetcher(lambda: server.connect, window=1024 * 1024)]
    mirror = make_mirror(sources, tmp_path, fetchers)
    path = mirror.ensure("SU16ne")
    assert path is not None
    check_cog(path)
    assert server.connections == 1
    assert not bad.exists()
    assert bad.with_name(bad.name + ".unreadable").is_file()


def test_a_tile_whose_every_copy_is_unreadable_is_a_data_integrity_error(
    sources: Path, tmp_path: Path
) -> None:
    bad = corrupt_copy(sources, tmp_path / "local", "SU16ne")
    mirror = make_mirror(sources, tmp_path, [LocalSourceFetcher(bad.parent)])
    with pytest.raises(DataIntegrityError) as raised:
        mirror.ensure("SU16ne")
    assert str(tmp_path) not in raised.value.message
    assert not mirror.has("SU16ne")
    # Set aside, so the next request doesn't convert it again.
    with pytest.raises(ElevationUnavailableError):
        mirror.ensure("SU16ne")
