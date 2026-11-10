"""The Itiner-e connector against a recorded cut of the nightly export.

`fixtures/itinere_segments.ndjson` is 14 whole lines of
https://itiner-e.org/route-segments/download, taken on 2026-11-10 from the
file the connector downloaded (a plain GET, 57.8 MB). Ten are in Britain,
chosen to cover each road type and certainty and the missing dates of a river.
Four are outside it: a road in Normandy, one on the Channel coast at
Boulogne, one in Algeria and one in Egypt. Three more were added from the same
file: the sea lanes from Boulogne to Dover (38992) and to Richborough (38994),
and Lindum-Durobrivae (13722), a segment in Britain with no length.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
import time_machine
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.aarhus_itinere_roman_roads import (
    EXPORT_URL,
    STATIC_VERSION,
    ItinerERoads,
    periods_between,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.research.support import FIXTURES, assert_source_matches_worklist, rows

KEY = "aarhus-itinere-roman-roads"
EXPORT = FIXTURES / "itinere_segments.ndjson"
IN_BRITAIN = 10


def serve(body: bytes) -> respx.Route:
    return respx.get(EXPORT_URL).mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Length": str(len(body))})
    )


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is ItinerERoads


def test_the_source_carries_the_work_list_licence_and_cites_the_static_version() -> None:
    entry_attribution = (
        "Itiner-e: the digital atlas of ancient roads © 2024 by Brughmans, Pažout, de Soto and "
        "Bjerregaard Vahlstrup is licensed under CC BY 4.0"
    )
    assert_source_matches_worklist(ItinerERoads.source, attribution=f"{entry_attribution}. {STATIC_VERSION}")
    assert "10.5281/zenodo.17122148" in STATIC_VERSION


@respx.mock
def test_a_run_stores_only_the_segments_in_britain(db: Session) -> None:
    serve(EXPORT.read_bytes())
    run = run_connector(ItinerERoads())
    assert run.stats is not None
    assert run.stats["seen"] == IN_BRITAIN
    ids = set(db.scalars(select(Record.external_id)).all())
    # Normandy (29986), Boulogne (17260), Algeria (4472) and Egypt (9) are left out.
    assert not ids & {"29986", "17260", "4472", "9"}


@respx.mock
def test_the_channel_crossings_and_segments_with_no_length_are_left_out(db: Session) -> None:
    serve(EXPORT.read_bytes())
    run_connector(ItinerERoads())
    ids = set(db.scalars(select(Record.external_id)).all())
    assert not ids & {"38992", "38994"}  # Boulogne to Dover, and to Richborough
    assert "13722" not in ids  # two identical points


@respx.mock
def test_segment_fields_are_mapped(db: Session) -> None:
    serve(EXPORT.read_bytes())
    run_connector(ItinerERoads())
    road = db.scalars(select(Record).where(Record.external_id == "13516")).one()
    assert road.name == "Brocavum-Low Borrowbridge"
    assert road.category == "monument"
    assert road.record_type == "Main Road"
    assert road.monument_types == ["Main Road"]
    assert road.summary is not None
    assert road.summary.startswith("Conjectured line.")
    assert road.url == "https://itiner-e.org/route-segment/13516"
    assert road.periods == ["roman"]  # dated 0 to 0, which the export uses for "no date", on a Roman road
    assert road.raw is not None
    assert road.raw["segmentCertainty"] == "Conjectured"
    assert road.raw["bibliography"]
    lon, lat = point_lon_lat(road.centroid)
    assert -3 < lon < -2
    assert 54 < lat < 55

    river = db.scalars(select(Record).where(Record.external_id == "32529")).one()
    assert river.record_type == "River"
    assert river.periods is None  # the segment gives no dates


def test_periods_come_from_the_date_range() -> None:
    assert periods_between(0, 0) == ["roman"]  # the export's placeholder for no date, on a Roman road
    assert periods_between(50, 200) == ["roman"]
    assert periods_between(-100, 100) == ["iron_age", "roman"]
    assert periods_between(300, 600) == ["roman", "early_medieval"]
    assert periods_between(None, None) == []
    assert periods_between(200, 50) == ["roman"]
    assert periods_between(True, 3) == []


@respx.mock
def test_the_stored_attribution_is_dated_from_the_download(db: Session) -> None:
    serve(EXPORT.read_bytes())
    with time_machine.travel(datetime(2027, 1, 2, 9, tzinfo=UTC), tick=False):
        run_connector(ItinerERoads())
    source = db.get(Source, KEY)
    assert source is not None
    assert source.attribution.endswith(f"CC BY 4.0. {STATIC_VERSION}")


@respx.mock
def test_running_twice_gives_the_same_rows_and_uses_the_copy_on_disk(db: Session) -> None:
    route = serve(EXPORT.read_bytes())
    run_connector(ItinerERoads())
    before = rows(db, KEY)
    second = run_connector(ItinerERoads())
    assert len(before) == IN_BRITAIN
    assert rows(db, KEY) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["deleted"]) == (0, 0)
    assert route.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve(EXPORT.read_bytes())
    # Hadrian's Wall country: Brocavum (Brougham) and the Pons Aelius road are in the north.
    run = run_connector(ItinerERoads(), bbox=(-3.0, 54.0, -2.0, 55.0))
    assert run.stats is not None
    assert not run.stats["full"]
    names = set(db.scalars(select(Record.name)).all())
    assert "Brocavum-Low Borrowbridge" in names
    assert "Nash Mills-Flaunden" not in names  # Hertfordshire


@respx.mock
def test_an_export_that_changed_shape_fails_the_run(db: Session) -> None:
    lines = [json.loads(line) for line in EXPORT.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        line["properties"].pop("segmentCertainty")
    serve("\n".join(json.dumps(line) for line in lines).encode())
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(ItinerERoads())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_repeated_segment_id_fails_the_run(db: Session) -> None:
    text = EXPORT.read_text(encoding="utf-8").splitlines()
    serve("\n".join([text[2], text[2]]).encode())
    with pytest.raises(IngestFailedError, match="appears twice"):
        run_connector(ItinerERoads())


@respx.mock
def test_a_stale_copy_is_fetched_again(db: Session) -> None:
    route = serve(EXPORT.read_bytes())
    run_connector(ItinerERoads())
    with time_machine.travel(datetime.now(UTC) + timedelta(hours=21), tick=False):
        run_connector(ItinerERoads())
    assert route.call_count == 2
