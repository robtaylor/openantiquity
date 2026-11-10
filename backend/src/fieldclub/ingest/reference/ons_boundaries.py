"""Nation and county boundaries for `admin_areas`, from the Office for National Statistics.

Work-list key `ons-countries-2025` gives the four nations: ONS's Countries
(December 2025) boundaries, generalised to 20 m and clipped to the coastline.
The work-list lists no county boundaries in any wave except OS Boundary-Line,
which it marks as untested and leaves for later. So the counties come from
the same publisher and series: Counties and Unitary Authorities (December
2025), also generalised to 20 m and clipped. That is England's counties and
unitary authorities, Wales's and Scotland's council areas and Northern
Ireland's districts, about 220 areas. ONS publishes no ceremonial counties.
Its licence page, read on 2026-11-10, puts both under the Open Government
Licence with the statement in `ONS_STATEMENT`.

Each is one request for GeoJSON, cached under `var/ingest/<key>/` for a month,
because ONS publishes a new edition once a year.

`services.geo.locate` asks which areas cover a point, so every lookup tests a
point against the boundaries that contain it. Boundaries as published have
tens of thousands of vertices each, so they are simplified before they are
stored, by `SIMPLIFY_M` on the British grid, which keeps a lookup well under
a millisecond. Nations are simplified as one coverage, so the border between
two of them stays shared and no point falls between them or in both.

The coastline is mean high water. A point on the foreshore or just out to sea
would be in no nation, so each nation is extended `SEAWARD_M` out to sea, and
water within that distance of two nations, as in the Severn and the Solway,
is left to neither. Counties reach out to sea the same way, so sea near the
coastal end of a border between two counties is in neither county.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import timedelta
from functools import cache
from typing import Any, ClassVar

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import to_wgs84
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_vector, vector_info
from fieldclub.ingest.base import BBox, SourceInfo
from fieldclub.ingest.reference import register
from fieldclub.ingest.reference.base import Loader
from fieldclub.models import AdminArea
from fieldclub.vocab import AdminAreaKind, Nation, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

SERVICES = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/ArcGIS/rest/services"
COUNTRIES = f"{SERVICES}/Countries_December_2025_Boundaries_UK_BGC/FeatureServer/0"
COUNTIES = f"{SERVICES}/Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC/FeatureServer/0"
# The statement ONS's licence page asks for with its digital boundaries.
ONS_STATEMENT = (
    "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
    "Contains OS data © Crown copyright and database right [year]."
)
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

NATIONS = {
    "E92000001": Nation.ENGLAND,
    "S92000003": Nation.SCOTLAND,
    "W92000004": Nation.WALES,
    "N92000002": Nation.NORTHERN_IRELAND,
}
# The first letter of an ONS area code says which nation it is in.
CODE_NATIONS = {code[0]: nation for code, nation in NATIONS.items()}
# Council areas and districts as they stood in December 2025. England's
# counties and unitary authorities change more often, so only a floor is held.
COUNTIES_PER_NATION = {Nation.WALES: 22, Nation.SCOTLAND: 32, Nation.NORTHERN_IRELAND: 11}
MIN_ENGLISH_COUNTIES = 140

GRID = "EPSG:27700"
# How far land boundaries are simplified, how far out to sea an area reaches,
# and how coarse the outline it reaches out from is.
SIMPLIFY_M = 20.0
SEAWARD_M = 2000.0
COARSE_M = 200.0


def _polygons(geom: BaseGeometry) -> MultiPolygon:
    """The polygons of a geometry, as a MultiPolygon. Lines and points left by an operation are dropped."""
    parts: list[Polygon] = []
    for part in shapely.get_parts(geom):
        if isinstance(part, Polygon):
            parts.append(part)
        elif isinstance(part, MultiPolygon | GeometryCollection):
            parts.extend(_polygons(part).geoms)
    return MultiPolygon([part for part in parts if not part.is_empty])


def _valid(geom: BaseGeometry) -> BaseGeometry:
    """The geometry, repaired if it isn't valid. Published boundaries usually are."""
    return geom if geom.is_valid else _polygons(shapely.make_valid(geom))


