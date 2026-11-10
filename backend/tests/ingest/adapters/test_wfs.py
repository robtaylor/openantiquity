from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import box

from fieldclub.ingest.adapters.common import UpstreamFormatError
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
