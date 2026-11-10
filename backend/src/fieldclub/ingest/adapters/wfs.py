"""OGC Web Feature Service 2.0 layers.

    layer = WFSLayer("https://datamap.gov.wales/geoserver/ows", "inspire-wg:Cadw_SAM",
                     client=connector.http, sort_by="RecordNumber")
    for feature in layer.features(bbox=bbox): ...

The reader counts first with `resultType=hits`, then pages with `count` and
`startIndex`. Paging is only stable when the server sorts, so `sort_by` is
required and names a unique property, usually the record number. The reader
also counts distinct values of it, so a feature repeated across pages can't
hide one that was skipped. `startIndex` moves by however many features came
back, so a server that caps pages below `count` (GeoServer's `maxFeatures`)
still reads completely.

Features are asked for in a projected CRS, the layer's own by default, and
reprojected here. A WFS 2.0 server writes EPSG:4326 latitude first, and
servers differ in whether they honour that in GeoJSON, so asking in a grid
CRS is the one way to know which number is which. GeoJSON output is read
directly. Any other output format (GML 3.2 is the usual) goes through pyogrio.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pyogrio.raw
from pyproj import CRS, Transformer

from fieldclub.ingest.adapters.common import (
    WGS84,
    Feature,
    Polite,
    Tally,
    UpstreamFormatError,
    plain_tree,
)
from fieldclub.ingest.adapters.files import geojson_geometry, ogr_features, quiet_ogr
from fieldclub.ingest.base import BBox

logger = logging.getLogger(__name__)

_NUMBER_MATCHED = re.compile(rb'numberMatched="(\d+)"')
_JSON_FORMATS = ("application/json", "json", "geojson", "application/geo+json")


class WFSLayer:
    def __init__(
        self,
        url: str,
        type_name: str,
        *,
        client: httpx.Client,
        polite: Polite | None = None,
        srs_name: str = "EPSG:27700",
        sort_by: str,
        page_size: int = 1000,
        output_format: str = "application/json",
        tolerance: float = 0.0,
    ) -> None:
        crs = CRS.from_user_input(srs_name)
        assert crs.is_projected, (
            f"ask for features in a projected CRS, not {srs_name}: geographic axis order is ambiguous"
        )
        assert sort_by, "name a unique property to sort by, or paging can repeat and skip features"
        assert page_size >= 1, "page_size must be at least 1"
        assert 0 <= tolerance < 1, "tolerance is a share between 0 and 1"
        self.url = url
        self.type_name = type_name
        self.client = client
        self.polite = polite or Polite()
        self.srs_name = srs_name
        self.sort_by = sort_by
        self.page_size = page_size
        self.output_format = output_format
        self.tolerance = tolerance
        self._to_grid = Transformer.from_crs(WGS84, crs, always_xy=True)

    def _params(self, bbox: BBox | None) -> dict[str, str]:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": self.type_name,
        }
        if bbox is not None:
            west, south, east, north = self._to_grid.transform_bounds(*bbox, densify_pts=21)
            params["bbox"] = f"{west!r},{south!r},{east!r},{north!r},{self.srs_name}"
        return params

    def count(self, bbox: BBox | None = None) -> int:
        response = self.polite.request(
            self.client, "GET", self.url, params={**self._params(bbox), "resultType": "hits"}
        )
        match = _NUMBER_MATCHED.search(response.content)
        if match is None:
            raise UpstreamFormatError(f"{self.url} gave no numberMatched for {self.type_name}.")
        return int(match.group(1))

    def _page(self, bbox: BBox | None, start: int) -> list[Feature]:
        params = {
            **self._params(bbox),
            "outputFormat": self.output_format,
            "srsName": self.srs_name,
            "count": str(self.page_size),
            "startIndex": str(start),
            "sortBy": self.sort_by,
        }
        response = self.polite.request(self.client, "GET", self.url, params=params)
        if b"ExceptionReport" in response.content[:400]:
            raise UpstreamFormatError(f"{self.url} refused the request: {response.text[:300]!r}")
        if self.output_format.lower() in _JSON_FORMATS:
            return self._from_geojson(response)
        return self._from_ogr(response.content)

    def _from_geojson(self, response: httpx.Response) -> list[Feature]:
        try:
            body: Any = response.json()
        except ValueError:
            raise UpstreamFormatError(f"{self.url} did not answer with JSON.") from None
        if not isinstance(body, dict) or not isinstance(body.get("features"), list):
            raise UpstreamFormatError(f"{self.url} did not answer with a FeatureCollection.")
        stated = ((body.get("crs") or {}).get("properties") or {}).get("name")
        if stated is not None and CRS.from_user_input(stated) != CRS.from_user_input(self.srs_name):
            raise UpstreamFormatError(f"{self.url} answered in {stated}, not {self.srs_name}.")
        return [
            Feature(
                plain_tree(item.get("properties") or {}),
                geojson_geometry(item.get("geometry"), self.srs_name, where=str(item.get("id"))),
                item.get("id"),
            )
            for item in body["features"]
        ]

    def _from_ogr(self, content: bytes) -> list[Feature]:
        # DOWNLOAD_SCHEMA=NO: GDAL would otherwise fetch the XSD the response points at.
        with quiet_ogr():
            meta, fids, geometries, fields = pyogrio.raw.read(
                io.BytesIO(content), return_fids=True, DOWNLOAD_SCHEMA="NO"
            )
        return list(ogr_features(meta, fids, geometries, fields, meta.get("crs") or self.srs_name))

    def features(self, bbox: BBox | None = None) -> Iterator[Feature]:
        expected = self.count(bbox)
        logger.info("%s %s: %d features to read", self.url, self.type_name, expected)
        tally = Tally(self.url, expected, self.tolerance, what=self.type_name)
        start = 0
        while start < expected:
            page = self._page(bbox, start)
            if not page:
                break
            for feature in page:
                tally.add(feature.properties.get(self.sort_by))
                yield feature
            start += len(page)
        tally.check()
