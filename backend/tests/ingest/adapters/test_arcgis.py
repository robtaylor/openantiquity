from __future__ import annotations

import copy
import re
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from fieldclub.ingest.adapters.arcgis import ArcGISLayer, esri_geometry
from fieldclub.ingest.adapters.common import AdapterError, IncompleteReadError, UpstreamFormatError
from tests.ingest.adapters.support import NoWait, fixture_json

LAYER = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/6"
)
# The box the fixtures were recorded with, around Silbury Hill.
BBOX = (-1.865, 51.41, -1.84, 51.42)


class RecordedLayer:
    """Answers the way the live layer did when the fixtures were recorded."""

    def __init__(self, info: dict[str, Any] | None = None) -> None:
        self.info = info or fixture_json("arcgis_layer.json")
        self.pages = {0: fixture_json("arcgis_page_0.json"), 2: fixture_json("arcgis_page_2.json")}
        self.queries: list[dict[str, str]] = []

    @property
    def all_features(self) -> list[dict[str, Any]]:
        return [feature for page in self.pages.values() for feature in page["features"]]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        assert params.pop("f") == "json"
        if request.url.path.endswith("/6"):
            return httpx.Response(200, json=self.info)
        self.queries.append(params)
        if params.get("returnCountOnly") == "true":
            return httpx.Response(200, json=fixture_json("arcgis_count.json"))
        if params.get("returnIdsOnly") == "true":
            return httpx.Response(200, json=fixture_json("arcgis_ids.json"))
        assert params["outSR"] == "4326"
        if "resultOffset" in params:
            return httpx.Response(200, json=self.pages[int(params["resultOffset"])])
        # Paging by object id range: answer with the recorded features in it.
        low, high = (int(value) for value in re.findall(r"OBJECTID [<>]= (\d+)", params["where"]))
        body = copy.deepcopy(self.pages[0])
        body["features"] = [f for f in self.all_features if low <= f["attributes"]["OBJECTID"] <= high]
        body["exceededTransferLimit"] = False
        return httpx.Response(200, json=body)


def make_layer(**kwargs: Any) -> ArcGISLayer:
    return ArcGISLayer(LAYER, client=httpx.Client(), polite=NoWait(delay_s=0), **kwargs)


@respx.mock
def test_pages_by_offset_and_reads_every_feature() -> None:
    recorded = RecordedLayer()
    respx.route(host="services-eu1.arcgis.com").mock(side_effect=recorded)
    features = list(make_layer(page_size=2, geometry_precision=6).features(bbox=BBOX))

    names = [feature.properties["Name"] for feature in features]
    assert len(features) == 3
    assert any(name.startswith("Silbury Hill") for name in names)
    pages = [query for query in recorded.queries if "resultOffset" in query]
    assert [query["resultOffset"] for query in pages] == ["0", "2"]
    assert all(query["resultRecordCount"] == "2" for query in pages)
    assert all(query["orderByFields"] == "OBJECTID" for query in pages)
    assert all(query["geometry"] == "-1.865,51.41,-1.84,51.42" for query in pages)
    assert pages[0]["geometryPrecision"] == "6"


@respx.mock
def test_features_are_plain_and_in_wgs84() -> None:
    respx.route(host="services-eu1.arcgis.com").mock(side_effect=RecordedLayer())
    silbury = next(
        feature
        for feature in make_layer(page_size=2).features(bbox=BBOX)
        if feature.properties["ListEntry"] == 1008445
    )
    assert silbury.id == silbury.properties["OBJECTID"]
    assert silbury.geometry is not None
    assert silbury.geometry.geom_type in ("Polygon", "MultiPolygon")
    assert silbury.geometry.is_valid
    # Silbury Hill's mound, not somewhere in the sea off Africa.
    assert silbury.geometry.contains(Point(-1.8574, 51.4156))


