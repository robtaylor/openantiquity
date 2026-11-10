"""`GET /api/v1/meta` in the documented shape."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub import vocab
from fieldclub.auth import providers
from fieldclub.models import Source


@pytest.fixture
def meta(client: TestClient) -> dict:
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    return response.json()


def test_top_level_keys(meta: dict) -> None:
    assert list(meta) == ["app", "auth", "vocab", "layers", "sources", "notices"]


def test_app(meta: dict) -> None:
    assert meta["app"] == {"name": "Field Club", "version": "0.1.0", "contribution_licence": "CC BY 4.0"}


SIGN_IN_ORDER = [
    ("google", "Google"),
    ("apple", "Apple"),
    ("microsoft", "Microsoft"),
    ("facebook", "Facebook"),
    ("osm", "OpenStreetMap"),
    ("email", "Email link"),
]


def test_auth_lists_every_provider_in_order_and_none_enabled_until_configured(meta: dict) -> None:
    assert meta["auth"] == {
        "providers": [{"id": id_, "label": label, "enabled": False} for id_, label in SIGN_IN_ORDER]
    }
    assert all("guest" not in item["id"] for item in meta["auth"]["providers"])


def test_auth_marks_a_provider_enabled_only_while_its_settings_enable_it(client: TestClient) -> None:
    saved = dict(providers._providers)
    try:
        providers.register_provider("email", lambda settings: True)
        providers.register_provider("apple", lambda settings: True)
        providers.register_provider("google", lambda settings: True)
        providers.register_provider("osm", lambda settings: False)
        # The shape in docs/ARCHITECTURE.md, "The meta document".
        listed = client.get("/api/v1/meta").json()["auth"]["providers"]
        assert [(item["id"], item["label"]) for item in listed] == SIGN_IN_ORDER
        assert {item["id"]: item["enabled"] for item in listed} == {
            "google": True,
            "apple": True,
            "microsoft": False,
            "facebook": False,
            "osm": False,
            "email": True,
        }
    finally:
        providers._providers.clear()
        providers._providers.update(saved)


def test_vocab_has_exactly_the_documented_vocabularies(meta: dict) -> None:
    assert list(meta["vocab"]) == [
        "feature_classes",
        "periods",
        "evidence_kinds",
        "tiers",
        "states",
        "checks",
        "explanations",
        "mention_kinds",
        "record_categories",
        "report_reasons",
    ]


@pytest.mark.parametrize(
    ("name", "keys", "count"),
    [
        ("feature_classes", ["id", "label", "hint", "fish_term"], len(vocab.FeatureClass)),
        ("periods", ["id", "label", "hint"], len(vocab.Period)),
        ("evidence_kinds", ["id", "label", "strand", "group", "hint"], len(vocab.EvidenceKind)),
        ("tiers", ["id", "label", "description", "base_score"], len(vocab.Tier)),
        ("states", ["id", "label", "description"], len(vocab.FindingState)),
        ("checks", ["id", "question", "hint"], len(vocab.Check)),
        ("explanations", ["id", "label", "hint"], len(vocab.Explanation)),
        ("mention_kinds", ["id", "label"], len(vocab.MentionKind)),
        ("record_categories", ["id", "label", "colour"], len(vocab.RecordCategory)),
    ],
)
def test_each_vocabulary_has_the_documented_item_shape(
    meta: dict, name: str, keys: list[str], count: int
) -> None:
    items = meta["vocab"][name]
    assert len(items) == count
    for item in items:
        assert list(item) == keys
        assert all(value not in ("", None) for value in item.values())


def test_vocab_examples_from_the_contract(meta: dict) -> None:
    by_id = {name: {item["id"]: item for item in items} for name, items in meta["vocab"].items()}
    assert by_id["feature_classes"]["enclosure"]["label"] == "Enclosure"
    assert by_id["feature_classes"]["enclosure"]["fish_term"] == "ENCLOSURE"
    assert by_id["periods"]["iron_age"] == {"id": "iron_age", "label": "Iron Age", "hint": "800 BC to AD 43"}
    aerial = by_id["evidence_kinds"]["aerial"]
    assert (aerial["label"], aerial["strand"], aerial["group"]) == ("Aerial photo", "aerial", "desk")
    seen = by_id["tiers"]["seen"]
    assert (seen["label"], seen["base_score"]) == ("Seen by others", 30)
    assert by_id["states"]["known"]["label"] == "Matches a known record"
    assert by_id["checks"]["not_modern"]["question"] == "Could it be modern?"
    assert by_id["explanations"]["modern"]["label"] == "Modern feature"
    assert by_id["mention_kinds"]["video"] == {"id": "video", "label": "Video"}
    assert by_id["record_categories"]["designation"] == {
        "id": "designation",
        "label": "Designations",
        "colour": "#d9544d",
    }


def test_layers(meta: dict) -> None:
    layers = meta["layers"]
    assert list(layers) == ["views", "dem", "overlays", "initial_view"]
    assert [view["id"] for view in layers["views"]][:7] == [
        "composite",
        "local_relief",
        "sky_view",
        "multi_shade",
        "slope",
        "openness",
        "raking",
    ]
    composite = layers["views"][0]
    assert composite["tiles"][0].startswith("/tiles/lidar/composite/{z}/{x}/{y}.png?v=")
    assert (composite["bounds"], composite["default"]) == (None, True)
    raking = layers["views"][6]
    assert set(raking) == {
        "id",
        "title",
        "group",
        "type",
        "description",
        "attribution",
        "licence",
        "licence_url",
        "reuse",
    }
    assert layers["dem"]["encoding"] == "terrarium"
    assert [overlay["type"] for overlay in layers["overlays"]] == [
        "openmaptiles",
        "records",
        "findings",
        "coverage",
    ]
    assert set(layers["overlays"][2]) == {"id", "title", "type"}, "findings come through the API, not tiles"
    assert set(layers["overlays"][3]) == {"id", "title", "type"}
    assert layers["initial_view"] == {"center": [-1.8542, 51.4286], "zoom": 14}


def test_sources_is_empty_until_something_is_ingested(meta: dict) -> None:
    assert meta["sources"] == []


@pytest.fixture
def sources(db: Session) -> None:
    common = {"licence": "OGL v3.0", "access": "bulk", "reuse": "open"}
    db.add_all(
        [
            Source(
                key="nhle-scheduled",
                name="Scheduled monuments",
                publisher="Historic England",
                attribution="© Historic England",
                homepage="https://historicengland.org.uk/listing/the-list/",
                category="designation",
                record_count=19_900,
                **common,
            ),
            Source(
                key="fresh",
                name="Not ingested yet",
                publisher="Someone",
                attribution="© Someone",
                category="monument",
                **common,
            ),
            Source(
                key="switched-off",
                name="Disabled source",
                publisher="Nobody",
                attribution="none",
                category="find",
                enabled=False,
                **common,
            ),
        ]
    )
    db.commit()


def test_sources_lists_enabled_sources_with_attribution(sources: None, client: TestClient) -> None:
    """Each source carries what showing or copying its records needs, reuse class included (Decision 0004)."""
    listed = client.get("/api/v1/meta").json()["sources"]
    assert listed == [
        {
            "key": "fresh",
            "name": "Not ingested yet",
            "publisher": "Someone",
            "licence": "OGL v3.0",
            "licence_url": None,
            "attribution": "© Someone",
            "reuse": "open",
            "homepage": None,
            "coverage": None,
            "category": "monument",
            "access": "bulk",
            "record_count": 0,
            "last_ingest_at": None,
        },
        {
            "key": "nhle-scheduled",
            "name": "Scheduled monuments",
            "publisher": "Historic England",
            "licence": "OGL v3.0",
            "licence_url": None,
            "attribution": "© Historic England",
            "reuse": "open",
            "homepage": "https://historicengland.org.uk/listing/the-list/",
            "coverage": None,
            "category": "designation",
            "access": "bulk",
            "record_count": 19_900,
            "last_ingest_at": None,
        },
    ]


def test_meta_and_the_sources_list_describe_a_source_the_same_way(sources: None, client: TestClient) -> None:
    assert client.get("/api/v1/meta").json()["sources"] == client.get("/api/v1/sources").json()


def test_notices(meta: dict) -> None:
    notices = meta["notices"]
    assert list(notices) == ["field_visit", "field_visit_16_17", "sensitivity"]
    assert list(notices["field_visit"]) == ["england", "scotland", "wales", "northern_ireland"]
    for nation, lines in notices["field_visit"].items():
        assert lines == list(vocab.FIELD_VISIT_NOTICES[vocab.Nation(nation)])
        assert len(lines) >= 4
        assert all(isinstance(line, str) and line.endswith(".") for line in lines)
    assert notices["field_visit_16_17"] == vocab.FIELD_VISIT_NOTICE_16_17
    assert "adult" in notices["field_visit_16_17"]
    assert "one-kilometre" in notices["sensitivity"]
    assert "protected" in notices["sensitivity"]


def test_meta_needs_no_session_and_no_client_header(app) -> None:
    bare = TestClient(app, base_url="https://testserver")
    assert bare.get("/api/v1/meta").status_code == 200


def test_meta_is_described_in_the_openapi_schema(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    operation = schema["paths"]["/api/v1/meta"]["get"]
    assert operation["operationId"] == "meta_get_meta"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Meta"
    }
    auth = schema["components"]["schemas"]["AuthInfo"]
    assert list(auth["properties"]) == ["providers"]
    assert auth["properties"]["providers"]["items"] == {"$ref": "#/components/schemas/ProviderOut"}
    assert list(schema["components"]["schemas"]["ProviderOut"]["properties"]) == ["id", "label", "enabled"]
    assert "tiles" not in schema["components"]["schemas"]["FindingsOverlay"]["properties"]
    views = schema["components"]["schemas"]["Layers"]["properties"]["views"]["items"]
    assert {ref["$ref"].rsplit("/", 1)[-1] for ref in views["oneOf"]} == {"RasterView", "RakingView"}
    assert views["discriminator"]["propertyName"] == "type"
