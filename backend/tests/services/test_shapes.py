"""The curve, the path's rules and the size limits (`services.shapes`). No database."""

from __future__ import annotations

import json
import math
from pathlib import Path as FilePath
from typing import Any

import pytest
from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from fieldclub.errors import ValidationFailedError
from fieldclub.services import shapes
from fieldclub.services.shapes import Path, PathPoint
from fieldclub.vocab import PointKind, ShapeChangeKind, ShapeKind

VECTORS_FILE = FilePath(__file__).resolve().parents[3] / "docs" / "architecture" / "curve-vectors.json"
GEOD = Geod(ellps="WGS84")
CORNER, SMOOTH = PointKind.CORNER, PointKind.SMOOTH

# Near Avebury.
LON, LAT = -1.854173, 51.428637


def path(*points: tuple[float, float, str], closed: bool = False) -> Path:
    return shapes.read_path(
        {"closed": closed, "points": [{"lon": lon, "lat": lat, "kind": kind} for lon, lat, kind in points]}
    )


def along_meridian(count: int, kind: str, step: float = 0.001) -> Path:
    return path(*((LON, LAT + i * step, kind) for i in range(count)))


def coords(geometry: BaseGeometry) -> list[tuple[float, float]]:
    assert isinstance(geometry, LineString | Polygon), geometry.geom_type
    line = geometry.exterior if isinstance(geometry, Polygon) else geometry
    return [(x, y) for x, y in line.coords]


def rounded(*positions: tuple[float, float]) -> list[tuple[float, float]]:
    """Positions as the curve writes them, to 7 places."""
    return [(round(x, 7), round(y, 7)) for x, y in positions]


def east_by(metres: float, lon: float = LON, lat: float = LAT) -> float:
    east, _, _ = GEOD.fwd(lon, lat, 90, metres)
    return east


# --------------------------------------------------------------------------
# The shared vectors
# --------------------------------------------------------------------------


def _vectors() -> dict[str, Any]:
    return json.loads(VECTORS_FILE.read_text(encoding="utf-8"))


def test_the_vectors_name_this_curve_and_cover_every_case_the_plan_lists() -> None:
    data = _vectors()
    assert data["curve"] == shapes.CURVE
    names = {vector["name"] for vector in data["vectors"]}
    assert names >= {
        "straight",
        "single-smooth",
        "mixed",
        "closed-all-smooth",
        "closed-one-corner",
        "hairpin",
        "unequal-spacing",
        "near-61-north",
        "at-49-9-north",
        "extended-at-start",
        "extended-at-end",
    }


@pytest.mark.parametrize("vector", _vectors()["vectors"], ids=lambda vector: vector["name"])
def test_each_vector_derives_to_its_expected_geometry(vector: dict[str, Any]) -> None:
    tolerance = _vectors()["tolerance_deg"]
    derived = shapes.derive(shapes.read_path(vector["path"]))
    expected = vector["expected"]
    assert derived.geom_type == expected["type"]
    ring = expected["coordinates"][0] if expected["type"] == "Polygon" else expected["coordinates"]
    got = coords(derived)
    assert len(got) == len(ring)
    for (x, y), (ex, ey) in zip(got, ring, strict=True):
        assert abs(x - ex) <= tolerance
        assert abs(y - ey) <= tolerance


@pytest.mark.parametrize(
    "vector", [v for v in _vectors()["vectors"] if "extends" in v], ids=lambda vector: vector["name"]
)
def test_an_extension_leaves_every_segment_more_than_one_from_the_new_point_alone(
    vector: dict[str, Any],
) -> None:
    """Checked from the vectors' own geometry, so the Vitest suite can check the same slices."""
    base = next(v for v in _vectors()["vectors"] if v["name"] == vector["extends"])
    kept = vector["unchanged"]
    before = base["expected"]["coordinates"][slice(*kept["base"])]
    after = vector["expected"]["coordinates"][slice(*kept["extended"])]
    assert before == after
    # The slice is every segment more than one from the new point.
    old, new = shapes.read_path(base["path"]), shapes.read_path(vector["path"])
    count = len(old.points)
    counts = shapes.segment_vertex_counts(old)
    added_at_start = new.points[1:] == old.points
    assert added_at_start or new.points[:-1] == old.points
    if added_at_start:
        kept_vertices = 1 + sum(counts[1:])
        assert kept["base"][1] - kept["base"][0] == kept_vertices
        assert kept["base"][1] == len(base["expected"]["coordinates"])
    else:
        kept_vertices = 1 + sum(counts[: count - 2])
        assert kept["base"] == [0, kept_vertices]


