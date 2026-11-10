"""The map's search box. Places are made here rather than loaded from the gazetteer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Place, User
from fieldclub.models.common import db_point
from fieldclub.services import records, search
from fieldclub.vocab import FeatureClass
from tests.helpers import AVEBURY, ClientAs, MakeFinding, MakeUser, add_record, add_source
from tests.records.support import SILBURY_MOUND


def add_place(db: Session, name: str, lon: float, lat: float, kind: str = "Village", rank: int = 1) -> Place:
    place = Place(
        name=name,
        kind=kind,
        county="Wiltshire",
        nation="england",
        geom=db_point(lon, lat),
        rank=rank,
        source="test",
    )
    db.add(place)
    db.flush()
    return place


@pytest.fixture
def gazetteer(db: Session) -> None:
    add_place(db, "Avebury", *AVEBURY, rank=3)
    add_place(db, "Avebury Trusloe", -1.8670, 51.4260)
    add_place(db, "Aveton Gifford", -3.8410, 50.3070)
    add_place(db, "Swindon", -1.7797, 51.5558, kind="Town", rank=8)
    source = add_source(db)
    add_record(db, source, "Silbury Hill", geom=SILBURY_MOUND, record_type="Scheduled monument")
    add_record(db, source, "Avebury henge and stone circles", *AVEBURY)
    db.commit()


def types(hits: list[search.GeoHit]) -> list[str]:
    return [hit.type for hit in hits]


@pytest.mark.parametrize(
    ("query", "label", "zoom"),
    [
        ("SU 1025 6996", "SU 1025 6996", 17),
        ("su10256996", "SU 1025 6996", 17),
        ("SU16", "SU 1 6", 11),
        ("SU1069", "SU 10 69", 14),
        ("J 338 740", "J 338 740", 16),
    ],
)
def test_grid_references(db: Session, query: str, label: str, zoom: int) -> None:
    [hit] = search.geo_search(db, query, None)
    assert hit.type == "gridref"
    assert hit.label == label
    assert hit.zoom == zoom
    assert hit.bbox is not None
    west, south, east, north = hit.bbox
    assert west < hit.lon < east
    assert south < hit.lat < north


@pytest.mark.parametrize(
    "query",
    ["51.4286, -1.8542", "51.4286 -1.8542", "-1.8542, 51.4286", "51.4286N 1.8542W", "1.8542W, 51.4286N"],
)
def test_latitude_and_longitude_in_either_order(db: Session, query: str) -> None:
    [hit] = search.geo_search(db, query, None)
    assert hit.type == "coordinates"
    assert (hit.lon, hit.lat) == pytest.approx((-1.8542, 51.4286))
    assert hit.detail is not None
    assert hit.detail.startswith("SU ")


def test_coordinates_outside_britain_are_taken_latitude_first(db: Session) -> None:
    [hit] = search.geo_search(db, "40.7, -74.0", None)
    assert (hit.lat, hit.lon) == (40.7, -74.0)
    assert hit.detail is None
    assert search.geo_search(db, "95, 10", None) == []


def test_eastings_and_northings(db: Session) -> None:
    [hit] = search.geo_search(db, "410132 170023", None)
    assert hit.type == "coordinates"
    assert (hit.lon, hit.lat) == pytest.approx(gridref.to_lonlat(gridref.GridSystem.OSGB, 410132, 170023))


def test_places_prefix_first_then_bigger(db: Session, gazetteer: None) -> None:
    hits = search.geo_search(db, "avebury", None)
    places = [hit.label for hit in hits if hit.type == "place"]
    assert places[:2] == ["Avebury", "Avebury Trusloe"]
    assert hits[0].detail == "Wiltshire"
    # A half-typed name finds the place.
    assert next(hit.label for hit in search.geo_search(db, "aveb", None) if hit.type == "place") == "Avebury"
    # So does a misspelt one.
    assert "Swindon" in [hit.label for hit in search.geo_search(db, "swindom", None)]
    assert next(hit for hit in search.geo_search(db, "swindon", None) if hit.type == "place").zoom == 13


def test_places_come_before_records(db: Session, gazetteer: None) -> None:
    hits = search.geo_search(db, "avebury", None)
    assert types(hits).index("place") < types(hits).index("record")
    record = next(hit for hit in hits if hit.type == "record")
    assert record.label == "Avebury henge and stone circles"
    assert record.ref is not None


def test_a_record_by_name(db: Session, gazetteer: None) -> None:
    [hit] = search.geo_search(db, "silbury", None)
    assert hit.type == "record"
    assert hit.detail == "Scheduled monument · Test designations"
    assert hit.bbox is not None


def test_a_finding_by_public_id(db: Session, make_finding: MakeFinding) -> None:
    finding = make_finding(lon=-1.8, lat=51.4)
    hits = search.geo_search(db, finding.public_id.lower(), None)
    assert hits[0].type == "finding"
    assert hits[0].ref == finding.public_id
    assert (hits[0].lon, hits[0].lat) == (-1.8, 51.4)
    assert hits[0].zoom == 16  # from the finding's view state
    assert not hits[0].obscured


def test_a_protected_finding_is_placed_at_its_square(
    client: TestClient, client_as: ClientAs, make_finding: MakeFinding, make_user: MakeUser
) -> None:
    exact = (-1.8590, 51.4160)
    finding = make_finding(lon=exact[0], lat=exact[1], feature_class=FeatureClass.ROUND_BARROW)
    public = client.get("/api/v1/geo/search", params={"q": finding.public_id}).json()["items"][0]
    assert public["type"] == "finding"
    assert public["obscured"] is True
    square = gridref.to_gridref(*exact, digits=4, compact=True)
    assert (public["lon"], public["lat"]) == pytest.approx(gridref.centre_of_square(square), abs=1e-6)
    assert public["bbox"] is not None
    member = (
        client_as(make_user()).get("/api/v1/geo/search", params={"q": finding.public_id}).json()["items"][0]
    )
    assert (member["lon"], member["lat"]) == exact
    assert member["obscured"] is False


def test_a_hidden_finding_is_not_found(db: Session, make_finding: MakeFinding) -> None:
    finding = make_finding(hidden_at=datetime(2026, 11, 1, tzinfo=UTC))
    assert "finding" not in types(search.geo_search(db, finding.public_id, None))


def test_a_withdrawn_finding_is_left_out_as_the_findings_list_leaves_it_out(
    db: Session, make_finding: MakeFinding
) -> None:
    finding = make_finding(state="withdrawn")
    assert "finding" not in types(search.geo_search(db, finding.public_id, db.get(User, finding.author_id)))


def test_places_and_records_share_one_time_limit(
    db: Session, gazetteer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow place query is cancelled like a slow record query, and the exact hits still come back."""
    import time

    from sqlalchemy import func, select

    def slow_places(db: Session, text: str) -> list[search.GeoHit]:
        db.execute(select(func.pg_sleep(2)))
        return []

    monkeypatch.setattr(records, "SEARCH_TIMEOUT_MS", 100)
    monkeypatch.setattr(search, "places", slow_places)
    started = time.monotonic()
    hits = search.geo_search(db, "SU 1025 6996", None)
    assert time.monotonic() - started < 1.5
    assert types(hits) == ["gridref"]
    # The session is still usable.
    assert types(search.geo_search(db, "SU 1025 6996", None)) == ["gridref"]


