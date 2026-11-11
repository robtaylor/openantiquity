"""What the terrain service keeps in a bucket, against a stand-in S3 store, from upload to cached tile.

GDAL reads `/vsis3/` paths from a local server holding the stand-in's objects
(`tests/fake_s3.py`), so a tile goes from upload to rendered PNG the way it
does in production.
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
from fieldclub.storage import S3Storage, StorageNotFoundError
from fieldclub.terrain.blobs import LocalFolder, LockTimeoutError, ObjectLock, S3Folder, gdal_s3_options
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.grid import tile_at
from fieldclub.terrain.mirror import Fetched, LocalSourceFetcher, Mirror, S3MirrorStore
from fieldclub.terrain.national import Builder, NationalStore
from fieldclub.terrain.overview import Overview
from fieldclub.terrain.service import Terrain
from tests.fake_s3 import FakeS3, client_error, serve_for_gdal
from tests.helpers import settings
from tests.terrain.fakes import TO_LONLAT, catalogue_of, decode_png, small_cog, write_source_tile


@pytest.fixture
def s3() -> FakeS3:
    return FakeS3()


@pytest.fixture
def bucket() -> str:
    # GDAL caches what it learns about a /vsis3/ address, so every test has its own bucket.
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


def test_a_bucket_folder_reads_writes_and_lists_under_its_prefix(s3: FakeS3, tmp_path: Path) -> None:
    folder = S3Folder("b", "england/mirror", client=s3.client())
    assert folder.read("national.json") is None
    folder.write("national.json", b"{}", "application/json")
    assert folder.read("national.json") == b"{}"
    local = tmp_path / "a.tif"
    local.write_bytes(b"cog" * 100)
    folder.upload(local, "SU16nw.tif", "image/tiff")
    assert local.exists()
    assert s3.data("b", "england/mirror/SU16nw.tif") == b"cog" * 100
    folder.write("locks/SU16nw.lock", b"{}", "application/json")
    # Only what is directly in the folder, not the locks below it.
    assert folder.names(".tif") == ["SU16nw.tif"]
    assert folder.names() == ["SU16nw.tif", "national.json"]
    assert folder.gdal_path("SU16nw.tif") == "/vsis3/b/england/mirror/SU16nw.tif"
    info = folder.stat("SU16nw.tif")
    assert info is not None
    assert info.size == 300
    folder.delete("SU16nw.tif")
    folder.delete("SU16nw.tif")
    assert not folder.exists("SU16nw.tif")


def test_create_writes_only_when_nothing_is_there(s3: FakeS3) -> None:
    folder = S3Folder("b", client=s3.client())
    assert folder.create("lock", b"one")
    assert not folder.create("lock", b"two")
    assert folder.read("lock") == b"one"


def test_delete_if_removes_only_the_object_that_was_looked_at(s3: FakeS3) -> None:
    folder = S3Folder("b", client=s3.client())
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
    s3: FakeS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = S3Folder("b", client=s3.client())
    local = tmp_path / "a.tif"
    local.write_bytes(b"x" * 10)
    real_put = s3.put

    def truncated(bucket: str, name: str, data: bytes, *args: Any) -> Any:
        return real_put(bucket, name, data[:5], *args)

    monkeypatch.setattr(s3, "put", truncated)
    with pytest.raises(DataIntegrityError):
        folder.upload(local, "a.tif", "image/tiff")


# --------------------------------------------------------------------------
# The lock
# --------------------------------------------------------------------------


def quick_lock(folder: S3Folder, **options: Any) -> ObjectLock:
    return ObjectLock(folder, poll_s=0.01, max_poll_s=0.02, **options)


def test_a_held_lock_makes_others_wait_until_the_work_is_done(s3: FakeS3) -> None:
    folder = S3Folder("b", client=s3.client())
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


def test_an_abandoned_lock_is_taken_over_once_it_is_stale(s3: FakeS3) -> None:
    now = [datetime(2026, 11, 10, 12, tzinfo=UTC)]
    s3.now = lambda: now[0]
    folder = S3Folder("b", client=s3.client())
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
    s3: FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = S3Folder("b", client=s3.client())
    real_put = s3.put

    def stored_then_refused(bucket: str, name: str, data: bytes, *args: Any) -> Any:
        real_put(bucket, name, data, *args)
        # The library retried after a lost answer, and the retry saw the object it had made.
        raise client_error("PutObject", 412, "PreconditionFailed")

    monkeypatch.setattr(s3, "put", stored_then_refused)
    lock = quick_lock(folder, wait_s=1)
    assert lock.acquire("locks/x.lock", done=lambda: False) is not None


def test_a_held_lock_is_refreshed_so_long_work_is_not_taken_over(s3: FakeS3) -> None:
    # Ages of a fraction of a second need finer times than S3's whole seconds.
    s3.whole_seconds = False
    folder = S3Folder("b", client=s3.client())
    holder = quick_lock(folder, stale_after_s=0.3, heartbeat_s=0.05)
    rival = quick_lock(folder, stale_after_s=0.3, wait_s=0)
    with holder.hold("locks/build.lock", done=lambda: False) as held:
        assert held
        # Twice the stale age: without the heartbeat the rival would take it over here.
        time.sleep(0.6)
        with pytest.raises(LockTimeoutError):
            rival.acquire("locks/build.lock", done=lambda: False)
    assert not folder.exists("locks/build.lock")


def test_a_lock_taken_over_is_not_refreshed_over_its_new_owner(s3: FakeS3) -> None:
    folder = S3Folder("b", client=s3.client())
    lock = quick_lock(folder)
    owner = lock.acquire("locks/x.lock", done=lambda: False)
    assert owner is not None
    assert lock.refresh("locks/x.lock", owner)
    folder.delete("locks/x.lock")
    assert folder.create("locks/x.lock", json.dumps({"owner": "another machine"}).encode())
    assert not lock.refresh("locks/x.lock", owner)
    data = folder.read("locks/x.lock")
    assert data is not None
    assert json.loads(data)["owner"] == "another machine"


def test_replace_if_writes_only_over_the_object_that_was_looked_at(s3: FakeS3, tmp_path: Path) -> None:
    for folder in (S3Folder("b", client=s3.client()), LocalFolder(tmp_path)):
        folder.write("x.json", b"1", "application/json")
        info = folder.stat("x.json")
        assert info is not None
        assert folder.replace_if("x.json", b"2", info.token)
        assert folder.read("x.json") == b"2"
        assert not folder.replace_if("x.json", b"3", info.token)
        assert not folder.replace_if("missing.json", b"3", info.token)
        assert folder.read("x.json") == b"2"


# --------------------------------------------------------------------------
# Tokens are ETags, which come from the bytes
# --------------------------------------------------------------------------


def test_two_writes_of_the_same_bytes_share_a_token_in_a_bucket(s3: FakeS3) -> None:
    """Why the lock makes every write unique: a token alone can't tell such writes apart."""
    folder = S3Folder("b", client=s3.client())
    folder.write("x.json", b"same", "application/json")
    first = folder.stat("x.json")
    folder.write("x.json", b"same", "application/json")
    second = folder.stat("x.json")
    assert first is not None
    assert second is not None
    assert first.token == second.token


