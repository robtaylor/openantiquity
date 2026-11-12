"""Lines and shapes over HTTP: the contract's fields, every error code, the map's shapes and `/meta`."""

from __future__ import annotations

import math
from typing import Any

import pytest
from pyproj import Geod
from sqlalchemy.orm import Session

from fieldclub.services import shapes
from tests.findings.support import API, LAT, LON, point
from tests.helpers import ClientAs, MakeUser, error_code

GEOD = Geod(ellps="WGS84")
K = math.cos(math.radians(LAT))


def path_body(*points: tuple[float, float], kind: str = "corner", closed: bool = False, **extra: Any) -> dict:
    return {
        "closed": closed,
        "points": [{"lon": lon, "lat": lat, "kind": kind} for lon, lat in points],
        **extra,
    }


def up(*offsets: float, lon: float = LON, kind: str = "corner") -> dict:
    """A path of points up a meridian at these offsets from LAT."""
    return path_body(*((lon, LAT + offset) for offset in offsets), kind=kind)


def east(metres: float) -> float:
    lon, _, _ = GEOD.fwd(LON, LAT, 90, metres)
    return lon


def body(**fields: Any) -> dict:
    return {"feature_class": "linear", **fields}


# --------------------------------------------------------------------------
# Every error code
# --------------------------------------------------------------------------

_ZIGZAG = [(-3.0 + (i % 2) * 0.01, 50.5 + i * 0.0001) for i in range(shapes.SHAPE_MAX_VERTICES // 16 + 1)]
_BOW_TIE = [(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001)]


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"path": {**up(0, 0.01), "curve": "bezier"}}, "unknown_curve"),
        ({"path": up(0, 1e-7)}, "points_too_close"),
        (
            {"path": path_body(*((LON + i * 1e-5, LAT) for i in range(shapes.PATH_MAX_POINTS + 1)))},
            "path_too_many_points",
        ),
        ({"path": path_body(*_ZIGZAG, kind="smooth")}, "shape_too_complex"),
        (
            {"path": path_body((LON, LAT), (LON + 0.4, LAT), (LON + 0.4, LAT + 0.1), closed=True)},
            "shape_too_big",
        ),
        ({"path": path_body((-2.0, 50.6), (-2.0, 56.1))}, "line_too_long"),
        ({"location": point(east(2000), LAT), "path": up(0, 0.01)}, "outline_too_far"),
        ({"path": path_body(*_BOW_TIE, closed=True)}, "shape_crosses_itself"),
        (
            {
                "location": point(),
                "outline": {"type": "MultiLineString", "coordinates": [[[LON, LAT], [LON + 0.001, LAT]]]},
            },
            "outline_not_a_path",
        ),
        (
            {
                "location": point(),
                "path": up(0, 0.01),
                "outline": {"type": "LineString", "coordinates": [[LON, LAT], [LON, LAT + 0.01]]},
            },
            "outline_and_path",
        ),
        ({"path": path_body((2.30, 48.85), (2.31, 48.86))}, "outside_british_isles"),
        ({"path": path_body((LON, LAT), (LON + 0.01, LAT), closed=True)}, "validation_error"),
        (
            {"path": {"closed": False, "points": [{"lon": LON, "lat": LAT, "kind": "wiggly"}]}},
            "validation_error",
        ),
    ],
)
def test_creating_refuses_with_the_contracts_code(
    client_as: ClientAs, make_user: MakeUser, fields: dict, code: str
) -> None:
    response = client_as(make_user()).post(f"{API}/findings", json=body(**fields))
    assert (response.status_code, error_code(response)) == (422, code), response.text


def test_a_finding_without_a_point_or_a_path_is_one_error_with_one_status_on_both_routes(
    client_as: ClientAs, make_user: MakeUser
) -> None:
    client = client_as(make_user())
    created = client.post(f"{API}/findings", json=body())
    assert (created.status_code, error_code(created)) == (400, "location_required"), created.text
    made = client.post(f"{API}/findings", json=body(location=point())).json()
    edited = client.patch(f"{API}/findings/{made['public_id']}", json={"location": None})
    assert (edited.status_code, error_code(edited)) == (400, "location_required"), edited.text
    assert created.json()["error"]["message"] == edited.json()["error"]["message"]


