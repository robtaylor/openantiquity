from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import box

from fieldclub.ingest.adapters.common import IncompleteReadError, UpstreamFormatError
from fieldclub.ingest.adapters.wfs import WFSLayer
from tests.ingest.adapters.support import NoWait, fixture_bytes

URL = "https://datamap.gov.wales/geoserver/ows"
TYPE = "inspire-wg:Cadw_SAM"
# The recorded box, 270000,200000,276000,206000 on the British grid, near Neath.
AREA = box(-3.885, 51.683, -3.795, 51.739)


class RecordedWfs:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        assert params["typeNames"] == TYPE
        if params.get("resultType") == "hits":
            return httpx.Response(200, content=fixture_bytes("wfs_hits.xml"))
        if "gml" in params["outputFormat"]:
            return httpx.Response(200, content=fixture_bytes("wfs_page_gml.xml"))
        return httpx.Response(200, content=fixture_bytes(f"wfs_page_{params['startIndex']}.json"))


def make_layer(**kwargs: Any) -> WFSLayer:
    options = {"sort_by": "RecordNumber", "page_size": 2} | kwargs
    return WFSLayer(URL, TYPE, client=httpx.Client(), polite=NoWait(delay_s=0), **options)


@respx.mock
def test_counts_then_pages_through_every_feature() -> None:
    recorded = RecordedWfs()
    respx.get(URL).mock(side_effect=recorded)
    layer = make_layer()
    features = list(layer.features(bbox=AREA.bounds))

    assert len(features) == 6
    assert len({feature.properties["SAMNumber"] for feature in features}) == 6
    assert all(feature.geometry is not None and AREA.intersects(feature.geometry) for feature in features)
    pages = [request for request in recorded.requests if "startIndex" in request]
    assert [page["startIndex"] for page in pages] == ["0", "2", "4"]
    assert all(page["sortBy"] == "RecordNumber" and page["srsName"] == "EPSG:27700" for page in pages)
    assert pages[0]["bbox"].endswith(",EPSG:27700")


@respx.mock
def test_reads_gml_through_ogr() -> None:
    respx.get(URL).mock(side_effect=RecordedWfs())
    layer = make_layer(output_format="application/gml+xml; version=3.2")
    gml = layer._page(None, 0)
    json_layer = make_layer()
    first_json_page = json_layer._page(None, 0)
    # The same two monuments, whichever format they came in.
    assert [f.properties["SAMNumber"] for f in gml] == [f.properties["SAMNumber"] for f in first_json_page]
    for from_gml, from_json in zip(gml, first_json_page, strict=True):
        assert from_gml.geometry is not None
        assert from_json.geometry is not None
        assert from_gml.geometry.equals_exact(from_json.geometry, 1e-7)


@respx.mock
def test_an_exception_report_is_an_error() -> None:
    report = (
        b'<?xml version="1.0" encoding="UTF-8"?><ows:ExceptionReport><ows:Exception>'
        b"<ows:ExceptionText>Illegal property name: SAM</ows:ExceptionText>"
        b"</ows:Exception></ows:ExceptionReport>"
    )
    respx.get(URL).mock(return_value=httpx.Response(200, content=report))
    with pytest.raises(UpstreamFormatError, match="Illegal property name"):
        make_layer()._page(None, 0)


@respx.mock
def test_hits_without_a_count_is_an_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"<html></html>"))
    with pytest.raises(UpstreamFormatError, match="numberMatched"):
        make_layer().count()


def test_a_geographic_crs_is_refused() -> None:
    with pytest.raises(AssertionError, match="projected CRS"):
        make_layer(srs_name="EPSG:4326")


class SyntheticWfs:
    """A WFS of `size` features numbered 1 up, serving at most `cap` a page whatever `count` asks."""

    def __init__(self, size: int = 10, *, cap: int, shift: bool = False) -> None:
        self.size = size
        self.cap = cap
        self.shift = shift
        self.starts: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("resultType") == "hits":
            return httpx.Response(
                200, content=f'<wfs:FeatureCollection numberMatched="{self.size}"/>'.encode()
            )
        start, count = int(params["startIndex"]), int(params["count"])
        self.starts.append(start)
        order = list(range(1, self.size + 1))
        if self.shift and start > 0:
            # Feature 5 moved in front of feature 4 after the first page.
            order = [1, 2, 3, 5, 4, *order[5:]]
        numbers = order[start : start + min(count, self.cap)]
        features = [
            {
                "type": "Feature",
                "id": f"Thing.{number}",
                "properties": {"RecordNumber": number},
                "geometry": {"type": "Point", "coordinates": [270_000 + number, 200_000]},
            }
            for number in numbers
        ]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})


def read_synthetic(upstream: SyntheticWfs, page_size: int) -> list[object]:
    with respx.mock:
        respx.get(URL).mock(side_effect=upstream)
        layer = make_layer(page_size=page_size)
        return [feature.properties["RecordNumber"] for feature in layer.features()]


def test_pages_capped_below_count_still_read_completely() -> None:
    upstream = SyntheticWfs(cap=3)
    assert read_synthetic(upstream, page_size=4) == list(range(1, 11))
    assert upstream.starts == [0, 3, 6, 9]


def test_a_repeat_cannot_hide_a_skipped_feature() -> None:
    with pytest.raises(
        IncompleteReadError, match="said it had 10 inspire-wg:Cadw_SAM and gave 9, and 1 more"
    ):
        read_synthetic(SyntheticWfs(cap=4, shift=True), page_size=4)


def test_sorting_is_required() -> None:
    with pytest.raises(AssertionError, match="unique property to sort by"):
        WFSLayer(URL, TYPE, client=httpx.Client(), sort_by="")
