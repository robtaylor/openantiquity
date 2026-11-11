"""The Wikidata connector against recorded query answers.

The four files in `fixtures/` were recorded from https://query.wikidata.org/sparql
on 2026-11-10, one GET a minute (the rule in force that day), with the project's
`User-Agent`:

- `wikidata_P4102_rows.json`: the connector's own query for items with an Atlas
  of Hillforts number (P4102), cut to six rows with `LIMIT 6`.
- `wikidata_P4102_count.json`: the connector's count query for the same property,
  which counts all of its rows.
- `wikidata_P718_rows.json` and `wikidata_P718_count.json`: the same two queries
  for Canmore numbers (P718), with a `VALUES` clause that limits them to the six
  hillforts above, so that the same items turn up under two properties.

The live count for P4102 is 4,155 rows, since the query is not cut to six there, so
the tests serve a count that matches the rows the fixture holds, and the recorded
count answers are used only to check that a count is read.
"""

from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.config import get_settings
from fieldclub.ingest import registry
from fieldclub.ingest.adapters.common import Feature, UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.sparql import SparqlQuery
from fieldclub.ingest.connectors import wikimedia_wikidata_heritage_items as wikidata
from fieldclub.ingest.connectors.wikimedia_wikidata_heritage_items import (
    ENDPOINT,
    Item,
    WikidataHeritageItems,
    expected_rows,
    merge,
    normalise_identifier,
    qid_of,
    to_record,
)
from fieldclub.ingest.runner import ConnectorNotConfiguredError, IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from fieldclub.services import records as record_service
from tests.connectors.research.support import assert_source_matches_worklist, fixture_json, rows
from tests.ingest.adapters.support import NoWait

KEY = "wikimedia-wikidata-heritage-items"
HILLFORTS = {"Q1015054", "Q1025082", "Q1027253", "Q1049577", "Q1088007", "Q1091047"}


def wikidata_directory() -> Path:
    return cache_dir(get_settings(), KEY)


@pytest.fixture(autouse=True)
def two_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wikidata, "PROPERTIES", ("P4102", "P718"))


@pytest.fixture(autouse=True)
def with_contact(env: Callable[..., None]) -> None:
    """Wikimedia wants a contact in the `User-Agent`, and the connector won't run without one."""
    env(CONTACT="research@example.org", USER_AGENT="")


def count_answer(rows_: int) -> dict[str, Any]:
    return {
        "head": {"vars": ["rows"]},
        "results": {"bindings": [{"rows": {"type": "literal", "value": str(rows_)}}]},
    }


