"""A finding's line or shape: the points its finder tapped, the curve through them, and the limits.

The path is the source of truth. `derive` makes the stored geometry from it
with one fixed curve, `catmull-rom-centripetal-1`, so a finder can reopen a
path, move a point or extend it, and the geometry can be made again if the
curve's definition ever changes. The definition is in prose in
`docs/plans/lines-and-curves.md` ("The curve") and as data in
`docs/architecture/curve-vectors.json`, which the backend and the frontend
suites both read.

1. An open path of n points has segments P[i] to P[i+1]. A closed one also
   has P[n-1] to P[0], and its indices wrap.
2. A segment between two corners emits its end point alone.
3. Otherwise its ends A and B take their real neighbours where A or B is
   smooth and the neighbour exists, and a phantom otherwise, made in the
   projected plane as 2A' - B' or 2B' - A'.
4. Each segment projects with its own scale k = cos((A.lat + B.lat) / 2), so
   extending a path changes no segment more than one from the new point.
5. Knots are centripetal: each interval is the square root of the projected
   distance.
6. A segment of projected length L has N = min(16, max(2, ceil(L / 0.0003)))
   steps. It emits the curve at j / N for j = 1 .. N-1, then B itself.
7. The curve is evaluated in the Barry-Goldman form.
8. The geometry starts at P[0]. An open path is a LineString, a closed one a
   one-ring Polygon. Every coordinate is rounded to 7 decimal places, the
   tapped points as they are read.

Nothing here touches the database, so the backfill and the tests use it
directly. Checking that a shape lies in the British Isles is
`services.findings.check_in_british_isles`, which runs after these limits.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from fieldclub.errors import ValidationFailedError
from fieldclub.vocab import PointKind, ShapeChangeKind, ShapeKind

CURVE = "catmull-rom-centripetal-1"

# The limits, and why each is set where it is: `docs/plans/lines-and-curves.md`, "Limits".
PATH_MAX_POINTS = 5_000
SHAPE_MAX_VERTICES = 50_000
SHAPE_MAX_ACROSS_M = 25_000
LINE_MAX_LENGTH_M = 600_000
SHAPE_MAX_GAP_M = 1_000
# A derived anchor stays where it is while the shape still passes this close.
ANCHOR_KEEP_M = 25

# Two neighbouring points closer than this in the projected plane would make
# the curve divide by almost nothing.
POINT_MIN_SEPARATION_DEG = 1e-6
DECIMALS = 7
# One sample about every 33 m, and at most 16 a segment.
SAMPLE_SPACING_DEG = 0.0003
SAMPLES_MIN = 2
SAMPLES_MAX = 16

# The simplified copies: about 3 to 5 m, for zooms 13 to 15 and the finding
# page, and about 35 to 55 m, for zooms 9 to 12.
SIMPLIFY_MID_DEG = 0.00005
SIMPLIFY_LOW_DEG = 0.0005

# A view that frames an extension: the findings overlay starts at zoom 9, and
# closer than 17 shows nothing more of an earthwork.
VIEW_MIN_ZOOM = 9
VIEW_MAX_ZOOM = 17
# The part of the screen the added part is fitted into, in CSS pixels, and a map tile's size.
_VIEW_WIDTH_PX = 600
_VIEW_HEIGHT_PX = 400
_TILE_PX = 256

GEOD = Geod(ellps="WGS84")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class UnknownCurveError(ValidationFailedError):
    code = "unknown_curve"
    message = f"The only curve is {CURVE}. Leave `curve` out and the server writes it."


class PointsTooCloseError(ValidationFailedError):
    code = "points_too_close"
    message = "Two neighbouring points are on top of each other. Move one, or delete it."


class PathTooManyPointsError(ValidationFailedError):
    code = "path_too_many_points"
    message = f"A line or shape can have at most {PATH_MAX_POINTS:,} points."


class ShapeTooComplexError(ValidationFailedError):
    code = "shape_too_complex"
    message = (
        f"That would draw more than {SHAPE_MAX_VERTICES:,} vertices. Use straight points on the long "
        "straight stretches."
    )


class ShapeTooBigError(ValidationFailedError):
    code = "shape_too_big"
    message = f"A closed shape can be at most {SHAPE_MAX_ACROSS_M // 1000} km across."


class LineTooLongError(ValidationFailedError):
    code = "line_too_long"
    message = f"A line can be at most {LINE_MAX_LENGTH_M // 1000} km long."


class OutlineTooFarError(ValidationFailedError):
    code = "outline_too_far"
    message = f"The line or shape must come within {SHAPE_MAX_GAP_M:,} m of the marked point."


class ShapeCrossesItselfError(ValidationFailedError):
    code = "shape_crosses_itself"
    message = "A closed shape's edge can't cross itself."


class OutlineNotAPathError(ValidationFailedError):
    code = "outline_not_a_path"
    message = "An outline must be one line or one ring without holes. Send it as a `path` instead."


class OutlineAndPathError(ValidationFailedError):
    code = "outline_and_path"
    message = "Send the shape as a `path` or as an `outline`, not both."


# --------------------------------------------------------------------------
# The path
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PathPoint:
    lon: float
    lat: float
    kind: PointKind


@dataclass(frozen=True)
class Path:
    """The points a finder tapped, in order, and whether the shape is closed.

    Make one with `read_path`, which checks it. Built directly, as the tests
    and `path_from_outline` do, it must already hold rounded points.
    """

    closed: bool
    points: tuple[PathPoint, ...]

    def to_json(self) -> dict[str, Any]:
        """As stored in `findings.path` and served: the curve is always written."""
        return {
            "closed": self.closed,
            "curve": CURVE,
            "points": [{"lon": p.lon, "lat": p.lat, "kind": p.kind.value} for p in self.points],
        }


_NOT_DEGREES = "Each point needs `lon` and `lat` in degrees and a `kind` of corner or smooth."


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        # False for NaN and the infinities, and for an int too large to be a float.
        and abs(value) <= sys.float_info.max
    )


def _read_point(value: Any) -> PathPoint:
    if not isinstance(value, Mapping):
        raise ValidationFailedError(_NOT_DEGREES)
    lon, lat, kind = value.get("lon"), value.get("lat"), value.get("kind")
    if not (_is_number(lon) and _is_number(lat)) or kind not in tuple(PointKind):
        raise ValidationFailedError(_NOT_DEGREES)
    lon, lat = float(lon), float(lat)  # pyright: ignore[reportArgumentType]
    # At a pole the projection's scale is nothing.
    if not (-180 <= lon <= 180 and -90 < lat < 90):
        raise ValidationFailedError(_NOT_DEGREES)
    return PathPoint(round(lon, DECIMALS), round(lat, DECIMALS), PointKind(kind))


def read_path(data: Mapping[str, Any]) -> Path:
    """A checked path from a request or from storage, with its points rounded.

    The points are counted before any is read, so a huge path costs no more
    than its length. Raises `PathTooManyPointsError`, `UnknownCurveError`,
    `PointsTooCloseError`, or `ValidationFailedError` for anything malformed.
    """
    points = data.get("points")
    if not isinstance(points, list | tuple):
        raise ValidationFailedError("A path needs a list of `points`.")
    if len(points) > PATH_MAX_POINTS:
        raise PathTooManyPointsError()
    if data.get("curve") not in (None, CURVE):
        raise UnknownCurveError()
    closed = data.get("closed", False)
    if not isinstance(closed, bool):
        raise ValidationFailedError("`closed` is true or false.")
    least = 3 if closed else 2
    if len(points) < least:
        raise ValidationFailedError(
            "A closed shape needs three points at least." if closed else "A line needs two points at least."
        )
    path = Path(closed=closed, points=tuple(_read_point(point) for point in points))
    for a, b in _pairs(path):
        if _projected_distance(a, b) < POINT_MIN_SEPARATION_DEG:
            raise PointsTooCloseError()
    return path


def _pairs(path: Path) -> Iterator[tuple[PathPoint, PathPoint]]:
    """Each segment's two ends, in order, the closing one included."""
    points = path.points
    for i in range(len(points) - 1):
        yield points[i], points[i + 1]
    if path.closed:
        yield points[-1], points[0]


