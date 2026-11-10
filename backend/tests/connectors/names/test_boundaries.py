"""The ONS nation and county loaders, against GeoJSON recorded from ONS's layers.

See `tests/connectors/names/support.py` for how the fixtures were recorded.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from shapely.geometry import Point, box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.ingest.reference import get as get_loader
from fieldclub.ingest.reference import ons_boundaries
from fieldclub.ingest.reference.base import BBoxNotSupportedError, run_loader
from fieldclub.ingest.reference.ons_boundaries import (
    COUNTIES,
    COUNTRIES,
    ONS_STATEMENT,
    OnsCounties,
    OnsCountries,
    out_to_sea,
)
from fieldclub.ingest.runner import IngestFailedError
from fieldclub.models import AdminArea, Finding, Source
from fieldclub.services import context, findings, geo
from fieldclub.vocab import AdminAreaKind, FeatureClass, Nation
from tests.connectors.names.support import ONS_COUNTIES, ONS_COUNTRIES, serve_file, worklist_entry
from tests.helpers import AVEBURY, ClientAs, MakeUser

CARDIFF = (-3.1791, 51.4816)
EDINBURGH = (-3.1883, 55.9533)
BELFAST = (-5.9301, 54.5973)
DUBLIN = (-6.2603, 53.3498)
NORTH_SEA = (1.9, 52.9)
# In Wales by the fixture's simplified border, near Knighton, in a 1 km
# square (SO 34 72) that meets England too.
BORDER_WALES = (-2.97, 52.343)
SEVERN_BRIDGE = (-2.64, 51.61)
THE_WASH = (0.25, 52.95)


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    env(VAR_DIR=str(tmp_path / "var"))


@pytest.fixture
def few_counties(monkeypatch: pytest.MonkeyPatch) -> None:
    """The counties fixture holds only the 20 areas from the Welsh border to Wiltshire."""
    monkeypatch.setattr(ons_boundaries, "COUNTIES_PER_NATION", {Nation.WALES: 8})
    monkeypatch.setattr(ons_boundaries, "MIN_ENGLISH_COUNTIES", 12)


def serve_ons() -> tuple[respx.Route, respx.Route]:
    return (
        serve_file(f"{COUNTRIES}/query", ONS_COUNTRIES.read_bytes()),
        serve_file(f"{COUNTIES}/query", ONS_COUNTIES.read_bytes()),
    )


def areas(db: Session) -> list[tuple[str, str, str, bytes]]:
    db.expire_all()
    rows = db.scalars(select(AdminArea).order_by(AdminArea.kind, AdminArea.code)).all()
    return [(area.kind, area.code, area.name, bytes(area.geom.data)) for area in rows]


def test_the_loaders_are_registered() -> None:
    assert get_loader("ons-countries-2025") is OnsCountries
    assert get_loader("ons-counties-2025") is OnsCounties


def test_the_nations_carry_the_work_list_licence() -> None:
    entry = worklist_entry("ons-countries-2025")
    info = OnsCountries.source
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.attribution == entry["attribution"] == ONS_STATEMENT


def test_the_counties_carry_the_ons_licence() -> None:
    assert OnsCounties.source.licence == OnsCountries.source.licence == "Open Government Licence v3.0"
    assert OnsCounties.source.attribution == ONS_STATEMENT


@respx.mock
def test_the_nations_are_loaded_with_their_vocabulary_codes(db: Session) -> None:
    serve_ons()
    run = run_loader(OnsCountries())
    assert run.status == "completed"
    assert [(kind, code, name) for kind, code, name, _ in areas(db)] == [
        ("nation", "england", "England"),
        ("nation", "northern_ireland", "Northern Ireland"),
        ("nation", "scotland", "Scotland"),
        ("nation", "wales", "Wales"),
    ]
    source = db.get(Source, "ons-countries-2025")
    assert source is not None
    assert source.record_count == 4
    assert "Source: Office for National Statistics" in source.attribution
    assert "[year]" not in source.attribution


@respx.mock
@pytest.mark.usefixtures("few_counties")
def test_a_point_gets_its_nation_and_county(db: Session) -> None:
    serve_ons()
    run_loader(OnsCountries())
    run_loader(OnsCounties())
    assert geo.locate(db, *AVEBURY) == geo.Locality(nation="england", county="Wiltshire")
    assert geo.locate(db, *CARDIFF) == geo.Locality(nation="wales", county="Cardiff")
    assert geo.locate(db, *EDINBURGH).nation == "scotland"
    assert geo.locate(db, *BELFAST).nation == "northern_ireland"
    # Dublin is in Ireland, and the North Sea is in no nation.
    assert geo.locate(db, *DUBLIN) == geo.Locality(nation=None, county=None)
    assert geo.locate(db, *NORTH_SEA) == geo.Locality(nation=None, county=None)


@respx.mock
@pytest.mark.usefixtures("few_counties")
def test_the_status_bar_shows_nation_and_county(db: Session, client: TestClient) -> None:
    serve_ons()
    run_loader(OnsCountries())
    run_loader(OnsCounties())
    body = client.get("/api/v1/geo/point", params={"lon": AVEBURY[0], "lat": AVEBURY[1]}).json()
    assert (body["nation"], body["county"]) == ("england", "Wiltshire")
    assert [source["key"] for source in body["sources"]] == ["ons-counties-2025", "ons-countries-2025"]
    for source in body["sources"]:
        assert source["attribution"].startswith("Source: Office for National Statistics")


def test_the_loaders_fill_the_areas_whose_sources_go_with_them() -> None:
    loaders = {AdminAreaKind.NATION: OnsCountries.source.key, AdminAreaKind.COUNTY: OnsCounties.source.key}
    assert loaders == geo.AREA_SOURCES


@respx.mock
def test_each_nation_is_offered_only_its_own_viewers(db: Session) -> None:
    serve_ons()
    run_loader(OnsCountries())
    at_avebury = {link.key for link in context.links_for(db, *AVEBURY).links}
    assert "trove-map-at-point" not in at_avebury
    assert "he-apex-viewer" in at_avebury
    in_edinburgh = {link.key for link in context.links_for(db, *EDINBURGH).links}
    assert "trove-map-at-point" in in_edinburgh
    assert "he-apex-viewer" not in in_edinburgh


@respx.mock
def test_a_new_finding_gets_its_nation(db: Session, make_user: MakeUser) -> None:
    serve_ons()
    run_loader(OnsCountries())
    finding = findings.create_finding(
        db, make_user(), location=Point(*CARDIFF), feature_class=FeatureClass.ENCLOSURE
    )
    db.commit()
    assert finding.nation == "wales"


@respx.mock
def test_a_finding_at_sea_gets_the_nearest_nation(db: Session, make_user: MakeUser) -> None:
    serve_ons()
    run_loader(OnsCountries())
    assert geo.locate(db, *THE_WASH).nation is None
    finding = findings.create_finding(
        db, make_user(), location=Point(*THE_WASH), feature_class=FeatureClass.ENCLOSURE
    )
    assert finding.nation == "england"
    assert geo.nation_of(db, Point(*NORTH_SEA)) is None


@respx.mock
def test_a_point_in_an_estuary_between_nations_is_offered_both_nations_viewers(db: Session) -> None:
    """Not every viewer in Great Britain, as once happened for any point between two nations."""
    serve_ons()
    run_loader(OnsCountries())
    assert geo.locate(db, *SEVERN_BRIDGE).nation is None
    assert [code for code, _ in geo.nations_near(db, Point(*SEVERN_BRIDGE))] == ["england", "wales"]
    links = {link.key for link in context.links_for(db, *SEVERN_BRIDGE).links}
    assert "he-apex-viewer" in links
    assert "trove-map-at-point" not in links
    in_the_wash = {link.key for link in context.links_for(db, *THE_WASH).links}
    assert "he-apex-viewer" in in_the_wash
    assert "trove-map-at-point" not in in_the_wash


@respx.mock
def test_the_nation_of_a_finding_seen_only_by_its_square_comes_from_the_square(
    db: Session, client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    """Decision 0005: a square that meets two nations must not tell which side of the border a finding is."""
    serve_ons()
    run_loader(OnsCountries())
    finder = make_user()

    def barrow(at: tuple[float, float]) -> Finding:
        return findings.create_finding(
            db, finder, location=Point(*at), feature_class=FeatureClass.ROUND_BARROW
        )

    border, inland = barrow(BORDER_WALES), barrow(CARDIFF)
    db.commit()
    assert border.nation == inland.nation == "wales"
    assert border.sensitivity == inland.sensitivity == "protected"

    def nation(viewer: TestClient, finding: Finding) -> str | None:
        body = viewer.get(f"/api/v1/findings/{finding.public_id}").json()
        return body["nation"]

    assert nation(client, border) is None
    assert nation(client, inland) == "wales"
    member = client_as(make_user())
    assert nation(member, border) == "wales"
    assert nation(member, inland) == "wales"


@respx.mock
def test_running_twice_gives_the_same_areas(db: Session) -> None:
    countries, _ = serve_ons()
    run_loader(OnsCountries())
    before = areas(db)
    run_loader(OnsCountries())
    assert areas(db) == before
    assert countries.call_count == 1


@respx.mock
@pytest.mark.usefixtures("few_counties")
def test_nations_and_counties_replace_only_their_own_kind(db: Session) -> None:
    serve_ons()
    run_loader(OnsCountries())
    run_loader(OnsCounties())
    run_loader(OnsCountries())
    counts = dict(db.execute(select(AdminArea.kind, func.count()).group_by(AdminArea.kind)).all())
    assert counts == {"nation": 4, "county": 20}


def test_boundaries_are_loaded_whole() -> None:
    with pytest.raises(BBoxNotSupportedError, match="takes no --bbox"):
        run_loader(OnsCountries(), bbox=(-2, 51, -1, 52))


@respx.mock
def test_a_layer_short_of_counties_fails_and_stores_nothing(db: Session) -> None:
    """Without `few_counties`, the fixture's 20 areas are far short of the United Kingdom's."""
    serve_ons()
    with pytest.raises(IngestFailedError, match="areas per nation"):
        run_loader(OnsCounties())
    assert areas(db) == []


@respx.mock
def test_a_layer_that_changed_shape_fails_and_keeps_the_nations(
    db: Session, env: Callable[..., None], tmp_path: Path
) -> None:
    serve_ons()
    run_loader(OnsCountries())
    before = areas(db)
    changed: dict[str, Any] = json.loads(ONS_COUNTRIES.read_text(encoding="utf-8"))
    for feature in changed["features"]:
        feature["properties"]["CTRY26CD"] = feature["properties"].pop("CTRY25CD")
    serve_file(f"{COUNTRIES}/query", json.dumps(changed).encode())
    env(VAR_DIR=str(tmp_path / "later"))
    with pytest.raises(IngestFailedError, match="lack"):
        run_loader(OnsCountries())
    assert areas(db) == before


# --------------------------------------------------------------------------
# Out to sea, on the British grid
# --------------------------------------------------------------------------


def test_an_area_reaches_out_to_sea_except_where_it_meets_another() -> None:
    # Two areas side by side along a coast at y = 0, with the sea to the south.
    west, east = box(0, 0, 10_000, 10_000), box(10_000, 0, 20_000, 10_000)
    reached = out_to_sea({"west": west, "east": east}, seaward_m=2000)
    # The land is unchanged, and the border is still shared.
    assert reached["west"].covers(west)
    assert reached["east"].covers(east)
    assert reached["west"].intersection(reached["east"]).area == 0
    # A kilometre out to sea, well away from the border, is in the area it faces.
    assert reached["west"].covers(Point(3000, -1000))
    assert reached["east"].covers(Point(17_000, -1000))
    # Sea within reach of both, off the end of the border, is in neither.
    assert not reached["west"].covers(Point(10_000, -1000))
    assert not reached["east"].covers(Point(10_000, -1000))
    # Three kilometres out is in neither.
    assert not reached["west"].covers(Point(3000, -3000))


def test_the_reach_out_to_sea_never_crosses_land() -> None:
    # A peninsula of one area reaching past another's coast: the reach stops at land.
    home, neighbour = box(0, 0, 10_000, 10_000), box(10_500, 0, 12_000, 10_000)
    reached = out_to_sea({"home": home, "neighbour": neighbour}, seaward_m=2000)
    assert not reached["home"].intersects(neighbour.buffer(-1))
