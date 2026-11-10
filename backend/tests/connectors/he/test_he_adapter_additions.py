"""The small additions to the shared adapters that the Historic England connectors need."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from shapely.geometry import Point, box

from fieldclub.ingest.adapters.arcgis import ArcGISLayer, esri_date
from fieldclub.ingest.adapters.common import FeatureKeys, UpstreamFormatError, json_ready
from tests.connectors.he.support import HOST, RecordedLayer
from tests.ingest.adapters.support import NoWait


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


def test_json_ready_can_leave_out_empty_values() -> None:
    properties = {"a": None, "b": " ", "c": "", "d": 0, "e": "x", "f": datetime(2020, 1, 2, tzinfo=UTC)}
    assert json_ready(properties) == {**properties, "f": "2020-01-02T00:00:00+00:00"}
    assert json_ready(properties, drop_empty=True) == {"d": 0, "e": "x", "f": "2020-01-02T00:00:00+00:00"}


def test_esri_dates_are_milliseconds_since_1970_in_utc() -> None:
    assert esri_date(1275350400000) == datetime(2010, 6, 1, tzinfo=UTC)
    assert esri_date(None) is None
    with pytest.raises(UpstreamFormatError):
        esri_date("2010-06-01")


@respx.mock
def test_require_shape_names_what_is_missing() -> None:
    layer = RecordedLayer("he-aim-project-areas")
    respx.route(host=HOST).mock(side_effect=layer)
    reader = ArcGISLayer(
        "https://services-eu1.arcgis.com/x/arcgis/rest/services/s/FeatureServer/2",
        client=httpx.Client(),
        polite=NoWait(),
    )
    reader.require_shape(["PROJECT_NA", "Status"], "esriGeometryPolygon")
    with pytest.raises(UpstreamFormatError, match=r"missing fields \['Nothing'\]"):
        reader.require_shape(["PROJECT_NA", "Nothing"])
    with pytest.raises(UpstreamFormatError, match="geometry esriGeometryPolygon"):
        reader.require_shape(["PROJECT_NA"], "esriGeometryPoint")