def serve(
    answers: dict[str, dict[str, Any]] | None = None, counts: dict[str, int] | None = None
) -> respx.Route:
    """Answer each query by what it asks: a COUNT, or rows of a property, by its LIMIT and OFFSET."""
    answers = answers or {
        "P4102": fixture_json("wikidata_P4102_rows.json"),
        "P718": fixture_json("wikidata_P718_rows.json"),
    }
    counts = counts or {"P4102": 6, "P718": 2}

    def answer(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        prop = "P4102" if "wdt:P4102" in query else "P718"
        if "COUNT(*)" in query:
            return httpx.Response(200, json=count_answer(counts[prop]))
        body = copy.deepcopy(answers[prop])
        if "OFFSET" in query and "OFFSET 0" not in query:
            body["results"]["bindings"] = []
        return httpx.Response(200, json=body)

    return respx.get(ENDPOINT).mock(side_effect=answer)


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is WikidataHeritageItems


def test_the_source_carries_the_work_list_licence() -> None:
    assert_source_matches_worklist(WikidataHeritageItems.source)


@respx.mock
def test_items_known_under_two_identifiers_become_one_record_with_both(db: Session) -> None:
    route = serve()
    run = run_connector(WikidataHeritageItems())
    assert run.stats is not None
    assert run.stats["seen"] == len(HILLFORTS)
    assert set(db.scalars(select(Record.external_id)).all()) == HILLFORTS

    cadbury = db.scalars(select(Record).where(Record.external_id == "Q1025082")).one()
    assert cadbury.source_key == KEY
    assert cadbury.name == "Cadbury Castle"
    assert cadbury.category == "monument"
    assert cadbury.record_type == "Wikidata item"
    assert cadbury.url == "https://www.wikidata.org/wiki/Q1025082"
    lon, lat = point_lon_lat(cadbury.centroid)
    assert (round(lon, 4), round(lat, 4)) == (-2.5317, 51.0242)
    assert cadbury.raw is not None
    identifiers = cadbury.raw["identifiers"]
    assert identifiers == {"P4102": ["3948"], "P1216": ["1011980"]}
    burghead = db.scalars(select(Record).where(Record.external_id == "Q1015054")).one()
    assert burghead.raw is not None
    assert burghead.raw["identifiers"] == {"P4102": ["2925"], "P718": ["16146"]}
    # Two counts, and a first page of each property.
    queries = [call.request.url.params["query"] for call in route.calls]
    assert sum("COUNT(*)" in query for query in queries) == 2


@respx.mock
def test_an_identifier_with_a_leading_zero_is_stored_as_the_other_sources_write_it(db: Session) -> None:
    serve()
    run_connector(WikidataHeritageItems())
    chun = db.scalars(select(Record).where(Record.external_id == "Q1091047")).one()
    assert chun.raw is not None
    assert chun.raw["identifiers"]["P4102"] == ["617"]
    assert chun.raw["published"] == {"P4102": {"617": "0617"}}
    cadbury = db.scalars(select(Record).where(Record.external_id == "Q1025082")).one()
    assert cadbury.raw is not None
    assert cadbury.raw["published"] == {}


def test_normalising_an_identifier() -> None:
    assert normalise_identifier("0095") == "95"
    assert normalise_identifier("000") == "0"
    assert normalise_identifier("3749") == "3749"
    assert normalise_identifier("ANT 001:001") == "ANT 001:001"
    assert normalise_identifier("0A1") == "0A1"


@respx.mock
def test_the_items_are_stored_but_never_shown_on_the_map_or_in_search(db: Session) -> None:
    serve()
    run_connector(WikidataHeritageItems())
    assert db.scalars(select(Source.enabled).where(Source.key == KEY)).one() is False
    assert len(db.scalars(select(Record).where(Record.source_key == KEY)).all()) == len(HILLFORTS)
    found, _ = record_service.search(db, "Cadbury Castle")
    assert found == []
    assert [source.key for source in record_service.list_sources(db)] == []


def test_the_source_is_skipped_without_a_contact(env: Callable[..., None]) -> None:
    assert WikidataHeritageItems().is_configured()
    env(CONTACT="", USER_AGENT="")
    assert not WikidataHeritageItems().is_configured()
    with pytest.raises(ConnectorNotConfiguredError):
        run_connector(WikidataHeritageItems())
    env(CONTACT="", USER_AGENT="OpenAntiquity-test/1 (+https://example.org)")
    assert WikidataHeritageItems().is_configured()


@respx.mock
def test_a_second_run_the_same_day_asks_wikidata_for_nothing(db: Session) -> None:
    route = serve()
    run_connector(WikidataHeritageItems())
    asked = route.call_count
    assert asked > 0
    before = rows(db, KEY)
    run_connector(WikidataHeritageItems())
    assert route.call_count == asked
    assert rows(db, KEY) == before


@respx.mock
def test_a_run_that_failed_part_way_starts_again_at_the_property_it_failed_on(db: Session) -> None:
    answers = {
        "P4102": fixture_json("wikidata_P4102_rows.json"),
        "P718": fixture_json("wikidata_P718_rows.json"),
    }
    route = serve(answers=answers, counts={"P4102": 6, "P718": 600})
    with pytest.raises(IngestFailedError, match="said it had 600 rows"):
        run_connector(WikidataHeritageItems())
    properties_asked = {
        "P4102" if "wdt:P4102" in c.request.url.params["query"] else "P718" for c in route.calls
    }
    assert properties_asked == {"P4102", "P718"}
    route.reset()
    route = serve(answers=answers)
    run_connector(WikidataHeritageItems())
    queries = [call.request.url.params["query"] for call in route.calls]
    assert queries
    assert all("wdt:P718" in query for query in queries)


@respx.mock
def test_a_copy_older_than_a_day_is_asked_for_again(db: Session) -> None:
    route = serve()
    run_connector(WikidataHeritageItems())
    asked = route.call_count
    for path in (Path(wikidata_directory()) / name for name in ("P4102.json", "P718.json")):
        old = time.time() - 2 * 86_400
        os.utime(path, (old, old))
    run_connector(WikidataHeritageItems())
    assert route.call_count == 2 * asked


@respx.mock
def test_every_request_is_a_get_with_the_json_results_accept_header() -> None:
    route = serve()
    run_connector(WikidataHeritageItems())
    assert all(call.request.method == "GET" for call in route.calls)
    assert all(call.request.headers["accept"] == "application/sparql-results+json" for call in route.calls)
    assert all(call.request.extensions["timeout"]["read"] == wikidata.QUERY_TIMEOUT_S for call in route.calls)


@respx.mock
def test_a_partial_run_reads_one_property_and_asks_for_no_count(db: Session) -> None:
    route = serve()
    run = run_connector(WikidataHeritageItems(), limit=6)
    assert run.stats is not None
    assert not run.stats["full"]
    queries = [call.request.url.params["query"] for call in route.calls]
    assert len(queries) == 1
    assert "COUNT(*)" not in queries[0]
    assert queries[0].rstrip().endswith("LIMIT 6")


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    serve()
    run_connector(WikidataHeritageItems())
    before = rows(db, KEY)
    second = run_connector(WikidataHeritageItems())
    assert len(before) == len(HILLFORTS)
    assert rows(db, KEY) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve()
    run = run_connector(WikidataHeritageItems(), bbox=(-3.6, 57.0, -3.0, 58.0))
    assert run.stats is not None
    assert not run.stats["full"]
    assert set(db.scalars(select(Record.name)).all()) == {"Burghead Fort"}


@respx.mock
def test_an_answer_with_fewer_rows_than_counted_fails_the_run(db: Session) -> None:
    serve(counts={"P4102": 600, "P718": 2})
    with pytest.raises(IngestFailedError, match="said it had 600 rows and gave 6"):
        run_connector(WikidataHeritageItems())


@respx.mock
def test_an_answer_that_changed_shape_fails_the_run(db: Session) -> None:
    changed = fixture_json("wikidata_P4102_rows.json")
    for binding in changed["results"]["bindings"]:
        binding["identifier"] = binding.pop("id")
    serve(answers={"P4102": changed, "P718": fixture_json("wikidata_P718_rows.json")})
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(WikidataHeritageItems())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_the_recorded_count_answers_are_read() -> None:
    respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json=fixture_json("wikidata_P4102_count.json")),
            httpx.Response(200, json=fixture_json("wikidata_P718_count.json")),
        ]
    )
    counter = SparqlQuery(
        ENDPOINT, "SELECT (COUNT(*) AS ?rows) WHERE { ?s ?p ?o }", client=httpx.Client(), polite=NoWait()
    )
    assert expected_rows(counter) == 4155
    assert expected_rows(counter) == 2


