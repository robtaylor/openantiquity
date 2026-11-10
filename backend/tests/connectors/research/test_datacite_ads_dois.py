"""The ADS DOIs connector, end to end against recorded DataCite pages.

`fixtures/datacite_pages.json` holds 14 DOIs from api.datacite.org, recorded on
2026-11-10 with the connector's own query (`client-id=bl.ads`, a point or a box
in `geoLocations`, cursor paging): two pages of five for the first two
requests, then four more records from two further small requests (a point
query and a box query), so that the fixture holds correctly oriented points,
swapped ones, small boxes and a box the size of a county. Each record is kept
whole except `relationships`. `meta.total` is set to the 14 records kept and
the next link is a placeholder.
"""

from __future__ import annotations

import copy
import shutil
from typing import Any

import httpx
import pytest
import respx
import shapely
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.config import get_settings
from fieldclub.ingest import registry
from fieldclub.ingest.adapters.common import cache_dir
from fieldclub.ingest.connectors.datacite_ads_dois import DOIS_URL, AdsDois, position, to_record
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.research.support import assert_source_matches_worklist, fixture_json, rows

KEY = "datacite-ads-dois"


def serve(pages: dict[str, Any]) -> respx.Route:
    """The first page, and the second one the first points to."""
    respx.get(DOIS_URL, params={"page[cursor]": "NEXT"}).mock(
        return_value=httpx.Response(200, json=pages["page2"])
    )
    return respx.get(DOIS_URL, params={"page[cursor]": "1"}).mock(
        return_value=httpx.Response(200, json=pages["page1"])
    )


def pages() -> dict[str, Any]:
    return copy.deepcopy(fixture_json("datacite_pages.json"))


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is AdsDois


def test_the_source_carries_the_work_list_licence() -> None:
    assert_source_matches_worklist(AdsDois.source)


@respx.mock
def test_a_run_stores_the_placed_dois_with_their_fields(db: Session) -> None:
    first = serve(pages())
    run = run_connector(AdsDois())
    assert run.status == "completed"
    assert run.stats is not None
    # 14 recorded; the county-sized box (Milton Ironworks) is left out.
    assert run.stats["seen"] == 13

    request = first.calls[0].request
    assert request.url.params["client-id"] == "bl.ads"
    assert "geoLocationBox" in request.url.params["query"]
    assert request.url.params["page[size]"] == "1000"

    wendover = db.scalars(select(Record).where(Record.external_id == "10.5284/1147323")).one()
    assert wendover.source_key == KEY
    assert wendover.name.startswith("PXA Report for Archaeological Recording at Rocky Lane")
    assert wendover.category == "document"
    assert wendover.record_type == "Report"
    assert wendover.url == "https://doi.org/10.5284/1147323"
    assert wendover.summary is not None
    assert wendover.summary.startswith("Archaeological mitigation was undertaken in two locations")
    assert wendover.source_updated_at is not None
    lon, lat = point_lon_lat(wendover.centroid)
    assert (round(lon, 3), round(lat, 3)) == (-0.731, 51.746)
    assert wendover.raw is not None
    assert wendover.raw["axes_swapped"] is False
    assert wendover.raw["rightsList"][0]["rightsUri"].endswith("/open-government-licence/version/3/")
    assert wendover.raw["creators"][0] == "Hutton, Jacqui"
    assert wendover.raw["publicationYear"] == 2021

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == 13
    assert source.attribution == "None required for CC0 metadata; cite DOIs"


@respx.mock
def test_older_records_with_latitude_and_longitude_the_wrong_way_round_are_put_right(db: Session) -> None:
    serve(pages())
    run_connector(AdsDois())
    framlingham = db.scalars(select(Record).where(Record.external_id == "10.5284/1059004")).one()
    lon, lat = point_lon_lat(framlingham.centroid)
    assert (round(lon, 4), round(lat, 4)) == (1.3466, 52.2239)
    assert framlingham.raw is not None
    assert framlingham.raw["axes_swapped"] is True
    # The record keeps the position as the source wrote it.
    assert framlingham.raw["geoLocations"][0]["geoLocationPoint"]["pointLatitude"] == "1.346643"


