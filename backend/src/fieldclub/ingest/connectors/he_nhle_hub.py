"""What the National Heritage List layers share: one export address pattern, one reader.

Historic England publishes the NHLE as one Open Data Hub item with a layer per
kind of designation. Each layer is a GeoPackage export, rebuilt daily, in
EPSG:27700, and each source in the work-list is one layer. The layers carry no
description text, only a list entry number, so each record links to its list
entry page. This module holds the part every layer has in common: the address,
the licence and attribution, the currency statement, and `NhleLayer`, which
checks the shape of the export, reads it and turns each row into a record.
A connector for one layer subclasses `NhleLayer` and says what is particular
to it. This module registers no connector of its own.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature, json_ready
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_vector, vector_info
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

NHLE_ITEM = "767f279327a24845bf47dfe5eae9862b"
HUB_HOMEPAGE = "https://opendata-historicengland.hub.arcgis.com/"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
NHLE_LICENCE = "Open Government Licence v3.0, via Historic England Open Data Hub Terms and Conditions"
NHLE_ATTRIBUTION = (
    "© Historic England [year]. Contains Ordnance Survey data © Crown copyright and database right [year]."
)
LIST_ENTRY_URL = "https://historicengland.org.uk/listing/the-list/list-entry/{ListEntry}"
# Historic England recommends this statement with its data. The work-list keeps it among the gotchas.
CURRENCY_STATEMENT = (
    "The Historic England Data contained in this material was obtained on [date]. "
    "The most publicly available up to date Historic England Data can be obtained from "
    "HistoricEngland.org.uk."
)
_SLUG = re.compile(r"[^a-z0-9]+")


def hub_export_url(item: str, layer: int) -> str:
    """The Hub's download address for one layer of an item. Its redirect targets are short-lived."""
    return f"{HUB_HOMEPAGE}api/download/v1/items/{item}/geoPackage?layers={layer}"


def nhle_source(key: str, name: str, *, enabled: bool = True) -> SourceInfo:
    """The `sources` row for an NHLE layer, with the licence and attribution the work-list gives them.

    The currency statement is Historic England's own recommendation for its
    data, kept among each entry's gotchas. The runner fills in `[year]` and
    `[date]`.
    """
    return SourceInfo(
        key=key,
        name=name,
        publisher="Historic England",
        licence=NHLE_LICENCE,
        licence_url=OGL_URL,
        attribution=f"{NHLE_ATTRIBUTION} {CURRENCY_STATEMENT}",
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage=HUB_HOMEPAGE,
        coverage="England",
        enabled=enabled,
    )


def slug(text: str) -> str:
    """Lower-case words joined by hyphens, for the part of an id that says which piece of a designation."""
    return _SLUG.sub("-", text.lower()).strip("-")


class NhleLayer(Connector):
    """One layer of an Open Data Hub GeoPackage export, one record per row.

    A subclass sets `source`, `export_url`, `file_name`, `geometry_kinds` and
    `record_type`, and overrides `summary`, `external_id` or `where` where its
    layer needs them. The row's own text and dates all stay in `raw`.
    """

    export_url: ClassVar[str]
    # The file under `var/ingest/<key>/`, without its `.gpkg`.
    file_name: ClassVar[str]
    # The OGR geometry types the layer may hold, as `vector_info` names them.
    geometry_kinds: ClassVar[tuple[str, ...]]
    record_type: ClassVar[str]
    id_field: ClassVar[str] = "ListEntry"
    name_field: ClassVar[str] = "Name"
    # The dates that say when the entry last changed. The latest is `source_updated_at`.
    date_fields: ClassVar[tuple[str, ...]] = ("AmendDate",)
    # Fields the subclass reads beyond the ones above, so a renamed column stops the run.
    extra_fields: ClassVar[tuple[str, ...]] = ()
    # An OGR SQL filter, for a layer where only some rows are wanted.
    where: ClassVar[str | None] = None
    # The export is rebuilt daily, so a copy younger than this is current.
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    @property
    def required_fields(self) -> tuple[str, ...]:
        return (self.id_field, self.name_field, *self.date_fields, *self.extra_fields)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        path = cache_dir(self.settings, self.source.key) / f"{self.file_name}.gpkg"
        fetched = download(self.export_url, path, client=self.http, max_age=self.max_age)
        self.obtained_at = fetched.fetched_at  # dates the attribution
        info = vector_info(path)
        fields = {str(name) for name in info["fields"]}
        missing = [name for name in self.required_fields if name not in fields]
        if missing or info.get("crs") != "EPSG:27700" or info.get("geometry_type") not in self.geometry_kinds:
            raise UpstreamFormatError(
                f"The {self.source.name} export changed shape: crs {info.get('crs')}, "
                f"geometry {info.get('geometry_type')}, missing {missing}."
            )
        self.prepare(path, info)
        seen: set[str] = set()
        for feature in read_vector(path, where=self.where, bbox=bbox, info=info):
            record = self.to_record(feature)
            if record.external_id in seen:
                raise UpstreamFormatError(
                    f"The {self.source.name} export has two rows with the id {record.external_id}."
                )
            seen.add(record.external_id)
            yield record

    def prepare(self, path: Path, info: dict[str, Any]) -> None:
        """Run before the rows are read, for a layer that needs the whole file to name a row."""

    def to_record(self, feature: Feature) -> RecordIn:
        properties = feature.properties
        external_id = self.external_id(properties)
        if feature.geometry is None:
            raise UpstreamFormatError(f"{self.source.name} row {external_id} has no geometry.")
        name = str(properties[self.name_field] or "").strip()
        return RecordIn(
            external_id=external_id,
            name=name or f"{self.record_type} {external_id}",
            geom=feature.geometry,
            record_type=self.record_type,
            summary=self.summary(properties),
            url=self.url(properties),
            source_updated_at=self.updated(properties),
            raw=json_ready(properties),
        )

    def external_id(self, properties: dict[str, Any]) -> str:
        """The list entry number. A layer that holds one entry in several pieces adds the piece."""
        entry = properties[self.id_field]
        if not isinstance(entry, int) or entry <= 0:
            raise UpstreamFormatError(f"A row of {self.source.name} has list entry {entry!r}.")
        return str(entry)

    def summary(self, properties: dict[str, Any]) -> str | None:
        return None

    def url(self, properties: dict[str, Any]) -> str | None:
        return LIST_ENTRY_URL.format(ListEntry=properties[self.id_field])

    def updated(self, properties: dict[str, Any]) -> datetime | None:
        dates = [properties[name] for name in self.date_fields if isinstance(properties[name], datetime)]
        return max(dates) if dates else None