# --------------------------------------------------------------------------
# The curve, checked by hand
# --------------------------------------------------------------------------


def test_a_path_of_corners_is_its_points() -> None:
    corners = path((LON, LAT, CORNER), (LON + 0.002, LAT + 0.001, CORNER), (LON + 0.003, LAT, CORNER))
    assert coords(shapes.derive(corners)) == rounded(
        (LON, LAT), (LON + 0.002, LAT + 0.001), (LON + 0.003, LAT)
    )


def test_a_closed_path_of_corners_is_a_ring_ending_on_its_first_point() -> None:
    square = path(
        (LON, LAT, CORNER),
        (LON + 0.001, LAT, CORNER),
        (LON + 0.001, LAT + 0.001, CORNER),
        (LON, LAT + 0.001, CORNER),
        closed=True,
    )
    derived = shapes.derive(square)
    assert isinstance(derived, Polygon)
    assert coords(derived) == rounded(
        (LON, LAT), (LON + 0.001, LAT), (LON + 0.001, LAT + 0.001), (LON, LAT + 0.001), (LON, LAT)
    )


def test_smooth_points_evenly_spaced_on_a_meridian_give_evenly_spaced_samples() -> None:
    """Equal spacing makes equal knots, and Catmull-Rom then reproduces a straight line exactly.

    Each 0.001° segment is about 111 m, so it has ceil(0.001 / 0.0003) = 4 steps.
    """
    derived = shapes.derive(along_meridian(3, SMOOTH))
    expected = [(LON, round(LAT + j * 0.00025, 7)) for j in range(9)]
    assert len(coords(derived)) == len(expected)
    for (x, y), (ex, ey) in zip(coords(derived), expected, strict=True):
        assert x == pytest.approx(ex, abs=1e-7)
        assert y == pytest.approx(ey, abs=1e-7)


def test_one_smooth_point_between_corners_bends_symmetrically() -> None:
    """A smooth point at the top of a symmetric tent gives a curve mirrored about it."""
    k = math.cos(math.radians(LAT))
    dx = 0.001 / k
    tent = path((LON - dx, LAT, CORNER), (LON, LAT + 0.001, SMOOTH), (LON + dx, LAT, CORNER))
    got = coords(shapes.derive(tent))
    assert got[0] == (round(LON - dx, 7), LAT)
    assert got[-1] == (round(LON + dx, 7), LAT)
    middle = len(got) // 2
    assert got[middle] == (LON, LAT + 0.001)
    for (left_x, left_y), (right_x, right_y) in zip(got[:middle], reversed(got[middle + 1 :]), strict=True):
        assert left_x - LON == pytest.approx(LON - right_x, abs=2e-7)
        assert left_y == pytest.approx(right_y, abs=2e-7)
    # The curve bulges outside the straight tent between the corners and the top.
    assert got[1][1] > LAT + (got[1][0] - got[0][0]) * k


def test_samples_follow_the_segment_length_and_stop_at_sixteen() -> None:
    assert shapes.segment_vertex_counts(along_meridian(2, SMOOTH, step=0.0001)) == [2]
    assert shapes.segment_vertex_counts(along_meridian(2, SMOOTH, step=0.0012)) == [4]
    assert shapes.segment_vertex_counts(along_meridian(2, SMOOTH, step=0.01)) == [16]
    assert shapes.segment_vertex_counts(along_meridian(3, CORNER, step=0.01)) == [1, 1]


def test_derived_and_tapped_coordinates_are_rounded_to_seven_places() -> None:
    tapped = path((LON + 1.23456789e-8, LAT, CORNER), (LON + 0.001, LAT + 0.00049999996, SMOOTH))
    assert tapped.points[0].lon == round(LON + 1.23456789e-8, 7)
    for x, y in coords(shapes.derive(tapped)):
        assert x == round(x, 7)
        assert y == round(y, 7)


