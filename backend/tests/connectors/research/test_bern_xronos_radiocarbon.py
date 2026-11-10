"""The XRONOS connector against recorded answers.

`fixtures/xronos_countries.json` holds, for each of the four country labels the
connector asks for, a few whole measurements from https://xronos.ch/api/v1/data
as answered on 2026-11-10 (`?query_country=GB`, `England/Wales`, `Scotland` and
`IE`, one request each, a few seconds apart; the live answers are 3 to 35 MB).
They were picked to cover a lab number held twice under two ids (Tamnyrankin,
UB-6737), a measurement with no coordinates (Ashton Farm), Stonehenge's
HAR-455 with its repeated period names, and an Irish date whose longitude has
lost its minus sign (Castle Roe).
"""

from __future__ import annotations

import copy
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.bern_xronos_radiocarbon import (
    COUNTRIES,
    DATA_URL,
    XronosRadiocarbon,
    period_names,
    periods_from,
    to_record,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from tests.connectors.research.support import assert_source_matches_worklist, fixture_json, rows

KEY = "bern-xronos-radiocarbon"
# Fifteen in the fixture, less Ashton Farm with no position and Castle Roe in the North Sea.
STORED = 11


def serve(answers: dict[str, Any] | None = None) -> dict[str, respx.Route]:
    data: dict[str, Any] = (
        copy.deepcopy(fixture_json("xronos_countries.json")) if answers is None else answers
    )
    return {
        country: respx.get(DATA_URL, params={"query_country": country}).mock(
            return_value=httpx.Response(200, json=data[country])
        )
        for country in COUNTRIES
    }


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is XronosRadiocarbon


def test_the_source_carries_the_work_list_licence() -> None:
    assert_source_matches_worklist(XronosRadiocarbon.source)


@respx.mock
def test_every_country_label_is_asked_for_once(db: Session) -> None:
    routes = serve()
    run_connector(XronosRadiocarbon())
    assert {country: route.call_count for country, route in routes.items()} == dict.fromkeys(COUNTRIES, 1)


@respx.mock
def test_a_run_stores_the_dated_samples_with_their_fields(db: Session) -> None:
    serve()
    run = run_connector(XronosRadiocarbon())
    assert run.stats is not None
    assert run.stats["seen"] == STORED

    stonehenge = db.scalars(select(Record).where(Record.external_id == "27327")).one()
    assert stonehenge.source_key == KEY
    assert stonehenge.name == "Stonehenge"
    assert stonehenge.category == "event"
    assert stonehenge.record_type == "henges"
    assert stonehenge.summary == "HAR-455: 9130 ± 180 BP, charcoal (Pinus)"
    assert stonehenge.url is None
    assert stonehenge.periods == ["prehistoric", "neolithic"]
    lon, lat = point_lon_lat(stonehenge.centroid)
    assert (round(lon, 4), round(lat, 4)) == (-1.8262, 51.1788)
    assert stonehenge.raw is not None
    assert stonehenge.raw["labnr"] == "HAR-455"
    assert stonehenge.raw["bp"] == 9130
    assert stonehenge.raw["period_names"] == ["Epipalaeolithic", "LMEN", "Neolithic", "UBA", "UM", "UN"]
    assert len(stonehenge.raw["reference"]) == 2


@respx.mock
def test_two_measurements_with_one_lab_number_are_both_kept(db: Session) -> None:
    serve()
    run_connector(XronosRadiocarbon())
    twins = db.scalars(select(Record).where(Record.name == "Tamnyrankin")).all()
    assert sorted(record.external_id for record in twins) == ["128709", "329711"]
    assert {record.raw["labnr"] for record in twins if record.raw} == {"UB-6737"}


@respx.mock
def test_samples_without_a_position_or_outside_the_islands_are_not_stored(db: Session) -> None:
    serve()
    run_connector(XronosRadiocarbon())
    ids = set(db.scalars(select(Record.external_id)).all())
    assert "117206" not in ids  # Ashton Farm: no coordinates
    assert "133503" not in ids  # Castle Roe: longitude 6.67 east


def test_period_names_are_deduplicated_and_only_plain_ones_mapped() -> None:
    names = period_names(
        [{"periode": "Neolithic"}, {"periode": "Neolithic"}, {"periode": "UBA"}, {"periode": " "}, {"x": 1}]
    )
    assert names == ["Neolithic", "UBA"]
    assert periods_from(["Late Neolithic/Early Bronze Age", "UN", "Mesolithic", "IA"]) == [
        "prehistoric",
        "neolithic",
        "bronze_age",
        "iron_age",
    ]
    assert periods_from(["UN", "unspec."]) == []


def test_a_measurement_with_text_for_a_coordinate_is_not_stored() -> None:
    base = {"id": 1, "labnr": "X-1", "site": "S", "lat": "north", "lng": "-1.0"}
    assert to_record({"measurement": base}) is None
    assert to_record({"measurement": base | {"lat": "51.5"}}) is not None


@respx.mock
def test_running_twice_gives_the_same_rows_and_uses_the_copies_on_disk(db: Session) -> None:
    routes = serve()
    run_connector(XronosRadiocarbon())
    before = rows(db, KEY)
    second = run_connector(XronosRadiocarbon())
    assert len(before) == STORED
    assert rows(db, KEY) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)
    assert all(route.call_count == 1 for route in routes.values())


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve()
    run = run_connector(XronosRadiocarbon(), bbox=(-2.0, 51.0, -1.5, 51.4))
    assert run.stats is not None
    assert not run.stats["full"]
    assert set(db.scalars(select(Record.name)).all()) == {"Stonehenge"}


@respx.mock
def test_an_answer_that_changed_shape_fails_the_run(db: Session) -> None:
    answers = copy.deepcopy(fixture_json("xronos_countries.json"))
    for item in answers["GB"]:
        item["measurement"]["longitude"] = item["measurement"].pop("lng")
    serve(answers)
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(XronosRadiocarbon())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_measurement_id_that_appears_in_two_answers_fails_the_run(db: Session) -> None:
    answers = copy.deepcopy(fixture_json("xronos_countries.json"))
    answers["Scotland"].append(answers["GB"][3])
    serve(answers)
    with pytest.raises(IngestFailedError, match="appears twice"):
        run_connector(XronosRadiocarbon())


@respx.mock
def test_an_answer_that_is_not_a_list_fails_the_run(db: Session) -> None:
    answers = copy.deepcopy(fixture_json("xronos_countries.json"))
    answers["IE"] = {"error": "nope"}
    serve(answers)
    with pytest.raises(IngestFailedError, match="other than a list"):
        run_connector(XronosRadiocarbon())
