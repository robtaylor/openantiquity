"""What every reference loader's row goes through before it is stored."""

from __future__ import annotations

import pytest
import shapely
from shapely.geometry import Polygon

from fieldclub.ingest.errors import InvalidRecordError
from fieldclub.ingest.reference import base

TRIANGLE = "(-1.86 51.42, -1.84 51.42, -1.84 51.44, -1.86 51.42)"


def test_a_boundary_s_empty_hole_is_dropped_before_it_is_stored() -> None:
    # GEOS calls such a polygon valid and then crashes in `contains` and `covers`
    # (https://github.com/libgeos/geos/issues/1604), and PostGIS refuses to store it.
    holed = shapely.from_wkt(f"MULTIPOLYGON (({TRIANGLE}, EMPTY))")
    assert holed.is_valid

    cleaned = base._check_geometry("fake-areas", {"name": "Wiltshire", "geom": holed})

    polygons = list(shapely.get_parts(cleaned))
    assert len(polygons) == 1
    assert isinstance(polygons[0], Polygon)
    assert len(polygons[0].interiors) == 0
    assert cleaned.equals(shapely.from_wkt(f"POLYGON ({TRIANGLE})"))


def test_a_whole_boundary_is_stored_as_it_came() -> None:
    whole = shapely.from_wkt(f"POLYGON ({TRIANGLE})")

    assert base._check_geometry("fake-areas", {"name": "Wiltshire", "geom": whole}) is whole


def test_a_row_without_a_shape_is_refused() -> None:
    with pytest.raises(InvalidRecordError, match="has no geometry"):
        base._check_geometry("fake-areas", {"name": "Nowhere", "geom": Polygon()})
