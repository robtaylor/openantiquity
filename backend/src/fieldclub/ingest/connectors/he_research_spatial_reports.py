"""Historic England Research Report Series locations.

Work-list key `he-research-spatial-reports`. A point for each place a Historic England
research report is about, from the `Historic_England_Research_Spatial_Reports`
FeatureServer, layer 475 (not 0). About 13,500 rows for about 7,400 reports: a report
with many sites has a row for each, and a project over a large area has a single point
at its centre. `Report_Num` is mostly a report number, but also holds series numbers and
a few words, and repeats across rows, so the external id is a hash of `Report_Num`, the
title and the geometry. Each record links to the report's page. Historic England's pages
answer 403 to scripts, so the link is only followed by a person.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
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


@register
class ResearchSpatialReports(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-research-spatial-reports",
        name="Historic England Research Report Series locations",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution="© Historic England 2026. Released under OGL.",
        category=RecordCategory.DOCUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://historicengland.org.uk/research/results/reports/",
        coverage="England",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, geometry_precision=6)
        layer.require_shape(FIELDS, "esriGeometryPoint")
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
        external_id=keys.key([number, title], feature.geometry),
        name=title,
        geom=feature.geometry,
        summary=str(properties["Brief_description"] or "").strip() or None,
        record_type=str(properties["Project_type"] or "").strip() or None,
        url=REPORT_PAGE.format(Report_Num=number) if REPORT_NUMBER.fullmatch(number) else None,
        raw=json_ready(properties),
    )
