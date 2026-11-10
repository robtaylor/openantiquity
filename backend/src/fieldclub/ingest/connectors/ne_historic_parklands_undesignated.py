"""England's Historic Parklands (undesignated), from Natural England's ArcGIS Online layer.

Work-list key `ne-historic-parklands-undesignated`. About 4,500 polygons mapped from
the Ordnance Survey's second edition and Hills Edition historic maps, for parks and
gardens that are not on Historic England's register. Each polygon is one part of a
park, so a park in two pieces is two features, told apart by `Part_N`.

The layer has no identifier. The external id is a hash of the park's name, the part
number and the name of the Historic Environment Record that supplied it. The three
together are unique in the data, and `fetch()` raises when they stop being so.
`GlobalID` would be shorter, but the publisher doesn't say it survives a rebuild of
the layer.

The layer also holds the initials of the contractor who drew each polygon and the
editor's. They say nothing about the park and are not kept.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, Polite, json_ready, text_of
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER = (
    "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/"
    "Englands_Historic_Parklands_Undesignated/FeatureServer/0"
)
FIELDS = ("Name", "Part_N", "Comment", "HER_Name", "HE_Region", "Area_m2", "C_Date", "E_Date")
# Left out of the record: who drew it and who edited it.
NOT_KEPT = ("Creator", "Editor")
RECORD_TYPE = "Historic parkland (undesignated)"


@register
class UndesignatedParklands(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="ne-historic-parklands-undesignated",
        name="England's Historic Parklands (undesignated)",
        publisher="Natural England",
        licence="Open Government Licence v3.0 ('Use of this data is subject to the Open Government Licence')",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution=(
            "© Natural England 2025, Contains historical maps provided by the National Library of "
            "Scotland, © Historic England 2025 Contains Ordnance Survey data © Crown copyright "
            "and database right 2025"
        ),
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://www.gov.uk/government/organisations/natural-england",
        coverage="England",
    )

    # Tests give it one that doesn't wait. A real run leaves a second between requests.
    polite: Polite | None = None

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER, client=self.http, polite=self.polite)
        layer.require(FIELDS, geometry_type="esriGeometryPolygon")
        seen: dict[str, str] = {}
        for feature in layer.features(bbox=bbox):
            record = to_record(feature)
            if record.external_id in seen:
                raise UpstreamFormatError(f"Two parklands share the name, part and HER of {record.name!r}.")
            seen[record.external_id] = record.name
            yield record


def external_id(name: str, part: str, her: str) -> str:
    """The id of one part of a park: a hash of what names it, which the publisher doesn't change."""
    key = "|".join(" ".join(value.split()).lower() for value in (name, part, her))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _date(value: Any) -> datetime | None:
    """A date field, which ArcGIS gives as milliseconds since 1970."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value / 1000, UTC)


def to_record(feature: Feature) -> RecordIn:
    """One part of one park as a record."""
    properties = feature.properties
    name = text_of(properties, "Name")
    if not name:
        raise UpstreamFormatError("A parkland has no name.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"Parkland {name} has no geometry.")
    dates = [date for date in (_date(properties["C_Date"]), _date(properties["E_Date"])) if date]
    part = text_of(properties, "Part_N")
    return RecordIn(
        external_id=external_id(name, part, text_of(properties, "HER_Name")),
        name=name,
        geom=feature.geometry,
        record_type=RECORD_TYPE,
        summary=text_of(properties, "Comment") or None,
        source_updated_at=max(dates) if dates else None,
        raw={key: value for key, value in json_ready(properties).items() if key not in NOT_KEPT},
    )
