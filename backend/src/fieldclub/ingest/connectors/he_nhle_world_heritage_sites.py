"""World Heritage Sites, from NHLE layer 10 of the Open Data Hub export.

Work-list key `he-nhle-world-heritage-sites`. 27 polygons for 18 sites: a site
has a row for its core area and often another for its buffer zone, both under
the one list entry number. The id is the list entry and the part, such as
`1000096-core-area`, so each part is stored once and none replaces another. A name search finds a
site and its buffer zone separately, as `<name>` and `<name> (buffer zone)`.
That is intended: the buffer zone is a place on the map in its own right.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.common import Feature
from fieldclub.ingest.base import RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source, slug
from fieldclub.ingest.registry import register


@register
class WorldHeritageSites(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source("he-nhle-world-heritage-sites", "NHLE: World Heritage Sites")
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 10)
    file_name: ClassVar[str] = "world-heritage-sites"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "World Heritage Site"
    date_fields: ClassVar[tuple[str, ...]] = ("InscrDate", "AmendDate")
    extra_fields: ClassVar[tuple[str, ...]] = ("Notes",)

    def external_id(self, properties: dict[str, Any]) -> str:
        part = slug(str(properties["Notes"] or ""))
        if not part:
            raise UpstreamFormatError(
                f"World Heritage Site {properties[self.id_field]} has no Notes to name its part."
            )
        return f"{super().external_id(properties)}-{part}"

    def to_record(self, feature: Feature) -> RecordIn:
        record = super().to_record(feature)
        part = str(feature.properties["Notes"]).strip()
        if part.lower() != "core area":
            # Two parts of one site share a name, so the part goes in it.
            record.name = f"{record.name} ({part.lower()})"
        record.summary = f"World Heritage Site: {part.lower()}"
        return record