def test_every_write_of_a_lock_has_a_token_of_its_own_even_with_a_clock_that_stands_still(
    s3: FakeS3,
) -> None:
    still = datetime(2026, 11, 11, 12, tzinfo=UTC)
    s3.now = lambda: still
    folder = S3Folder("b", client=s3.client())
    lock = quick_lock(folder, now=lambda: still)
    owner = lock.acquire("locks/x.lock", done=lambda: False)
    assert owner is not None
    tokens = []
    for _ in range(5):
        info = folder.stat("locks/x.lock")
        assert info is not None
        tokens.append(info.token)
        assert lock.refresh("locks/x.lock", owner)
    assert len(set(tokens)) == 5


def test_a_waiter_can_t_remove_a_lock_its_holder_refreshed_after_the_waiter_looked(s3: FakeS3) -> None:
    """The take-over rule: only the very lock that was seen stale may be removed."""
    now = [datetime(2026, 11, 11, 12, tzinfo=UTC)]
    s3.now = lambda: now[0]
    folder = S3Folder("b", client=s3.client())
    # The holder's clock stands still, so a refresh writes the same owner and time as before.
    holder = quick_lock(folder, now=lambda: datetime(2026, 11, 11, 12, tzinfo=UTC))
    owner = holder.acquire("locks/x.lock", done=lambda: False)
    assert owner is not None
    seen = folder.stat("locks/x.lock")
    assert seen is not None
    # The holder was slow, and its refresh lands after a waiter found the lock stale.
    now[0] += timedelta(seconds=600)
    assert holder.refresh("locks/x.lock", owner)
    assert not folder.delete_if("locks/x.lock", seen.token)
    data = folder.read("locks/x.lock")
    assert data is not None
    assert json.loads(data)["owner"] == owner


