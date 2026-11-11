from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString
from sqlalchemy import update
from sqlalchemy.orm import Session

from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import IngestRun, Record, Source
from fieldclub.services import record_tiles
from fieldclub.vocab import IngestStatus
from tests.helpers import add_record, add_source, count, error_code
from tests.ingest.fakes import FakeConnector, record
from tests.records import mvt
from tests.records.support import OVERTON, SILBURY, SILBURY_MOUND, add_finds_source, tile_of


@pytest.fixture
def index(db: Session) -> dict[str, int]:
    designations = add_source(db)
    finds = add_finds_source(db)
    hidden = add_source(db, "test-hidden", name="Hidden", enabled=False)
    made = {
        "silbury": add_record(db, designations, "Silbury Hill", geom=SILBURY_MOUND),
        "bowl": add_record(db, designations, "Bowl barrow", *OVERTON),
        "coin": add_record(db, finds, "Roman coin", -1.8570, 51.4150, precision_m=1000.0),
        "dyke": add_record(db, designations, "Wansdyke", geom=LineString([(-1.95, 51.37), (-1.80, 51.38)])),
        "secret": add_record(db, hidden, "Hidden record", -1.8560, 51.4160),
    }
    # The ingest runner does this after every run. These records were added by hand.
    record_tiles.refresh_counts(db)
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
    # A find published to a 1 km square says so, so the map can draw the square.
    assert by_name["Roman coin"].properties["precision_m"] == 1000.0


def test_the_token_changes_when_what_a_tile_holds_changes(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tile is immutable under its token, so a new property needs a new token too."""
    before = record_tiles.tile_token(db)
    monkeypatch.setattr(record_tiles, "TILE_FORMAT", record_tiles.TILE_FORMAT + 1)
    assert record_tiles.tile_token(db) != before


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


@pytest.mark.parametrize("path", ["1/2/0", "1/0/2", "23/0/0", "5/-1/0", "-1/0/0"])
def test_a_tile_off_the_map(client: TestClient, index: dict[str, int], path: str) -> None:
    """The same answer as a terrain tile off the map."""
    response = client.get(f"/tiles/records/{path}.mvt")
    assert response.status_code == 404
    assert error_code(response) == "tile_not_found"


def current_token(client: TestClient) -> str:
    [overlay] = [o for o in client.get("/api/v1/meta").json()["layers"]["overlays"] if o["type"] == "records"]
    [template] = overlay["tiles"]
    assert template.startswith("/tiles/records/{z}/{x}/{y}.mvt?v=")
    return template.rsplit("?v=", 1)[1]


def test_a_tile_with_the_current_token_is_immutable_and_answers_304(
    client: TestClient, index: dict[str, int]
) -> None:
    token = current_token(client)
    first = client.get("/tiles/records/0/0/0.mvt", params={"v": token})
    assert first.status_code == 200
    assert first.headers["cache-control"] == "public, max-age=31536000, immutable"
    etag = first.headers["etag"]
    again = client.get("/tiles/records/0/0/0.mvt", params={"v": token}, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    stale = client.get("/tiles/records/0/0/0.mvt", params={"v": "old"})
    assert stale.headers["cache-control"] == record_tiles.UNVERSIONED_CACHE
    assert stale.headers["etag"] == etag
    filtered = client.get("/tiles/records/0/0/0.mvt", params={"v": token, "category": "find"})
    assert filtered.headers["etag"] != etag


def test_a_completed_ingest_or_a_disabled_source_changes_the_token(client: TestClient, db: Session) -> None:
    before = current_token(client)
    run_connector(FakeConnector([record("A")]))
    after_ingest = current_token(client)
    assert after_ingest != before
    db.execute(update(Source).values(enabled=False))
    db.commit()
    assert current_token(client) not in (before, after_ingest)


def test_a_failed_run_that_stored_records_changes_the_token(client: TestClient, db: Session) -> None:
    """The runner commits batch by batch, so a run that fails part-way has still changed the tiles."""
    run_connector(FakeConnector([record("A")]))
    before = current_token(client)
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector([record("B"), RuntimeError("boom")]), batch_size=1)
    assert count(db, Record) == 2, "the failed run's first batch was kept"
    assert current_token(client) != before


def test_no_tile_is_immutable_while_a_run_is_going(client: TestClient, db: Session) -> None:
    """Each committed batch changes the tiles under the same token, so none can be kept."""
    add_source(db, "test-running")
    db.add(
        IngestRun(source_key="test-running", started_at=datetime.now(UTC), status=IngestStatus.RUNNING.value)
    )
    db.commit()
    token = current_token(client)
    response = client.get("/tiles/records/0/0/0.mvt", params={"v": token})
    assert response.status_code == 200
    assert response.headers["cache-control"] == record_tiles.UNVERSIONED_CACHE
    # The run ends, so the token moves on and its tiles can be kept again.
    db.execute(update(IngestRun).values(status=IngestStatus.FAILED.value, finished_at=datetime.now(UTC)))
    db.commit()
    settled = current_token(client)
    assert settled != token
    again = client.get("/tiles/records/0/0/0.mvt", params={"v": settled})
    assert again.headers["cache-control"] == record_tiles.IMMUTABLE_CACHE


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


def cells(tile: bytes) -> list[tuple[Any, ...]]:
    layer = mvt.decode(tile).get("record_counts")
    found = [] if layer is None else layer.features
    return sorted((f.first, *(f.properties[key] for key in ("category", "count", "sources"))) for f in found)


@pytest.mark.parametrize("z", range(record_tiles.FEATURES_FROM_ZOOM))
def test_stored_counts_match_counting_the_records(db: Session, z: int) -> None:
    """Every count zoom, around Avebury with records spread over several cells and a tile edge."""
    source = add_source(db)
    finds = add_source(db, "test-finds", name="Test finds", category="find")
    for step in range(40):
        lon, lat = -1.95 + step * 0.0071, 51.36 + (step % 7) * 0.013
        add_record(db, source if step % 3 else finds, f"Record {step}", lon, lat)
    record_tiles.refresh_counts(db)
    db.flush()
    x, y = tile_of(-1.85, 51.40, z)
    assert cells(record_tiles.record_tile(db, z, x, y)), "the tile in the middle has counts"
    for dx in (-1, 0, 1):
        if not 0 <= x + dx < 2**z:
            continue
        stored = record_tiles.record_tile(db, z, x + dx, y)
        live = db.execute(
            record_tiles._COUNTS,
            {"z": z, "x": x + dx, "y": y, "extent": record_tiles.EXTENT, "categories": None, "grid": 32},
        ).scalar()
        assert cells(stored) == cells(bytes(live) if live is not None else b"")


def test_an_ingest_run_refreshes_the_counts(client: TestClient, db: Session) -> None:
    def total() -> int:
        layers = get_tile(client, 6, *tile_of(-1.85, 51.43, 6))
        return sum(f.properties["count"] for f in layers["record_counts"].features) if layers else 0

    run_connector(FakeConnector([record("A"), record("B"), record("C")]))
    assert total() == 3
    run_connector(FakeConnector([record("A")]))
    assert total() == 1
    # A disabled source drops out at once, without a refresh.
    db.execute(update(Source).values(enabled=False))
    db.commit()
    assert total() == 0
