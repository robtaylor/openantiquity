"""What every Historic England ArcGIS connector must do, through the real runner and the recorded layers."""

from __future__ import annotations

import json
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.base import Connector
from fieldclub.ingest.connectors.he_aim_detailed_mapping import DetailedMapping
from fieldclub.ingest.connectors.he_aim_monument_extents import MonumentExtents
from fieldclub.ingest.connectors.he_aim_project_areas import ProjectAreas
from fieldclub.ingest.connectors.he_de_designated_sites import DeDesignatedSites
from fieldclub.ingest.connectors.he_greater_london_apas import GreaterLondonApas
from fieldclub.ingest.connectors.he_heritage_at_risk_2026 import HeritageAtRisk2026
from fieldclub.ingest.connectors.he_research_spatial_reports import ResearchSpatialReports
from fieldclub.ingest.connectors.he_turning_the_plough_2 import TurningThePlough2
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from tests.connectors.he.support import FIXTURES, fixture, serve, worklist_entry

CONNECTORS: dict[str, type[Connector]] = {
    "he-aim-detailed-mapping": DetailedMapping,
    "he-aim-monument-extents": MonumentExtents,
    "he-aim-project-areas": ProjectAreas,
    "he-heritage-at-risk-2026": HeritageAtRisk2026,
    "he-research-spatial-reports": ResearchSpatialReports,
    "he-turning-the-plough-2": TurningThePlough2,
    "he-de-designated-sites": DeDesignatedSites,
    "he-greater-london-apas": GreaterLondonApas,
}
KEYS = list(CONNECTORS)


def rows(db: Session) -> list[tuple[Any, ...]]:
    """Every stored record, in a form two runs can be compared by."""
    db.expire_all()
    return [
        (
            record.id,
            record.external_id,
            record.name,
            record.summary,
            record.category,
            record.record_type,
            record.monument_types,
            record.periods,
            record.url,
            record.source_updated_at,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in db.scalars(select(Record).order_by(Record.external_id)).all()
    ]


@pytest.mark.parametrize("key", KEYS)
def test_the_connector_is_registered_under_its_work_list_key(key: str) -> None:
    assert registry.get(key) is CONNECTORS[key]


@pytest.mark.parametrize("key", KEYS)
def test_the_source_carries_the_work_list_licence_and_attribution(key: str) -> None:
    entry = worklist_entry(key)
    info = CONNECTORS[key].source
    assert info.key == entry["key"]
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.publisher in entry["publisher"]
    assert info.access == "bulk"


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_a_run_stores_every_feature_the_layer_gave(key: str, db: Session) -> None:
    layer = serve(key)
    run = run_connector(CONNECTORS[key]())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == len(layer.features) > 0
    assert run.stats["duplicates"] == 0
    stored = db.scalars(select(Record)).all()
    assert len(stored) == len(layer.features)
    assert {record.source_key for record in stored} == {key}
    source = db.get(Source, key)
    assert source is not None
    assert source.record_count == len(layer.features)
    assert source.attribution.startswith("©")
    assert all(record.name.strip() and record.raw for record in stored)


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_running_twice_gives_the_same_rows(key: str, db: Session) -> None:
    serve(key)
    run_connector(CONNECTORS[key]())
    before = rows(db)
    second = run_connector(CONNECTORS[key]())
    assert rows(db) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)
    assert second.stats["updated"] == len(before)


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_a_partial_run_by_bbox_asks_the_server_for_the_box_and_deletes_nothing(key: str, db: Session) -> None:
    layer = serve(key)
    run_connector(CONNECTORS[key]())
    stored = len(db.scalars(select(Record)).all())
    lon, lat = db.execute(
        select(Record.centroid.ST_X(), Record.centroid.ST_Y()).order_by(Record.id)
    ).first() or (
        0,
        0,
    )
    layer.queries.clear()
    box = (lon - 0.0001, lat - 0.0001, lon + 0.0001, lat + 0.0001)
    run = run_connector(CONNECTORS[key](), bbox=box)
    assert run.stats is not None
    assert not run.stats["full"]
    assert 1 <= run.stats["seen"] <= stored
    assert {query["geometry"] for query in layer.queries if "geometry" in query} == {
        ",".join(repr(value) for value in box)
    }
    assert len(db.scalars(select(Record)).all()) == stored


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_a_layer_that_changed_shape_fails_the_run_and_writes_nothing(key: str, db: Session) -> None:
    layer = serve(key)
    renamed = layer.info["fields"][1]
    renamed["name"] = renamed["name"] + "_RENAMED"
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(CONNECTORS[key]())
    assert db.scalars(select(Record)).all() == []


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_a_layer_of_another_geometry_type_fails_the_run(key: str, db: Session) -> None:
    layer = serve(key)
    layer.info["geometryType"] = "esriGeometryPolyline"
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(CONNECTORS[key]())
    assert db.scalars(select(Record)).all() == []


@pytest.mark.parametrize("key", KEYS)
@respx.mock
def test_a_truncated_answer_fails_the_run_instead_of_looking_complete(key: str, db: Session) -> None:
    serve(key, count_adds=5)
    with pytest.raises(IngestFailedError, match="said it had"):
        run_connector(CONNECTORS[key]())


@pytest.mark.parametrize("key", KEYS)
def test_every_fixture_is_small_and_in_wgs84(key: str) -> None:
    assert (FIXTURES / f"{key}.json").stat().st_size < 150_000
    recorded = fixture(key)
    assert recorded["spatialReference"]["wkid"] == 4326
    assert recorded["recorded"] == "2026-11-10"


@pytest.mark.parametrize(
    "key", ["he-aim-detailed-mapping", "he-aim-monument-extents", "he-greater-london-apas"]
)
@respx.mock
def test_a_sliver_too_small_to_keep_its_shape_is_left_out_and_the_rest_stored(key: str, db: Session) -> None:
    layer = serve(key)
    point = layer.features[0]["geometry"]["rings"][0][0]
    layer.features[0]["geometry"] = {"rings": [[point] * 4]}
    run = run_connector(CONNECTORS[key]())
    assert run.status == "completed"
    assert len(db.scalars(select(Record)).all()) == len(layer.features) - 1
