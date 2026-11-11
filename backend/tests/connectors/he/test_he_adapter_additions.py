"""The small additions to the shared adapters that the Historic England connectors need."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import Point, box

from fieldclub.ingest.adapters.arcgis import esri_date
from fieldclub.ingest.adapters.common import FeatureKeys, UpstreamFormatError, json_ready


def test_feature_keys_are_the_same_in_every_run_and_differ_by_part_or_outline() -> None:
    square = box(0.0, 51.0, 0.001, 51.001)
    first, second = FeatureKeys(), FeatureKeys()
    assert first.key(["BANK", "Stonehenge", "123"], square) == second.key(
        ["BANK", "Stonehenge", "123"], square
    )
    keys = FeatureKeys()
    ids = {
        keys.key(["BANK", "Stonehenge", "123"], square),
        keys.key(["DITCH", "Stonehenge", "123"], square),
        keys.key(["BANK", "Stonehenge", "124"], square),
        keys.key(["BANK", "Stonehenge", "123"], box(0.0, 51.0, 0.002, 51.001)),
    }
    assert len(ids) == 4
    assert keys.repeats == 0


def test_feature_keys_ignore_case_spacing_and_the_last_few_decimals() -> None:
    keys = FeatureKeys()
    assert keys.key(["Bank "], Point(1.0000000001, 51.0)) == FeatureKeys().key(["BANK"], Point(1.0, 51.0))
    assert keys.key([None], None) == FeatureKeys().key([""], None)


def test_an_exact_repeat_gets_a_numbered_key_in_the_order_given() -> None:
    keys = FeatureKeys()
    point = Point(1.0, 51.0)
    one, two, three = (keys.key(["x"], point) for _ in range(3))
    assert (two, three) == (f"{one}-2", f"{one}-3")
    assert keys.repeats == 2


def test_a_key_from_the_native_grid_does_not_move_with_the_reprojection() -> None:
    """The WGS84 shape moves by about 1e-5 degrees when PROJ gets a datum grid. The id must not."""
    native = box(417000.0, 142000.0, 417050.0, 142040.0)
    here = box(-1.8297167, 51.1771118, -1.8296, 51.1772)
    shifted = box(-1.8297067, 51.1771068, -1.8295900, 51.1771950)
    assert FeatureKeys().key(["BANK"], here, native=native) == FeatureKeys().key(
        ["BANK"], shifted, native=native
    )
    # Without the grid shape the same shift gives another id, which is why callers pass it.
    assert FeatureKeys().key(["BANK"], here) != FeatureKeys().key(["BANK"], shifted)
    # Grid coordinates count to a tenth of a metre, and no finer.
    nudged = box(417000.04, 142000.0, 417050.0, 142040.0)
    assert FeatureKeys().key(["BANK"], here, native=native) == FeatureKeys().key(
        ["BANK"], here, native=nudged
    )
    moved = box(417000.3, 142000.0, 417050.0, 142040.0)
    assert FeatureKeys().key(["BANK"], here, native=native) != FeatureKeys().key(["BANK"], here, native=moved)


def test_a_repeat_with_the_same_detail_is_skipped_and_one_with_other_detail_is_named_for_it() -> None:
    keys = FeatureKeys()
    shape = Point(1.0, 51.0)
    bare = keys.distinct_key(["bank"], shape, ["BARROW", "BRONZE AGE"])
    assert bare is not None
    assert "-" not in bare
    assert keys.distinct_key(["bank"], shape, ["BARROW", "BRONZE AGE"]) is None
    other = keys.distinct_key(["bank"], shape, ["BARROW", "IRON AGE"])
    assert other is not None
    assert other.startswith(f"{bare}-")
    assert keys.repeats == 2
    # The name follows the detail, not the order: the same other interpretation is named the same
    # whether it comes second or third.
    again = FeatureKeys()
    assert again.distinct_key(["bank"], shape, ["BARROW", "BRONZE AGE"]) == bare
    assert again.distinct_key(["bank"], shape, ["x"]) is not None
    assert again.distinct_key(["bank"], shape, ["BARROW", "IRON AGE"]) == other


def test_json_ready_can_leave_out_empty_values() -> None:
    properties = {"a": None, "b": " ", "c": "", "d": 0, "e": "x", "f": datetime(2020, 1, 2, tzinfo=UTC)}
    assert json_ready(properties) == {**properties, "f": "2020-01-02T00:00:00+00:00"}
    assert json_ready(properties, drop_empty=True) == {"d": 0, "e": "x", "f": "2020-01-02T00:00:00+00:00"}


def test_esri_dates_are_milliseconds_since_1970_in_utc() -> None:
    assert esri_date(1275350400000) == datetime(2010, 6, 1, tzinfo=UTC)
    assert esri_date(None) is None
    with pytest.raises(UpstreamFormatError):
        esri_date("2010-06-01")


def test_a_ring_that_collapsed_to_a_point_is_dropped_not_kept_as_a_part() -> None:
    from fieldclub.ingest.adapters.arcgis import esri_geometry

    collapsed = [[-1.688685, 55.134636]] * 4
    square = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    geometry = esri_geometry({"rings": [collapsed, square]})
    assert geometry is not None
    assert geometry.geom_type == "Polygon"
    assert geometry.is_valid
    assert esri_geometry({"rings": [collapsed]}) is None