def test_a_path_writes_its_curve_when_stored_and_reads_back_the_same() -> None:
    tapped = path((LON, LAT, CORNER), (LON + 0.001, LAT, SMOOTH))
    stored = tapped.to_json()
    assert stored == {
        "closed": False,
        "curve": shapes.CURVE,
        "points": [
            {"lon": LON, "lat": LAT, "kind": "corner"},
            {"lon": round(LON + 0.001, 7), "lat": LAT, "kind": "smooth"},
        ],
    }
    assert shapes.read_path(stored) == tapped


# --------------------------------------------------------------------------
# What a path must be
# --------------------------------------------------------------------------


def _code(error: pytest.ExceptionInfo[ValidationFailedError]) -> str:
    return error.value.code


def test_another_curve_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as refused:
        shapes.read_path({"closed": False, "curve": "bezier", "points": []})
    assert _code(refused) == "unknown_curve"


@pytest.mark.parametrize(("count", "closed"), [(1, False), (2, True)])
def test_a_path_needs_two_points_or_three_when_closed(count: int, closed: bool) -> None:
    points = [(LON + i * 0.001, LAT + (i % 2) * 0.001, CORNER) for i in range(count)]
    with pytest.raises(ValidationFailedError) as refused:
        path(*points, closed=closed)
    assert _code(refused) == "validation_error"


def test_the_point_limit_is_counted_before_any_point_is_read() -> None:
    fits = [{"lon": LON + i * 1e-5, "lat": LAT, "kind": "corner"} for i in range(shapes.PATH_MAX_POINTS)]
    assert len(shapes.read_path({"closed": False, "points": fits}).points) == shapes.PATH_MAX_POINTS
    # Unreadable points past the limit are never looked at.
    with pytest.raises(ValidationFailedError) as refused:
        shapes.read_path({"closed": False, "points": [None] * (shapes.PATH_MAX_POINTS + 1)})
    assert _code(refused) == "path_too_many_points"


def test_points_closer_than_a_millionth_of_a_degree_are_refused() -> None:
    k = math.cos(math.radians(LAT))
    assert path((LON, LAT, CORNER), (LON + 1.1e-6 / k, LAT, CORNER))
    with pytest.raises(ValidationFailedError) as refused:
        path((LON, LAT, CORNER), (LON + 0.9e-6 / k, LAT, CORNER))
    assert _code(refused) == "points_too_close"
    # The last and the first of a closed path count as neighbours.
    with pytest.raises(ValidationFailedError) as closing:
        path(
            (LON, LAT, CORNER),
            (LON + 0.001, LAT, CORNER),
            (LON + 0.001, LAT + 0.001, CORNER),
            (LON, LAT + 5e-7, CORNER),
            closed=True,
        )
    assert _code(closing) == "points_too_close"


@pytest.mark.parametrize(
    "point",
    [
        {"lon": LON, "lat": LAT},
        {"lon": LON, "lat": LAT, "kind": "bezier"},
        {"lon": "west", "lat": LAT, "kind": "corner"},
        {"lon": math.nan, "lat": LAT, "kind": "corner"},
        {"lon": LON, "lat": 90.0, "kind": "corner"},
        {"lon": 181.0, "lat": LAT, "kind": "corner"},
        {"lon": True, "lat": LAT, "kind": "corner"},
    ],
)
def test_a_malformed_point_is_refused(point: dict[str, Any]) -> None:
    good = {"lon": LON + 0.01, "lat": LAT, "kind": "corner"}
    with pytest.raises(ValidationFailedError) as refused:
        shapes.read_path({"closed": False, "points": [good, point]})
    assert _code(refused) == "validation_error"


# --------------------------------------------------------------------------
# The limits, each at its edge and one past it
# --------------------------------------------------------------------------


def test_the_limits_are_the_contracts() -> None:
    assert (shapes.PATH_MAX_POINTS, shapes.SHAPE_MAX_VERTICES) == (5_000, 50_000)
    assert (shapes.SHAPE_MAX_ACROSS_M, shapes.LINE_MAX_LENGTH_M, shapes.SHAPE_MAX_GAP_M) == (
        25_000,
        600_000,
        1_000,
    )


