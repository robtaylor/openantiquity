"""Certificates of immunity from listing as outlines, from NHLE layer 5 of the Open Data Hub export.

Work-list key `he-nhle-certificates-of-immunity-polygons`. 222 polygons, the
outlines of the certificates the points layer marks. This is the layer that is
stored and shown. The id is built as the points layer's is: the list entry,
with the grid reference added for an entry that occurs more than once.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_certificates_of_immunity_points import CertificateOfImmunityPoints
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class CertificateOfImmunityPolygons(CertificateOfImmunityPoints):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-certificates-of-immunity-polygons", "NHLE: Certificates of immunity (polygons)"
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 5)
    file_name: ClassVar[str] = "certificates-of-immunity-polygons"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
