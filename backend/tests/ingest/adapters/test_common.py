from __future__ import annotations

import math
from datetime import UTC, datetime

import httpx
import numpy as np
import pytest
import respx
from shapely.geometry import Point

from fieldclub import gridref
from fieldclub.ingest.adapters.common import AdapterError, json_ready, plain, plain_tree, to_wgs84
from tests.helpers import run_fresh
from tests.ingest.adapters.support import NoWait, xy

URL = "https://upstream.example/thing"


@respx.mock
def test_a_server_error_is_retried_with_growing_gaps() -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"ok": True})]
    )
    polite = NoWait(backoff_s=2)
    with httpx.Client() as client:
        response = polite.request(client, "GET", URL)
    assert response.json() == {"ok": True}
    assert route.call_count == 3
    assert polite.slept == [2, 4]


@respx.mock
def test_retry_after_is_honoured_up_to_the_cap() -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429, headers={"Retry-After": "100000"}),
            httpx.Response(200),
        ]
    )
    polite = NoWait(max_backoff_s=60)
    with httpx.Client() as client:
        polite.request(client, "GET", URL)
    assert polite.slept == [7, 60]


@respx.mock
def test_a_dropped_connection_is_retried() -> None:
    respx.get(URL).mock(side_effect=[httpx.ConnectError("reset"), httpx.Response(200)])
    polite = NoWait()
    with httpx.Client() as client:
        assert polite.request(client, "GET", URL).status_code == 200


@respx.mock
def test_retries_run_out() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(500, text="broken"))
    polite = NoWait(retries=2)
    with httpx.Client() as client, pytest.raises(AdapterError, match="answered 500"):
        polite.request(client, "GET", URL)
    assert route.call_count == 3


@respx.mock
def test_a_refusal_is_not_retried() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(403, text="no scripts"))
    with httpx.Client() as client, pytest.raises(AdapterError, match="answered 403"):
        NoWait().request(client, "GET", URL)
    assert route.call_count == 1


@respx.mock
def test_requests_are_spaced_out() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200))
    polite = NoWait(delay_s=5)
    with httpx.Client() as client:
        polite.request(client, "GET", URL)
        polite.request(client, "GET", URL)
    assert len(polite.slept) == 1
    assert 4 < polite.slept[0] <= 5


def test_british_grid_is_reprojected_to_longitude_first() -> None:
    # Near Avebury. The grid module is the project's reference for this conversion.
    x, y = xy(to_wgs84(Point(410132, 170023), "EPSG:27700"))
    lon, lat = gridref.to_lonlat(gridref.GridSystem.OSGB, 410132, 170023)
    assert x == pytest.approx(lon, abs=1e-6)
    assert y == pytest.approx(lat, abs=1e-6)
    assert -1.86 < x < -1.85
    assert 51.42 < y < 51.43


def test_wgs84_is_left_alone() -> None:
    point = Point(-1.85, 51.43)
    assert to_wgs84(point, "EPSG:4326") is point


def test_plain_unwraps_numpy_and_drops_nan() -> None:
    assert plain(np.int32(7)) == 7
    assert type(plain(np.int32(7))) is int
    assert plain(np.float64("nan")) is None
    assert plain(np.datetime64("NaT", "ms")) is None
    assert plain(np.datetime64("1925-03-10T00:00:00.000", "ms")) == datetime(1925, 3, 10, tzinfo=UTC)
    assert plain(np.datetime64("2026-01-02T03:04:05.123456789", "ns")) == datetime(
        2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC
    )
    assert plain(math.inf) is None
    assert plain("text") == "text"


def test_json_ready_writes_datetimes_as_text() -> None:
    assert json_ready({"when": datetime(2026, 1, 1, tzinfo=UTC), "n": 1}) == {
        "when": "2026-01-01T00:00:00+00:00",
        "n": 1,
    }


def test_plain_tree_cleans_nested_values() -> None:
    value = {"a": [math.nan, {"b": math.inf, "c": np.int64(3)}], "d": "x"}
    assert plain_tree(value) == {"a": [None, {"b": None, "c": 3}], "d": "x"}


def test_the_adapters_dont_import_the_database_layer() -> None:
    # They know nothing about our tables, so loading one mustn't load the models or the runner.
    code = (
        "import sys\n"
        "import fieldclub.ingest.adapters.arcgis, fieldclub.ingest.adapters.download\n"
        "import fieldclub.ingest.adapters.files, fieldclub.ingest.adapters.sparql\n"
        "import fieldclub.ingest.adapters.wfs\n"
        "loaded = [m for m in ('fieldclub.db', 'fieldclub.models', 'fieldclub.ingest.runner', 'sqlalchemy')"
        " if m in sys.modules]\n"
        "assert not loaded, loaded\n"
    )
    run_fresh(code)