def to_grid(geom: BaseGeometry) -> BaseGeometry:
    """A WGS84 geometry on the British grid, where distances are in metres."""
    transformer = _to_grid()
    result = shapely.transform(geom, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))
    assert isinstance(result, BaseGeometry), "shapely.transform returns a geometry for a geometry"
    return result


@cache
def _to_grid() -> Transformer:
    return Transformer.from_crs("EPSG:4326", GRID, always_xy=True)


def simplified(areas: dict[str, BaseGeometry], simplify_m: float) -> dict[str, BaseGeometry]:
    """Areas that tile the land, simplified together on the British grid so neighbours keep a shared edge."""
    codes = list(areas)
    grid = [_valid(to_grid(areas[code])) for code in codes]
    if simplify_m:
        grid = list(shapely.coverage_simplify(grid, simplify_m))
    return dict(zip(codes, grid, strict=True))


def out_to_sea(areas: dict[str, BaseGeometry], seaward_m: float) -> dict[str, BaseGeometry]:
    """Each area with the sea within about `seaward_m` of it, except sea that close to another area too.

    Takes and gives areas on the British grid that tile the land. The reach
    out to sea is measured from a coarse copy of each area, so its outline
    has few vertices, and it is taken out by at least `seaward_m - COARSE_M`.
    Where it meets the area's own coast, the coastline goes inside the area,
    which is what makes a point lookup quick.
    """
    codes = list(areas)
    shapes = [areas[code] for code in codes]
    reach = [
        shapely.buffer(shapely.simplify(shape, COARSE_M, preserve_topology=True), seaward_m, quad_segs=2)
        for shape in shapes
    ]
    shape_tree = shapely.STRtree(shapes)
    reach_tree = shapely.STRtree(reach)
    result: dict[str, BaseGeometry] = {}
    for index, code in enumerate(codes):
        near_land = shapely.union_all([shapes[i] for i in shape_tree.query(reach[index])])
        rivals = shapely.union_all([reach[i] for i in reach_tree.query(reach[index]) if i != index])
        sea = shapely.difference(shapely.difference(reach[index], near_land), rivals)
        result[code] = shapely.union(shapes[index], sea)
    return result


def in_wgs84(areas: dict[str, BaseGeometry]) -> dict[str, MultiPolygon]:
    """Areas on the British grid as valid WGS84 multipolygons."""
    result: dict[str, MultiPolygon] = {}
    for code, area in areas.items():
        shape = _polygons(to_wgs84(area, GRID))
        result[code] = _polygons(_valid(shape))
    return result


