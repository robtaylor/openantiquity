from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Evidence
from fieldclub.services import findings, records
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Relation
from tests.findings.support import create
from tests.helpers import ClientAs, MakeFinding, MakeUser, add_record, add_source, error_code
from tests.records.support import OVERTON, SILBURY, SILBURY_MOUND, add_finds_source


@pytest.fixture
def index(db: Session) -> dict[str, int]:
    designations = add_source(db)
    finds = add_finds_source(db)
    made = {
        "silbury": add_record(
            db,
            designations,
            "Silbury Hill: a monumental Neolithic mound",
            geom=SILBURY_MOUND,
            record_type="Scheduled monument",
            url="https://historicengland.org.uk/listing/the-list/list-entry/1008445",
        ),
        "bowl": add_record(db, designations, "Bowl barrow on Overton Hill", *OVERTON),
        "coin": add_record(db, finds, "Roman coin", -1.8570, 51.4150, precision_m=1000),
    }
    db.commit()
    return {name: record.id for name, record in made.items()}


def assert_carries_its_source(item: dict) -> None:
    source = item["source"]
    assert source["key"] == item["source_key"]
    assert source["licence"]
    assert source["attribution"]
    assert source["reuse"] in ("open", "share_alike", "non_commercial", "link_only")


def test_search(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/records/search", params={"q": "silbury"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["name"].startswith("Silbury Hill")
    for item in items:
        assert_carries_its_source(item)


def test_search_filters_and_pages(client: TestClient, index: dict[str, int]) -> None:
    only_finds = client.get("/api/v1/records/search", params={"category": "find"}).json()["items"]
    assert [item["name"] for item in only_finds] == ["Roman coin"]
    by_source = client.get("/api/v1/records/search", params={"source": ["test-designations", "nope"]}).json()
    assert len(by_source["items"]) == 2
    first = client.get("/api/v1/records/search", params={"limit": 2}).json()
    assert first["next_cursor"]
    second = client.get("/api/v1/records/search", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [item["name"] for item in second["items"]] == ["Silbury Hill: a monumental Neolithic mound"]
    assert second["next_cursor"] is None
    boxed = client.get("/api/v1/records/search", params={"bbox": "-1.83,51.405,-1.82,51.415"}).json()
    assert [item["name"] for item in boxed["items"]] == ["Bowl barrow on Overton Hill"]


@pytest.mark.parametrize(
    "params",
    [
        {"q": "\x00\x00"},
        {"q": "silbury\u202e"},
        {"q": "' OR 1=1 --"},
        {"q": "a & b | !c <-> d:*"},
        {"q": "\\\\\\"},
        {"q": "😀 barrow"},
        {"q": "\u0130stanbul"},
    ],
)
def test_hostile_search_text_is_answered(client: TestClient, index: dict[str, int], params: dict) -> None:
    response = client.get("/api/v1/records/search", params=params)
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["items"], list)


def test_a_search_that_runs_out_of_time(
    client: TestClient, index: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(*args: object, **kwargs: object) -> None:
        raise records.SearchTimeoutError()

    monkeypatch.setattr(records, "search", too_slow)
    response = client.get("/api/v1/records/search", params={"q": "barrow"})
    assert response.status_code == 503
    assert error_code(response) == "search_timeout"


def test_too_long_a_search_is_refused(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/records/search", params={"q": "s" * 201})
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"bbox": "1,2,3"}, "invalid_bbox"),
        ({"bbox": "a,b,c,d"}, "invalid_bbox"),
        ({"bbox": "1,52,0,51"}, "invalid_bbox"),
        ({"bbox": "nan,51,0,52"}, "invalid_bbox"),
        ({"category": "nonsense"}, "validation_error"),
        ({"cursor": "WyJhIl0"}, "invalid_cursor"),
        # JSON true, which once read as offset 1.
        ({"cursor": "W3RydWVd"}, "invalid_cursor"),
        ({"cursor": "not-a-cursor"}, "invalid_cursor"),
        ({"limit": "0"}, "validation_error"),
    ],
)
def test_bad_search_parameters(client: TestClient, index: dict[str, int], params: dict, code: str) -> None:
    response = client.get("/api/v1/records/search", params=params)
    assert response.status_code in (400, 422)
    assert error_code(response) == code