@respx.mock
def test_a_count_that_is_not_a_number_fails_the_run() -> None:
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json=count_answer(0) | {"results": {"bindings": []}})
    )
    with pytest.raises(IngestFailedError, match="count query with a number"):
        run_connector(WikidataHeritageItems())


def test_an_iri_must_be_an_item() -> None:
    assert qid_of("http://www.wikidata.org/entity/Q42") == "Q42"
    for iri in (
        "http://www.wikidata.org/entity/P625",
        "Q42",
        "http://example.org/Q1",
        "http://www.wikidata.org/entity/Qx",
    ):
        with pytest.raises(UpstreamFormatError):
            qid_of(iri)


def test_merging_collects_every_identifier_of_an_item() -> None:
    items: dict[str, Item] = {}
    iri = "http://www.wikidata.org/entity/Q7"
    point = Point(-1.0, 51.0)
    merge(items, "P718", Feature({"item": iri, "id": "100", "itemLabel": "Seven"}, point))
    merge(items, "P718", Feature({"item": iri, "id": "101", "coord": "x"}, point))
    merge(items, "P4658", Feature({"item": iri, "id": "200", "nhle": "9"}, point))
    assert items["Q7"].label == "Seven"
    assert items["Q7"].identifiers == {"P718": {"100", "101"}, "P4658": {"200"}, "P1216": {"9"}}


def test_an_item_without_an_english_label_or_inside_the_isles_gives_no_record() -> None:
    assert to_record("Q1", Item(label=None, geometry=Point(-1, 51))) is None
    assert to_record("Q2", Item(label="Far away", geometry=Point(-74.0, 40.7))) is None
    assert to_record("Q3", Item(label="No position", geometry=None)) is None
    record = to_record("Q4", Item(label=" Close ", geometry=Point(-1, 51)))
    assert record is not None
    assert record.name == "Close"