def _scale(a: PathPoint, b: PathPoint) -> float:
    return math.cos(math.radians((a.lat + b.lat) / 2))


def _projected_distance(a: PathPoint, b: PathPoint) -> float:
    k = _scale(a, b)
    return math.hypot((b.lon - a.lon) * k, b.lat - a.lat)


def path_from_outline(outline: BaseGeometry) -> Path | None:
    """An all-corner path that derives to `outline` exactly, or None when it isn't one line or one ring.

    For outlines saved before paths existed, and for a request that still sends
    an `outline`. The points are taken as stored, not checked: `read_path` on
    `to_json()` checks them.
    """
    if isinstance(outline, LineString):
        closed, positions = False, list(outline.coords)
    elif isinstance(outline, Polygon) and not outline.interiors:
        closed, positions = True, list(outline.exterior.coords)[:-1]
    else:
        return None
    return Path(
        closed=closed,
        points=tuple(
            PathPoint(round(x, DECIMALS), round(y, DECIMALS), PointKind.CORNER) for x, y, *_ in positions
        ),
    )


def stored_path(path: Mapping[str, Any] | None, outline: BaseGeometry | None) -> Path | None:
    """A finding's path as stored, or for an outline saved before paths, the all-corner path it is.

    None without a shape, and for an old outline of several parts or with
    holes, which can be replaced but not changed.
    """
    if path is not None:
        return read_path(path)
    if outline is not None:
        return path_from_outline(outline)
    return None


