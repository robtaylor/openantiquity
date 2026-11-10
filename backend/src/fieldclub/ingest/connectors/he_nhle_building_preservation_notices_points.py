"""Building preservation notices as points, from NHLE layer 1 of the Open Data Hub export.

Work-list key `he-nhle-building-preservation-notices-points`. Six points. The
polygon layer holds the same notices with real outlines and is the one
stored, so this source is registered disabled and no notice is found twice
(`he_nhle_building_preservation_notices_polygons.py`).

The layer has `BPNStart` and `BPNExpire` where the others have `AmendDate`.
The expiry is a date in the future, so only the start says when the entry changed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class BuildingPreservationNoticePoints(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-building-preservation-notices-points",
        "NHLE: Building preservation notices (points)",
        enabled=False,
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 1)
    file_name: ClassVar[str] = "building-preservation-notices-points"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPoint", "Point")
    record_type: ClassVar[str] = "Building preservation notice"
    date_fields: ClassVar[tuple[str, ...]] = ("BPNStart",)
    extra_fields: ClassVar[tuple[str, ...]] = ("BPNExpire",)

    def summary(self, properties: dict[str, Any]) -> str | None:
        start, expire = properties["BPNStart"], properties["BPNExpire"]
        if start is None or expire is None:
            return None
        return f"Notice served {start:%-d %B %Y}, expiring {expire:%-d %B %Y}"
