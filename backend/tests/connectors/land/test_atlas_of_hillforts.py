"""The Atlas of Hillforts connector, end to end against the recorded layer.

The fixture is six hillforts: three from Herefordshire, and one each from
Scotland, Wales and Ireland. See `support.py` for how it was recorded.
"""

from __future__ import annotations

import copy

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.oxford_edinburgh_atlas_of_hillforts import AtlasOfHillforts
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.land.support import RecordedService, no_wait, rows, worklist_entry

KEY = "oxford-edinburgh-atlas-of-hillforts"
HOST = "services1.arcgis.com"
# Herefordshire, around Aconbury, Bach and Backbury camps.
HEREFORDSHIRE = (-2.8, 51.9, -2.5, 52.3)


def connector() -> AtlasOfHillforts:
    atlas = AtlasOfHillforts()
    atlas.polite = no_wait()
    return atlas


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is AtlasOfHillforts


def test_the_source_carries_the_work_list_terms_unchanged() -> None:
    entry = worklist_entry(KEY)
    info = AtlasOfHillforts.source
    assert info.licence == entry["licence"] == "CC BY-SA 4.0"
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "share_alike"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    assert info.publisher == entry["publisher"]


@respx.mock
def test_a_run_stores_every_hillfort_with_its_fields(db: Session) -> None:
    RecordedService("atlas_of_hillforts.json").mount(HOST)
    run = run_connector(connector())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == 6

    aconbury = db.scalars(select(Record).where(Record.external_id == "1")).one()
    assert aconbury.source_key == KEY
    assert aconbury.name == "Aconbury Camp"
    assert aconbury.category == "monument"
    assert aconbury.record_type == "Hillfort"
    assert aconbury.monument_types == ["Partial contour fort", "Promontory fort"]
    assert aconbury.periods == ["iron_age", "roman"]
    assert aconbury.summary is not None
    assert aconbury.summary.startswith("Large, wooded, univallate, partial contour hillfort")
    assert aconbury.url == "https://hillforts.arch.ox.ac.uk/records/EN0001.html"
    assert aconbury.precision_m is None
    lon, lat = point_lon_lat(aconbury.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-2.725, 51.994)
    assert aconbury.raw is not None
    assert aconbury.raw["HER_Primary_Record_Number"] == "MHE413"
    assert aconbury.raw["Scheduled_Monument_Number"] == "1001754"

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == 6
    assert source.reuse == "share_alike"
    assert source.licence == "CC BY-SA 4.0"
    assert source.attribution == worklist_entry(KEY)["attribution"]


@respx.mock
def test_dating_spans_map_onto_periods(db: Session) -> None:
    RecordedService("atlas_of_hillforts.json").mount(HOST)
    run_connector(connector())
    periods = {r.external_id: r.periods for r in db.scalars(select(Record))}
    assert periods["2"] == ["unknown"]  # dating evidence of "Unknown"
    assert periods["71"] == ["iron_age", "roman"]  # 400 BC to AD 400
    assert periods["671"] == ["iron_age", "early_medieval"]  # 400 BC to AD 800, Ireland


@respx.mock
def test_the_raw_payload_keeps_what_is_there_and_drops_blanks(db: Session) -> None:
    RecordedService("atlas_of_hillforts.json").mount(HOST)
    run_connector(connector())
    carghidown = db.scalars(select(Record).where(Record.external_id == "229")).one()
    assert carghidown.raw is not None
    assert carghidown.raw["Country"] == "Scotland"
    assert carghidown.raw["Dating_Evidence__Reliability"] == "B - Medium"
    assert "Alternative_Name_s_" not in carghidown.raw  # blank for this hillfort
    assert all(value is not None and value != "" for value in carghidown.raw.values())


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    RecordedService("atlas_of_hillforts.json").mount(HOST)
    first = run_connector(connector())
    before = rows(db)
    second = run_connector(connector())
    assert rows(db) == before
    assert len(before) == 6
    assert first.stats is not None
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 6, 0)


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    service = RecordedService("atlas_of_hillforts.json")
    service.mount(HOST)
    run = run_connector(connector(), bbox=HEREFORDSHIRE)
    assert run.stats is not None
    assert not run.stats["full"]
    assert set(db.scalars(select(Record.external_id)).all()) == {"1", "2", "3"}
    assert all(query["geometry"] == "-2.8,51.9,-2.5,52.3" for query in service.queries)


@respx.mock
def test_two_hillforts_with_one_atlas_number_fail_the_run(db: Session) -> None:
    service = RecordedService("atlas_of_hillforts.json")
    features = service.layers["0"]["features"]
    twin = copy.deepcopy(features[0])
    twin["attributes"]["OBJECTID"] = 99
    features.append(twin)
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match="Atlas number 1 is used by two hillforts"):
        run_connector(connector())


@respx.mock
def test_a_layer_that_changed_shape_fails_the_run(db: Session) -> None:
    service = RecordedService("atlas_of_hillforts.json")
    for field in service.layers["0"]["info"]["fields"]:
        if field["name"] == "Atlas_Number":
            field["name"] = "Atlas_No"
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match=r"changed shape: missing fields \['Atlas_Number'\]"):
        run_connector(connector())
    assert db.scalars(select(Record)).all() == []
