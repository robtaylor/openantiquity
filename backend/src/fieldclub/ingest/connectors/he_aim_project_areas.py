"""Historic England's Aerial Investigation and Mapping project areas.

Work-list key `he-aim-project-areas`. About 160 polygons, `HE_AIM_data` FeatureServer
layer 2, each the area one mapping project covered. They show where the other two
layers have anything to say: outside them the ground is unmapped, not empty. Several
polygons can belong to one project, and the layer has no identifier, so the external
id is a hash of `PROJECT_NA`, `TYPE`, `layer` and the geometry on the British National Grid.

Each is category `monument` because the records table has no category for coverage, but its
record type is in `vocab.COVERAGE_RECORD_TYPES`, so `services.records.nearby` and the
"is this already recorded?" suggestions leave it out. A coverage overlay would be its own
change and decision.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer, esri_date
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import HUB_HOMEPAGE, OGL_URL
from fieldclub.ingest.registry import register
from fieldclub.vocab import MAPPING_PROJECT_AREA, RecordCategory, SourceAccess, SourceReuse

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer/2"
)
FIELDS = ("OBJECTID", "layer", "TYPE", "PROJECT_NA", "Status", "Sources", "RRS_No", "RRS_URL", "Completed")


@register
class ProjectAreas(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-aim-project-areas",
        name="Aerial Investigation and Mapping: project areas",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url=OGL_URL,
        attribution="© Historic England [year]",
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage=HUB_HOMEPAGE,
        coverage="England, where the mapping projects have been done",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, out_sr=27700, geometry_precision=1)
        layer.require(FIELDS, geometry_type="esriGeometryPolygon")
        keys = FeatureKeys()
        for feature in layer.features(bbox=bbox):
            yield to_record(feature, keys)


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One project area as a record."""
    properties = feature.properties
    if feature.geometry is None:
        raise UpstreamFormatError(f"AIM project area {feature.id} has no geometry.")
    name = str(properties["PROJECT_NA"] or "").strip()
    if not name:
        raise UpstreamFormatError(f"AIM project area {feature.id} has no project name.")
    kind = str(properties["TYPE"] or "").strip()
    sources = [part.strip() for part in str(properties["Sources"] or "").split("\\") if part.strip()]
    summary = " ".join(
        sentence
        for sentence in (
            f"Mapped from {', '.join(sources)}." if sources else "",
            f"Status: {str(properties['Status']).strip().lower()}." if properties["Status"] else "",
        )
        if sentence
    )
    completed = esri_date(properties["Completed"])
    raw = json_ready({**properties, "Completed": completed}, drop_empty=True)
    report_url = str(properties["RRS_URL"] or "").strip()
    return RecordIn(
        external_id=keys.key(
            [name, kind, str(properties["layer"] or "")], feature.geometry, native=feature.native
        ),
        name=name,
        geom=feature.geometry,
        summary=summary or None,
        record_type=MAPPING_PROJECT_AREA,
        url=report_url if report_url.startswith("https://") else None,
        source_updated_at=completed,
        raw=raw,
    )
