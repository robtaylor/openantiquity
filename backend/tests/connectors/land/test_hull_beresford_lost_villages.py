"""The Lost Villages connector, end to end against the recorded layer.

The fixture is six sites: two different places both called Astwick, Cainhoe,
Landwade, Nuthill (which shares the layer's `ID` number with Landwade) and
Etonbury. See `support.py` for how it was recorded.
"""

from __future__ import annotations

import copy

import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.hull_beresford_lost_villages import (
    BeresfordLostVillages,
    external_id,
    placed,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.land.support import RecordedService, no_wait, rows, worklist_entry

KEY = "hull-beresford-lost-villages"
HOST = "services2.arcgis.com"
# Bedfordshire: the Astwick, Cainhoe and Etonbury of the Bedfordshire list.
BEDFORDSHIRE = (-0.5, 52.0, -0.2, 52.1)


def connector() -> BeresfordLostVillages:
    hull = BeresfordLostVillages()
    hull.polite = no_wait()
    return hull


def stored(db: Session, name: str, grid_reference: str) -> Record:
    return db.scalars(select(Record).where(Record.external_id == external_id(name, grid_reference))).one()


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is BeresfordLostVillages


def test_the_source_carries_the_work_list_terms_unchanged() -> None:
    entry = worklist_entry(KEY)
    info = BeresfordLostVillages.source
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "non_commercial"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    assert info.publisher == entry["publisher"]


@respx.mock
def test_a_run_stores_every_site_with_the_non_commercial_terms(db: Session) -> None:
    RecordedService("lost_villages.json").mount(HOST)
    run = run_connector(connector())
    assert run.stats is not None
    assert run.stats["seen"] == 6

    cainhoe = stored(db, "Cainhoe", "TL 098374")
    assert cainhoe.name == "Cainhoe"
    assert cainhoe.category == "monument"
    assert cainhoe.record_type == "Deserted medieval village"
    assert cainhoe.periods == ["medieval"]
    assert cainhoe.precision_m == 100
    assert cainhoe.summary is not None
    assert cainhoe.summary.startswith("The settlement of Cainhoe is thought to be located")
    lon, lat = point_lon_lat(cainhoe.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-0.4, 52.025)
    assert cainhoe.raw is not None
    assert cainhoe.raw["Site_status"] == "Scheduled 1009248 (Castle)"
    assert cainhoe.raw["NMR_no"] == "1091365"
    assert "FID" not in cainhoe.raw

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == 6
    assert source.reuse == "non_commercial"
    assert source.licence == worklist_entry(KEY)["licence"]
    assert source.attribution == worklist_entry(KEY)["attribution"]


@respx.mock
def test_site_types_are_spelled_out_where_the_codes_are_known(db: Session) -> None:
    RecordedService("lost_villages.json").mount(HOST)
    run_connector(connector())
    assert stored(db, "Nuthill", "TA 215300").record_type == "Deserted medieval hamlet"
    assert stored(db, "Etonbury", "TL 197383").record_type == "Deserted medieval village (doubtful)"
    assert stored(db, "Astwick", "TL 213385").record_type == "Shrunken medieval village"


@respx.mock
def test_a_doubtful_site_is_not_dated_to_the_middle_ages(db: Session) -> None:
    RecordedService("lost_villages.json").mount(HOST)
    run_connector(connector())
    assert stored(db, "Etonbury", "TL 197383").periods in (None, [])
    assert stored(db, "Cainhoe", "TL 098374").periods == ["medieval"]


@respx.mock
def test_a_site_is_placed_by_its_grid_reference_not_by_the_layers_geometry(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    service = RecordedService("lost_villages.json")
    # Cainhoe's longitude with its sign flipped, and Astwick (Bedfordshire) put in Powys.
    for feature in service.layers["0"]["features"]:
        if feature["attributes"]["Site_name"] == "Cainhoe":
            feature["geometry"] = {"x": 0.401118, "y": 52.02417}
        if feature["attributes"]["Grid_reference"] == "TL 213385":
            feature["geometry"] = {"x": -3.058, "y": 52.027}
    service.mount(HOST)
    with caplog.at_level("WARNING", logger="fieldclub.ingest.connectors.hull_beresford_lost_villages"):
        run_connector(connector())
    cainhoe = stored(db, "Cainhoe", "TL 098374")
    lon, lat = point_lon_lat(cainhoe.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-0.4, 52.025)
    lon, lat = point_lon_lat(stored(db, "Astwick", "TL 213385").centroid)
    assert (round(lon, 3), round(lat, 3)) == (-0.232, 52.032)
    assert sorted(record.getMessage().split(" (")[0] for record in caplog.records) == [
        "Lost village Astwick",
        "Lost village Cainhoe",
    ]
    assert "which is used" in caplog.text


@respx.mock
def test_places_that_share_a_name_or_a_layer_id_are_different_records(db: Session) -> None:
    RecordedService("lost_villages.json").mount(HOST)
    run_connector(connector())
    beds, bucks = stored(db, "Astwick", "TL 213385"), stored(db, "Astwick", "SP 570342")
    assert beds.id != bucks.id
    assert bucks.summary is None  # the layer has no description for it
    assert stored(db, "Landwade", "TL 622682").raw["ID"] == 405  # type: ignore[index]
    assert stored(db, "Nuthill", "TA 215300").raw["ID"] == 405  # type: ignore[index]


def test_the_id_ignores_case_spacing_and_the_layer_numbering() -> None:
    assert external_id("Astwick", "TL 213385") == external_id(" astwick ", "TL213385")
    assert external_id("Astwick", "TL 213385") != external_id("Astwick", "SP 570342")
    assert len(external_id("Astwick", "TL 213385")) == 20


def test_precision_follows_the_figures_of_the_grid_reference() -> None:
    here = Point(-0.2, 52.0)
    assert placed("TL 213385", here)[1] == 100
    assert placed("TL213385", here)[1] == 100
    assert placed("TL 21303850", here)[1] == 10
    assert placed("TL 2138", here)[1] == 1000
    assert placed("TL 2130038500", here)[1] == 1
    assert placed("SP 28 65", here)[1] == 1000  # spaced in the middle, as some are
    assert placed("SZ 3175 9825", here)[1] == 10
    assert placed("TL 6626426", here)[1] == 100  # seven figures say nothing
    assert placed("somewhere near the church", here)[1] == 100  # what the work-list says of the layer


def test_a_grid_reference_that_does_not_parse_leaves_the_layers_geometry() -> None:
    here = Point(-0.2, 52.0)
    assert placed("somewhere near the church", here) == (here, 100.0, None)


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    RecordedService("lost_villages.json").mount(HOST)
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
    service = RecordedService("lost_villages.json")
    service.mount(HOST)
    run = run_connector(connector(), bbox=BEDFORDSHIRE)
    assert run.stats is not None
    assert not run.stats["full"]
    names = sorted(db.scalars(select(Record.name)).all())
    assert names == ["Astwick", "Cainhoe", "Etonbury"]
    assert all(query["geometry"] == "-0.5,52.0,-0.2,52.1" for query in service.queries)


@respx.mock
def test_two_sites_with_one_name_and_grid_reference_fail_the_run(db: Session) -> None:
    service = RecordedService("lost_villages.json")
    features = service.layers["0"]["features"]
    twin = copy.deepcopy(features[0])
    twin["attributes"]["FID"] = 9999
    features.append(twin)
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match="share the name and grid reference 'Astwick'"):
        run_connector(connector())


@respx.mock
def test_a_layer_that_changed_shape_fails_the_run(db: Session) -> None:
    service = RecordedService("lost_villages.json")
    for field in service.layers["0"]["info"]["fields"]:
        if field["name"] == "Grid_reference":
            field["name"] = "NGR"
    service.mount(HOST)
    with pytest.raises(IngestFailedError, match=r"changed shape: missing fields \['Grid_reference'\]"):
        run_connector(connector())
    assert db.scalars(select(Record)).all() == []
