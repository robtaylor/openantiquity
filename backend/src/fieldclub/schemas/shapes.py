"""The structure of GeoJSON geometry from outside, checked before shapely and GEOS see it.

Imports nothing of the database, so ingest adapters use it too.
"""

from __future__ import annotations

import sys
from typing import Any, NamedTuple

from fieldclub.errors import ValidationFailedError

# The most positions and parts a shape sent by a client may have, counting every
# ring, line and member. A finding's outline and an investigation's area are
# drawn by hand, and every list of findings carries the outline, so a shape
# with hundreds of thousands of points would be paid for by every visitor.
GEOMETRY_MAX_POINTS = 2000
GEOMETRY_MAX_PARTS = 200


class GeometryTooComplexError(ValidationFailedError):
    code = "geometry_too_complex"
    message = f"A shape can have at most {GEOMETRY_MAX_POINTS} points and {GEOMETRY_MAX_PARTS} parts."


class _Part(NamedTuple):
    # How many lists deep the positions are.
    depth: int
    # The fewest positions each innermost list must have.
    least: int
    # Whether each innermost list must end where it starts.
    closed: bool = False


# The shape of each GeoJSON type's coordinates.
_PARTS: dict[str, _Part] = {
    "Point": _Part(0, 1),
    "MultiPoint": _Part(1, 1),
    "LineString": _Part(1, 2),
    "MultiLineString": _Part(2, 2),
    "Polygon": _Part(2, 4, closed=True),
    "MultiPolygon": _Part(3, 4, closed=True),
}
MALFORMED = "That isn't valid GeoJSON geometry."
_EMPTY = "The geometry is empty, or has an empty part."
_SHORT = {
    False: "A line needs two positions at least.",
    True: "A ring needs four positions at least, and must end where it starts.",
}


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list | tuple)
        and len(value) in (2, 3)
        and all(isinstance(number, int | float) and not isinstance(number, bool) for number in value)
        # False for NaN and the infinities, and for a whole number too large to be a float,
        # which `math.isfinite` would raise on.
        and all(abs(number) <= sys.float_info.max for number in value)
    )


def _is_known_type(value: Any) -> bool:
    # A list or an object can't be looked up, so ask first.
    return isinstance(value, str) and value in _PARTS


def check_shape(
    data: dict[str, Any], *, max_points: int = GEOMETRY_MAX_POINTS, max_parts: int = GEOMETRY_MAX_PARTS
) -> None:
    """Check a GeoJSON geometry's structure, and count its positions and parts, before shapely sees it.

    GEOS can crash the whole process on a shape with an empty part, such as
    a polygon with an empty hole (https://github.com/libgeos/geos/issues/1604,
    seen in GEOS 3.13.1 and 3.14.1), so every list must be the right depth and
    hold enough positions: a line two, a ring four, ending where it starts.
    Keep the check whatever GEOS is installed: a shape must never be able to
    end the process.
    Counting stops as soon as there are too many positions or parts, so a
    huge shape costs no more than the counting up to the limit. Each
    type has a fixed depth, so nothing recurses.
    """
    if data.get("type") == "GeometryCollection":
        members = data.get("geometries")
        if not isinstance(members, list | tuple) or not members:
            raise ValidationFailedError(_EMPTY)
        if not all(isinstance(member, dict) and _is_known_type(member.get("type")) for member in members):
            raise ValidationFailedError(MALFORMED)
    else:
        members = [data]
    points = parts = 0
    for member in members:
        part = _PARTS.get(str(member.get("type")))
        if part is None:
            raise ValidationFailedError(MALFORMED)
        level: list[Any] = [member.get("coordinates")]
        for depth in range(part.depth, 0, -1):
            below: list[Any] = []
            for value in level:
                if not isinstance(value, list | tuple):
                    raise ValidationFailedError(MALFORMED)
                if not value:
                    raise ValidationFailedError(_EMPTY)
                if depth == 1:
                    parts += 1
                    if len(value) < part.least:
                        raise ValidationFailedError(_EMPTY if part.least == 1 else _SHORT[part.closed])
                    if part.closed:
                        first, last = value[0], value[-1]
                        if not (isinstance(first, list | tuple) and isinstance(last, list | tuple)):
                            raise ValidationFailedError(MALFORMED)
                        # A list and a tuple of the same numbers are the same position.
                        if list(first) != list(last):
                            raise ValidationFailedError(_SHORT[True])
                below.extend(value)
                # Every list holds a position at least, so too many lists is too many positions.
                if len(below) > max_points or parts > max_parts:
                    raise GeometryTooComplexError()
            level = below
        if part.depth == 0 and isinstance(level[0], list | tuple) and not level[0]:
            raise ValidationFailedError(_EMPTY)
        points += len(level)
        if points > max_points:
            raise GeometryTooComplexError()
        if not all(_is_position(value) for value in level):
            raise ValidationFailedError(MALFORMED)
