"""The undesignated parklands connector, end to end against the recorded layer.

The fixture is five parts of parks: Camerton Park, the two parts of Claverton
Manor, Lentongrove and Compton House. See `support.py` for how it was recorded.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.ne_historic_parklands_undesignated import (
    UndesignatedParklands,
    external_id,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from tests.connectors.land.support import RecordedService, no_wait, rows, worklist_entry

KEY = "ne-historic-parklands-undesignated"
HOST = "services.arcgis.com"
# Around Bath, which holds Camerton and Claverton.
BATH = (-2.5, 51.3, -2.3, 51.4)
HER = "Bath and North East Somerset HER"


def connector() -> UndesignatedParklands:
    parklands = UndesignatedParklands()
    parklands.polite = no_wait()
    return parklands


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is UndesignatedParklands


def test_the_source_carries_the_work_list_terms_unchanged() -> None:
    entry = worklist_entry(KEY)
    info = UndesignatedParklands.source
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    assert info.publisher == entry["publisher"]


@respx.mock
def test_a_run_stores_every_part_with_its_fields(db: Session) -> None:
    RecordedService("parklands.json").mount(HOST)
    run = run_connector(connector())
    assert run.stats is not None
    assert run.stats["seen"] == 5

    camerton = db.scalars(
        select(Record).where(Record.external_id == external_id("Camerton Park", "1", HER))
    ).one()
    assert camerton.name == "Camerton Park"
    assert camerton.category == "monument"
    assert camerton.record_type == "Historic parkland (undesignated)"
    assert camerton.summary is None  # the layer writes a space for no comment
    assert camerton.url is None
    assert camerton.source_updated_at == datetime(2025, 2, 21, tzinfo=UTC)
    assert camerton.geom is not None
    assert camerton.raw is not None
    assert camerton.raw["HE_Region"] == "SOUTH WEST"
    assert camerton.raw["Area_m2"] == 568675

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == 5
    assert source.licence == worklist_entry(KEY)["licence"]
    assert source.reuse == "open"


@respx.mock
def test_the_initials_of_those_who_drew_and_edited_it_are_not_kept(db: Session) -> None:
    RecordedService("parklands.json").mount(HOST)
    run_connector(connector())
    for record in db.scalars(select(Record)):
        assert record.raw is not None
        assert "Creator" not in record.raw
        assert "Editor" not in record.raw


@respx.mock
def test_two_parts_of_one_park_are_two_records(db: Session) -> None:
    RecordedService("parklands.json").mount(HOST)
    run_connector(connector())
    parts = db.scalars(select(Record).where(Record.name == "Claverton Manor")).all()
    assert len(parts) == 2
    assert {part.raw["Part_N"] for part in parts if part.raw} == {"1", "2"}
    assert parts[0].external_id != parts[1].external_id


@respx.mock
def test_a_comment_becomes_the_summary(db: Session) -> None:
    service = RecordedService("parklands.json")
    service.layers["0"]["features"][0]["attributes"]["Comment"] = "Name uncertain - taken from a settlement."
    service.mount(HOST)
    run_connector(connector())
    camerton = db.scalars(select(Record).where(Record.name == "Camerton Park")).one()
    assert camerton.summary == "Name uncertain - taken from a settlement."


def test_the_id_ignores_case_and_spacing() -> None:
    assert external_id("Camerton Park", "1", HER) == external_id("  camerton  PARK", "1", HER.upper())
    assert external_id("Camerton Park", "1", HER) != external_id("Camerton Park", "2", HER)
    assert external_id("Camerton Park", "1", HER) != external_id("Camerton Park", "1", "Somerset HER")


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    RecordedService("parklands.json").mount(HOST)
    first = run_connector(connector())
    before = rows(db)
    second = run_connector(connector())
    assert rows(db) == before
    assert len(before) == 5
    assert first.stats is not None
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 5, 0)


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    service = RecordedService("parklands.json")
    service.mount(HOST)
    run = run_connector(connector(), bbox=BATH)
    assert run.stats is not None
    assert not run.stats["full"]
    assert sorted(db.scalars(select(Record.name)).all()) == [
        "Camerton Park",
        "Claverton Manor",
        "Claverton Manor",
    ]
    assert all(query["geometry"] == "-2.5,51.3,-2.3,51.4" for query in service.queries)


@respx.mock
def test_two_parts_with_one_name_part_and_her_fail_the_run(db: Session) -> None:
    service = RecordedService("parklands.json")
    features = service.layers["0"]["features"]
    twin = copy.deepcopy(features[0])
    twin["attributes"]["OBJECTID"] = 9999
    features.append(twin)
    service.mount(HOST)
    with pytest.raises(
        IngestFailedError, match="Two parklands share the name, part and HER of 'Camerton Park'"
    ):
        run_connector(connector())


@respx.mock
def test_a_layer_that_changed_shape_fails_the_run(db: Session) -> None:
    service = RecordedService("parklands.json")
    service.layers["0"]["info"]["geometryType"] = "esriGeometryPoint"
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(connector())
    assert db.scalars(select(Record)).all() == []
