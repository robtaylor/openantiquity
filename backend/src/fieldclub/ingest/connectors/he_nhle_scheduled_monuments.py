"""Historic England's scheduled monuments, from the Open Data Hub GeoPackage export.

Work-list key `he-nhle-scheduled-monuments`. The export is NHLE layer 6, about
20,000 polygons in EPSG:27700, 45 MB, refreshed daily. It is fetched at most
once every 20 hours and kept under `var/ingest/`. There is no description text
in it, only the list entry number, so each record links to its list entry page.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import ClassVar

from fieldclub.ingest.adapters import Polite, UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature, json_ready
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_vector, vector_info
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

HUB_EXPORT = (
    "https://opendata-historicengland.hub.arcgis.com/api/download/v1/items/"
    "767f279327a24845bf47dfe5eae9862b/geoPackage?layers=6"
)
LIST_ENTRY_URL = "https://historicengland.org.uk/listing/the-list/list-entry/{ListEntry}"
FIELDS = ("ListEntry", "Name", "SchedDate", "AmendDate", "CaptureScale", "NGR", "area_ha")


@register
class ScheduledMonuments(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-nhle-scheduled-monuments",
        name="Scheduled monuments",
        publisher="Historic England",
        licence="Open Government Licence v3.0, via the Historic England Open Data Hub terms",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution=(
            "© Historic England 2026. "
            "Contains Ordnance Survey data © Crown copyright and database right 2026."
        ),
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="England",
    )
    # The export is rebuilt daily, so a copy younger than this is current.
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        path = cache_dir(self.settings, self.source.key) / "scheduled-monuments.gpkg"
        download(HUB_EXPORT, path, client=self.http, polite=Polite(), max_age=self.max_age)
        info = vector_info(path)
        missing = [name for name in FIELDS if name not in list(info["fields"])]
        if missing or info.get("crs") != "EPSG:27700":
            raise UpstreamFormatError(
                f"The scheduled monuments export changed shape: crs {info.get('crs')}, missing {missing}."
            )
        for feature in read_vector(path, bbox=bbox):
            yield to_record(feature)


def to_record(feature: Feature) -> RecordIn:
    """One row of the export as a record."""
    properties = feature.properties
    entry = properties["ListEntry"]
    if not isinstance(entry, int) or entry <= 0:
        raise UpstreamFormatError(f"A scheduled monument has list entry {entry!r}.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"Scheduled monument {entry} has no geometry.")
    dates = [
        value for value in (properties["SchedDate"], properties["AmendDate"]) if isinstance(value, datetime)
    ]
    return RecordIn(
        external_id=str(entry),
        name=str(properties["Name"] or "").strip(),
        geom=feature.geometry,
        record_type="Scheduled monument",
        url=LIST_ENTRY_URL.format(ListEntry=entry),
        source_updated_at=max(dates) if dates else None,
        raw=json_ready(properties),
    )
