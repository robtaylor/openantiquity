"""Capture years for the coverage layer, from a recorded sample of Defra's survey index."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from shapely.geometry import box

from fieldclub.http import get_client
from fieldclub.ingest.adapters.common import Polite
from fieldclub.terrain import years
from fieldclub.terrain.catalogue import england_catalogue
from fieldclub.terrain.years import IndexClient, Survey, flown_years, parse_years, years_by_tile

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded from the live WFS on 2026-11-10: a survey over Avebury, three in the south west and one
# on the Isles of Scilly, and the outlines of the three whose boxes span more than one tile.
INDEX = json.loads((FIXTURES / "survey_index.json").read_text())
OUTLINES = json.loads((FIXTURES / "survey_outlines.json").read_text())


def replay(request: httpx.Request) -> httpx.Response:
    query = parse_qs(urlsplit(str(request.url)).query)
    assert query["typeNames"] == [years.LAYER]
    if "resourceId" in query:
        wanted = set(query["resourceId"][0].split(","))
        assert query["srsName"] == ["EPSG:27700"]
        features = [feature for feature in OUTLINES["features"] if feature["id"] in wanted]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})
    return httpx.Response(200, json=INDEX)


@pytest.fixture
def index() -> IndexClient:
    return IndexClient(get_client(), Polite(delay_s=0, sleep=lambda seconds: None), expected=5)


def test_a_survey_counts_every_year_it_was_flown() -> None:
    assert flown_years({"sd_flown": "2018-12-10T00:00:00Z", "ed_flown": "2019-01-09T00:00:00Z"}) == (
        2018,
        2019,
    )
    assert flown_years({"sd_flown": "2020-03-01T00:00:00Z", "ed_flown": "2020-03-04T00:00:00Z"}) == (2020,)
    assert flown_years({"year": "2003", "sd_flown": None, "ed_flown": None}) == (2003,)


def test_an_index_that_returned_less_than_it_matched_is_refused() -> None:
    with pytest.raises(AssertionError, match="matched"):
        years.parse_surveys({**INDEX, "numberMatched": len(INDEX["features"]) + 1})


def test_years_come_from_the_recorded_index(index: IndexClient, tmp_path: Path) -> None:
    dest = tmp_path / "years.tsv"
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(years.WFS_URL).mock(side_effect=replay)
        found = years.build(england_catalogue(), index, dest)
    assert route.call_count == 2
    # Every request names the project.
    assert all(call.request.headers["User-Agent"].startswith("FieldClub/") for call in route.calls)
    # The Avebury survey covers the 5 km tiles round it.
    assert found["SU16nw"] == (2018, 2019)
    assert found["SU07se"] == (2018, 2019)
    # A survey wholly inside one tile counts for that tile alone.
    assert found["SY58nw"] == (2003,)
    assert parse_years(dest.read_text()) == found
    assert dest.read_text().startswith("# The years each 5 km tile")


def test_a_survey_that_only_touches_a_tile_does_not_add_its_year() -> None:
    catalogue = england_catalogue()
    # Inside SU16nw, with a 10 cm sliver along its eastern edge into SU16ne: 200 m² of it.
    outline = box(411_000, 166_000, 415_000.1, 168_000)
    survey = Survey("one", outline.bounds, (2015,))
    found = years_by_tile(catalogue, [survey], lambda ids: [("one", outline)])
    assert found == {"SU16nw": (2015,)}


def test_the_packaged_years_cover_every_tile() -> None:
    packaged = years.england_years()
    assert len(packaged) == len(england_catalogue())
    assert packaged["SU16nw"] == (2018, 2019)
    assert set(packaged) <= {tile.name for tile in england_catalogue()}
    assert len(years.years_edition()) == 12
