"""Sites removed from the National Heritage List for England since April 2011.

Work-list key `he-de-designated-sites`. The `Delisted` FeatureServer, layer 0: about 2,700
polygons, nearly all listed buildings, 161 scheduled monuments, two parks and gardens and
a wreck. The work-list says the layer has no identifier or name field, but it has
`ARTICLEUID`, which is unique in all 2,733 rows, and `ARTICLEVERSIONNAME`. Those are used.
The layer is of what is no longer designated, so every record's type says so. `DecisionText`
is the summary. The layer does not give a page to link to.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer, esri_date
from fieldclub.ingest.adapters.common import Feature, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER_URL = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/Delisted/FeatureServer/0"
FIELDS = (
    "OBJECTID",
    "ARTICLEUID",
    "ARTICLEVERSIONNAME",
    "HERITAGECATEGORYDESCRIPTION",
    "DateRemovedFromList",
    "DecisionText",
    "OriginalListEntryNumber",
)


@register
class DeDesignatedSites(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-de-designated-sites",
        name="Sites removed from the National Heritage List since April 2011",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution=(
            "© Crown Copyright 2026. Contains Ordnance Survey data © Crown copyright and database right 2026."
        ),
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="England",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, geometry_precision=6)
        layer.require_shape(FIELDS, "esriGeometryPolygon")
        seen: set[int] = set()
        for feature in layer.features(bbox=bbox):
            record = to_record(feature)
            uid = feature.properties["ARTICLEUID"]
            if uid in seen:
                raise UpstreamFormatError(f"Two removed sites have ARTICLEUID {uid}.")
            seen.add(uid)
            yield record


def to_record(feature: Feature) -> RecordIn:
    """One removed designation as a record."""
    properties = feature.properties
    uid = properties["ARTICLEUID"]
    if not isinstance(uid, int) or uid <= 0:
        raise UpstreamFormatError(f"A removed site has ARTICLEUID {uid!r}.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"Removed site {uid} has no geometry.")
    removed = esri_date(properties["DateRemovedFromList"])
    category = str(properties["HERITAGECATEGORYDESCRIPTION"] or "").strip().lower()
    return RecordIn(
        external_id=str(uid),
        name=str(properties["ARTICLEVERSIONNAME"] or "").strip() or f"Removed site {uid}",
        geom=feature.geometry,
        summary=str(properties["DecisionText"] or "").strip() or None,
        record_type=f"Removed from the list ({category})" if category else "Removed from the list",
        source_updated_at=removed,
        raw=json_ready({**properties, "DateRemovedFromList": removed}),
    )
