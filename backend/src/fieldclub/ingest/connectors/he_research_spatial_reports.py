"""Historic England Research Report Series locations.

Work-list key `he-research-spatial-reports`. A point for each place a Historic England
research report is about, from the `Historic_England_Research_Spatial_Reports`
FeatureServer, layer 475 (not 0). About 13,500 rows for about 7,400 reports: a report
with many sites has a row for each, and a project over a large area has a single point
at its centre. `Report_Num` is mostly a report number, but also holds series numbers and
a few words, and repeats across rows, so the external id is a hash of `Report_Num`, the
title and the geometry on the British National Grid (the layer is asked for
EPSG:27700, to a tenth of a metre, so the id doesn't move with the reprojection).
Each record links to the address in the layer's own `Report_URL`, which every row has.
Building one from `Report_Num` would be wrong: it gave no link for 670 rows whose number
is a series or a few words, and a different page from the layer's on 31 others.
`REPORT_PAGE` is the fallback for a row whose `Report_URL` is blank. Historic England's
pages answer 403 to scripts, so the link is only followed by a person.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import OGL_URL
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "Historic_England_Research_Spatial_Reports/FeatureServer/475"
)
REPORT_PAGE = "https://historicengland.org.uk/research/results/reports/{Report_Num}"
FIELDS = (
    "OBJECTID",
    "Report_Num",
    "Report_title",
    "Brief_description",
    "Report_URL",
    "Project_type",
    "Year",
)
# A report number is letters, digits and hyphens. Anything else would make an address that goes nowhere.
REPORT_NUMBER = re.compile(r"[A-Za-z0-9-]+")
# The only host the layer's own addresses are trusted to point at.
REPORT_HOST = "https://historicengland.org.uk/"


@register
class ResearchSpatialReports(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-research-spatial-reports",
        name="Historic England Research Report Series locations",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url=OGL_URL,
        attribution="© Historic England 2026. Released under OGL.",
        category=RecordCategory.DOCUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://historicengland.org.uk/research/results/reports/",
        coverage="England",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, out_sr=27700, geometry_precision=1)
        layer.require(FIELDS, geometry_type="esriGeometryPoint")
        keys = FeatureKeys()
        for feature in layer.features(bbox=bbox):
            yield to_record(feature, keys)


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One report location as a record."""
    properties = feature.properties
    if feature.geometry is None:
        raise UpstreamFormatError(f"Research report row {feature.id} has no location.")
    number = str(properties["Report_Num"] or "").strip()
    title = str(properties["Report_title"] or "").strip()
    if not title:
        raise UpstreamFormatError(f"Research report row {feature.id} has no title.")
    return RecordIn(
        external_id=keys.key([number, title], feature.geometry, native=feature.native),
        name=title,
        geom=feature.geometry,
        summary=str(properties["Brief_description"] or "").strip() or None,
        record_type=str(properties["Project_type"] or "").strip() or None,
        url=report_url(properties["Report_URL"], number),
        raw=json_ready(properties),
    )


def report_url(given: object, number: str) -> str | None:
    """The layer's own link when it is a Historic England address, else one built from a plain number."""
    text = given.strip() if isinstance(given, str) else ""
    if text.startswith(REPORT_HOST):
        return text
    return REPORT_PAGE.format(Report_Num=number) if REPORT_NUMBER.fullmatch(number) else None
