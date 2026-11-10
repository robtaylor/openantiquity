"""Registered parks and gardens, from NHLE layer 7 of the Open Data Hub export.

Work-list key `he-nhle-registered-parks-and-gardens`. About 1,700 polygons.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class RegisteredParksAndGardens(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-registered-parks-and-gardens", "NHLE: Registered parks and gardens"
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 7)
    file_name: ClassVar[str] = "registered-parks-and-gardens"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "Registered park and garden"
    date_fields: ClassVar[tuple[str, ...]] = ("RegDate", "AmendDate")
    extra_fields: ClassVar[tuple[str, ...]] = ("Grade",)

    def summary(self, properties: dict[str, Any]) -> str | None:
        grade = str(properties["Grade"] or "").strip()
        return f"Grade {grade} registered park and garden" if grade else None