@respx.mock
def test_a_small_box_is_stored_as_an_area_and_a_county_sized_one_is_not(db: Session) -> None:
    serve(pages())
    run_connector(AdsDois())
    twyford = db.scalars(select(Record).where(Record.external_id == "10.5284/1074966")).one()
    west, south, east, north = shapely.from_wkb(bytes(twyford.geom.data)).bounds
    assert (round(west, 3), round(south, 3), round(east, 3), round(north, 3)) == (
        -1.317,
        51.013,
        -1.299,
        51.014,
    )
    assert db.scalars(select(Record).where(Record.external_id == "10.5284/1058996")).first() is None


def test_positions_are_read_the_way_the_rules_say() -> None:
    def point(lat: object, lon: object) -> list[dict[str, Any]]:
        return [{"geoLocationPoint": {"pointLatitude": lat, "pointLongitude": lon}}]

    placed = position(point(51.5, -0.1))
    assert placed is not None
    assert isinstance(placed[0], Point)
    assert placed[1] is False
    swapped = position(point("-0.1", "51.5"))
    assert swapped is not None
    assert (swapped[0].wkt, swapped[1]) == ("POINT (-0.1 51.5)", True)
    assert position(point(40.7, -74.0)) is None  # New York
    assert position(point("north", "west")) is None
    assert position(point(None, None)) is None
    assert position([{"geoLocationPlace": "Somewhere"}]) is None
    assert position("not a list") is None
    two = position(point(51.5, -0.1) + point(52.5, -1.1))
    assert two is not None
    assert two[0].geom_type == "MultiPoint"


def test_an_item_without_an_id_or_attributes_is_an_upstream_format_error() -> None:
    from fieldclub.ingest.adapters.common import UpstreamFormatError

    with pytest.raises(UpstreamFormatError, match="no id or attributes"):
        to_record({"type": "dois"})


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    serve(pages())
    first = run_connector(AdsDois())
    before = rows(db, KEY)
    second = run_connector(AdsDois())
    assert len(before) == 13
    assert rows(db, KEY) == before
    assert first.stats is not None
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 13, 0)


@respx.mock
def test_a_second_run_the_same_day_asks_datacite_for_nothing(db: Session) -> None:
    serve(pages())
    run_connector(AdsDois())
    asked = respx.calls.call_count
    assert asked == 2
    run_connector(AdsDois())
    assert respx.calls.call_count == asked


def test_a_point_on_the_continent_is_not_stored() -> None:
    def point(lat: object, lon: object) -> list[dict[str, Any]]:
        return [{"geoLocationPoint": {"pointLatitude": lat, "pointLongitude": lon}}]

    assert position(point(50.996, 2.123)) is None  # Smallhythe, Kent, as DataCite has it: near Dunkirk
    assert position(point(49.4, 1.1)) is None  # Rouen
    assert position(point(51.1, 1.3)) is not None  # Dover


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve(pages())
    run = run_connector(AdsDois(), bbox=(-0.8, 51.7, -0.7, 51.8))
    assert run.stats is not None
    assert not run.stats["full"]
    ids = set(db.scalars(select(Record.external_id)).all())
    assert ids == {"10.5284/1147323"}


@respx.mock
def test_an_upstream_that_changed_shape_fails_the_run(db: Session) -> None:
    changed = pages()
    changed["page1"] = {"errors": [{"title": "gone"}]}
    serve(changed)
    with pytest.raises(IngestFailedError, match="no list at 'data'"):
        run_connector(AdsDois())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_truncated_answer_fails_the_run_and_deletes_nothing(db: Session) -> None:
    serve(pages())
    run_connector(AdsDois())
    truncated = pages()
    truncated["page2"]["data"] = truncated["page2"]["data"][:2]
    serve(truncated)
    shutil.rmtree(cache_dir(get_settings(), KEY))  # the pages of the first run are a day old
    with pytest.raises(IngestFailedError, match="said it had 14 items"):
        run_connector(AdsDois())
    assert len(rows(db, KEY)) == 13
