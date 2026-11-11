"""Historic England's Aerial Investigation and Mapping, monument extents layer.

Work-list key `he-aim-monument-extents`. One polygon for each whole monument the
interpreters mapped, drawn round the detailed features of the first layer: about
197,000 of them, from `HE_AIM_data` FeatureServer layer 1. Coverage is the mapped
project areas only. The work-list lists `MONUMENT_TYPE` and `PERIOD` for this
layer, but it has neither (see the layer's fields), so a record here has no type
or period of its own. `HE_UID` links an extent to the detailed features of the
same monument, and to Historic England's research record.

As in the detailed layer, `HE_UID` is shared and often ` NONE GIVEN` (see
`he_aim_detailed_mapping`), so the external id is a hash of `layer`, `project`,
`HE_UID` and the geometry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_aim_detailed_mapping import EMPTY, GEOMETRY_PRECISION
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer/1"
)
FIELDS = ("OBJECTID", "layer", "project", "HE_UID", "HER_No")


@register
class MonumentExtents(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-aim-monument-extents",
        name="Aerial Investigation and Mapping: monument extents",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution="© Historic England [year]",
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="England, where the mapping projects have been done",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, geometry_precision=GEOMETRY_PRECISION)
        layer.require_shape(FIELDS, "esriGeometryPolygon")
        keys = FeatureKeys()
        collapsed = 0
        for feature in layer.features(bbox=bbox):
            if feature.geometry is None:
                collapsed += 1  # a sliver too small to keep its shape at six decimal places
                continue
            yield to_record(feature, keys)
        if collapsed:
            logger.info("%s: %d extents were too small to keep their shape", self.source.key, collapsed)
        if keys.repeats:
            logger.info(
                "%s: %d extents repeat another's project, monument and outline", self.source.key, keys.repeats
            )


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One monument extent as a record."""
    properties = feature.properties
    assert feature.geometry is not None, "the caller skips features with no shape"
    layer = str(properties["layer"] or "").strip()
    project = str(properties["project"] or "").strip()
    uid = str(properties["HE_UID"] or "").strip()
    named = uid.upper() not in EMPTY
    return RecordIn(
        external_id=keys.key([layer, project, uid], feature.geometry),
        name=f"Monument extent (Historic England record {uid})" if named else "Monument extent",
        geom=feature.geometry,
        summary=f"Project: {project}." if project else None,
        record_type="Monument extent",
        raw=json_ready(properties, drop_empty=True),
    )