@respx.mock
def test_the_page_size_never_exceeds_the_layers_limit() -> None:
    info = fixture_json("arcgis_layer.json") | {"maxRecordCount": 2}
    recorded = RecordedLayer(info)
    respx.route(host="services-eu1.arcgis.com").mock(side_effect=recorded)
    assert len(list(make_layer(page_size=5000).features(bbox=BBOX))) == 3
    assert {query["resultRecordCount"] for query in recorded.queries if "resultRecordCount" in query} == {"2"}


@respx.mock
def test_a_layer_without_pagination_is_read_by_object_id_ranges() -> None:
    info = fixture_json("arcgis_layer.json")
    info["advancedQueryCapabilities"]["supportsPagination"] = False
    recorded = RecordedLayer(info)
    respx.route(host="services-eu1.arcgis.com").mock(side_effect=recorded)
    features = list(make_layer(page_size=2).features(bbox=BBOX))

    assert len(features) == 3
    ranges = [query["where"] for query in recorded.queries if "OBJECTID >=" in query.get("where", "")]
    assert len(ranges) == 2
    assert ranges[0].startswith("(1=1) AND OBJECTID >= ")


@respx.mock
def test_a_short_read_is_an_error() -> None:
    recorded = RecordedLayer()
    recorded.pages[2] = recorded.pages[2] | {"features": []}
    respx.route(host="services-eu1.arcgis.com").mock(side_effect=recorded)
    with pytest.raises(IncompleteReadError, match="said it had 3 features and gave 2"):
        list(make_layer(page_size=2).features(bbox=BBOX))


@respx.mock
def test_an_error_object_in_a_200_is_an_error() -> None:
    respx.route(host="services-eu1.arcgis.com").mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid query"}})
    )
    with pytest.raises(AdapterError, match="Invalid query"):
        make_layer().count()


@respx.mock
def test_a_service_that_isnt_a_layer_is_refused() -> None:
    respx.route(host="services-eu1.arcgis.com").mock(return_value=httpx.Response(200, json={"layers": []}))
    with pytest.raises(UpstreamFormatError, match="does not look like a layer"):
        make_layer().info()


def test_the_url_must_name_a_layer() -> None:
    with pytest.raises(AssertionError, match="layer number"):
        ArcGISLayer(LAYER.rsplit("/", 1)[0], client=httpx.Client())


# --------------------------------------------------------------------------
# Esri geometry
# --------------------------------------------------------------------------

# Clockwise outer ring, anticlockwise hole, as Esri writes them.
OUTER = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
HOLE = [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]
OTHER = [[20, 0], [20, 5], [25, 5], [25, 0], [20, 0]]


def test_rings_become_a_polygon_with_its_hole() -> None:
    polygon = esri_geometry({"rings": [OUTER, HOLE]})
    assert isinstance(polygon, Polygon)
    assert len(polygon.interiors) == 1
    assert polygon.area == 100 - 4


def test_two_outer_rings_become_a_multipolygon() -> None:
    geometry = esri_geometry({"rings": [OUTER, HOLE, OTHER]})
    assert isinstance(geometry, MultiPolygon)
    assert sorted(part.area for part in geometry.geoms) == [25, 96]


def test_points_and_paths() -> None:
    assert esri_geometry({"x": 1.5, "y": 2.5}) == Point(1.5, 2.5)
    assert esri_geometry({"x": None, "y": None}) is None
    assert esri_geometry({"paths": [[[0, 0], [1, 1]]]}) == LineString([(0, 0), (1, 1)])
    lines = esri_geometry({"paths": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]})
    assert lines is not None
    assert lines.geom_type == "MultiLineString"
    points = esri_geometry({"points": [[0, 0, 5], [1, 1, 6]]})
    assert points is not None
    assert points.geom_type == "MultiPoint"
    assert not points.has_z


def test_empty_and_unknown_geometry() -> None:
    assert esri_geometry(None) is None
    assert esri_geometry({}) is None
    assert esri_geometry({"rings": []}) is None
    with pytest.raises(UpstreamFormatError, match="true curves"):
        esri_geometry({"curveRings": []})
    with pytest.raises(UpstreamFormatError, match="Unknown Esri geometry"):
        esri_geometry({"spline": []})
