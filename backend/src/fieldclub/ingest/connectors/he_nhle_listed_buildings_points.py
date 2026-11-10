"""Listed buildings as points, from NHLE layer 0 of the Open Data Hub export.

Work-list key `he-nhle-listed-buildings-points`. About 380,000 points, one for
every listed building, 103 MB, refreshed daily. This is the layer that is
stored and shown. The polygon layer of the same entries holds a real outline
for only 10,080 of them, so it is built but not enabled
(`he_nhle_listed_buildings_polygons.py`).
"""

from __future__ import annotations

from typing import Any, ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class ListedBuildingPoints(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-listed-buildings-points", "NHLE: Listed buildings (points)"
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 0)
    file_name: ClassVar[str] = "listed-buildings-points"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPoint", "Point")
    record_type: ClassVar[str] = "Listed building"
    date_fields: ClassVar[tuple[str, ...]] = ("ListDate", "AmendDate")
    extra_fields: ClassVar[tuple[str, ...]] = ("Grade",)

    def summary(self, properties: dict[str, Any]) -> str | None:
        grade = str(properties["Grade"] or "").strip()
        return f"Grade {grade} listed building" if grade else None
