"""Scan a square: naming squares, keeping results, choosing the next square, and coverage."""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import SquareSurvey, User
from fieldclub.services import squares
from fieldclub.terrain.catalogue import england_catalogue
from fieldclub.vocab import SurveyResult
from tests.helpers import AVEBURY, ClientAs, MakeUser, admin_area, count, error_code, run_fresh

API = "/api/v1/squares"
# The square the henge at Avebury is in.
HENGE = "SU1069"


def survey(
    db: Session, user: User, square: str, result: SurveyResult = SurveyResult.NOTHING, n: int = 0
) -> None:
    squares.record_survey(db, user, squares.parse_square(square), result, findings_count=n)
    db.commit()


def distance_km(square: str, lon: float, lat: float) -> float:
    ref = squares.parse_square(square)
    _, easting, northing = gridref.to_grid(lon, lat)
    return (((ref.easting + 500 - easting) ** 2 + (ref.northing + 500 - northing) ** 2) ** 0.5) / 1000


# --------------------------------------------------------------------------
# Squares
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["SU1069", "su1069", "SU 10 69", " su10 69 "])
def test_a_square_is_named_by_its_1_km_reference(text: str) -> None:
    assert squares.name(squares.parse_square(text)) == HENGE


@pytest.mark.parametrize("text", ["SU16", "SU106699", "SU", "XX1069", "hello", ""])
def test_anything_else_is_not_a_square(text: str) -> None:
    with pytest.raises(squares.InvalidSquareError):
        squares.parse_square(text)


def test_only_squares_with_1_m_elevation_count() -> None:
    catalogue = england_catalogue()
    assert squares.has_elevation(squares.parse_square(HENGE), catalogue)
    # Edinburgh and Belfast: no England tile covers them.
    assert not squares.has_elevation(squares.parse_square("NT2573"), catalogue)
    assert not squares.has_elevation(squares.parse_square("J3374"), catalogue)


def test_the_squares_service_loads_no_raster_library() -> None:
    run_fresh(
        "import sys; import fieldclub.services.squares; "
        "loaded = sorted(m for m in sys.modules if m.startswith('fieldclub.terrain')); "
        "assert loaded == ['fieldclub.terrain', 'fieldclub.terrain.catalogue'], loaded; "
        "assert 'rasterio' not in sys.modules; assert 'pyogrio' not in sys.modules"
    )


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


def test_a_result_is_kept_once_per_person_and_square(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    user = make_user()
    me = client_as(user)
    first = me.put(f"{API}/su 10 69", json={"result": "nothing", "seconds": 120})
    assert first.status_code == 201, first.text
    assert first.json() | {"created_at": None} == {
        "square": HENGE,
        "grid_ref": "SU 10 69",
        "result": "nothing",
        "findings_count": 0,
        "seconds": 120,
        "created_at": None,
    }
    again = me.put(f"{API}/{HENGE}", json={"result": "marked", "findings_count": 2, "seconds": 300})
    assert again.status_code == 200
    assert (again.json()["result"], again.json()["findings_count"]) == ("marked", 2)
    stored = db.scalars(select(SquareSurvey)).one()
    assert (stored.user_id, stored.square, stored.result, stored.seconds) == (user.id, HENGE, "marked", 300)
    assert gridref.square_1km(*AVEBURY).polygon.equals_exact(squares.parse_square(HENGE).polygon(), 1e-9)
    client_as(make_user()).put(f"{API}/{HENGE}", json={"result": "skipped"})
    assert count(db, SquareSurvey) == 2


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"result": "nothing", "findings_count": 1}, "invalid_survey"),
        ({"result": "skipped", "findings_count": 3}, "invalid_survey"),
        ({"result": "marked"}, "invalid_survey"),
        ({"result": "marked", "findings_count": 101}, "validation_error"),
        ({"result": "nothing", "seconds": -1}, "validation_error"),
        ({"result": "nothing", "seconds": 86_401}, "validation_error"),
        ({"result": "looked"}, "validation_error"),
        ({"result": "nothing", "user_id": 1}, "validation_error"),
    ],
)
def test_a_result_must_make_sense(make_user: MakeUser, client_as: ClientAs, body: dict, code: str) -> None:
    response = client_as(make_user()).put(f"{API}/{HENGE}", json=body)
    assert response.status_code == 422
    assert error_code(response) == code


