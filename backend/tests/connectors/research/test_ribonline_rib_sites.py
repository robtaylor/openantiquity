"""The RIB Online connector against a recorded cut of the sites feed.

`fixtures/rib_sites.json` is 16 features, whole, from the one request
`findspot.php?format=json&entity=site&qtype=radius&key=&radius=600&lat=54.09&lng=-2.2`
made on 2026-11-10 (the answer holds 1,046 and is 473 KB), after the 20 seconds
the site's robots.txt asks for. One of each site type was kept. The feed's
"Outside Britain" section is not in it, so the test makes one.
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
from fieldclub.ingest.connectors.ribonline_rib_sites import FEED_URL, RibSites
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from tests.connectors.research.support import assert_source_matches_worklist, fixture_json, rows

KEY = "ribonline-rib-sites"


def feed() -> dict[str, Any]:
    return copy.deepcopy(fixture_json("rib_sites.json"))


def serve(body: Any) -> respx.Route:
    return respx.get(FEED_URL).mock(return_value=httpx.Response(200, json=body))


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is RibSites


def test_the_source_carries_the_work_list_licence() -> None:
    assert_source_matches_worklist(RibSites.source)


@respx.mock
def test_a_run_stores_every_site_with_its_fields(db: Session) -> None:
    route = serve(feed())
    run = run_connector(RibSites())
    assert run.stats is not None
    assert run.stats["seen"] == 16
    params = route.calls[0].request.url.params
    assert (params["entity"], params["radius"], params["format"]) == ("site", "600", "json")

    cave = db.scalars(select(Record).where(Record.external_id == "945")).one()
    assert cave.source_key == KEY
    assert cave.name == "Victoria Cave"
    assert cave.category == "find"
    assert cave.record_type == "Modern"
    assert cave.periods == ["roman"]
    assert cave.summary == "West Yorkshire"
    # The address drops the `site-` the feed puts in front of every key.
    assert cave.url == "https://romaninscriptionsofbritain.org/sites/victoria-cave"
    lon, lat = point_lon_lat(cave.centroid)
    assert (round(lon, 4), round(lat, 4)) == (-2.2489, 54.0808)
    assert cave.raw is not None
    assert cave.raw["site_key"] == "site-victoria-cave"
    assert "popupContent" not in cave.raw


@respx.mock
def test_a_latin_name_goes_into_the_summary(db: Session) -> None:
    serve(feed())
    run_connector(RibSites())
    chester = db.scalars(select(Record).where(Record.external_id == "80")).one()
    assert chester.summary == "Latin name: Deva. Cheshire"


@respx.mock
def test_sites_in_the_outside_britain_section_are_not_stored(db: Session) -> None:
    body = feed()
    body["features"][0]["properties"]["section"] = "Outside Britain"
    stray = body["features"][0]["properties"]["id_code"]
    serve(body)
    run_connector(RibSites())
    assert str(stray) not in set(db.scalars(select(Record.external_id)).all())
    assert len(db.scalars(select(Record)).all()) == 15


@respx.mock
def test_running_twice_gives_the_same_rows_and_asks_once(db: Session) -> None:
    route = serve(feed())
    run_connector(RibSites())
    before = rows(db, KEY)
    second = run_connector(RibSites())
    assert len(before) == 16
    assert rows(db, KEY) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)
    assert route.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve(feed())
    run = run_connector(RibSites(), bbox=(-2.6, 54.0, -2.0, 54.2))
    assert run.stats is not None
    assert not run.stats["full"]
    names = set(db.scalars(select(Record.name)).all())
    assert "Victoria Cave" in names
    assert "Chester" not in names


@respx.mock
def test_a_feed_that_changed_shape_fails_the_run(db: Session) -> None:
    body = feed()
    for item in body["features"]:
        item["properties"]["site_id"] = item["properties"].pop("id_code")
    serve(body)
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(RibSites())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_an_answer_that_is_not_a_feature_collection_fails_the_run(db: Session) -> None:
    serve([{"id_code": 1}])
    with pytest.raises(IngestFailedError, match="not a GeoJSON FeatureCollection"):
        run_connector(RibSites())