def test_search_as_geojson_carries_the_licence_per_feature(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/records/search", params={"format": "geojson"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    for feature in body["features"]:
        properties = feature["properties"]
        assert properties["source_key"]
        assert properties["licence"]
        assert properties["attribution"]
        assert properties["reuse"]
        assert feature["geometry"]["type"] in ("Point", "Polygon")
    coin = next(f for f in body["features"] if f["properties"]["name"] == "Roman coin")
    assert coin["properties"]["reuse"] == "non_commercial"


def test_nearby(client: TestClient, index: dict[str, int]) -> None:
    response = client.get(
        "/api/v1/records/nearby", params={"lon": SILBURY[0], "lat": SILBURY[1], "radius": 1000}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items][:2] == [
        "Silbury Hill: a monumental Neolithic mound",
        "Roman coin",
    ]
    assert items[0]["distance_m"] == 0
    assert items[1]["distance_m"] > 0
    for item in items:
        assert_carries_its_source(item)
    exported = client.get(
        "/api/v1/records/nearby", params={"lon": SILBURY[0], "lat": SILBURY[1], "format": "geojson"}
    ).json()
    assert all("distance_m" in feature["properties"] for feature in exported["features"])


def test_nearby_needs_a_position(client: TestClient) -> None:
    assert client.get("/api/v1/records/nearby", params={"lon": 300, "lat": 51}).status_code == 422
    assert client.get("/api/v1/records/nearby", params={"lon": -1.8}).status_code == 422
    assert (
        client.get("/api/v1/records/nearby", params={"lon": -1, "lat": 51, "radius": 50_000}).status_code
        == 422
    )


def test_one_record(client: TestClient, index: dict[str, int]) -> None:
    response = client.get(f"/api/v1/records/{index['silbury']}")
    assert response.status_code == 200
    body = response.json()
    assert body["external_id"] == "test-designations-Silbury Hill: a monumental Neolithic mound"
    assert body["geometry"]["type"] == "Polygon"
    assert body["url"].startswith("https://historicengland.org.uk/")
    assert body["source"]["licence_url"].startswith("https://www.nationalarchives.gov.uk/")
    assert_carries_its_source(body)


def test_an_unknown_record(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/records/999999")
    assert response.status_code == 404
    assert error_code(response) == "record_not_found"
    assert client.get("/api/v1/records/0").status_code == 422
    assert client.get("/api/v1/records/99999999999999999999").status_code == 422


def test_sources(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    by_key = {source["key"]: source for source in response.json()}
    assert set(by_key) == {"test-designations", "test-finds"}
    finds = by_key["test-finds"]
    assert finds["reuse"] == "non_commercial"
    assert finds["access"] == "bulk"
    assert finds["record_count"] == 0
    assert finds["licence"]
    assert finds["attribution"]


# --------------------------------------------------------------------------
# Suggested records
# --------------------------------------------------------------------------


def test_suggested_records_for_an_open_finding(
    client: TestClient, make_finding: MakeFinding, index: dict[str, int]
) -> None:
    finding = make_finding(lon=SILBURY[0], lat=SILBURY[1], feature_class=FeatureClass.UNKNOWN)
    response = client.get(f"/api/v1/findings/{finding.public_id}/suggested-records")
    assert response.status_code == 200
    body = response.json()
    assert body["origin"] == {"lon": SILBURY[0], "lat": SILBURY[1], "obscured": False, "square": None}
    assert body["items"][0]["name"].startswith("Silbury Hill")
    assert body["items"][0]["distance_m"] == 0
    for item in body["items"]:
        assert_carries_its_source(item)
        assert 0 <= item["score"] <= 1


def test_suggested_records_never_reveal_an_exact_position(
    client: TestClient,
    client_as: ClientAs,
    make_finding: MakeFinding,
    make_user: MakeUser,
    index: dict[str, int],
) -> None:
    """A protected finding: the public may see its square, a member its position."""
    exact = (-1.8590, 51.4160)
    finding = make_finding(lon=exact[0], lat=exact[1], feature_class=FeatureClass.ROUND_BARROW)
    url = f"/api/v1/findings/{finding.public_id}/suggested-records"
    square = gridref.to_gridref(*exact, digits=4, compact=True)
    centre = gridref.centre_of_square(square)

    public = client.get(url).json()
    assert public["origin"]["obscured"] is True
    assert public["origin"]["square"] == square
    assert (public["origin"]["lon"], public["origin"]["lat"]) == pytest.approx(centre, abs=1e-6)
    text = str(public)
    for value in (f"{exact[0]:.4f}", f"{exact[1]:.4f}"):
        assert value not in text, "the exact position leaked into the public answer"

    # A member may see a protected finding's position.
    member = client_as(make_user()).get(url).json()
    assert member["origin"] == {"lon": exact[0], "lat": exact[1], "obscured": False, "square": None}

    # A restricted one is the square even for a member.
    restricted = make_finding(lon=exact[0], lat=exact[1], sensitivity="restricted")
    member_view = (
        client_as(make_user()).get(f"/api/v1/findings/{restricted.public_id}/suggested-records").json()
    )
    assert member_view["origin"]["obscured"] is True


def test_suggested_records_for_an_unknown_finding(client: TestClient) -> None:
    response = client.get("/api/v1/findings/ZZZZZZ/suggested-records")
    assert response.status_code == 404
    assert error_code(response) == "finding_not_found"


# --------------------------------------------------------------------------
# The findings linked to a record
# --------------------------------------------------------------------------


def _link(db: Session, finding, user, record_id: int):
    evidence, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        user,
        EvidenceFields(kind=EvidenceKind.RECORD_LINK, record_id=record_id, relation=Relation.SAME_AS),
    )
    db.commit()
    return evidence


def test_a_record_lists_the_findings_linked_to_it(
    client: TestClient, db: Session, index: dict[str, int], make_user: MakeUser
) -> None:
    finder = make_user()
    first = create(db, finder, title="Bank by the hill")
    second = create(db, finder, title="Second bank")
    unlinked = create(db, finder, title="Nothing to do with it")
    _link(db, first, finder, index["silbury"])
    _link(db, second, make_user(), index["silbury"])
    _link(db, second, make_user(), index["silbury"])
    _link(db, unlinked, finder, index["bowl"])
    response = client.get(f"/api/v1/records/{index['silbury']}/findings")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "public_id": found.public_id,
                "title": found.title,
                "feature_class": "enclosure",
                "tier": found.tier,
                "state": found.state,
            }
            for found in (first, second)
        ],
        "next_cursor": None,
    }
    page = client.get(f"/api/v1/records/{index['silbury']}/findings", params={"limit": 1}).json()
    assert [item["public_id"] for item in page["items"]] == [first.public_id]
    rest = client.get(
        f"/api/v1/records/{index['silbury']}/findings", params={"limit": 1, "cursor": page["next_cursor"]}
    ).json()
    assert ([item["public_id"] for item in rest["items"]], rest["next_cursor"]) == ([second.public_id], None)