@pytest.mark.parametrize(("ref", "status", "code"), [("NT2573", 422, "square_has_no_elevation"),
                                                     ("SU16", 400, "invalid_square"),
                                                     ("x" * 40, 400, "invalid_square")])  # fmt: skip
def test_a_square_must_exist_and_have_elevation(
    make_user: MakeUser, client_as: ClientAs, ref: str, status: int, code: str
) -> None:
    response = client_as(make_user()).put(f"{API}/{ref}", json={"result": "nothing"})
    assert response.status_code == status
    assert error_code(response) == code


def test_recording_needs_a_contributor(client: TestClient, client_as: ClientAs, newcomer: User) -> None:
    assert client.put(f"{API}/{HENGE}", json={"result": "nothing"}).status_code == 401
    response = client_as(newcomer).put(f"{API}/{HENGE}", json={"result": "nothing"})
    assert error_code(response) == "onboarding_required"


# Part of TM58se, a partial tile on the Suffolk coast. TM5984's centre is offshore
# of Kessingland; TM4580's is inland. England here is everything west of 1.70 E.
OFFSHORE, INLAND = "TM5984", "TM4580"
ENGLAND_TO_1_70_E = (-6.5, 49.8, 1.70, 55.9)


def add_england(db: Session) -> None:
    db.add(admin_area("nation", "england", "England", ENGLAND_TO_1_70_E))
    db.commit()


def centre_lon(square: str) -> float:
    ref = squares.parse_square(square)
    lon, _ = gridref.transformer(27700, 4326).transform(ref.easting + 500, ref.northing + 500)
    return lon


