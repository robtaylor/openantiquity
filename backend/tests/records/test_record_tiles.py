from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point
from sqlalchemy.orm import Session

from fieldclub.services import record_tiles
from tests.helpers import error_code
from tests.records import mvt
from tests.records.support import OVERTON, SILBURY, add_record, add_source


def tile_of(lon: float, lat: float, z: int) -> tuple[int, int]:
    """The Web Mercator tile holding a point."""
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


@pytest.fixture
def index(db: Session) -> dict[str, int]:
    designations = add_source(db)
    finds = add_source(db, "test-finds", name="Test finds", category="find", reuse="non_commercial")
    hidden = add_source(db, "test-hidden", name="Hidden", enabled=False)
    made = {
        "silbury": add_record(db, designations, "Silbury Hill", geom=Point(*SILBURY).buffer(0.001)),
        "bowl": add_record(db, designations, "Bowl barrow", *OVERTON),
        "coin": add_record(db, finds, "Roman coin", -1.8570, 51.4150),
        "dyke": add_record(db, designations, "Wansdyke", geom=LineString([(-1.95, 51.37), (-1.80, 51.38)])),
        "secret": add_record(db, hidden, "Hidden record", -1.8560, 51.4160),
    }
    db.commit()
    return {name: record.id for name, record in made.items()}


def get_tile(client: TestClient, z: int, x: int, y: int, **params: str) -> dict[str, mvt.Layer]:
    response = client.get(f"/tiles/records/{z}/{x}/{y}.mvt", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == record_tiles.MEDIA_TYPE
    assert response.headers["cache-control"].startswith("public, max-age=")
    return mvt.decode(response.content)


def test_a_high_zoom_tile_holds_the_records(client: TestClient, index: dict[str, int]) -> None:
    layers = get_tile(client, 15, *tile_of(*SILBURY, 15))
    assert set(layers) == {"records"}
    by_name = {feature.properties["name"]: feature for feature in layers["records"].features}
    assert "Silbury Hill" in by_name
    silbury = by_name["Silbury Hill"]
    assert silbury.id == index["silbury"]
    assert silbury.type == "Polygon"
    assert silbury.properties == {
        "name": "Silbury Hill",
        "category": "designation",
        "source": "test-designations",
        "reuse": "open",
    }
    assert "Hidden record" not in by_name
    assert by_name["Roman coin"].properties["reuse"] == "non_commercial"


def test_a_low_zoom_tile_holds_counts_by_category(client: TestClient, index: dict[str, int]) -> None:
    layers = get_tile(client, 8, *tile_of(*SILBURY, 8))
    assert set(layers) == {"record_counts"}
    counts = layers["record_counts"].features
    assert all(feature.type == "Point" for feature in counts)
    by_category: dict[str, int] = {}
    for feature in counts:
        by_category[feature.properties["category"]] = (
            by_category.get(feature.properties["category"], 0) + (feature.properties["count"])
        )
    # The hidden source's record is not counted.
    assert by_category == {"designation": 3, "find": 1}
    find_cell = next(feature for feature in counts if feature.properties["category"] == "find")
    assert find_cell.properties["sources"] == "test-finds"


def test_each_record_is_counted_once_across_tiles(client: TestClient, index: dict[str, int]) -> None:
    """Wansdyke crosses tile edges at zoom 11. It is counted where its centroid is."""
    z = 11
    x, y = tile_of(*SILBURY, z)
    total = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            layers = get_tile(client, z, x + dx, y + dy)
            if "record_counts" in layers:
                total += sum(feature.properties["count"] for feature in layers["record_counts"].features)
    assert total == 4


def test_the_category_filter(client: TestClient, index: dict[str, int]) -> None:
    layers = get_tile(client, 15, *tile_of(*SILBURY, 15), category="find")
    assert [feature.properties["name"] for feature in layers["records"].features] == ["Roman coin"]
    counts = get_tile(client, 8, *tile_of(*SILBURY, 8), category="find,event")
    assert {feature.properties["category"] for feature in counts["record_counts"].features} == {"find"}


@pytest.mark.parametrize("z", [3, 9, 14, 18])
def test_an_empty_area_is_a_valid_empty_tile(client: TestClient, index: dict[str, int], z: int) -> None:
    # The middle of the Atlantic.
    response = client.get(f"/tiles/records/{z}/{'/'.join(map(str, tile_of(-35.0, 40.0, z)))}.mvt")
    assert response.status_code == 200
    assert response.content == b""
    assert mvt.decode(response.content) == {}
    assert response.headers["content-type"] == record_tiles.MEDIA_TYPE


def test_an_empty_index_gives_empty_tiles(client: TestClient, db: Session) -> None:
    assert get_tile(client, 0, 0, 0) == {}
    assert get_tile(client, 16, *tile_of(*SILBURY, 16)) == {}


@pytest.mark.parametrize("path", ["1/2/0", "1/0/2", "23/0/0", "5/-1/0"])
def test_a_tile_off_the_map(client: TestClient, index: dict[str, int], path: str) -> None:
    response = client.get(f"/tiles/records/{path}.mvt")
    assert response.status_code in (404, 422)


def test_an_unknown_category(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/tiles/records/8/127/85.mvt", params={"category": "treasure"})
    assert response.status_code == 400
    assert error_code(response) == "invalid_tile_filter"


def test_tiles_are_outside_the_api_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/tiles/records/0/0/0.mvt").status_code == 404
    assert client.get("/tiles/records/0/0/0.mvt").status_code == 200


def test_a_busy_feature_tile_falls_back_to_counts(
    client: TestClient, index: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Silbury Hill and the coin share this tile.
    monkeypatch.setattr(record_tiles, "MAX_TILE_FEATURES", 1)
    layers = get_tile(client, 15, *tile_of(*SILBURY, 15))
    assert set(layers) == {"record_counts"}
    assert sum(feature.properties["count"] for feature in layers["record_counts"].features) == 2
    # With the filter, few enough records remain to send them one by one.
    filtered = get_tile(client, 15, *tile_of(*SILBURY, 15), category="find")
    assert set(filtered) == {"records"}
