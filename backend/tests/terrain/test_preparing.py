"""No request waits for elevation to be added to the mirror, and tiles can't starve the rest of the API."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.grid import tile_at
from fieldclub.terrain.mirror import Fetched, LocalSourceFetcher
from fieldclub.terrain.prefetch import Prefetcher
from fieldclub.terrain.render import RenderedTile
from fieldclub.terrain.service import Terrain, get_terrain, get_tile_workers
from fieldclub.terrain.workers import TileWorkers
from tests.helpers import BASE_URL, WEB, error_code
from tests.terrain.fakes import TO_LONLAT, local_mirror, local_terrain, write_source_tile

# The middle of SU16nw, by Avebury.
INSIDE = TO_LONLAT.transform(412_505, 167_505)


def plane(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 150 + 0.02 * (east - 410_000)


class CountingFetcher:
    """Source files on disk, counting how often each tile is asked for and holding each until released."""

    def __init__(self, root: Path) -> None:
        self.inner = LocalSourceFetcher(root)
        self.calls: list[str] = []
        self.release = threading.Event()

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        self.calls.append(tile.name)
        assert self.release.wait(30), "the test never let the fetch finish"
        return self.inner.fetch(tile, work_dir)


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("preparing") / "src"
    write_source_tile(root, "SU16nw", formula=plane)
    return root


@pytest.fixture
def fetcher(sources: Path) -> CountingFetcher:
    return CountingFetcher(sources)


@pytest.fixture
def terrain(sources: Path, fetcher: CountingFetcher, tmp_path: Path) -> Iterator[Terrain]:
    mirror = local_mirror(tmp_path, sources=sources, extra=["SU16ne"], fetchers=[fetcher])
    prefetch = Prefetcher(mirror, 1)
    yield local_terrain(mirror, tmp_path / "tiles", prefetch=prefetch)
    fetcher.release.set()
    prefetch.wait(timeout=60)
    prefetch.close()


@pytest.fixture
def api(app: FastAPI, client: TestClient, terrain: Terrain) -> TestClient:
    app.dependency_overrides[get_terrain] = lambda: terrain
    return client


def prefetch_of(terrain: Terrain) -> Prefetcher:
    assert terrain.prefetch is not None
    return terrain.prefetch


def tile_path(z: int = 15) -> str:
    x, y = tile_at(*INSIDE, z)
    return f"/tiles/lidar/composite/{z}/{x}/{y}.png"


# --------------------------------------------------------------------------
# Map tiles
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["lidar", "dem"])
def test_a_tile_whose_elevation_is_missing_is_answered_at_once_and_fetched_behind(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher, kind: str
) -> None:
    x, y = tile_at(*INSIDE, 15)
    path = f"/tiles/lidar/composite/15/{x}/{y}.png" if kind == "lidar" else f"/tiles/dem/15/{x}/{y}.png"
    started = time.monotonic()
    response = api.get(path)
    # The fetch is held until released, so an answer at all shows the request didn't wait for it.
    assert time.monotonic() - started < 5
    assert response.status_code == 503
    assert error_code(response) == "elevation_preparing"
    assert response.json()["error"]["details"] == {"tiles": ["SU16nw"]}
    assert response.headers["retry-after"] == "20"
    assert "no-cache" in response.headers["cache-control"]
    assert prefetch_of(terrain).pending() == {"SU16nw"}
    fetcher.release.set()
    prefetch_of(terrain).wait(timeout=60)
    assert terrain.mirror.has("SU16nw")
    drawn = api.get(path)
    assert drawn.status_code == 200
    assert drawn.headers["content-type"] == "image/png"


def test_a_missing_tile_is_fetched_once_however_many_ask(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher
) -> None:
    for z in (13, 14, 15, 16, 16, 15):
        assert error_code(api.get(tile_path(z))) == "elevation_preparing"
    assert error_code(api.get(tile_path(15).replace("composite", "slope"))) == "elevation_preparing"
    fetcher.release.set()
    prefetch_of(terrain).wait(timeout=60)
    assert fetcher.calls == ["SU16nw"]
    assert api.get(tile_path(16)).status_code == 200


def test_nothing_is_cached_while_a_tile_is_being_prepared(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher, tmp_path: Path
) -> None:
    api.get(tile_path())
    assert not list((tmp_path / "tiles").rglob("*"))


def test_a_tile_whose_fetch_failed_says_so_rather_than_being_prepared_for_ever(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher
) -> None:
    # SU16ne is in the catalogue, but the fetcher has no file for it.
    lon, lat = TO_LONLAT.transform(417_500, 167_500)
    x, y = tile_at(lon, lat, 15)
    path = f"/tiles/lidar/composite/15/{x}/{y}.png"
    fetcher.release.set()
    assert error_code(api.get(path)) == "elevation_preparing"
    prefetch_of(terrain).wait(timeout=60)
    response = api.get(path)
    assert response.status_code == 503
    assert error_code(response) == "elevation_unavailable"


def test_low_zooms_never_ask_for_a_tile_to_be_fetched(api: TestClient, terrain: Terrain) -> None:
    response = api.get(tile_path(12))
    assert response.status_code == 200
    assert prefetch_of(terrain).pending() == frozenset()


def test_the_commands_still_fetch_in_the_foreground(
    sources: Path, fetcher: CountingFetcher, tmp_path: Path
) -> None:
    fetcher.release.set()
    terrain = local_terrain(local_mirror(tmp_path, sources=sources, fetchers=[fetcher]), tmp_path / "tiles")
    x, y = tile_at(*INSIDE, 15)
    assert terrain.renderer.lidar_png("composite", 15, x, y).png
    assert terrain.mirror.has("SU16nw")


# --------------------------------------------------------------------------
# Profiles and points
# --------------------------------------------------------------------------


def line_across(west: float, east: float) -> dict[str, object]:
    start = TO_LONLAT.transform(west, 167_000)
    end = TO_LONLAT.transform(east, 167_000)
    return {"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 11}


def test_a_profile_says_the_data_is_being_prepared_instead_of_waiting(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher
) -> None:
    response = api.post("/api/v1/terrain/profile", json=line_across(411_000, 411_400))
    assert response.status_code == 503
    assert error_code(response) == "elevation_preparing"
    assert response.headers["retry-after"] == "20"
    fetcher.release.set()
    prefetch_of(terrain).wait(timeout=60)
    answered = api.post("/api/v1/terrain/profile", json=line_across(411_000, 411_400))
    assert answered.status_code == 200
    assert all(sample["elevation"] is not None for sample in answered.json()["samples"])


def test_a_point_says_its_data_is_being_prepared_and_starts_nothing(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher
) -> None:
    lon, lat = INSIDE
    body = api.get("/api/v1/geo/point", params={"lon": lon, "lat": lat}).json()
    assert body["elevation_status"] == "preparing"
    assert fetcher.calls == []
    assert prefetch_of(terrain).pending() == frozenset()


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def test_coverage_says_which_tiles_are_in_the_mirror_yet(
    api: TestClient, terrain: Terrain, fetcher: CountingFetcher
) -> None:
    before = api.get("/api/v1/terrain/coverage")
    assert {f["id"]: f["properties"]["mirrored"] for f in before.json()["features"]} == {
        "SU16nw": False,
        "SU16ne": False,
    }
    fetcher.release.set()
    terrain.mirror.ensure("SU16nw")
    after = api.get("/api/v1/terrain/coverage", headers={"If-None-Match": before.headers["etag"]})
    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]
    assert {f["id"]: f["properties"]["mirrored"] for f in after.json()["features"]} == {
        "SU16nw": True,
        "SU16ne": False,
    }


# --------------------------------------------------------------------------
# Tiles can't starve the rest of the API
# --------------------------------------------------------------------------


class StuckRenderer:
    """Draws nothing until released, as a tile reading a slow bucket would."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Semaphore(0)

    def lidar_png(self, style: str, z: int, x: int, y: int) -> RenderedTile:
        self.started.release()
        assert self.release.wait(30), "the test never let the tiles finish"
        return RenderedTile(b"png", cacheable=False, version="v")


