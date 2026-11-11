"""Historic England's scheduled monuments, from the Open Data Hub GeoPackage export.

Work-list key `he-nhle-scheduled-monuments`. The export is NHLE layer 6, about
20,000 polygons in EPSG:27700, 45 MB, refreshed daily. It is read through
`he_nhle_hub.NhleLayer`, as every other National Heritage List layer is: fetched
at most once every 20 hours, kept under `var/ingest/`, its shape checked, and
each row a record. There is no description text in it, only the list entry
number, so each record links to its list entry page. A row's date is the later
of when it was scheduled and when it was last amended.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import (
    CURRENCY_STATEMENT,
    LIST_ENTRY_URL,
    NHLE_ITEM,
    NhleLayer,
    hub_export_url,
    nhle_source,
)
from fieldclub.ingest.registry import register

HUB_EXPORT = hub_export_url(NHLE_ITEM, 6)

__all__ = ["CURRENCY_STATEMENT", "HUB_EXPORT", "LIST_ENTRY_URL", "ScheduledMonuments"]


@register
class ScheduledMonuments(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source("he-nhle-scheduled-monuments", "Scheduled monuments")
    export_url: ClassVar[str] = HUB_EXPORT
    file_name: ClassVar[str] = "scheduled-monuments"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    record_type: ClassVar[str] = "Scheduled monument"
    date_fields: ClassVar[tuple[str, ...]] = ("SchedDate", "AmendDate")
    # Read by nothing here, but kept in `raw`: a renamed column means the export changed.
    extra_fields: ClassVar[tuple[str, ...]] = ("CaptureScale", "NGR", "area_ha")