def test_a_closed_shape_may_be_25_km_across_and_no_more() -> None:
    def area(across_m: float) -> Path:
        east = east_by(across_m)
        return path((LON, LAT, CORNER), (east, LAT, CORNER), (east, LAT + 0.01, CORNER), closed=True)

    fits = shapes.shape_of(area(shapes.SHAPE_MAX_ACROSS_M - 10))
    assert fits.kind is ShapeKind.AREA
    with pytest.raises(ValidationFailedError) as refused:
        shapes.shape_of(area(shapes.SHAPE_MAX_ACROSS_M + 10))
    assert _code(refused) == "shape_too_big"


def test_a_closed_shape_is_measured_north_to_south_too() -> None:
    _, north, _ = GEOD.fwd(LON, LAT, 0, shapes.SHAPE_MAX_ACROSS_M + 10)
    tall = path((LON, LAT, CORNER), (LON + 0.001, LAT, CORNER), (LON, north, CORNER), closed=True)
    with pytest.raises(ValidationFailedError) as refused:
        shapes.shape_of(tall)
    assert _code(refused) == "shape_too_big"


def test_a_line_has_no_across_limit_but_may_run_600_km_and_no_more() -> None:
    """A line along the 51st parallel or so, of corners every 100 km."""

    def line(length_m: float) -> Path:
        points = [(-5.0, 52.0, CORNER)]
        lon, lat = -5.0, 52.0
        remaining = length_m
        while remaining > 0:
            lon, lat, _ = GEOD.fwd(lon, lat, 80, min(100_000.0, remaining))
            remaining -= 100_000.0
            points.append((lon, lat, CORNER))
        return path(*points)

    fits = shapes.shape_of(line(shapes.LINE_MAX_LENGTH_M - 100))
    assert fits.kind is ShapeKind.LINE
    assert fits.length_m == pytest.approx(shapes.LINE_MAX_LENGTH_M - 100, abs=5)
    with pytest.raises(ValidationFailedError) as refused:
        shapes.shape_of(line(shapes.LINE_MAX_LENGTH_M + 100))
    assert _code(refused) == "line_too_long"


def test_the_derived_vertex_limit_is_counted_before_the_curve_is_drawn() -> None:
    # Smooth points 0.01° apart take 16 samples each: 3,125 segments make 50,001 vertices.
    count = shapes.SHAPE_MAX_VERTICES // 16 + 1
    long = shapes.read_path(
        {
            "closed": False,
            "points": [
                {"lon": -3.0 + (i % 2) * 0.01, "lat": 50.0 + i * 0.0001, "kind": "smooth"}
                for i in range(count)
            ],
        }
    )
    assert 1 + sum(shapes.segment_vertex_counts(long)) == shapes.SHAPE_MAX_VERTICES + 1
    with pytest.raises(ValidationFailedError) as refused:
        shapes.shape_of(long)
    assert _code(refused) == "shape_too_complex"
    # One point fewer passes the count, and is then too long: no open line inside
    # 600 km can take 50,000 vertices, so only an area's perimeter reaches the cap.
    fits = Path(closed=False, points=long.points[:-1])
    assert 1 + sum(shapes.segment_vertex_counts(fits)) == shapes.SHAPE_MAX_VERTICES - 15
    with pytest.raises(ValidationFailedError) as too_long:
        shapes.shape_of(fits)
    assert _code(too_long) == "line_too_long"


def test_a_closed_shape_that_crosses_itself_is_refused() -> None:
    bow_tie = path(
        (LON, LAT, CORNER),
        (LON + 0.001, LAT + 0.001, CORNER),
        (LON + 0.001, LAT, CORNER),
        (LON, LAT + 0.001, CORNER),
        closed=True,
    )
    with pytest.raises(ValidationFailedError) as refused:
        shapes.shape_of(bow_tie)
    assert _code(refused) == "shape_crosses_itself"
    # The same points as an open line are fine: a line may cross itself.
    assert shapes.shape_of(Path(closed=False, points=bow_tie.points)).kind is ShapeKind.LINE


