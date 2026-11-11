"""SPARQL endpoints, read as rows of plain values.

    query = SparqlQuery("https://query.wikidata.org/sparql", QUERY, client=connector.http,
                        geometry="coord", page_size=50_000)
    for feature in query.features(): ...

Each row's bindings become a dict of strings, one per variable that is bound.
The variable named by `geometry` holds a GeoSPARQL `wktLiteral`, which may
start with a CRS URI, as in `<http://www.opengis.net/def/crs/EPSG/0/27700>
POINT(410132 170023)`. Without one it is CRS84, longitude first, which is what
Wikidata writes. `wkt_literal` handles both.

With `page_size`, the query is paged by appending `LIMIT` and `OFFSET`. The
query must then have an `ORDER BY`, or the pages could overlap, and must not
have a `LIMIT` of its own. Wikidata turns away generic clients, which is why
every request carries the project `User-Agent` from the shared client.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import httpx
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.errors import ShapelyError
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters.common import WGS84, Feature, Polite, UpstreamFormatError

logger = logging.getLogger(__name__)

RESULTS_JSON = "application/sparql-results+json"
_CRS_PREFIX = re.compile(r"^\s*<([^>]+)>\s*(.*)$", re.DOTALL)
_CRS84 = ("http://www.opengis.net/def/crs/OGC/1.3/CRS84", "http://www.opengis.net/def/crs/OGC/0/CRS84")


def wkt_literal(value: str) -> BaseGeometry | None:
    """A GeoSPARQL WKT literal as shapely in WGS84, longitude first. None when empty."""
    match = _CRS_PREFIX.match(value)
    uri, wkt = (match.group(1), match.group(2)) if match else (None, value)
    try:
        geometry = shapely.from_wkt(wkt.strip())
    except ShapelyError:
        raise UpstreamFormatError(f"{value[:80]!r} isn't a WKT literal.") from None
    if geometry is None or geometry.is_empty:
        return None
    if uri is None or uri in _CRS84:
        return geometry
    # GeoSPARQL takes axis order from the CRS definition: latitude first for
    # EPSG:4326, easting first for the British grid. Read it that way, then
    # put longitude first.
    transformer = _latlon_transformer(uri)
    result = shapely.transform(geometry, lambda xy: _swap(transformer.transform(xy[:, 0], xy[:, 1])))
    assert isinstance(result, BaseGeometry), "shapely.transform returns a geometry for a geometry"
    return result


@lru_cache(maxsize=32)
def _latlon_transformer(uri: str) -> Transformer:
    """From the CRS a literal names to WGS84, in each CRS's own axis order."""
    return Transformer.from_crs(CRS.from_user_input(uri), WGS84, always_xy=False)


def _swap(latlon: tuple[Any, Any]) -> Any:
    lat, lon = latlon
    return np.column_stack((lon, lat))


# RDF 1.1 gives a blank node that has been made into an IRI this path, so it can be told from a real one.
_SKOLEM_PATH = "/.well-known/genid/"


def _has_value(cell: Any) -> bool:
    """Whether a result cell holds a value. A blank node doesn't, however it is written.

    Wikidata answers "unknown value" for a statement, such as a coordinate
    nobody has recorded, with a blank node or with the skolem IRI standing for
    one. It says a value exists and not what it is, so it is treated like an
    unbound variable.
    """
    if not isinstance(cell, dict) or "value" not in cell:
        return False
    if cell.get("type") == "bnode":
        return False
    return not (cell.get("type") == "uri" and _SKOLEM_PATH in str(cell["value"]))


class SparqlQuery:
    def __init__(
        self,
        endpoint: str,
        query: str,
        *,
        client: httpx.Client,
        polite: Polite | None = None,
        geometry: str | None = None,
        page_size: int | None = None,
        timeout: float | None = None,
    ) -> None:
        upper = query.upper()
        if page_size is not None:
            assert page_size >= 1, "page_size must be at least 1"
            assert "ORDER BY" in upper, "a paged query needs an ORDER BY, or pages may overlap"
            assert not re.search(r"\b(LIMIT|OFFSET)\b", upper), "a paged query must not set LIMIT or OFFSET"
        self.endpoint = endpoint
        self.query = query
        self.client = client
        self.polite = polite or Polite()
        self.geometry = geometry
        self.page_size = page_size
        # Seconds to wait for an answer. Wikidata lets a query run for a minute, past the client's own limit.
        self.timeout = timeout

    def _ask(self, query: str) -> list[dict[str, Any]]:
        extra = {} if self.timeout is None else {"timeout": self.timeout}
        response = self.polite.request(
            self.client,
            "GET",
            self.endpoint,
            params={"query": query},
            headers={"Accept": RESULTS_JSON},
            **extra,
        )
        try:
            body = response.json()
            bindings = body["results"]["bindings"]
        except (ValueError, KeyError, TypeError):
            raise UpstreamFormatError(f"{self.endpoint} did not answer with SPARQL JSON results.") from None
        if not isinstance(bindings, list):
            raise UpstreamFormatError(f"{self.endpoint} gave bindings that are not a list.")
        return bindings

    def rows(self) -> Iterator[dict[str, str]]:
        """Every result row as `{variable: value}`. Unbound variables are left out."""
        if self.page_size is None:
            pages: Iterator[list[dict[str, Any]]] = iter([self._ask(self.query)])
        else:
            pages = self._pages(self.page_size)
        for page in pages:
            for binding in page:
                yield {name: str(cell["value"]) for name, cell in binding.items() if _has_value(cell)}

    def _pages(self, size: int) -> Iterator[list[dict[str, Any]]]:
        offset = 0
        while True:
            page = self._ask(f"{self.query}\nLIMIT {size}\nOFFSET {offset}")
            yield page
            if len(page) < size:
                return
            offset += size

    def features(self) -> Iterator[Feature]:
        """Rows as features, with the geometry read from the `geometry` variable."""
        for row in self.rows():
            geometry = None
            if self.geometry is not None and self.geometry in row:
                geometry = wkt_literal(row[self.geometry])
            yield Feature(row, geometry)