@pytest.mark.parametrize(
    "query", ["", "   ", "\x00", "'; --", "& | !", "\u202e", "SU", "SU 12 3", "\u0130", "\u0130stanbul"]
)
def test_odd_queries_give_nothing_or_names(db: Session, gazetteer: None, query: str) -> None:
    hits = search.geo_search(db, query, None)
    assert all(hit.type in ("place", "record") for hit in hits)


def test_the_endpoint(client: TestClient, gazetteer: None) -> None:
    response = client.get("/api/v1/geo/search", params={"q": "SU 1025 6996"})
    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item["type"] == "gridref"
    assert len(item["bbox"]) == 4
    assert item["source"] is None
    record = next(item for item in client.get("/api/v1/geo/search", params={"q": "silbury"}).json()["items"])
    assert record["type"] == "record"
    assert record["source"]["key"] == "test-designations"
    assert record["source"]["licence"]
    assert record["source"]["attribution"]
    assert record["source"]["reuse"] == "open"
    assert client.get("/api/v1/geo/search", params={"q": ""}).status_code == 422
    assert client.get("/api/v1/geo/search", params={"q": "x" * 201}).status_code == 422
    # Lower-casing a Turkish dotted I adds a combining mark, which once failed an assertion.
    assert client.get("/api/v1/geo/search", params={"q": "\u0130"}).status_code == 200
    assert (
        client.get("/api/v1/geo/search", params={"q": "avebury", "limit": 2}).json()["items"][1]["type"]
        == "place"
    )