def kind_of(geometry: BaseGeometry) -> ShapeKind:
    """Whether an outline is a line or an area, for one saved before `shape_kind` was."""
    return ShapeKind.LINE if geometry.geom_type in ("LineString", "MultiLineString") else ShapeKind.AREA


# --------------------------------------------------------------------------
# The curve
# --------------------------------------------------------------------------


def _steps(length: float) -> int:
    return min(SAMPLES_MAX, max(SAMPLES_MIN, math.ceil(length / SAMPLE_SPACING_DEG)))


@dataclass(frozen=True)
class _Segment:
    index: int
    a: PathPoint
    b: PathPoint
    # The neighbours where they are real and used, else None for a phantom.
    prev: PathPoint | None
    next: PathPoint | None

    @property
    def straight(self) -> bool:
        return self.a.kind is PointKind.CORNER and self.b.kind is PointKind.CORNER

    def vertex_count(self) -> int:
        return 1 if self.straight else _steps(_projected_distance(self.a, self.b))


def _segments(path: Path) -> Iterator[_Segment]:
    points, n = path.points, len(path.points)
    for i in range(n if path.closed else n - 1):
        j = (i + 1) % n
        a, b = points[i], points[j]
        has_prev = path.closed or i > 0
        has_next = path.closed or j < n - 1
        yield _Segment(
            index=i,
            a=a,
            b=b,
            prev=points[(i - 1) % n] if a.kind is PointKind.SMOOTH and has_prev else None,
            next=points[(j + 1) % n] if b.kind is PointKind.SMOOTH and has_next else None,
        )


def segment_vertex_counts(path: Path) -> list[int]:
    """How many vertices each segment adds after the first point.

    Their sum plus one is the size of the geometry.
    """
    return [segment.vertex_count() for segment in _segments(path)]


def _lerp(
    t: float, ta: float, tb: float, pa: tuple[float, float], pb: tuple[float, float]
) -> tuple[float, float]:
    span = tb - ta
    return ((tb - t) * pa[0] + (t - ta) * pb[0]) / span, ((tb - t) * pa[1] + (t - ta) * pb[1]) / span