def test_a_placed_point_must_be_within_a_kilometre_of_the_shape() -> None:
    line = shapes.shape_of(path((LON, LAT, CORNER), (LON, LAT + 0.01, CORNER)))
    shapes.check_shape(line.geometry, Point(east_by(shapes.SHAPE_MAX_GAP_M - 5), LAT + 0.005))
    with pytest.raises(ValidationFailedError) as refused:
        shapes.check_shape(line.geometry, Point(east_by(shapes.SHAPE_MAX_GAP_M + 5), LAT + 0.005))
    assert _code(refused) == "outline_too_far"
    # Inside an area is no distance at all.
    k = math.cos(math.radians(LAT))
    ring = [(LON - 0.02 / k, LAT - 0.02), (LON + 0.02 / k, LAT - 0.02), (LON, LAT + 0.02)]
    area = shapes.shape_of(path(*((x, y, CORNER) for x, y in ring), closed=True))
    shapes.check_shape(area.geometry, Point(LON, LAT))


# --------------------------------------------------------------------------
# A shape's measures, simplifications and anchor
# --------------------------------------------------------------------------


def test_a_shape_carries_its_kind_length_and_simplifications() -> None:
    line = shapes.shape_of(along_meridian(5, SMOOTH, step=0.01))
    assert line.kind is ShapeKind.LINE
    _, _, metres = GEOD.inv(LON, LAT, LON, LAT + 0.04)
    assert line.length_m == pytest.approx(metres, rel=1e-6)
    # Straight, so both simplifications keep the ends alone.
    assert coords(line.mid) == [(LON, LAT), (LON, LAT + 0.04)]
    assert coords(line.low) == [(LON, LAT), (LON, LAT + 0.04)]


def test_a_wiggle_smaller_than_the_low_tolerance_goes_from_low_but_not_mid() -> None:
    wiggle = shapes.shape_of(
        path((LON, LAT, CORNER), (LON + 0.0002, LAT + 0.005, CORNER), (LON, LAT + 0.01, CORNER))
    )
    assert len(coords(wiggle.mid)) == 3
    assert len(coords(wiggle.low)) == 2


def test_a_lines_derived_anchor_is_the_vertex_nearest_half_its_length() -> None:
    line = shapes.shape_of(
        path(
            (LON, LAT, CORNER),
            (LON, LAT + 0.01, CORNER),
            (LON, LAT + 0.011, CORNER),
            (LON, LAT + 0.03, CORNER),
        )
    )
    # Half of 0.03° is 0.015°, nearest the vertex at 0.011°.
    assert shapes.derived_anchor(line).coords[0] == (LON, round(LAT + 0.011, 7))


def test_an_areas_derived_anchor_is_its_centroid_or_a_point_inside() -> None:
    k = math.cos(math.radians(LAT))
    square = [(LON, LAT), (LON + 0.01 / k, LAT), (LON + 0.01 / k, LAT + 0.01), (LON, LAT + 0.01)]
    area = shapes.shape_of(path(*((x, y, CORNER) for x, y in square), closed=True))
    anchor = shapes.derived_anchor(area)
    assert (anchor.x, anchor.y) == pytest.approx((LON + 0.005 / k, LAT + 0.005), abs=1e-7)
    # A C shape's centroid lies in its mouth, so the anchor is somewhere inside instead.
    c_shape = [
        (LON, LAT),
        (LON + 0.01, LAT),
        (LON + 0.01, LAT + 0.002),
        (LON + 0.002, LAT + 0.002),
        (LON + 0.002, LAT + 0.008),
        (LON + 0.01, LAT + 0.008),
        (LON + 0.01, LAT + 0.01),
        (LON, LAT + 0.01),
    ]
    area = shapes.shape_of(path(*((x, y, CORNER) for x, y in c_shape), closed=True))
    assert not area.geometry.contains(area.geometry.centroid)
    assert area.geometry.contains(shapes.derived_anchor(area))


def test_the_nearest_point_on_a_shape_and_the_distance_to_it_are_in_metres() -> None:
    line = shapes.shape_of(path((LON, LAT, CORNER), (LON, LAT + 0.01, CORNER)))
    off = Point(east_by(300), LAT + 0.004)
    nearest = shapes.nearest_point(line.geometry, off)
    assert (nearest.x, nearest.y) == pytest.approx((LON, LAT + 0.004), abs=1e-7)
    assert shapes.distance_m(line.geometry, off) == pytest.approx(300, abs=0.5)


