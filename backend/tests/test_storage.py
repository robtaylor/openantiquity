"""Storage: local files, the bucket adapter, and keys that can't escape."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from google.api_core.exceptions import NotFound

from fieldclub import storage
from fieldclub.storage import (
    GcsStorage,
    LocalStorage,
    Storage,
    StorageKeyError,
    StorageNotFoundError,
    check_key,
    get_storage,
)
from tests.helpers import run_fresh


class FakeBlob:
    def __init__(self, bucket: FakeBucket, name: str) -> None:
        self.bucket = bucket
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str | None = None) -> None:
        self.bucket.objects[self.name] = (data, content_type)

    def download_as_bytes(self) -> bytes:
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        return self.bucket.objects[self.name][0]

    def exists(self) -> bool:
        return self.name in self.bucket.objects

    def delete(self) -> None:
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        del self.bucket.objects[self.name]


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


class FakeGcsClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket())


@pytest.fixture(params=["local", "gcs"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Storage:
    if request.param == "local":
        return LocalStorage(tmp_path / "store")
    return GcsStorage("test-bucket", "prefix", client=FakeGcsClient())


def test_both_backends_satisfy_the_protocol(store: Storage) -> None:
    assert isinstance(store, Storage)


def test_put_get_exists_delete(store: Storage) -> None:
    key = "tiles/composite/14/8107/5448.png"
    assert not store.exists(key)
    store.put(key, b"\x89PNG tile", "image/png")
    assert store.exists(key)
    assert store.get(key) == b"\x89PNG tile"
    store.put(key, b"newer")
    assert store.get(key) == b"newer"
    store.delete(key)
    assert not store.exists(key)


def test_get_of_a_missing_key_raises(store: Storage) -> None:
    with pytest.raises(StorageNotFoundError) as caught:
        store.get("tiles/missing.png")
    assert caught.value.status_code == 404


def test_delete_of_a_missing_key_is_quiet(store: Storage) -> None:
    store.delete("tiles/missing.png")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/etc/passwd",
        "../outside",
        "tiles/../../outside",
        "tiles//double",
        "tiles/",
        "a\\b",
        ".hidden",
        "a/b c",
        # `$` in a pattern also matches just before a final newline.
        "tiles/a.png\n",
        "tiles\n/a.png",
        "tiles/a.png\x00",
    ],
)
def test_keys_that_could_escape_are_refused(store: Storage, key: str) -> None:
    for call in (lambda: store.put(key, b"x"), lambda: store.get(key), lambda: store.exists(key)):
        with pytest.raises(StorageKeyError):
            call()
    with pytest.raises(StorageKeyError):
        store.delete(key)
    with pytest.raises(StorageKeyError):
        store.url(key)


def test_check_key_accepts_ordinary_paths() -> None:
    assert check_key("media/2026/11/ab12cd.jpg") == "media/2026/11/ab12cd.jpg"
    assert check_key("dem_14_8107-5448.npy") == "dem_14_8107-5448.npy"
    with pytest.raises(StorageKeyError):
        check_key("a/" * 300 + "b")


def test_local_storage_writes_under_its_root_and_leaves_no_temp_files(tmp_path: Path) -> None:
    root = tmp_path / "var" / "tiles"
    store = LocalStorage(root)
    store.put("a/b/c.bin", b"123")
    assert (root / "a" / "b" / "c.bin").read_bytes() == b"123"
    assert [path.name for path in (root / "a" / "b").iterdir()] == ["c.bin"]
    assert store.url("a/b/c.bin") == (root.resolve() / "a" / "b" / "c.bin").as_uri()


def test_local_storage_treats_a_directory_as_missing(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    store.put("a/b.bin", b"1")
    assert not store.exists("a")
    with pytest.raises(StorageNotFoundError):
        store.get("a")


def test_gcs_storage_prefixes_names_and_sets_content_type() -> None:
    client = FakeGcsClient()
    store = GcsStorage("fieldclub-data", "/cache/", client=client)
    store.put("tiles/a.png", b"png", "image/png")
    store.put("tiles/b.bin", b"raw")
    assert client.buckets["fieldclub-data"].objects == {
        "cache/tiles/a.png": (b"png", "image/png"),
        "cache/tiles/b.bin": (b"raw", "application/octet-stream"),
    }
    assert store.url("tiles/a.png") == "https://storage.googleapis.com/fieldclub-data/cache/tiles/a.png"
    assert (
        GcsStorage("fieldclub-data", client=client).url("x.png")
        == "https://storage.googleapis.com/fieldclub-data/x.png"
    )


def test_gcs_client_is_only_built_when_first_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []

    class Client(FakeGcsClient):
        def __init__(self) -> None:
            super().__init__()
            built.append(self)

    import google.cloud.storage as gcs

    monkeypatch.setattr(gcs, "Client", Client)
    store = GcsStorage("fieldclub-data")
    assert built == []
    assert store.url("a.png")
    assert built == []
    store.put("a.png", b"1")
    assert store.exists("a.png")
    assert len(built) == 1


def test_importing_fieldclub_does_not_load_the_google_client() -> None:
    code = (
        "import sys; import fieldclub.storage, fieldclub.main; "
        "sys.exit(1 if any(name.startswith('google.cloud') for name in sys.modules) else 0)"
    )
    run_fresh(code)


def test_get_storage_follows_settings(env: Callable[..., None], tmp_path: Path) -> None:
    env(VAR_DIR=str(tmp_path))
    get_storage.cache_clear()
    try:
        local = get_storage("tiles")
        assert isinstance(local, LocalStorage)
        assert local.root == (tmp_path / "tiles").resolve()
        assert get_storage("tiles") is local
        assert get_storage("media") is not local

        env(STORAGE_BACKEND="gcs", GCS_BUCKET="fieldclub-data", GCS_PREFIX="prod")
        get_storage.cache_clear()
        bucket = get_storage("tiles")
        assert isinstance(bucket, GcsStorage)
        assert (bucket.bucket_name, bucket.prefix) == ("fieldclub-data", "prod/tiles")
        with pytest.raises(StorageKeyError):
            get_storage("../elsewhere")
    finally:
        storage.get_storage.cache_clear()


def test_a_namespace_can_have_a_bucket_of_its_own(env: Callable[..., None]) -> None:
    env(
        STORAGE_BACKEND="gcs",
        GCS_BUCKET="fieldclub-cache",
        GCS_PREFIX="prod",
        GCS_NAMESPACE_BUCKETS='{"media": "fieldclub-photos"}',
    )
    get_storage.cache_clear()
    try:
        photos = get_storage("media")
        assert isinstance(photos, GcsStorage)
        # Its own bucket, under the same prefix the shared bucket would use.
        assert (photos.bucket_name, photos.prefix) == ("fieldclub-photos", "prod/media")
        tiles = get_storage("tiles")
        assert isinstance(tiles, GcsStorage)
        assert (tiles.bucket_name, tiles.prefix) == ("fieldclub-cache", "prod/tiles")
    finally:
        storage.get_storage.cache_clear()