def test_withdrawn_hidden_and_unlinked_findings_are_left_out(
    client: TestClient, client_as: ClientAs, db: Session, index: dict[str, int], make_user: MakeUser
) -> None:
    finder = make_user()
    withdrawn = create(db, finder)
    hidden = create(db, finder)
    taken_back = create(db, finder)
    for found in (withdrawn, hidden, taken_back):
        _link(db, found, finder, index["silbury"])
    findings.withdraw_finding(db, findings.lock(db, withdrawn), finder)
    hidden.hidden_at = datetime.now(UTC)
    removed = db.scalars(select(Evidence).where(Evidence.finding_id == taken_back.id)).one()
    findings.delete_evidence(db, removed.id, finder)
    db.commit()
    path = f"/api/v1/records/{index['silbury']}/findings"
    assert client.get(path).json()["items"] == []
    # The finder and moderators still see a hidden finding, as in every list.
    assert [item["public_id"] for item in client_as(finder).get(path).json()["items"]] == [hidden.public_id]
    assert [item["public_id"] for item in client_as(make_user("moderator")).get(path).json()["items"]] == [
        hidden.public_id
    ]


def test_an_unknown_records_findings(client: TestClient, index: dict[str, int]) -> None:
    response = client.get("/api/v1/records/999999/findings")
    assert (response.status_code, error_code(response)) == (404, "record_not_found")


def test_record_reads_are_the_same_for_everyone_and_cacheable_for_a_few_minutes(
    client: TestClient, index: dict[str, int]
) -> None:
    for path in (
        f"/api/v1/records/{index['silbury']}",
        "/api/v1/records/search?q=barrow",
        "/api/v1/records/search?q=barrow&format=geojson",
        "/api/v1/records/nearby?lon=-1.85&lat=51.41",
        "/api/v1/records/nearby?lon=-1.85&lat=51.41&format=geojson",
        "/api/v1/sources",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "public, max-age=300", path
    # An error is never cached as public.
    assert client.get("/api/v1/records/999999").headers["cache-control"].startswith("private")