def test_a_record_search_that_runs_out_of_time_leaves_the_rest(
    db: Session, gazetteer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(*args: object, **kwargs: object) -> None:
        raise records.SearchTimeoutError()

    monkeypatch.setattr(records, "search", too_slow)
    hits = search.geo_search(db, "avebury", None)
    assert hits
    assert {hit.type for hit in hits} == {"place"}


def test_a_monument_named_exactly_comes_before_places_named_after_it(db: Session) -> None:
    """With the gazetteer loaded, a search for a monument once opened with five places named after it."""
    add_place(db, "Stonehenge Works", -0.62, 52.05, kind="Other Settlement", rank=480)
    add_place(db, "Stonehenge Down", -1.83, 51.18, kind="Hill Or Mountain", rank=240)
    add_place(db, "Maiden Castle Wood", -2.0, 50.7, kind="Woodland Or Forest", rank=240)
    add_place(db, "Castle Eden", -1.35, 54.74, kind="Village", rank=750)
    source = add_source(db)
    add_record(db, source, "STONEHENGE", -1.8262, 51.1789)
    add_record(db, source, "Maiden Castle", -2.4637, 50.6944)
    add_record(db, source, "Grim's Ditch", -1.43, 51.55)
    db.commit()
    assert [hit.label for hit in search.geo_search(db, "Stonehenge", None)][:3] == [
        "STONEHENGE",
        "Stonehenge Works",
        "Stonehenge Down",
    ]
    labels = [hit.label for hit in search.geo_search(db, "maiden castle", None)]
    assert labels[:2] == ["Maiden Castle", "Maiden Castle Wood"]
    assert labels.index("Castle Eden") > 1
    assert search.geo_search(db, "Grim's Ditch", None)[0].label == "Grim's Ditch"


def test_a_place_still_comes_before_a_record_named_alike(db: Session, gazetteer: None) -> None:
    hits = search.geo_search(db, "aveb", None)
    labels = [hit.label for hit in hits]
    assert labels[:3] == ["Avebury", "Avebury Trusloe", "Avebury henge and stone circles"]


def test_loose_matches_come_by_likeness_whatever_their_type(db: Session) -> None:
    add_place(db, "Silverly Hill", -1.9, 51.4, rank=750)
    add_record(db, add_source(db), "Silbury Hill", -1.8571, 51.4156)
    db.commit()
    assert [hit.label for hit in search.geo_search(db, "silbery hill", None)] == [
        "Silbury Hill",
        "Silverly Hill",
    ]


def test_a_place_carries_its_source(db: Session, client: TestClient) -> None:
    add_source(db, "os-open-names", name="OS Open Names", category="place", attribution="Contains OS data")
    add_place(db, "Avebury", *AVEBURY).source = "os-open-names"
    db.commit()
    [item] = client.get("/api/v1/geo/search", params={"q": "avebury"}).json()["items"]
    assert item["type"] == "place"
    assert item["source"]["key"] == "os-open-names"
    assert item["source"]["attribution"] == "Contains OS data"


def test_a_place_search_that_runs_out_of_time_gives_no_places(
    db: Session, gazetteer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def too_slow(db: Session, milliseconds: int = records.SEARCH_TIMEOUT_MS) -> Iterator[None]:
        raise records.SearchTimeoutError()
        yield

    monkeypatch.setattr(records, "time_limit", too_slow)
    assert search.places(db, "avebury") == []


def test_places_alike_by_spelling_are_ranked_from_a_capped_few(
    db: Session, gazetteer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert len(search.places(db, "avebery")) == 2
    monkeypatch.setattr(search, "PLACE_CANDIDATES", 1)
    assert len(search.places(db, "avebery")) == 1