def test_a_flood_of_slow_tiles_leaves_meta_answered_promptly(
    app: FastAPI, terrain: Terrain, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Far more tiles than the 40 threads every plain endpoint shares.
    flood = 120
    workers = TileWorkers(workers=2, queue=10)
    stuck = StuckRenderer()
    monkeypatch.setattr(terrain, "renderer", stuck)
    app.dependency_overrides[get_terrain] = lambda: terrain
    app.dependency_overrides[get_tile_workers] = lambda: workers

    async def scenario() -> tuple[list[httpx.Response], httpx.Response, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL, headers=WEB) as http:
            tiles = [
                asyncio.create_task(http.get(f"/tiles/lidar/composite/15/{x}/0.png")) for x in range(flood)
            ]
            # Wait until the tile threads are all taken.
            for _ in range(2):
                assert await asyncio.to_thread(stuck.started.acquire, True, 30)
            started = time.monotonic()
            meta = await http.get("/api/v1/meta")
            took = time.monotonic() - started
            stuck.release.set()
            return await asyncio.gather(*tiles), meta, took

    try:
        responses, meta, took = asyncio.run(scenario())
    finally:
        stuck.release.set()
        workers.close()
    assert meta.status_code == 200
    assert took < 5, f"/meta took {took:.1f} s while tiles were stuck"
    codes = [response.status_code for response in responses]
    assert codes.count(200) == workers.capacity
    turned_away = [response for response in responses if response.status_code == 503]
    assert len(turned_away) == flood - workers.capacity
    assert {error_code(response) for response in turned_away} == {"tiles_busy"}
    assert all(response.headers["retry-after"] == "1" for response in turned_away)
    assert workers.in_hand == 0
