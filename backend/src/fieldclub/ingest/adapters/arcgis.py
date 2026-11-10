"""ArcGIS REST feature and map service layers.

    layer = ArcGISLayer(url, client=connector.http)
    for feature in layer.features(bbox=bbox):
        ...

The reader asks the layer for its metadata, then for a count, then pages. A
layer that supports pagination is paged by `resultOffset`, ordered by object
id. One that doesn't is paged by ranges of object ids, from `returnIdsOnly`.
The page size never exceeds the layer's `maxRecordCount`. Servers cap pages
lower than they say (Historic England's says 22,000 at the root and gives
2,000), so the offset moves by however many features came back, and a range
that comes back short is asked for again from the first id still missing.
Geometry is asked for in EPSG:4326 and checked on the way back. When fewer
distinct object ids arrive than the count promised, the reader raises
`IncompleteReadError` instead of letting a short run look complete.

Responses are Esri JSON, not GeoJSON, because every ArcGIS server version
speaks it. `esri_geometry` turns its geometries into shapely.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from itertools import pairwise
from typing import Any

import httpx
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters.common import (
    AdapterError,
    Feature,
    Polite,
    Tally,
    UpstreamFormatError,
    json_body,
    plain,
    to_wgs84,
)
from fieldclub.ingest.base import BBox

logger = logging.getLogger(__name__)

# A layer that states no maxRecordCount gets this, the ArcGIS Server default.
DEFAULT_PAGE_SIZE = 1000


class ArcGISLayer:
    """One layer of an ArcGIS FeatureServer or MapServer, such as `.../FeatureServer/6`."""

    def __init__(
        self,
        url: str,
        *,
        client: httpx.Client,
        polite: Polite | None = None,
        where: str = "1=1",
        out_fields: Sequence[str] | str = "*",
        page_size: int | None = None,
        geometry_precision: int | None = None,
        tolerance: float = 0.0,
    ) -> None:
        """`tolerance` is the share of the count that may go missing between counting and paging.

        Leave it at 0 unless the layer is edited while it is read.
        """
        assert url.rstrip("/").rsplit("/", 1)[-1].isdigit(), f"{url} must end with the layer number"
        assert page_size is None or page_size >= 1, "page_size must be at least 1"
        assert 0 <= tolerance < 1, "tolerance is a share between 0 and 1"
        self.url = url.rstrip("/")
        self.client = client
        self.polite = polite or Polite()
        self.where = where
        self.out_fields = out_fields if isinstance(out_fields, str) else ",".join(out_fields)
        self.page_size = page_size
        self.geometry_precision = geometry_precision
        self.tolerance = tolerance
        self._info: dict[str, Any] | None = None

    # ------------------------------------------------------------------ metadata

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        response = self.polite.request(
            self.client, "GET", f"{self.url}{path}", params={**params, "f": "json"}
        )
        body = json_body(response, f"{self.url}{path}")
        if not isinstance(body, dict):
            raise UpstreamFormatError(f"{self.url}{path} answered with {type(body).__name__}, not an object.")
        if "error" in body:
            # ArcGIS reports errors with HTTP 200 and an error object.
            error = body["error"]
            raise AdapterError(f"{self.url}{path} reported an error: {error}")
        return body

    def info(self) -> dict[str, Any]:
        """The layer's metadata, fetched once."""
        if self._info is None:
            self._info = self._get("", {})
            if "fields" not in self._info and "name" not in self._info:
                raise UpstreamFormatError(f"{self.url} does not look like a layer: {sorted(self._info)[:8]}")
        return self._info

    @property
    def object_id_field(self) -> str:
        info = self.info()
        name = info.get("objectIdField")
        if not name:
            name = next(
                (f["name"] for f in info.get("fields", []) if f.get("type") == "esriFieldTypeOID"), None
            )
        if not name:
            raise UpstreamFormatError(f"{self.url} names no object id field.")
        return str(name)

    @property
    def max_record_count(self) -> int:
        value = self.info().get("maxRecordCount")
        return int(value) if isinstance(value, int) and value > 0 else DEFAULT_PAGE_SIZE

    @property
    def supports_pagination(self) -> bool:
        capabilities = self.info().get("advancedQueryCapabilities") or {}
        return bool(capabilities.get("supportsPagination"))

    def _filter(self, bbox: BBox | None) -> dict[str, str]:
        params = {"where": self.where}
        if bbox is not None:
            params |= {
                "geometry": ",".join(repr(float(value)) for value in bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        return params

    def count(self, bbox: BBox | None = None) -> int:
        """How many features match, optionally inside a WGS84 west, south, east, north box."""
        body = self._get("/query", {**self._filter(bbox), "returnCountOnly": "true"})
        value = body.get("count")
        if not isinstance(value, int) or value < 0:
            raise UpstreamFormatError(f"{self.url} gave a count of {value!r}.")
        return value

    def object_ids(self, bbox: BBox | None = None) -> list[int]:
        body = self._get("/query", {**self._filter(bbox), "returnIdsOnly": "true"})
        ids = body.get("objectIds")
        if ids is None:
            return []
        if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
            raise UpstreamFormatError(f"{self.url} gave object ids that are not whole numbers.")
        return sorted(ids)

    # ------------------------------------------------------------------ paging

    def _query(self, params: dict[str, str]) -> list[Feature]:
        query = {
            **params,
            "outFields": self.out_fields,
            "outSR": "4326",
            "returnGeometry": "true",
        }
        if self.geometry_precision is not None:
            query["geometryPrecision"] = str(self.geometry_precision)
        body = self._get("/query", query)
        raw_features = body.get("features")
        if not isinstance(raw_features, list):
            raise UpstreamFormatError(f"{self.url} query gave no features list.")
        crs = _crs_of(body.get("spatialReference"))
        oid = self.object_id_field
        features = []
        for item in raw_features:
            attributes = item.get("attributes")
            if not isinstance(attributes, dict):
                raise UpstreamFormatError(f"{self.url} gave a feature without attributes.")
            geometry = esri_geometry(item.get("geometry"))
            if geometry is not None and crs is not None:
                geometry = to_wgs84(geometry, crs)
            properties = {key: plain(value) for key, value in attributes.items()}
            if not isinstance(properties.get(oid), int):
                raise UpstreamFormatError(f"{self.url} gave a feature without its object id {oid}.")
            features.append(Feature(properties, geometry, properties[oid]))
        return features

    def _by_offset(self, bbox: BBox | None, expected: int, page: int) -> Iterator[Feature]:
        """Pages by offset until the count is reached or a page comes back empty."""
        offset = 0
        base = {**self._filter(bbox), "orderByFields": self.object_id_field}
        while offset < expected:
            features = self._query({**base, "resultOffset": str(offset), "resultRecordCount": str(page)})
            if not features:
                break
            yield from features
            offset += len(features)

    def _by_id_range(self, bbox: BBox | None, page: int) -> Iterator[Feature]:
        """Pages by ranges of object ids, asking again for the part of a range a capped answer left out."""
        ids = self.object_ids(bbox)
        oid = self.object_id_field
        filters = self._filter(bbox)
        for start in range(0, len(ids), page):
            chunk = ids[start : start + page]
            missing, given = set(chunk), set()
            low = chunk[0]
            while True:
                where = f"({filters['where']}) AND {oid} >= {low} AND {oid} <= {chunk[-1]}"
                features = self._query({**filters, "where": where})
                if len(features) > len(chunk):
                    raise UpstreamFormatError(
                        f"{self.url} returned more features than ids in {low}..{chunk[-1]}."
                    )
                fresh = [feature for feature in features if feature.id not in given]
                yield from fresh
                given.update(feature.id for feature in fresh)
                before = len(missing)
                missing -= given
                # Stop when the range is complete, or when asking again brought nothing new:
                # the rest has gone since the ids were listed, and the tally will say so.
                if not missing or len(missing) == before:
                    break
                low = min(missing)

    def features(self, bbox: BBox | None = None) -> Iterator[Feature]:
        """Every matching feature. Raises `IncompleteReadError` when the pages come up short."""
        expected = self.count(bbox)
        page = min(self.page_size or self.max_record_count, self.max_record_count)
        logger.info("%s: %d features to read, %d per page", self.url, expected, page)
        pages = (
            self._by_offset(bbox, expected, page)
            if self.supports_pagination
            else self._by_id_range(bbox, page)
        )
        tally = Tally(self.url, expected, self.tolerance)
        for feature in pages:
            tally.add(feature.id)
            yield feature
        tally.check()


def _crs_of(reference: Any) -> str | None:
    """The CRS of a response's `spatialReference`, or None for WGS84."""
    if not isinstance(reference, dict):
        return None
    wkid = reference.get("latestWkid") or reference.get("wkid")
    if wkid in (4326, None):
        if wkid is None and reference.get("wkt"):
            return str(reference["wkt"])
        return None
    if wkid == 102100:
        wkid = 3857
    return f"EPSG:{wkid}"


def _xy(points: Any) -> list[tuple[float, float]]:
    return [(float(point[0]), float(point[1])) for point in points]


def _signed_area(ring: Sequence[tuple[float, float]]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in pairwise(ring)) / 2


def _polygons_from_rings(rings: list[list[tuple[float, float]]]) -> BaseGeometry:
    """Esri rings to shapely. Outer rings run clockwise, holes anticlockwise.

    Each hole goes into the outer ring that contains it. A hole that no
    outer ring contains is kept as a polygon of its own, which is how some
    servers write rings with the wrong orientation.
    """
    outers: list[list[tuple[float, float]]] = []
    holes: list[list[tuple[float, float]]] = []
    for ring in rings:
        if len(ring) < 4:
            continue
        (outers if _signed_area(ring) <= 0 else holes).append(ring)
    shells = [Polygon(ring) for ring in outers]
    owned: list[list[list[tuple[float, float]]]] = [[] for _ in outers]
    for hole in holes:
        probe = Point(hole[0])
        owner = next((index for index, shell in enumerate(shells) if shell.covers(probe)), None)
        if owner is None:
            outers.append(hole)
            owned.append([])
        else:
            owned[owner].append(hole)
    polygons = [Polygon(shell, holes) for shell, holes in zip(outers, owned, strict=True)]
    if not polygons:
        return Polygon()
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def esri_geometry(geometry: Any) -> BaseGeometry | None:
    """A shapely geometry from an Esri JSON geometry, or None for a missing or empty one."""
    if not geometry:
        return None
    if not isinstance(geometry, dict):
        raise UpstreamFormatError(f"An Esri geometry must be an object, not {type(geometry).__name__}.")
    if "curvePaths" in geometry or "curveRings" in geometry:
        raise UpstreamFormatError("Esri true curves are not supported. Don't ask for returnTrueCurves.")
    result: BaseGeometry
    if "x" in geometry:
        if geometry["x"] is None or geometry.get("y") is None:
            return None
        result = Point(float(geometry["x"]), float(geometry["y"]))
    elif "points" in geometry:
        result = MultiPoint(_xy(geometry["points"]))
    elif "paths" in geometry:
        paths = [_xy(path) for path in geometry["paths"] if len(path) >= 2]
        result = LineString(paths[0]) if len(paths) == 1 else MultiLineString(paths)
    elif "rings" in geometry:
        result = _polygons_from_rings([_xy(ring) for ring in geometry["rings"]])
    else:
        raise UpstreamFormatError(f"Unknown Esri geometry with keys {sorted(geometry)}.")
    return None if result.is_empty else shapely.force_2d(result)