def test_a_square_in_a_listed_tile_needs_its_centre_in_england(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    catalogue = england_catalogue()
    for square in (OFFSHORE, INLAND):
        assert squares.has_elevation(squares.parse_square(square), catalogue)
    add_england(db)
    assert not squares.scannable(db, squares.parse_square(OFFSHORE), catalogue)
    assert squares.scannable(db, squares.parse_square(INLAND), catalogue)
    me = client_as(make_user())
    offshore = me.put(f"{API}/{OFFSHORE}", json={"result": "nothing"})
    assert offshore.status_code == 422
    assert error_code(offshore) == "square_has_no_elevation"
    assert me.put(f"{API}/{INLAND}", json={"result": "nothing"}).status_code == 201


def test_the_next_square_on_the_coast_is_never_at_sea(db: Session) -> None:
    add_england(db)
    near = (1.75, 52.38)
    handed_out = {
        squares.name(squares.next_square(db, None, near=near, rng=random.Random(seed)).ref)
        for seed in range(30)
    }
    assert all(centre_lon(square) < 1.70 for square in handed_out), handed_out


def test_until_england_is_loaded_the_tile_alone_decides(db: Session) -> None:
    assert squares.england_area(db) is None
    assert squares.scannable(db, squares.parse_square(OFFSHORE), england_catalogue())


# --------------------------------------------------------------------------
# The next square
# --------------------------------------------------------------------------


def test_the_next_square_is_near_the_point_and_has_elevation(client: TestClient) -> None:
    response = client.get(f"{API}/next", params={"lon": AVEBURY[0], "lat": AVEBURY[1]})
    assert response.status_code == 200
    body = response.json()
    ref = squares.parse_square(body["square"])
    assert squares.has_elevation(ref, england_catalogue())
    assert distance_km(body["square"], *AVEBURY) < 5
    assert body["grid_ref"] == ref.format()
    assert body["geometry"]["type"] == "Polygon"
    west, south, east, north = body["bbox"]
    assert west < body["centre"][0] < east
    assert south < body["centre"][1] < north
    assert body["scans"] == 0


def test_without_a_point_the_next_square_is_anywhere_with_elevation(db: Session) -> None:
    seen = {squares.name(squares.next_square(db, None, rng=random.Random(seed)).ref) for seed in range(20)}
    assert len(seen) > 10
    assert all(squares.has_elevation(squares.parse_square(square), england_catalogue()) for square in seen)


def test_the_next_square_is_never_one_already_done(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    done: set[str] = set()
    for seed in range(60):
        chosen = squares.next_square(db, user, near=AVEBURY, rng=random.Random(seed))
        square = squares.name(chosen.ref)
        assert square not in done, f"{square} was handed out again"
        result = SurveyResult.SKIPPED if seed % 3 == 0 else SurveyResult.NOTHING
        survey(db, user, square, result)
        done.add(square)
    assert len(done) == 60


def test_signed_out_drafts_can_be_left_out(client: TestClient) -> None:
    params = {"lon": AVEBURY[0], "lat": AVEBURY[1]}
    left_out: list[str] = []
    for _ in range(15):
        response = client.get(f"{API}/next", params=params | {"exclude": left_out})
        assert response.json()["square"] not in left_out
        left_out.append(response.json()["square"])
    bad = client.get(f"{API}/next", params=params | {"exclude": ["SU1069", "SU16"]})
    assert error_code(bad) == "invalid_square"
    # A repeated parameter, as every list filter is: one value naming several squares is refused.
    joined = client.get(f"{API}/next", params=params | {"exclude": "SU1069,SU10"})
    assert error_code(joined) == "invalid_square"
    too_many = client.get(f"{API}/next", params=params | {"exclude": ["SU1069"] * 101})
    assert too_many.status_code == 422
    assert error_code(too_many) == "validation_error"


def test_people_asking_at_once_are_spread_over_several_squares(db: Session, make_user: MakeUser) -> None:
    people = [make_user() for _ in range(20)]
    chosen = [
        squares.name(squares.next_square(db, person, near=AVEBURY, rng=random.Random(n)).ref)
        for n, person in enumerate(people)
    ]
    assert len(set(chosen)) >= 5, chosen
    assert max(chosen.count(square) for square in chosen) <= 6, chosen


def test_squares_others_have_scanned_come_after_ones_nobody_has(db: Session, make_user: MakeUser) -> None:
    others = [make_user() for _ in range(3)]
    newcomer = make_user()
    nearest: list[str] = []
    for seed in range(squares.CHOICES * 2):
        square = squares.name(squares.next_square(db, others[0], near=AVEBURY, rng=random.Random(seed)).ref)
        nearest.append(square)
        for person in others:
            survey(db, person, square)
    for seed in range(30):
        square = squares.name(squares.next_square(db, newcomer, near=AVEBURY, rng=random.Random(seed)).ref)
        assert square not in nearest


def test_no_square_far_from_any_elevation(client: TestClient) -> None:
    response = client.get(f"{API}/next", params={"lon": -30.0, "lat": 50.0})
    assert response.status_code == 404
    assert error_code(response) == "no_square_available"
    assert error_code(client.get(f"{API}/next", params={"lon": -1.85})) == "invalid_point"


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def test_coverage_counts_people_per_square(db: Session, make_user: MakeUser, client: TestClient) -> None:
    ann, bob, cat = make_user(), make_user(), make_user()
    survey(db, ann, HENGE)
    survey(db, bob, HENGE, SurveyResult.MARKED, 2)
    survey(db, cat, HENGE, SurveyResult.SKIPPED)
    survey(db, ann, "SU1169", SurveyResult.SKIPPED)
    survey(db, ann, "SU1170")
    survey(db, ann, "SU5050")
    response = client.get(f"{API}/coverage", params={"bbox": "-1.9,51.4,-1.8,51.45"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=300"
    features = {f["id"]: f for f in response.json()["features"]}
    assert set(features) == {HENGE, "SU1170"}
    assert features[HENGE]["properties"] == {"square": HENGE, "scans": 2, "marked": 1}
    assert features["SU1170"]["properties"] == {"square": "SU1170", "scans": 1, "marked": 0}
    assert features[HENGE]["geometry"]["type"] == "Polygon"
    next_square = client.get(f"{API}/next", params={"lon": AVEBURY[0], "lat": AVEBURY[1]}).json()
    assert next_square["square"] != HENGE or next_square["scans"] == 2


@pytest.mark.parametrize(
    ("bbox", "code"),
    [
        ("-3,50,0,52", "bbox_too_large"),
        ("1,2,3", "invalid_bbox"),
        ("0,0,0,0", "invalid_bbox"),
        ("a,b,c,d", "invalid_bbox"),
    ],
)
def test_coverage_needs_a_modest_box(client: TestClient, bbox: str, code: str) -> None:
    response = client.get(f"{API}/coverage", params={"bbox": bbox})
    assert response.status_code == 400
    assert error_code(response) == code


def test_the_coverage_box_cap_is_about_50_km_square() -> None:
    assert 2400 < squares.area_km2((-1.75, 51.0, -1.03, 51.45)) < 2600