def _segment_vertices(segment: _Segment) -> list[tuple[float, float]]:
    """The vertices a segment adds, ending on its end point, rounded."""
    a, b = segment.a, segment.b
    end = (b.lon, b.lat)
    if segment.straight:
        return [end]
    k = _scale(a, b)
    p1, p2 = (a.lon * k, a.lat), (b.lon * k, b.lat)
    p0 = (segment.prev.lon * k, segment.prev.lat) if segment.prev else (2 * p1[0] - p2[0], 2 * p1[1] - p2[1])
    p3 = (segment.next.lon * k, segment.next.lat) if segment.next else (2 * p2[0] - p1[0], 2 * p2[1] - p1[1])
    d01, d12, d23 = math.dist(p0, p1), math.dist(p1, p2), math.dist(p2, p3)
    assert min(d01, d12, d23) > 0, f"segment {segment.index} has two points on top of each other"
    t0 = 0.0
    t1 = t0 + math.sqrt(d01)
    t2 = t1 + math.sqrt(d12)
    t3 = t2 + math.sqrt(d23)
    steps = _steps(d12)
    out: list[tuple[float, float]] = []
    for j in range(1, steps):
        t = t1 + (t2 - t1) * j / steps
        a1 = _lerp(t, t0, t1, p0, p1)
        a2 = _lerp(t, t1, t2, p1, p2)
        a3 = _lerp(t, t2, t3, p2, p3)
        b1 = _lerp(t, t0, t2, a1, a2)
        b2 = _lerp(t, t1, t3, a2, a3)
        x, y = _lerp(t, t1, t2, b1, b2)
        out.append((round(x / k, DECIMALS), round(y, DECIMALS)))
    out.append(end)
    return out


def derive(path: Path) -> LineString | Polygon:
    """The geometry a path draws: a LineString when open, a one-ring Polygon when closed.

    Doesn't check the limits. `shape_of` does, and counts the vertices before drawing.
    """
    first = path.points[0]
    vertices = [(first.lon, first.lat)]
    for segment in _segments(path):
        vertices.extend(_segment_vertices(segment))
    if path.closed:
        assert vertices[-1] == vertices[0], "a closed path ends on its first point"
        return Polygon(vertices)
    return LineString(vertices)


# --------------------------------------------------------------------------
# A shape and its limits
# --------------------------------------------------------------------------


def length_m(geometry: BaseGeometry) -> float:
    """The geodesic length of a line, or the perimeter of an area, in metres."""
    return float(GEOD.geometry_length(geometry))


def across_m(geometry: BaseGeometry) -> float:
    """The larger of east-west width at the middle latitude and north-south height, in metres."""
    west, south, east, north = geometry.bounds
    middle_lat, middle_lon = (south + north) / 2, (west + east) / 2
    _, _, width = GEOD.inv(west, middle_lat, east, middle_lat)
    _, _, height = GEOD.inv(middle_lon, south, middle_lon, north)
    return max(float(width), float(height))


@dataclass(frozen=True)
class Shape:
    """A checked path and what it draws."""

    path: Path
    geometry: LineString | Polygon

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.AREA if self.path.closed else ShapeKind.LINE

    @cached_property
    def length_m(self) -> float:
        return length_m(self.geometry)

    @cached_property
    def mid(self) -> BaseGeometry:
        return simplified(self.geometry, SIMPLIFY_MID_DEG)

    @cached_property
    def low(self) -> BaseGeometry:
        return simplified(self.geometry, SIMPLIFY_LOW_DEG)


def simplified(geometry: BaseGeometry, tolerance: float) -> BaseGeometry:
    """`geometry` simplified without letting a ring cross itself."""
    result = geometry.simplify(tolerance, preserve_topology=True)
    assert not result.is_empty, "simplifying never empties a shape"
    return result


def shape_of(path: Path) -> Shape:
    """Draw a path and hold it to the limits, all but the gap to a placed point (`check_shape`).

    The vertices are counted before the curve is drawn.
    """
    if 1 + sum(segment_vertex_counts(path)) > SHAPE_MAX_VERTICES:
        raise ShapeTooComplexError()
    shape = Shape(path, derive(path))
    if path.closed:
        if not shape.geometry.is_valid:
            raise ShapeCrossesItselfError()
        if across_m(shape.geometry) > SHAPE_MAX_ACROSS_M:
            raise ShapeTooBigError()
    elif shape.length_m > LINE_MAX_LENGTH_M:
        raise LineTooLongError()
    return shape


def nearest_point(geometry: BaseGeometry, point: Point) -> Point:
    """The point of `geometry` nearest `point`, measured in a plane scaled for its latitude.

    Inside an area, that is `point` itself.
    """
    k = math.cos(math.radians(point.y))
    scaled = shapely.transform(geometry, lambda xy: xy * np.array([k, 1.0]))
    _, nearest = nearest_points(Point(point.x * k, point.y), scaled)
    return Point(round(nearest.x / k, DECIMALS), round(nearest.y, DECIMALS))


