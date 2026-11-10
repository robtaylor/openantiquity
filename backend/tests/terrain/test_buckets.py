"""What the terrain service keeps in a bucket, against a fake Cloud Storage, from upload to cached tile.

GDAL reads `/vsigs/` paths from a local server holding the fake's objects
(`tests/terrain/gcs.py`), so a tile goes from upload to rendered PNG the way
it does in production.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio

from fieldclub.errors import DataIntegrityError
from fieldclub.storage import GcsStorage, StorageNotFoundError
from fieldclub.terrain.blobs import GcsFolder, LockTimeoutError, ObjectLock
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.grid import tile_at
from fieldclub.terrain.mirror import Fetched, GcsMirrorStore, LocalSourceFetcher, Mirror
from fieldclub.terrain.national import Builder, NationalStore
from fieldclub.terrain.overview import Overview
from fieldclub.terrain.service import Terrain
from tests.terrain.fakes import TO_LONLAT, catalogue_of, decode_png, small_cog, write_source_tile
from tests.terrain.gcs import FakeGcs, serve_for_gdal


@pytest.fixture
def gcs() -> FakeGcs:
    return FakeGcs()


@pytest.fixture
def bucket() -> str:
    # GDAL caches what it learns about a /vsigs/ address, so every test has its own bucket.
    return f"lidar-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("bucket-sources")
    for name in ("SU16nw", "SU16ne", "SU17sw", "SU17se"):
        write_source_tile(folder, name)
    return folder


# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------


def test_a_bucket_folder_reads_writes_and_lists_under_its_prefix(gcs: FakeGcs, tmp_path: Path) -> None:
    folder = GcsFolder("b", "england/mirror", client=gcs.client())
    assert folder.read("national.json") is None
    folder.write("national.json", b"{}", "application/json")
    assert folder.read("national.json") == b"{}"
    local = tmp_path / "a.tif"
    local.write_bytes(b"cog" * 100)
    folder.upload(local, "SU16nw.tif", "image/tiff")
    assert local.exists()
    assert gcs.data("b", "england/mirror/SU16nw.tif") == b"cog" * 100
    folder.write("locks/SU16nw.lock", b"{}", "application/json")
    # Only what is directly in the folder, not the locks below it.
    assert folder.names(".tif") == ["SU16nw.tif"]
    assert folder.names() == ["SU16nw.tif", "national.json"]
    assert folder.gdal_path("SU16nw.tif") == "/vsigs/b/england/mirror/SU16nw.tif"
    info = folder.stat("SU16nw.tif")
    assert info is not None
    assert info.size == 300
    folder.delete("SU16nw.tif")
    folder.delete("SU16nw.tif")
    assert not folder.exists("SU16nw.tif")


def test_create_writes_only_when_nothing_is_there(gcs: FakeGcs) -> None:
    folder = GcsFolder("b", client=gcs.client())
    assert folder.create("lock", b"one")
    assert not folder.create("lock", b"two")
    assert folder.read("lock") == b"one"


def test_delete_if_removes_only_the_object_that_was_looked_at(gcs: FakeGcs) -> None:
    folder = GcsFolder("b", client=gcs.client())
    folder.create("lock", b"one")
    seen = folder.stat("lock")
    assert seen is not None
    folder.write("lock", b"replaced", "application/json")
    assert not folder.delete_if("lock", seen.token)
    assert folder.read("lock") == b"replaced"
    now = folder.stat("lock")
    assert now is not None
    assert folder.delete_if("lock", now.token)
    assert not folder.delete_if("lock", now.token)


def test_an_upload_stored_short_is_refused(
    gcs: FakeGcs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = GcsFolder("b", client=gcs.client())
    local = tmp_path / "a.tif"
    local.write_bytes(b"x" * 10)
    real_put = gcs.put

    def truncated(bucket: str, name: str, data: bytes, *args: Any) -> Any:
        return real_put(bucket, name, data[:5], *args)

    monkeypatch.setattr(gcs, "put", truncated)
    with pytest.raises(DataIntegrityError):
        folder.upload(local, "a.tif", "image/tiff")


# --------------------------------------------------------------------------
# The lock
# --------------------------------------------------------------------------


def quick_lock(folder: GcsFolder, **options: Any) -> ObjectLock:
    return ObjectLock(folder, poll_s=0.01, max_poll_s=0.02, **options)


def test_a_held_lock_makes_others_wait_until_the_work_is_done(gcs: FakeGcs) -> None:
    folder = GcsFolder("b", client=gcs.client())
    lock = quick_lock(folder)
    done = threading.Event()
    with lock.hold("locks/x.lock", done=done.is_set) as held:
        assert held
        waiter: list[bool] = []
        thread = threading.Thread(
            target=lambda: waiter.append(lock.acquire("locks/x.lock", done.is_set) is None)
        )
        thread.start()
        time.sleep(0.05)
        done.set()
        thread.join(5)
        assert waiter == [True]
    assert not folder.exists("locks/x.lock")


def test_an_abandoned_lock_is_taken_over_once_it_is_stale(gcs: FakeGcs) -> None:
    now = [datetime(2026, 11, 10, 12, tzinfo=UTC)]
    gcs.now = lambda: now[0]
    folder = GcsFolder("b", client=gcs.client())
    folder.create("locks/x.lock", json.dumps({"owner": "a machine that died"}).encode())
    lock = quick_lock(folder, stale_after_s=600, wait_s=1, now=lambda: now[0])
    with pytest.raises(LockTimeoutError) as raised:
        lock.acquire("locks/x.lock", done=lambda: False)
    assert raised.value.status_code == 503
    assert raised.value.code == "elevation_busy"
    now[0] += timedelta(seconds=601)
    owner = lock.acquire("locks/x.lock", done=lambda: False)
    assert owner is not None
    data = folder.read("locks/x.lock")
    assert data is not None
    assert json.loads(data)["owner"] == owner


def test_a_create_that_succeeded_before_its_retry_failed_is_still_ours(
    gcs: FakeGcs, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.api_core.exceptions import PreconditionFailed

    folder = GcsFolder("b", client=gcs.client())
    real_put = gcs.put

    def stored_then_refused(bucket: str, name: str, data: bytes, content_type: Any, match: Any) -> Any:
        real_put(bucket, name, data, content_type, match)
        # The library retried after a lost answer, and the retry saw the object it had made.
        raise PreconditionFailed("retry")

    monkeypatch.setattr(gcs, "put", stored_then_refused)
    lock = quick_lock(folder, wait_s=1)
    assert lock.acquire("locks/x.lock", done=lambda: False) is not None


# --------------------------------------------------------------------------
# The mirror in a bucket
# --------------------------------------------------------------------------


class SlowFetcher:
    """Hands out a local source file slowly, and counts the fetches across every mirror sharing it."""

    def __init__(self, folder: Path) -> None:
        self.inner = LocalSourceFetcher(folder)
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        with self.lock:
            self.calls.append(tile.name)
        time.sleep(0.3)
        return self.inner.fetch(tile, work_dir)


def bucket_mirror(
    gcs: FakeGcs, bucket: str, sources: Path, work: Path, fetchers: list[Any] | None = None
) -> Mirror:
    store = GcsMirrorStore(bucket, "england/dtm-2022", client=gcs.client())
    return Mirror(
        catalogue_of(sources.glob("*.tif")),
        store,
        fetchers if fetchers is not None else [LocalSourceFetcher(sources)],
        work,
        convert=small_cog(),
        lock=ObjectLock(store.folder, poll_s=0.02, max_poll_s=0.05, wait_s=30),
    )


def test_twenty_servers_asking_for_one_missing_tile_cause_one_fetch(
    gcs: FakeGcs, bucket: str, sources: Path, tmp_path: Path
) -> None:
    fetcher = SlowFetcher(sources)
    # A mirror each, with its own work directory: only the bucket's lock is shared.
    mirrors = [bucket_mirror(gcs, bucket, sources, tmp_path / f"server{i}", [fetcher]) for i in range(20)]
    barrier = threading.Barrier(20)
    results: list[str | None] = []

    def ask(mirror: Mirror) -> None:
        barrier.wait()
        results.append(mirror.ensure("SU16nw"))

    threads = [threading.Thread(target=ask, args=(mirror,)) for mirror in mirrors]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert fetcher.calls == ["SU16nw"]
    assert results == [f"/vsigs/{bucket}/england/dtm-2022/SU16nw.tif"] * 20
    assert [name for name in gcs.names(bucket) if "lock" in name] == []
    uploads = [call for call in gcs.calls if call == ("put", "england/dtm-2022/SU16nw.tif")]
    assert len(uploads) == 1


def test_the_whole_gs_path_from_mirror_to_overview_to_cached_tiles(
    gcs: FakeGcs, bucket: str, sources: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve_for_gdal(gcs, monkeypatch):
        mirror = bucket_mirror(gcs, bucket, sources, tmp_path / "work")
        for name in ("SU16nw", "SU16ne", "SU17sw", "SU17se"):
            path = mirror.ensure(name)
            assert path is not None
            # GDAL reads the uploaded COG back through /vsigs/.
            with rasterio.open(path) as ds:
                assert ds.crs.to_epsg() == 27700
                assert ds.overviews(1)
        assert mirror.store.names() == ["SU16ne", "SU16nw", "SU17se", "SU17sw"]

        national = NationalStore(GcsFolder(bucket, "england/national", client=gcs.client()))
        report = Builder(mirror, national, tmp_path / "work", threads=1).build()
        assert report.read == 4
        manifest = national.manifest()
        assert manifest is not None
        assert gcs.names(bucket).count(f"england/national/{manifest.filename}") == 1
        # The build's lock is gone once it has published.
        assert not [name for name in gcs.names(bucket) if name.endswith("build.lock")]

        cache = GcsStorage(bucket, "tiles", client=gcs.client())
        terrain = Terrain(mirror, Overview(mirror, national, refresh_s=3600), cache)
        lon, lat = TO_LONLAT.transform(415_000, 170_000)
        for zoom in (11, 14):
            x, y = tile_at(lon, lat, zoom)
            first = terrain.renderer.lidar_png("composite", zoom, x, y)
            assert first.cacheable, zoom
            pixels = decode_png(first.png)
            # Greyscale with no alpha where every pixel has data, grey and alpha otherwise.
            assert pixels.ndim == 2 or pixels[..., -1].max() == 255, zoom
            stored = [
                name
                for name in gcs.names(bucket)
                if name.startswith("tiles/lidar/composite/") and f"/{zoom}/{x}/{y}.png" in name
            ]
            assert len(stored) == 1, zoom
            gets = len(gcs.calls)
            again = terrain.renderer.lidar_png("composite", zoom, x, y)
            assert again.png == first.png
            # Served from the bucket: a single read, nothing re-rendered or uploaded.
            assert [method for method, _ in gcs.calls[gets:]] == ["get"]
        dem = terrain.renderer.dem_png(14, *tile_at(lon, lat, 14))
        assert dem.cacheable
        height = terrain.elevation_at(lon, lat)
        assert height is not None
        assert np.isfinite(height)


def test_the_tile_cache_in_a_bucket(gcs: FakeGcs) -> None:
    cache = GcsStorage("b", "tiles", client=gcs.client())
    with pytest.raises(StorageNotFoundError):
        cache.get("lidar/x.png")
    cache.put("lidar/x.png", b"png", "image/png")
    assert cache.get("lidar/x.png") == b"png"
    assert cache.exists("lidar/x.png")
    assert gcs.objects[("b", "tiles/lidar/x.png")].content_type == "image/png"
    cache.delete("lidar/x.png")
    cache.delete("lidar/x.png")
    assert not cache.exists("lidar/x.png")
