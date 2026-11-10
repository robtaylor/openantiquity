"""Building preservation notices as outlines, from NHLE layer 4 of the Open Data Hub export.

Work-list key `he-nhle-building-preservation-notices-polygons`. Six polygons,
the outlines of the notices the points layer marks. This is the layer that is
stored and shown.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_building_preservation_notices_points import (
    BuildingPreservationNoticePoints,
)
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class BuildingPreservationNoticePolygons(BuildingPreservationNoticePoints):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-building-preservation-notices-polygons", "NHLE: Building preservation notices (polygons)"
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 4)
    file_name: ClassVar[str] = "building-preservation-notices-polygons"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
