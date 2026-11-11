"""Turning the Plough 2: how much ridge and furrow survives in parts of the Midlands.

Work-list key `he-turning-the-plough-2`. The `Turning_the_Plough_2_` FeatureServer, layer 0
(the name ends in an underscore): about 2,000 polygons surveyed in sample parishes, each with
its survival, condition, vulnerability and the surveyor's confidence. The layer gives no
period, so none is set. `FeatureID` is a number within a survey sheet, such as `17:56`, and
two of them occur twice, so the external id is a hash of `FeatureID`, `Parish` and the geometry.
Text fields have leading spaces, which are stripped in the record and kept in `raw`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER_URL = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/Turning_the_Plough_2_/FeatureServer/0"
FIELDS = (
    "OBJECTID",
    "FeatureID",
    "Parish",
    "RecordDate",
    "Survival",
    "Condition",
    "ConfidenceRating",
    "Vulnerability",
    "Comments",
)


@register
class TurningThePlough2(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-turning-the-plough-2",
        name="Turning the Plough 2",
        publisher="Historic England with Gloucestershire County Council",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution="© Gloucestershire County Council and Historic England",
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="Sample parishes in the Midlands",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, geometry_precision=6)
        layer.require_shape(FIELDS, "esriGeometryPolygon")
        keys = FeatureKeys()
        for feature in layer.features(bbox=bbox):
            yield to_record(feature, keys)


def record_date(text: object) -> datetime | None:
    """A survey date written `06-Jan-12`, or None when it is blank or written some other way."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip(), "%d-%b-%y").replace(tzinfo=UTC)
    except ValueError:
        return None


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One surveyed ridge and furrow polygon as a record."""
    properties = feature.properties
    if feature.geometry is None:
        raise UpstreamFormatError(f"Turning the Plough polygon {feature.id} has no geometry.")
    parish = str(properties["Parish"] or "").strip()
    judgements = [
        f"{label}: {value.lower()}."
        for label, field in (
            ("Survival", "Survival"),
            ("Condition", "Condition"),
            ("Vulnerability", "Vulnerability"),
            ("Confidence", "ConfidenceRating"),
        )
        if (value := str(properties[field] or "").strip())
    ]
    comment = str(properties["Comments"] or "").strip()
    return RecordIn(
        external_id=keys.key([str(properties["FeatureID"] or ""), parish], feature.geometry),
        name=f"Ridge and furrow, {parish}" if parish else "Ridge and furrow",
        geom=feature.geometry,
        summary=" ".join([*judgements, *([comment] if comment else [])]) or None,
        record_type="Ridge and furrow survey",
        monument_types=("RIDGE AND FURROW",),
        source_updated_at=record_date(properties["RecordDate"]),
        raw=json_ready(properties, drop_empty=True),
    )