class _OnsLayer(Loader):
    """One ONS boundary layer as `admin_areas` rows of one kind."""

    model = AdminArea
    supports_bbox = False
    kind: ClassVar[AdminAreaKind]
    layer: ClassVar[str]
    code_field: ClassVar[str]
    name_field: ClassVar[str]
    file_name: ClassVar[str]
    # ONS publishes a new edition once a year.
    max_age: ClassVar[timedelta] = timedelta(days=30)

    def owned(self) -> ColumnElement[bool]:
        return AdminArea.kind == self.kind.value

    def boundaries(self) -> dict[str, tuple[str, BaseGeometry]]:
        """Every area of the layer by code: its name and its boundary in WGS84, as published."""
        path = cache_dir(self.settings, self.source.key) / self.file_name
        params = {
            "where": "1=1",
            "outFields": f"{self.code_field},{self.name_field}",
            "outSR": "4326",
            "f": "geojson",
        }
        fetched = download(f"{self.layer}/query", path, client=self.http, max_age=self.max_age, params=params)
        self.obtained_at = fetched.fetched_at
        info = vector_info(path)
        missing = [name for name in (self.code_field, self.name_field) if name not in info["fields"]]
        if missing:
            raise UpstreamFormatError(f"{self.source.key} changed shape: its features lack {missing}.")
        areas: dict[str, tuple[str, BaseGeometry]] = {}
        for feature in read_vector(path, info=info):
            code = feature.properties[self.code_field]
            name = feature.properties[self.name_field]
            if not isinstance(code, str) or not isinstance(name, str) or feature.geometry is None:
                raise UpstreamFormatError(f"{self.source.key} has an area without a code, name or boundary.")
            if code in areas:
                raise UpstreamFormatError(f"{self.source.key} has two areas with the code {code}.")
            areas[code] = (name.strip(), feature.geometry)
        self.read = len(areas)
        return areas

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[dict[str, Any]]:
        assert bbox is None, "ONS boundaries are loaded whole"
        areas = self.boundaries()
        self.check(areas)
        land = simplified({code: geom for code, (_, geom) in areas.items()}, SIMPLIFY_M)
        shapes = in_wgs84(out_to_sea(land, SEAWARD_M))
        for code, (name, _) in sorted(areas.items()):
            yield {"kind": self.kind.value, "code": self.code_for(code), "name": name, "geom": shapes[code]}

    def check(self, areas: dict[str, tuple[str, BaseGeometry]]) -> None:
        """Raise `UpstreamFormatError` when the layer isn't what was expected."""

    def code_for(self, ons_code: str) -> str:
        return ons_code


@register
class OnsCountries(_OnsLayer):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="ons-countries-2025",
        name="Countries December 2025 boundaries (BGC)",
        publisher="Office for National Statistics",
        licence="OGL v3 (ONS); not re-read today",
        licence_url=OGL,
        attribution="Contains public sector information licensed under the Open Government Licence v3.0. "
        + ONS_STATEMENT,
        category="boundary",
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://geoportal.statistics.gov.uk/",
        coverage="United Kingdom",
    )
    kind = AdminAreaKind.NATION
    layer = COUNTRIES
    code_field = "CTRY25CD"
    name_field = "CTRY25NM"
    file_name = "countries.geojson"

    def check(self, areas: dict[str, tuple[str, BaseGeometry]]) -> None:
        if set(areas) != set(NATIONS):
            raise UpstreamFormatError(f"ONS countries changed: codes {sorted(areas)}, not {sorted(NATIONS)}.")

    def code_for(self, ons_code: str) -> str:
        # A nation's code in admin_areas is its vocab.Nation value.
        return NATIONS[ons_code].value


@register
class OnsCounties(_OnsLayer):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="ons-counties-2025",
        name="Counties and Unitary Authorities December 2025 boundaries (BGC)",
        publisher="Office for National Statistics",
        licence="Open Government Licence v3.0",
        licence_url=OGL,
        attribution=ONS_STATEMENT,
        category="boundary",
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://geoportal.statistics.gov.uk/",
        coverage="United Kingdom",
    )
    kind = AdminAreaKind.COUNTY
    layer = COUNTIES
    code_field = "CTYUA25CD"
    name_field = "CTYUA25NM"
    file_name = "counties.geojson"

    def check(self, areas: dict[str, tuple[str, BaseGeometry]]) -> None:
        per_nation: dict[Nation, int] = {}
        for code in areas:
            nation = CODE_NATIONS.get(code[:1])
            if nation is None:
                raise UpstreamFormatError(f"ONS counties has the code {code}, in no nation.")
            per_nation[nation] = per_nation.get(nation, 0) + 1
        expected = COUNTIES_PER_NATION | {Nation.ENGLAND: per_nation.get(Nation.ENGLAND, 0)}
        if per_nation != expected or per_nation[Nation.ENGLAND] < MIN_ENGLISH_COUNTIES:
            raise UpstreamFormatError(f"ONS counties changed: {per_nation} areas per nation.")
