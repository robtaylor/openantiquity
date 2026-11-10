"""The City of York HER connector, end to end against the recorded map service.

The fixture is six monuments with all their parts: 20 features across the
point, line and area layers. MYO2076 is ten stretches of one sewer, MYO1004 is
a point and two outlines, MYO167 has a part in each layer. See `support.py`.
"""

from __future__ import annotations

import pytest
import respx
from shapely import wkb
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors import york_her_monuments
from fieldclub.ingest.connectors.york_her_monuments import YorkHerMonuments
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.land.support import RecordedService, no_wait, rows, worklist_entry

KEY = "york-her-monuments"
HOST = "maps.york.gov.uk"
# The Roman centre of York: Eboracum, the walls tower, the church and the sewer, not Siwards How.
CENTRE = (-1.09, 53.955, -1.07, 53.965)
# A few metres around the point of the Poppleton fishponds, whose line and outline run further.
FISHPONDS = (-1.1407, 53.9896, -1.1405, 53.9898)


def connector() -> YorkHerMonuments:
    york = YorkHerMonuments()
    york.polite = no_wait()
    return york


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is YorkHerMonuments


def test_the_source_carries_the_work_list_terms_unchanged() -> None:
    entry = worklist_entry(KEY)
    info = YorkHerMonuments.source
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    assert info.publisher == entry["publisher"]


@respx.mock
def test_a_run_stores_a_record_per_monument_not_per_part(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    run = run_connector(connector())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == 6
    assert run.stats["duplicates"] == 0
    assert db.get(Source, KEY).record_count == 6  # type: ignore[union-attr]
    assert {record.external_id for record in db.scalars(select(Record))} == {
        "MYO1",
        "MYO104",
        "MYO1004",
        "MYO1090",
        "MYO167",
        "MYO2076",
    }


@respx.mock
def test_the_fields_of_a_monument(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    run_connector(connector())
    eboracum = db.scalars(select(Record).where(Record.external_id == "MYO1")).one()
    assert eboracum.name == "Eboracum (Roman York)"
    assert eboracum.category == "monument"
    assert eboracum.record_type == "Monument"
    assert eboracum.monument_types == ["SETTLEMENT", "MUNICIPIUM", "COLONIA"]
    assert eboracum.url == "https://her.york.gov.uk/monument/MYO1"
    assert eboracum.summary is None
    lon, lat = point_lon_lat(eboracum.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-1.085, 53.961)
    assert eboracum.raw == {
        "MonUID": "MYO1",
        "RecordType": "MON",
        "Name": "Eboracum (Roman York)",
        "MonType": "SETTLEMENT; MUNICIPIUM; COLONIA",
        "URL": "https://her.york.gov.uk/monument/MYO1",
        "parts": 1,
    }


@respx.mock
def test_repeated_terms_are_listed_once_and_codes_without_a_meaning_are_kept(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    run_connector(connector())
    church = db.scalars(select(Record).where(Record.external_id == "MYO1004")).one()
    assert church.record_type == "Building"
    assert church.monument_types is not None
    assert church.monument_types.count("PARISH CHURCH") == 1
    assert church.monument_types[:2] == ["GRAVE SLAB", "PARISH CHURCH"]
    tower = db.scalars(select(Record).where(Record.external_id == "MYO1090")).one()
    assert tower.record_type is None  # the layer gives this one no record type


@respx.mock
def test_the_parts_of_a_monument_are_one_geometry(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    run_connector(connector())
    kinds = {
        record.external_id: (wkb.loads(bytes(record.geom.data)).geom_type, record.raw["parts"])  # type: ignore[index]
        for record in db.scalars(select(Record))
    }
    assert kinds["MYO1"] == ("Point", 1)
    assert kinds["MYO1004"] == ("GeometryCollection", 3)  # a point and two outlines
    assert kinds["MYO167"] == ("GeometryCollection", 3)  # a point, a line and an outline
    assert kinds["MYO2076"] == ("GeometryCollection", 10)  # ten stretches of one sewer


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    first = run_connector(connector())
    before = rows(db)
    second = run_connector(connector())
    assert rows(db) == before
    assert len(before) == 6
    assert first.stats is not None
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 6, 0)


@respx.mock
def test_the_layers_are_read_by_id_range_because_the_area_layer_pages_short(db: Session) -> None:
    service = RecordedService("york_her.json")
    service.short_offset_pages = True
    service.phantom_ids = {"5": [90001, 90002, 90003]}
    service.mount(HOST)
    run = run_connector(connector())
    assert run.stats is not None
    assert run.stats["seen"] == 6
    assert not any("resultOffset" in query for query in service.queries)
    sewer = db.scalars(select(Record).where(Record.external_id == "MYO2076")).one()
    assert sewer.raw is not None
    assert sewer.raw["parts"] == 10


@respx.mock
def test_a_partial_run_by_bbox_finds_whole_monuments(db: Session) -> None:
    RecordedService("york_her.json").mount(HOST)
    run = run_connector(connector(), bbox=CENTRE)
    assert run.stats is not None
    assert not run.stats["full"]
    assert {record.external_id for record in db.scalars(select(Record))} == {
        "MYO1",
        "MYO1004",
        "MYO1090",
        "MYO2076",
    }


@respx.mock
def test_a_partial_run_never_stores_a_monument_cut_short_at_the_box(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordedService("york_her.json").mount(HOST)
    run_connector(connector())
    full = {row[2]: row for row in rows(db)}
    # One monument at a time, so the parts are asked for in more than one query.
    monkeypatch.setattr(york_her_monuments, "ID_CHUNK", 1)
    service = RecordedService("york_her.json")
    respx.mock.routes.clear()
    service.mount(HOST)
    run_connector(connector(), bbox=FISHPONDS)
    partial = {row[2]: row for row in rows(db)}
    assert partial == full  # the same six rows, the fishponds read again and unchanged
    assert any("MonUID IN ('MYO167')" in query["where"] for query in service.queries)
    row = full["MYO167"]
    assert '"parts": 3' in row[-1]


@respx.mock
def test_the_layer_metadata_is_fetched_once_however_many_chunks_a_partial_run_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(york_her_monuments, "ID_CHUNK", 1)
    service = RecordedService("york_her.json")
    service.mount(HOST)
    run_connector(connector(), bbox=CENTRE)
    assert sorted(service.info_requests) == ["3", "4", "5"]


@respx.mock
def test_parts_that_disagree_about_the_monument_fail_the_run(db: Session) -> None:
    service = RecordedService("york_her.json")
    sewer = service.layers["4"]["features"][-1]
    sewer["attributes"]["Name"] = "Another sewer"
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match="MYO2076 has parts with different values of Name"):
        run_connector(connector())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_service_that_changed_shape_fails_the_run(db: Session) -> None:
    service = RecordedService("york_her.json")
    service.layers["5"]["info"]["geometryType"] = "esriGeometryPoint"
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(connector())
    assert db.scalars(select(Record)).all() == []
