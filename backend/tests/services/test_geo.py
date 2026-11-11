"""Working out the nation and county of a point, and the nearest place."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pyproj import Geod
from sqlalchemy.orm import Session

from fieldclub.errors import DataIntegrityError
from fieldclub.models import Place
from fieldclub.models.common import db_point
from fieldclub.services import geo
from fieldclub.services.geo import Locality, locate
from tests.helpers import add_source, admin_area


@pytest.fixture
def areas(db: Session) -> None:
    db.add_all(
        [
            # Rough boxes. Good enough to tell the test points apart.
            admin_area("nation", "england", "England", (-5.75, 49.9, 1.8, 55.8)),
            admin_area("nation", "wales", "Wales", (-5.4, 51.3, -2.9, 53.5)),
            admin_area("nation", "scotland", "Scotland", (-7.7, 55.5, -0.7, 60.9)),
            admin_area("county", "E06000054", "Wiltshire", (-2.4, 50.9, -1.4, 51.7)),
            admin_area("county", "W06000023", "Powys", (-3.9, 51.7, -2.9, 52.9)),
        ]
    )
    db.commit()


def test_nation_and_county(db: Session, areas: None) -> None:
    assert locate(db, -1.8542, 51.4286) == Locality(nation="england", county="Wiltshire")


def test_nation_without_a_county(db: Session, areas: None) -> None:
    assert locate(db, 0.12, 52.2) == Locality(nation="england", county=None)


def test_where_boundaries_overlap_the_smaller_area_wins(db: Session, areas: None) -> None:
    # Inside both the England box and the Wales box.
    assert locate(db, -3.4, 52.3) == Locality(nation="wales", county="Powys")


def test_points_on_a_boundary_are_covered(db: Session, areas: None) -> None:
    assert locate(db, -2.4, 51.0).county == "Wiltshire"


BELFAST = (-5.9301, 54.5964)
ENNISKILLEN = (-7.64, 54.344)
DUBLIN = (-6.2603, 53.3498)
CORK = (-8.4756, 51.8985)


def test_without_a_northern_ireland_boundary_nothing_is_guessed(db: Session, areas: None) -> None:
    # The Irish Grid covers the whole island, so it can't say which side of
    # the border a point is on.
    for lon, lat in (BELFAST, ENNISKILLEN, DUBLIN, CORK):
        assert locate(db, lon, lat) == Locality(nation=None, county=None)


def test_a_northern_ireland_boundary_is_used_when_there_is_one(db: Session, areas: None) -> None:
    db.add(admin_area("nation", "northern_ireland", "Northern Ireland", (-8.2, 54.0, -5.4, 55.4)))
    db.add(admin_area("county", "N09000003", "Belfast", (-6.1, 54.5, -5.8, 54.7)))
    db.commit()
    assert locate(db, *BELFAST) == Locality(nation="northern_ireland", county="Belfast")
    assert locate(db, *ENNISKILLEN) == Locality(nation="northern_ireland", county=None)


def test_the_republic_of_ireland_is_never_called_northern_ireland(db: Session, areas: None) -> None:
    db.add(admin_area("nation", "northern_ireland", "Northern Ireland", (-8.2, 54.0, -5.4, 55.4)))
    db.commit()
    assert locate(db, *DUBLIN) == Locality(nation=None, county=None)
    assert locate(db, *CORK) == Locality(nation=None, county=None)


def test_points_outside_everything_have_no_nation(db: Session, areas: None) -> None:
    assert locate(db, 2.3522, 48.8566) == Locality(nation=None, county=None)
    assert locate(db, -30.0, 55.0) == Locality(nation=None, county=None)


def test_with_no_boundaries_loaded_nowhere_has_a_nation(db: Session) -> None:
    assert locate(db, -1.8542, 51.4286) == Locality(nation=None, county=None)
    assert locate(db, *BELFAST) == Locality(nation=None, county=None)
    assert locate(db, *DUBLIN) == Locality(nation=None, county=None)


def test_a_nation_row_with_an_unknown_code_is_reported(db: Session) -> None:
    db.add(admin_area("nation", "E92000001", "England", (-6.0, 49.9, 1.8, 55.8)))
    db.commit()
    with pytest.raises(DataIntegrityError, match="E92000001"):
        locate(db, -1.8542, 51.4286)


# --------------------------------------------------------------------------
# The nearest place, for a suggested title
# --------------------------------------------------------------------------


def _place(db: Session, name: str, kind: str, lon: float, lat: float, rank: int) -> None:
    db.add(Place(name=name, kind=kind, geom=db_point(lon, lat), rank=rank, source="os-open-names"))


@pytest.fixture
def places(db: Session) -> None:
    add_source(db, "os-open-names", name="OS Open Names", category="community")
    _place(db, "Avebury", "Village", -1.8540, 51.4285, 712)
    _place(db, "Avebury Trusloe", "Hamlet", -1.8650, 51.4260, 503)
    _place(db, "Waden Hill", "Hill Or Mountain", -1.8500, 51.4220, 230)
    _place(db, "Marlborough", "Town", -1.7290, 51.4200, 830)
    db.commit()


@pytest.mark.usefixtures("places")
def test_the_nearest_place_is_the_nearest_settlement_with_its_distance(db: Session) -> None:
    # Waden Hill is nearer this point than either village, but a hill is no place to name a finding after.
    near = geo.nearest_place(db, -1.8512, 51.4230)
    assert near is not None
    assert (near.name, near.kind, near.source) == ("Avebury", "Village", "os-open-names")
    assert near.distance_m == pytest.approx(
        Geod(ellps="WGS84").inv(-1.8512, 51.4230, -1.8540, 51.4285)[2], abs=1.0
    )
    trusloe = geo.nearest_place(db, -1.8640, 51.4262)
    assert trusloe is not None
    assert trusloe.name == "Avebury Trusloe"


@pytest.mark.usefixtures("places")
def test_there_is_no_nearest_place_beyond_its_reach(db: Session) -> None:
    assert geo.nearest_place(db, -1.0, 51.0) is None
    assert geo.nearest_place(db, -1.8512, 51.4230, within_m=50) is None


def test_the_point_endpoint_names_the_nearest_place(client: TestClient, db: Session, places: None) -> None:
    body = client.get("/api/v1/geo/point", params={"lon": -1.8512, "lat": 51.4230}).json()
    place = body["place"]
    assert (place["name"], place["kind"]) == ("Avebury", "Village")
    assert place["distance_m"] == round(place["distance_m"])
    assert place["source"]["key"] == "os-open-names"
    assert place["source"]["attribution"]
    far = client.get("/api/v1/geo/point", params={"lon": -1.0, "lat": 51.0}).json()
    assert far["place"] is None