def test_editing_refuses_a_stale_or_missing_revision_and_anyone_but_the_finder(
    client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    client = client_as(finder)
    made = client.post(f"{API}/findings", json=body(path=up(0, 0.01))).json()
    at = f"{API}/findings/{made['public_id']}"
    assert client.patch(at, json={"path": up(0, 0.01, 0.02), "path_revision": 0}).status_code == 200
    stale = client.patch(at, json={"path": up(0, 0.01, 0.03), "path_revision": 0})
    assert (stale.status_code, error_code(stale)) == (409, "shape_changed")
    missing = client.patch(at, json={"path": up(0, 0.01, 0.03)})
    assert (missing.status_code, error_code(missing)) == (422, "path_revision_required")
    stranger = client_as(make_user()).patch(at, json={"path": up(0, 0.01, 0.03), "path_revision": 1})
    assert (stranger.status_code, error_code(stranger)) == (403, "not_finder")
    too_far = client.patch(at, json={"location": point(east(3000), LAT)})
    assert (too_far.status_code, error_code(too_far)) == (422, "outline_too_far")


# --------------------------------------------------------------------------
# What the finding's page says
# --------------------------------------------------------------------------


def test_a_line_drawn_first_and_extended_over_http(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user())
    made = client.post(f"{API}/findings", json=body(path=up(0, 0.006, 0.012, kind="smooth")))
    assert made.status_code == 201, made.text
    where = made.json()["location"]
    assert (where["lon"], where["lat"]) == pytest.approx((LON, LAT + 0.006), abs=1e-6)
    assert where["shape_kind"] == "line"
    assert where["path"] == {**up(0, 0.006, 0.012, kind="smooth"), "curve": shapes.CURVE}
    assert where["outline"]["type"] == "LineString"
    shape = where["shape"]
    assert (shape["kind"], shape["revision"], shape["changes"], shape["added_since_looked_m"]) == (
        "line",
        0,
        [],
        None,
    )
    assert shape["length_m"] == pytest.approx(GEOD.inv(LON, LAT, LON, LAT + 0.012)[2], rel=1e-3)
    west, south, east_edge, north = shape["extent"]
    assert (south, north) == pytest.approx((LAT, LAT + 0.012), abs=1e-7)
    assert west <= LON <= east_edge

    extended = client.patch(
        f"{API}/findings/{made.json()['public_id']}",
        json={"path": up(0, 0.006, 0.012, 0.03, kind="smooth"), "path_revision": 0},
    )
    assert extended.status_code == 200, extended.text
    shape = extended.json()["location"]["shape"]
    assert shape["revision"] == 1
    (change,) = shape["changes"]
    assert change["kind"] == "extended"
    assert change["added_length_m"] == pytest.approx(GEOD.inv(LON, LAT + 0.012, LON, LAT + 0.03)[2], rel=0.01)
    assert set(change["added_view"]) == {"lon", "lat", "zoom"}
    assert extended.json()["location"]["lat"] == pytest.approx(LAT + 0.006, abs=1e-6)


def test_someone_who_sees_only_the_square_learns_only_that_the_shape_changed_and_when(
    client, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = client_as(make_user())
    made = finder.post(
        f"{API}/findings", json=body(path=up(0, 0.006, 0.012), sensitivity="restricted")
    ).json()
    at = f"{API}/findings/{made['public_id']}"
    finder.patch(at, json={"path": up(0, 0.006, 0.012, 0.02), "path_revision": 0})
    for viewer in (client, client_as(make_user())):
        where = viewer.get(at).json()["location"]
        assert where["obscured"] is True
        assert (where["outline"], where["path"], where["shape_kind"]) == (None, None, None)
        (change,) = where["shape"]["changes"]
        assert where["shape"] == {
            "kind": None,
            "length_m": None,
            "revision": None,
            "extent": None,
            "changes": [{"kind": "changed", "on": change["on"], "added_length_m": None, "added_view": None}],
            "added_since_looked_m": None,
            "added_view": None,
            "looked_at": None,
        }
        listed = viewer.get(f"{API}/findings").json()["items"]
        assert [item["location"]["shape_kind"] for item in listed] == [None]
    assert finder.get(f"{API}/findings").json()["items"][0]["location"]["shape_kind"] == "line"


def test_a_point_finding_has_an_empty_shape(client_as: ClientAs, make_user: MakeUser) -> None:
    made = client_as(make_user()).post(
        f"{API}/findings", json={"location": point(), "feature_class": "enclosure"}
    )
    where = made.json()["location"]
    assert (where["path"], where["outline"], where["shape_kind"]) == (None, None, None)
    assert where["shape"]["kind"] is None
    assert where["shape"]["changes"] == []


def test_an_outline_saved_before_paths_is_served_with_an_all_corner_path(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    from shapely.geometry import LineString

    from fieldclub.models import Finding
    from fieldclub.models.common import to_db_geometry

    finder = make_user()
    client = client_as(finder)
    made = client.post(f"{API}/findings", json={"location": point(), "feature_class": "linear"}).json()
    old = db.query(Finding).filter_by(public_id=made["public_id"]).one()
    old.outline = to_db_geometry(LineString([(LON, LAT), (LON, LAT + 0.004)]))
    db.commit()
    where = client.get(f"{API}/findings/{made['public_id']}").json()["location"]
    assert where["path"] == {**up(0, 0.004), "curve": shapes.CURVE}
    assert where["shape"]["kind"] == "line"
    assert where["shape"]["revision"] == 0


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------


def _wiggle(length: float = 0.2) -> dict:
    """Smooth points up a meridian, swinging 25 m east and west of it every 0.002 degrees."""
    count = int(length / 0.002) + 1
    return path_body(*((LON + (i % 2) * 0.0004, LAT + i * 0.002) for i in range(count)), kind="smooth")


def _features(client, **params: Any) -> list[dict]:
    response = client.get(f"{API}/findings", params={"format": "geojson", **params})
    assert response.status_code == 200, response.text
    return response.json()["features"]


def _vertices(feature: dict) -> int:
    shape = feature["properties"]["shape"]
    return len(shape["coordinates"] if shape["type"] == "LineString" else shape["coordinates"][0])


def test_the_map_sends_each_shape_simplified_for_the_zoom(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user())
    assert client.post(f"{API}/findings", json=body(path=_wiggle())).status_code == 201
    low, mid, full = (_vertices(feature) for zoom in (9, 14, 16) for feature in _features(client, zoom=zoom))
    assert _vertices(_features(client)[0]) == mid
    assert low < mid <= full
    for feature in _features(client, zoom=9):
        assert feature["geometry"]["type"] == "Point"
    for zoom in (8, 23):
        refused = client.get(f"{API}/findings", params={"format": "geojson", "zoom": zoom})
        assert (refused.status_code, error_code(refused)) == (422, "validation_error")


def test_the_map_clips_a_shape_to_the_box_widened_by_500_m(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user())
    client.post(f"{API}/findings", json=body(path=up(0, 0.1, 0.2)))
    box = (LON - 0.01, LAT + 0.05, LON + 0.01, LAT + 0.06)
    (feature,) = _features(client, zoom=16, bbox=",".join(map(str, box)))
    lats = [lat for _, lat in feature["properties"]["shape"]["coordinates"]]
    margin = 500 / 111_320
    assert min(lats) == pytest.approx(box[1] - margin, abs=2e-4)
    assert max(lats) == pytest.approx(box[3] + margin, abs=2e-4)


def test_a_box_matches_a_shape_only_for_someone_who_sees_it_exactly(
    client, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = client_as(make_user())
    restricted = finder.post(
        f"{API}/findings", json=body(path=up(0, 0.1, 0.2), sensitivity="restricted")
    ).json()
    opened = finder.post(f"{API}/findings", json=body(path=up(0, 0.1, 0.2, lon=LON + 0.05))).json()
    # The far end of both lines, kilometres from their anchors and squares.
    far_end = ",".join(map(str, (LON - 0.01, LAT + 0.18, LON + 0.06, LAT + 0.19)))
    assert {f["id"] for f in _features(finder, bbox=far_end)} == {
        restricted["public_id"],
        opened["public_id"],
    }
    for viewer in (client, client_as(make_user())):
        (only,) = _features(viewer, bbox=far_end)
        assert only["id"] == opened["public_id"]
        assert only["properties"]["shape"]["type"] == "LineString"
        listed = viewer.get(f"{API}/findings", params={"bbox": far_end}).json()["items"]
        assert [item["public_id"] for item in listed] == [opened["public_id"]]
        # Where it is seen as a square, it has no shape.
        (square,) = [f for f in _features(viewer) if f["id"] == restricted["public_id"]]
        assert square["properties"]["obscured"] is True
        assert square["properties"]["shape"] is None


# --------------------------------------------------------------------------
# /meta
# --------------------------------------------------------------------------


def test_meta_gives_the_shape_limits_and_the_curve(client) -> None:
    assert client.get(f"{API}/meta").json()["shapes"] == {
        "path_max_points": 5_000,
        "shape_max_vertices": 50_000,
        "shape_max_across_m": 25_000,
        "line_max_length_m": 600_000,
        "shape_max_gap_m": 1_000,
        "curve": "catmull-rom-centripetal-1",
        "looked_at_max_move_m": 250,
        "looked_at_min_kept": 0.75,
    }
