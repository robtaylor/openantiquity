"""Registered battlefields, from NHLE layer 8 of the Open Data Hub export.

Work-list key `he-nhle-registered-battlefields`. 47 polygons.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class RegisteredBattlefields(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-registered-battlefields", "NHLE: Registered battlefields"
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 8)
    file_name: ClassVar[str] = "registered-battlefields"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "Registered battlefield"
    date_fields: ClassVar[tuple[str, ...]] = ("RegDate", "AmendDate")