# --------------------------------------------------------------------------
# Old outlines
# --------------------------------------------------------------------------


def test_a_line_or_one_ring_outline_becomes_an_all_corner_path_that_derives_to_itself() -> None:
    line = LineString([(LON, LAT), (LON + 0.001, LAT), (LON + 0.001, LAT + 0.001)])
    from_line = shapes.path_from_outline(line)
    assert from_line is not None
    assert not from_line.closed
    assert {point.kind for point in from_line.points} == {CORNER}
    assert coords(shapes.derive(from_line)) == rounded(*coords(line))
    ring = Polygon([(LON, LAT), (LON + 0.001, LAT), (LON + 0.001, LAT + 0.001)])
    from_ring = shapes.path_from_outline(ring)
    assert from_ring is not None
    assert from_ring.closed
    assert len(from_ring.points) == 3
    assert coords(shapes.derive(from_ring)) == rounded(*coords(ring))


def test_an_outline_that_isnt_one_line_or_one_ring_has_no_path() -> None:
    from shapely.geometry import MultiLineString

    holed = Polygon(
        [(LON, LAT), (LON + 0.01, LAT), (LON + 0.01, LAT + 0.01), (LON, LAT + 0.01)],
        [[(LON + 0.004, LAT + 0.004), (LON + 0.006, LAT + 0.004), (LON + 0.005, LAT + 0.006)]],
    )
    assert shapes.path_from_outline(holed) is None
    assert shapes.path_from_outline(MultiLineString([[(LON, LAT), (LON + 0.01, LAT)]])) is None
    assert shapes.path_from_outline(Point(LON, LAT)) is None


# --------------------------------------------------------------------------
# Classifying a change
# --------------------------------------------------------------------------

A = (LON, LAT, CORNER)
B = (LON + 0.001, LAT, SMOOTH)
C = (LON + 0.002, LAT + 0.001, SMOOTH)
D = (LON + 0.003, LAT, CORNER)
E = (LON + 0.004, LAT + 0.001, SMOOTH)


@pytest.mark.parametrize(
    ("old", "new", "kind"),
    [
        (None, path(A, B), ShapeChangeKind.DRAWN),
        (path(A, B), None, ShapeChangeKind.REMOVED),
        (path(B, C), path(A, B, C), ShapeChangeKind.EXTENDED),
        (path(B, C), path(B, C, D), ShapeChangeKind.EXTENDED),
        (path(B, C), path(A, B, C, D, E), ShapeChangeKind.EXTENDED),
        (path(A, B, C), path(A, C), ShapeChangeKind.RESHAPED),
        (path(A, B, D), path(A, B, C, D), ShapeChangeKind.RESHAPED),
        (path(A, B, C), path(A, B, (C[0], C[1], CORNER)), ShapeChangeKind.RESHAPED),
        (path(A, B, C), path(C, B, A), ShapeChangeKind.RESHAPED),
        (path(A, B, C), path(A, B, C, closed=True), ShapeChangeKind.CLOSED),
        (path(A, B, C, closed=True), path(A, B, C), ShapeChangeKind.OPENED),
        (path(A, B, C, closed=True), path(A, B, C, D, closed=True), ShapeChangeKind.RESHAPED),
        (path(A, B, C), path(A, B, C), None),
        (None, None, None),
    ],
)
def test_classify_change(old: Path | None, new: Path | None, kind: ShapeChangeKind | None) -> None:
    assert shapes.classify_change(old, new) is kind


def test_an_extensions_view_frames_the_added_part_alone() -> None:
    old = along_meridian(3, CORNER, step=0.01)
    new = Path(closed=False, points=(*old.points, PathPoint(LON, LAT + 0.05, CORNER)))
    view = shapes.added_view(old, new)
    assert view is not None
    assert (view["lon"], view["lat"]) == pytest.approx((LON, LAT + 0.035), abs=1e-6)
    assert 9 <= view["zoom"] <= 17
    smaller = Path(closed=False, points=(*old.points, PathPoint(LON, LAT + 0.021, CORNER)))
    smaller_view = shapes.added_view(old, smaller)
    assert smaller_view is not None
    assert smaller_view["zoom"] > view["zoom"]
    assert shapes.added_view(old, Path(closed=False, points=old.points[:2])) is None
