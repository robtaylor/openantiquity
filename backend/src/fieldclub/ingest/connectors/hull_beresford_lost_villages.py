"""Beresford's Lost Villages: the deserted medieval villages of England, from the University of Hull.

Work-list key `hull-beresford-lost-villages`. The layer holds about 2,200 points with
45 fields each, mostly from the gazetteer Maurice Beresford and John Hurst compiled
in the 1950s to 1970s and the University of Hull has kept up. Positions come from
grid references, mostly six figures, so a record is placed at the centre of its grid
square, good to 100 m. The layer's own geometry follows its Latitude and Longitude
fields, which are wrong for some sites (a sign flipped, or a different place), so
it is used only when the grid reference does not parse. `to_record` logs each site
whose geometry lies further from its grid reference than the reference's precision.

The licence is Creative Commons Attribution-NonCommercial-ShareAlike 4.0, stated in
the website's footer and not in the ArcGIS item. OpenAntiquity is non-commercial
(Decision 0004), so the records are stored. The `sources` row carries the licence
and the university's attribution, and the reuse class `non_commercial`, which the
runner keeps with every record.

The layer has no identifier of its own. Its `ID` field is the number within a county,
so two sites share each one, and `FID` is the layer's object id. The external id is
a hash of the site's name and its grid reference. The pair is unique in the data, and
`fetch()` raises when it stops being so.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Iterator
from typing import ClassVar

from shapely.geometry import Point

from fieldclub.gridref import to_grid, try_parse_gridref
from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, Polite, json_ready, text_of
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

LAYER = "https://services2.arcgis.com/GTEgXeL0m6EyJsOO/arcgis/rest/services/Lost_Villages/FeatureServer/0"
FIELDS = ("Site_name", "Grid_reference", "Site_type", "Description", "Site_status", "NMR_no", "HER_no")
# The layer puts a status word where a code of the kind of site would go, for sites whose
# status matters more than their kind. Each is spelled out so that the type says what it is.
SITE_STATUSES = {
    "Doubtful": "Deserted medieval village (doubtful)",
    "Shrunken": "Shrunken medieval village",
    "Shifted": "Shifted medieval village",
    "Migrated": "Migrated medieval village",
}
# The Beresford gazetteer is of medieval settlements, but a doubtful site has no evidence of one.
NO_PERIOD = frozenset({"Doubtful"})
# The layer's own codes for the kinds of site. Others are kept as they are.
SITE_TYPES = {
    "DMV": "Deserted medieval village",
    "DMH": "Deserted medieval hamlet",
    **SITE_STATUSES,
}
# What the work-list gives for the layer, when a grid reference can't say.
DEFAULT_PRECISION_M = 100.0


@register
class BeresfordLostVillages(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="hull-beresford-lost-villages",
        name="Beresford's Lost Villages (deserted medieval villages)",
        publisher="University of Hull",
        licence="CC BY-NC-SA 4.0 (stated in the website footer; the ArcGIS item's licence field is empty)",
        licence_url=None,
        attribution=(
            "(c) 2009-2024 The University of Hull. This work is licensed under a Creative Commons "
            "Attribution-NonCommercial-ShareAlike 4.0 International License."
        ),
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.NON_COMMERCIAL,
        homepage="https://dmv.hull.ac.uk/",
        coverage="England",
    )

    # Tests give it one that doesn't wait. A real run leaves a second between requests.
    polite: Polite | None = None

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER, client=self.http, polite=self.polite)
        layer.require(FIELDS, geometry_type="esriGeometryPoint")
        seen: dict[str, str] = {}
        for feature in layer.features(bbox=bbox):
            record = to_record(feature)
            if record.external_id in seen:
                raise UpstreamFormatError(
                    f"Two lost villages share the name and grid reference {seen[record.external_id]!r}."
                )
            seen[record.external_id] = record.name
            yield record


def external_id(name: str, grid_reference: str) -> str:
    """The id of a site: a hash of its name and grid reference, which name the thing itself."""
    key = f"{' '.join(name.split()).lower()}|{''.join(grid_reference.split()).upper()}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def placed(grid_reference: str, geometry: Point) -> tuple[Point, float, float | None]:
    """Where a site is, how exactly in metres, and how far the layer's geometry lies from that.

    The point is the centre of the grid reference's square. A reference that does not
    parse, or that is not on the British grid, leaves the layer's geometry as it was,
    at the work-list's 100 m, and the distance is None.
    """
    parsed = try_parse_gridref(grid_reference)
    if parsed is None:
        return geometry, DEFAULT_PRECISION_M, None
    lon, lat = parsed.centre()
    system, easting, northing = to_grid(geometry.x, geometry.y)
    offset = None
    if system == parsed.system:
        half = parsed.precision_m / 2
        offset = math.hypot(easting - (parsed.easting + half), northing - (parsed.northing + half))
    return Point(lon, lat), float(parsed.precision_m), offset


def to_record(feature: Feature) -> RecordIn:
    """One lost village of the layer as a record."""
    properties = feature.properties
    name = text_of(properties, "Site_name")
    grid_reference = text_of(properties, "Grid_reference")
    if not name or not grid_reference:
        raise UpstreamFormatError(f"A lost village has name {name!r} and grid reference {grid_reference!r}.")
    if not isinstance(feature.geometry, Point):
        raise UpstreamFormatError(f"Lost village {name} ({grid_reference}) has no position.")
    position, precision, offset = placed(grid_reference, feature.geometry)
    if offset is not None and offset > precision:
        logger.warning(
            "Lost village %s (%s): the layer's geometry is %.0f m from its grid reference, which is used.",
            name,
            grid_reference,
            offset,
        )
    site_type = text_of(properties, "Site_type")
    return RecordIn(
        external_id=external_id(name, grid_reference),
        name=name,
        geom=position,
        record_type=SITE_TYPES.get(site_type, site_type) or None,
        periods=[] if site_type in NO_PERIOD else [Period.MEDIEVAL],
        summary=text_of(properties, "Description") or None,
        precision_m=precision,
        # The layer's FID changes when the layer is rebuilt, so it isn't kept.
        raw={
            key: value for key, value in json_ready(properties).items() if key != "FID" and value is not None
        },
    )
