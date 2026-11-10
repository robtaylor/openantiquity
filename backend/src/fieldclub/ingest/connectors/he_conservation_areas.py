"""Conservation areas in England, from the Open Data Hub GeoPackage export.

Work-list key `he-conservation-areas`. 8,749 polygons in EPSG:27700, 72 MB,
collected by Historic England from the local planning authorities. It is a
separate Hub item from the NHLE, with its own fields and no list entry pages,
so it shares `NhleLayer` but not the NHLE's licence text, attribution or links.
The count is below Historic England's own estimate of about 10,000.

The layer's `UID` is not an identifier. It is 0 for 91 areas and 1 for 36
more. The id is therefore built from the fields that name the area: a hash
of the local planning authority, the lower-cased name and the designation
date, `DATE_OF_DE`, which is unique in the export. An area renamed or
redesignated upstream is a new record and the old one is removed by the next
full run, and evidence and investigation links to it are cleared. So is every
area of an authority that is renamed, as local government reorganisation does
in bulk (the 2023 North Yorkshire and Somerset unitaries). The runner's shrink
check refuses a run that would delete over a quarter of the stored areas, but
not a smaller renaming, so a run that reports many `deleted` after a
reorganisation should be read before it is accepted.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.common import Feature
from fieldclub.ingest.base import RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import HUB_HOMEPAGE, OGL_URL, NhleLayer, hub_export_url
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

CONSERVATION_AREAS_ITEM = "446bc9bf8b5b440386d0c504caa3dac5"


@register
class ConservationAreas(NhleLayer):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-conservation-areas",
        name="Conservation areas (England)",
        publisher="Historic England and Local Planning Authorities",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url=OGL_URL,
        attribution=(
            "© Historic England and Local Planning Authorities 2026. "
            "Contains Ordnance Survey data © Crown copyright and database right 2026. Released under OGL."
        ),
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage=HUB_HOMEPAGE,
        coverage="England",
    )
    export_url: ClassVar[str] = hub_export_url(CONSERVATION_AREAS_ITEM, 0)
    file_name: ClassVar[str] = "conservation-areas"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "Conservation area"
    id_field: ClassVar[str] = "UID"
    name_field: ClassVar[str] = "NAME"
    date_fields: ClassVar[tuple[str, ...]] = ()
    extra_fields: ClassVar[tuple[str, ...]] = ("DATE_OF_DE", "LPA")

    def external_id(self, properties: dict[str, Any]) -> str:
        authority = str(properties["LPA"] or "").strip().lower()
        name = str(properties[self.name_field] or "").strip().lower()
        designated = str(properties["DATE_OF_DE"] or "").strip()
        if not authority or not name:
            raise UpstreamFormatError(f"A conservation area has no name or authority: {properties!r}.")
        return hashlib.sha256(f"{authority}|{name}|{designated}".encode()).hexdigest()[:20]

    def to_record(self, feature: Feature) -> RecordIn:
        record = super().to_record(feature)
        if published(record.name) is None:
            # 36 areas have a boundary and nothing else.
            record.name = f"Conservation area in {str(feature.properties['LPA']).strip()}"
        return record

    def summary(self, properties: dict[str, Any]) -> str | None:
        authority = str(properties["LPA"]).strip()
        designated = published(properties["DATE_OF_DE"])
        if designated is None:
            return f"Conservation area designated by {authority}"
        return f"Conservation area designated by {authority} on {designated}"

    def url(self, properties: dict[str, Any]) -> str | None:
        return None


def published(text: Any) -> str | None:
    """The text, or None where the layer says it has nothing: blank, `unknown` or `No data available...`."""
    value = str(text or "").strip()
    return (
        None if value.lower() in ("", "unknown", "none") or value.startswith("No data available") else value
    )
