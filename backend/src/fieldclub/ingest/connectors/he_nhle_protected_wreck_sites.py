"""Protected wreck sites, from NHLE layer 9 of the Open Data Hub export.

Work-list key `he-nhle-protected-wreck-sites`. 57 polygons. A wreck row has
`Latitude` and `Longitude` where the other layers have `Easting` and `Northing`.
Neither is read: the position is the polygon.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class ProtectedWreckSites(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source("he-nhle-protected-wreck-sites", "NHLE: Protected wreck sites")
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 9)
    file_name: ClassVar[str] = "protected-wreck-sites"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "Protected wreck site"
    date_fields: ClassVar[tuple[str, ...]] = ("DesigDate", "AmendDate")
