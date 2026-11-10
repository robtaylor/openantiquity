"""The Pleiades connector against a recorded cut of the GIS bundle.

`fixtures/pleiades_gis_data.zip` holds the three CSV files the connector reads,
cut down to nine places, with their rows as the live bundle
(https://atlantides.org/downloads/pleiades/gis/pleiades_gis_data.zip, one
GET on 2026-11-10, 36 MB) has them: Londinium, Vindolanda, Stonehenge and the
Britannia island at precise points, Hadrian's Wall and the province Britannia
I at rough ones, Germania II whose rough box reaches into the Continent,
Baqa with no position at all, and a house in Pompeii. Four more rows were
copied from the same bundle: Caen in Normandy and Samarobriva Ambianorum
(Amiens) in Picardy, which the runner's box for the isles holds, the bay
"Ouolas? Kolpos", and Oram's Arbour, whose type `fort` is the vocabulary's
deprecated term for `fort-2`.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.adapters.common import Feature
from fieldclub.ingest.connectors.isaw_pleiades_places import BUNDLE_URL, PleiadesPlaces, to_record
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from tests.connectors.research.support import FIXTURES, assert_source_matches_worklist, rows

KEY = "isaw-pleiades-places"
BUNDLE = FIXTURES / "pleiades_gis_data.zip"
STORED = {"79574", "89313", "509089189", "20419", "113170101"}


def serve(body: bytes) -> respx.Route:
    return respx.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Length": str(len(body))})
    )


def bundle_without(member: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(BUNDLE) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            if not info.filename.endswith(member):
                dst.writestr(info, src.read(info))
    return out.getvalue()


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is PleiadesPlaces


def test_the_source_carries_the_work_list_licence() -> None:
    # The work-list's category, "place", is not a record category, so places are stored as monuments.
    assert_source_matches_worklist(PleiadesPlaces.source, category="monument")


@respx.mock
def test_a_run_stores_the_places_in_britain(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run = run_connector(PleiadesPlaces())
    assert run.stats is not None
    assert run.stats["seen"] == len(STORED)
    assert set(db.scalars(select(Record.external_id)).all()) == STORED


@respx.mock
def test_place_fields_are_mapped(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    stonehenge = db.scalars(select(Record).where(Record.external_id == "509089189")).one()
    assert stonehenge.name == "Stonehenge"
    assert stonehenge.category == "monument"
    assert stonehenge.url == "https://pleiades.stoa.org/places/509089189"
    assert stonehenge.monument_types == ["cultural landscape", "archaeological site", "monument"]
    assert stonehenge.record_type == "cultural landscape, archaeological site, monument"
    assert stonehenge.precision_m is None
    assert stonehenge.periods is None
    assert stonehenge.raw is not None
    assert stonehenge.raw["location_precision"] == "precise"
    assert stonehenge.raw["uri"] == "https://pleiades.stoa.org/places/509089189"
    lon, lat = point_lon_lat(stonehenge.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-1.823, 51.18)

    londinium = db.scalars(select(Record).where(Record.external_id == "79574")).one()
    assert londinium.name == "Londinium/Augusta"
    assert londinium.summary


def place(**fields: str | None) -> Feature:
    """A precise place in Hampshire with `fields` over the top."""
    columns: dict[str, str | None] = {
        "id": "5",
        "title": "Somewhere",
        "description": "",
        "details": "",
        "provenance": "",
        "uri": "u",
        "created": "c",
        "representative_latitude": "51",
        "representative_longitude": "-1",
        "bounding_box_wkt": None,
        "location_precision": "precise",
    } | fields
    return Feature(
        columns,
        Point(
            float(columns["representative_longitude"] or 0), float(columns["representative_latitude"] or 0)
        ),
    )


def test_a_rough_place_says_how_rough() -> None:
    # A box 0.2 degrees wide and 0.1 high at 51 N: half the wider side.
    record = to_record(
        place(
            location_precision="rough",
            bounding_box_wkt="POLYGON ((-1.1 50.95, -1.1 51.05, -0.9 51.05, -0.9 50.95, -1.1 50.95))",
        ),
        {},
    )
    assert record is not None
    assert record.precision_m is not None
    assert round(record.precision_m / 1000) == 7


@respx.mock
def test_a_rough_place_above_ten_kilometres_is_not_stored(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    # Hadrian's Wall is a rough point in the middle of its box, 40 km or so from the ends.
    assert db.scalars(select(Record).where(Record.external_id == "91358")).first() is None


@respx.mock
def test_places_that_are_not_sites_are_not_stored(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    ids = set(db.scalars(select(Record.external_id)).all())
    assert "991321" not in ids  # Britannia I, a province
    assert "89270" not in ids  # Ouolas? Kolpos, a bay
    assert to_record(place(), {"5": ["province", "people, tribe (historical cultural group)"]}) is None
    assert to_record(place(), {"5": ["province", "settlement"]}) is not None
    assert to_record(place(), {}) is not None


@respx.mock
def test_places_on_the_continent_are_not_stored(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    ids = set(db.scalars(select(Record.external_id)).all())
    assert "69483" not in ids  # Caen, in Normandy
    assert "109321" not in ids  # Samarobriva, in Picardy
    assert to_record(place(representative_latitude="49.0", representative_longitude="-11.5"), {}) is None
    assert (
        to_record(place(representative_latitude="49.19", representative_longitude="-2.2"), {}) is not None
    )  # Jersey


@respx.mock
def test_a_deprecated_type_is_replaced_by_its_live_twin(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    arbour = db.scalars(select(Record).where(Record.external_id == "113170101")).one()
    assert arbour.monument_types == ["fort"]
    assert arbour.record_type == "fort"


@respx.mock
def test_a_rough_place_whose_box_reaches_the_continent_is_not_stored(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    # Germania II's representative point is at 2.5 E, inside the isles' box; its own box runs to 5 E.
    assert db.scalars(select(Record).where(Record.external_id == "991329")).first() is None


def test_a_place_with_no_title_is_named_by_its_number() -> None:
    columns = {
        "id": "5",
        "title": " ",
        "description": "",
        "details": "",
        "provenance": "",
        "uri": "u",
        "created": "c",
        "representative_latitude": "51",
        "representative_longitude": "-1",
        "bounding_box_wkt": None,
        "location_precision": "precise",
    }
    record = to_record(Feature(columns, Point(-1, 51)), {})
    assert record is not None
    assert record.name == "Pleiades place 5"
    assert record.summary is None
    assert record.monument_types == []


@respx.mock
def test_running_twice_gives_the_same_rows_and_uses_the_copy_on_disk(db: Session) -> None:
    route = serve(BUNDLE.read_bytes())
    run_connector(PleiadesPlaces())
    before = rows(db, KEY)
    second = run_connector(PleiadesPlaces())
    assert len(before) == len(STORED)
    assert rows(db, KEY) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)
    assert route.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve(BUNDLE.read_bytes())
    run = run_connector(PleiadesPlaces(), bbox=(-2.5, 54.9, -2.2, 55.1))
    assert run.stats is not None
    assert not run.stats["full"]
    assert set(db.scalars(select(Record.external_id)).all()) == {"89313"}


@respx.mock
@pytest.mark.parametrize("member", ["places_place_types.csv", "place_types.csv"])
def test_a_bundle_missing_a_file_fails_the_run(db: Session, member: str) -> None:
    serve(bundle_without(member))
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(PleiadesPlaces())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_places_file_that_lost_a_column_fails_the_run(db: Session) -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(BUNDLE) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data: Any = src.read(info)
            if info.filename.endswith("/places.csv"):
                data = data.replace(b"location_precision", b"precision")
            dst.writestr(info, data)
    serve(out.getvalue())
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(PleiadesPlaces())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_download_that_is_not_a_zip_fails_the_run(db: Session) -> None:
    serve(b"<html>Not found</html>")
    with pytest.raises(IngestFailedError, match="not a zip file"):
        run_connector(PleiadesPlaces())