def distance_m(geometry: BaseGeometry, point: Point) -> float:
    """How far `point` is from `geometry`, in metres. Nothing when it is inside an area."""
    nearest = nearest_point(geometry, point)
    _, _, metres = GEOD.inv(point.x, point.y, nearest.x, nearest.y)
    return float(metres)


def check_shape(geometry: BaseGeometry, placed: Point) -> None:
    """Refuse a shape that doesn't come within `SHAPE_MAX_GAP_M` of the point the finder placed.

    `geometry` is a shape that `shape_of` passed, or an outline saved before paths existed.
    """
    if distance_m(geometry, placed) > SHAPE_MAX_GAP_M:
        raise OutlineTooFarError()


def derived_anchor(shape: Shape) -> Point:
    """The point the server chooses for a finding drawn without one.

    For a line, the vertex nearest half its length. For an area, its centroid
    when that lies inside it, and a point inside it otherwise.
    """
    geometry = shape.geometry
    if isinstance(geometry, Polygon):
        centroid = geometry.centroid
        inside = centroid if geometry.contains(centroid) else geometry.point_on_surface()
        return Point(round(inside.x, DECIMALS), round(inside.y, DECIMALS))
    lons, lats = np.asarray(geometry.coords).T
    _, _, pieces = GEOD.inv(lons[:-1], lats[:-1], lons[1:], lats[1:])
    along = np.concatenate([[0.0], np.cumsum(pieces)])
    middle = int(np.argmin(np.abs(along - along[-1] / 2)))
    return Point(float(lons[middle]), float(lats[middle]))


# --------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------


def _run_start(old: Sequence[PathPoint], new: Sequence[PathPoint]) -> int | None:
    """Where `old` appears whole and in order inside a longer `new`, or None."""
    size = len(old)
    for start in range(len(new) - size + 1):
        if new[start] == old[0] and tuple(new[start : start + size]) == tuple(old):
            return start
    return None


def _extension_start(old: Path, new: Path) -> int | None:
    if old.closed or new.closed or len(new.points) <= len(old.points):
        return None
    return _run_start(old.points, new.points)


def classify_change(old: Path | None, new: Path | None) -> ShapeChangeKind | None:
    """How `new` changes `old`, or None when it doesn't.

    An extension keeps the old open path whole and in order, adding points
    only before or after it. A closed path has no ends, so a point added to
    one reshapes it.
    """
    if old == new:
        return None
    if old is None:
        return ShapeChangeKind.DRAWN
    if new is None:
        return ShapeChangeKind.REMOVED
    if old.closed != new.closed:
        return ShapeChangeKind.CLOSED if new.closed else ShapeChangeKind.OPENED
    if _extension_start(old, new) is not None:
        return ShapeChangeKind.EXTENDED
    return ShapeChangeKind.RESHAPED


def added_view(old: Path, new: Path) -> dict[str, float] | None:
    """A centre and a zoom framing what an extension added, or None when `new` doesn't extend `old`.

    Worked out from the vertices of the new path's added segments.
    """
    start = _extension_start(old, new)
    if start is None:
        return None
    end = start + len(old.points) - 1
    vertices: list[tuple[float, float]] = []
    for segment in _segments(new):
        if segment.index < start or segment.index >= end:
            vertices.append((segment.a.lon, segment.a.lat))
            vertices.extend(_segment_vertices(segment))
    assert vertices, "an extension adds a segment at least"
    lons, lats = zip(*vertices, strict=True)
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)
    lat = (south + north) / 2
    zooms = [float(VIEW_MAX_ZOOM)]
    # A map tile spans 360 / 2^z degrees of longitude, and 1 / cos(lat) times less of latitude.
    if east > west:
        zooms.append(math.log2(_VIEW_WIDTH_PX * 360 / (_TILE_PX * (east - west))))
    if north > south:
        zooms.append(
            math.log2(_VIEW_HEIGHT_PX * 360 * math.cos(math.radians(lat)) / (_TILE_PX * (north - south)))
        )
    zoom = max(VIEW_MIN_ZOOM, math.floor(min(zooms)))
    return {"lon": round((west + east) / 2, 6), "lat": round(lat, 6), "zoom": zoom}
