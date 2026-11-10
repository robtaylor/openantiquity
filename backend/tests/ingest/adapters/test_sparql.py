from __future__ import annotations

import httpx
import pytest
import respx

from fieldclub.ingest.adapters.common import UpstreamFormatError
from fieldclub.ingest.adapters.sparql import RESULTS_JSON, SparqlQuery, wkt_literal
from tests.ingest.adapters.support import NoWait, fixture_json, xy

ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = (
    "SELECT ?item ?itemLabel ?coord ?nhle WHERE { ?item wdt:P4102 ?hillfort ; wdt:P625 ?coord ; "
    "wdt:P1216 ?nhle . } ORDER BY ?item"
)


def make_query(**kwargs) -> SparqlQuery:
    return SparqlQuery(ENDPOINT, QUERY, client=httpx.Client(), polite=NoWait(), **kwargs)


@respx.mock
def test_rows_are_plain_values_with_a_geometry() -> None:
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=fixture_json("sparql_page.json")))
    features = list(make_query(geometry="coord").features())

    assert len(features) == 3
    cadbury = features[0]
    assert cadbury.properties["itemLabel"] == "Cadbury Castle"
    assert cadbury.properties["nhle"] == "1011980"
    assert xy(cadbury.geometry) == (-2.531667, 51.024167)
    assert route.calls[0].request.headers["Accept"] == RESULTS_JSON


@respx.mock
def test_paging_appends_limit_and_offset_until_a_short_page() -> None:
    page = fixture_json("sparql_page.json")
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json=page),
            httpx.Response(200, json={**page, "results": {"bindings": []}}),
        ]
    )
    rows = list(make_query(page_size=3).rows())
    assert len(rows) == 3
    queries = [call.request.url.params["query"] for call in route.calls]
    assert queries[0].endswith("LIMIT 3\nOFFSET 0")
    assert queries[1].endswith("LIMIT 3\nOFFSET 3")


def test_a_paged_query_must_be_ordered() -> None:
    with pytest.raises(AssertionError, match="ORDER BY"):
        SparqlQuery(ENDPOINT, "SELECT ?s WHERE { ?s ?p ?o }", client=httpx.Client(), page_size=10)
    with pytest.raises(AssertionError, match="LIMIT or OFFSET"):
        SparqlQuery(ENDPOINT, QUERY + " LIMIT 5", client=httpx.Client(), page_size=10)


@respx.mock
def test_an_answer_that_isnt_sparql_json_is_an_error() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, text="<html>Too many requests</html>"))
    with pytest.raises(UpstreamFormatError, match="SPARQL JSON"):
        list(make_query().rows())


def test_wkt_literals_in_each_crs() -> None:
    assert xy(wkt_literal("Point(-1.8574 51.4156)")) == (-1.8574, 51.4156)
    # EPSG:4326 by URI puts latitude first, per GeoSPARQL.
    lon, lat = xy(wkt_literal("<http://www.opengis.net/def/crs/EPSG/0/4326> POINT(51.4156 -1.8574)"))
    assert lon == pytest.approx(-1.8574)
    assert lat == pytest.approx(51.4156)
    lon, lat = xy(wkt_literal("<http://www.opengis.net/def/crs/EPSG/0/27700> POINT(410000 168700)"))
    assert -1.87 < lon < -1.85
    assert 51.40 < lat < 51.42
    assert wkt_literal("POINT EMPTY") is None
    with pytest.raises(UpstreamFormatError):
        wkt_literal("not wkt at all")