def test_a_refresh_whose_answer_was_lost_is_still_ours(s3: FakeS3, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = S3Folder("b", client=s3.client())
    lock = quick_lock(folder)
    owner = lock.acquire("locks/x.lock", done=lambda: False)
    assert owner is not None
    real_put = s3.put

    def stored_then_refused(bucket: str, name: str, data: bytes, *args: Any) -> Any:
        real_put(bucket, name, data, *args)
        # The retry carried the token the first attempt had just replaced.
        raise client_error("PutObject", 412, "PreconditionFailed")

    monkeypatch.setattr(s3, "put", stored_then_refused)
    assert lock.refresh("locks/x.lock", owner)


@pytest.mark.parametrize("status", [404, 409, 412])
def test_a_refused_conditional_write_is_an_answer_not_an_error(
    s3: FakeS3, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    folder = S3Folder("b", client=s3.client())
    folder.write("x.json", b"1", "application/json")

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise client_error("PutObject", status, "Refused")

    monkeypatch.setattr(s3, "put", refuse)
    monkeypatch.setattr(s3, "remove", refuse)
    assert not folder.replace_if("x.json", b"2", '"etag"')
    assert not folder.delete_if("x.json", '"etag"')
    if status != 404:
        assert not folder.create("x.json", b"2")


def test_an_unconditional_write_that_fails_is_an_error(s3: FakeS3, monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError

    folder = S3Folder("b", client=s3.client())

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise client_error("PutObject", 412, "PreconditionFailed")

    monkeypatch.setattr(s3, "put", refuse)
    with pytest.raises(ClientError):
        folder.write("national.json", b"{}", "application/json")


def test_a_listing_reads_every_page(s3: FakeS3) -> None:
    s3.page_size = 2
    folder = S3Folder("b", "mirror", client=s3.client())
    for name in ("a", "b", "c", "d", "e"):
        folder.write(f"{name}.tif", b"x", "image/tiff")
    folder.write("locks/a.lock", b"x", "application/json")
    assert folder.names(".tif") == ["a.tif", "b.tif", "c.tif", "d.tif", "e.tif"]


@pytest.mark.parametrize(
    ("endpoint", "options"),
    [
        (
            "https://fly.storage.tigris.dev",
            {"AWS_S3_ENDPOINT": "fly.storage.tigris.dev", "AWS_HTTPS": "YES", "AWS_VIRTUAL_HOSTING": "FALSE"},
        ),
        (
            "https://t3.storage.dev/",
            {"AWS_S3_ENDPOINT": "t3.storage.dev", "AWS_HTTPS": "YES", "AWS_VIRTUAL_HOSTING": "FALSE"},
        ),
        (
            "http://127.0.0.1:9000",
            {"AWS_S3_ENDPOINT": "127.0.0.1:9000", "AWS_HTTPS": "NO", "AWS_VIRTUAL_HOSTING": "FALSE"},
        ),
        ("", {}),
    ],
)
def test_gdal_is_given_the_endpoint_and_no_secret(endpoint: str, options: dict[str, str]) -> None:
    environ = {"AWS_ENDPOINT_URL_S3": endpoint, "AWS_SECRET_ACCESS_KEY": "tsec_test"}
    given = gdal_s3_options(environ)
    assert given == options
    assert "tsec_test" not in "".join(given.values())


def test_gdal_can_t_be_given_an_endpoint_with_a_path() -> None:
    with pytest.raises(AssertionError):
        gdal_s3_options({"AWS_ENDPOINT_URL_S3": "https://example.org/s3"})


def test_a_lock_left_by_a_crash_is_taken_over_within_a_request_s_wait() -> None:
    defaults = settings()
    assert defaults.terrain_lock_stale_s < defaults.terrain_lock_wait_s
    lock = ObjectLock(S3Folder("b", client=FakeS3().client()))
    assert lock.stale_after_s < lock.wait_s


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
    s3: FakeS3, bucket: str, sources: Path, work: Path, fetchers: list[Any] | None = None
) -> Mirror:
    store = S3MirrorStore(bucket, "england/dtm-2022", client=s3.client())
    return Mirror(
        catalogue_of(sources.glob("*.tif")),
        store,
        fetchers if fetchers is not None else [LocalSourceFetcher(sources)],
        work,
        convert=small_cog(),
        lock=ObjectLock(store.folder, poll_s=0.02, max_poll_s=0.05, wait_s=30),
    )


def test_twenty_servers_asking_for_one_missing_tile_cause_one_fetch(
    s3: FakeS3, bucket: str, sources: Path, tmp_path: Path
) -> None:
    fetcher = SlowFetcher(sources)
    # A mirror each, with its own work directory: only the bucket's lock is shared.
    mirrors = [bucket_mirror(s3, bucket, sources, tmp_path / f"server{i}", [fetcher]) for i in range(20)]
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
    assert results == [f"/vsis3/{bucket}/england/dtm-2022/SU16nw.tif"] * 20
    assert [name for name in s3.names(bucket) if "lock" in name] == []
    uploads = [call for call in s3.calls if call == ("put", "england/dtm-2022/SU16nw.tif")]
    assert len(uploads) == 1


def test_the_whole_s3_path_from_mirror_to_overview_to_cached_tiles(
    s3: FakeS3, bucket: str, sources: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve_for_gdal(s3, monkeypatch):
        mirror = bucket_mirror(s3, bucket, sources, tmp_path / "work")
        for name in ("SU16nw", "SU16ne", "SU17sw", "SU17se"):
            path = mirror.ensure(name)
            assert path is not None
            # GDAL reads the uploaded COG back through /vsis3/.
            with rasterio.open(path) as ds:
                assert ds.crs.to_epsg() == 27700
                assert ds.overviews(1)
        assert mirror.store.names() == ["SU16ne", "SU16nw", "SU17se", "SU17sw"]

        national = NationalStore(S3Folder(bucket, "england/national", client=s3.client()))
        report = Builder(mirror, national, tmp_path / "work", threads=1).build()
        assert report.read == 4
        manifest = national.manifest()
        assert manifest is not None
        assert s3.names(bucket).count(f"england/national/{manifest.filename}") == 1
        # The build's lock is gone once it has published.
        assert not [name for name in s3.names(bucket) if name.endswith("build.lock")]

        cache = S3Storage(bucket, "tiles", client=s3.client())
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
                for name in s3.names(bucket)
                if name.startswith("tiles/lidar/composite/") and f"/{zoom}/{x}/{y}.png" in name
            ]
            assert len(stored) == 1, zoom
            gets = len(s3.calls)
            again = terrain.renderer.lidar_png("composite", zoom, x, y)
            assert again.png == first.png
            # Served from the bucket: a single read, nothing re-rendered or uploaded.
            assert [method for method, _ in s3.calls[gets:]] == ["get"]
        dem = terrain.renderer.dem_png(14, *tile_at(lon, lat, 14))
        assert dem.cacheable
        height = terrain.elevation_at(lon, lat)
        assert height is not None
        assert np.isfinite(height)


def test_the_tile_cache_in_a_bucket(s3: FakeS3) -> None:
    cache = S3Storage("b", "tiles", client=s3.client())
    with pytest.raises(StorageNotFoundError):
        cache.get("lidar/x.png")
    cache.put("lidar/x.png", b"png", "image/png")
    assert cache.get("lidar/x.png") == b"png"
    assert cache.exists("lidar/x.png")
    assert s3.objects[("b", "tiles/lidar/x.png")].content_type == "image/png"
    cache.delete("lidar/x.png")
    cache.delete("lidar/x.png")
    assert not cache.exists("lidar/x.png")
