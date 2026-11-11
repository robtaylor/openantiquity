"""Greater London Archaeological Priority Areas.

Work-list key `he-greater-london-apas`. The `Greater_London___Archaeological_Priority_Areas`
FeatureServer, layer 0: 981 polygons for 753 areas, tiered I to III by how likely the ground
is to hold remains. An area made of several parts has a polygon for each, with the same
`resourcein` and `primary_re`, so the external id is a hash of those two and the geometry.
The layer gives no area name. A record is named after its tier and the HER reference. The
description is cut off at 254 characters by the layer, and carries HTML or non-breaking
spaces, which are stripped.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import HUB_HOMEPAGE, OGL_URL
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "Greater_London___Archaeological_Priority_Areas/FeatureServer/0"
)
FIELDS = ("OBJECTID", "designatio", "primary_re", "resourcein", "area_type", "descriptio")
logger = logging.getLogger(__name__)
_TAG = re.compile(r"<[^>]*>")


@register
class GreaterLondonApas(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-greater-london-apas",
        name="Greater London Archaeological Priority Areas",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url=OGL_URL,
        attribution=(
            "© Historic England 2026. Contains Ordnance Survey data © Crown copyright and "
            "database right 2026."
        ),
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage=HUB_HOMEPAGE,
        coverage="Greater London",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, out_sr=27700, geometry_precision=1)
        layer.require(FIELDS, geometry_type="esriGeometryPolygon")
        keys = FeatureKeys()
        collapsed = 0
        for feature in layer.features(bbox=bbox):
            if feature.geometry is None:
                # One part, OBJECTID 10690, is a triangle a few millimetres across, which has no shape
                # left at a tenth of a metre. It is a drawing slip, and is left out.
                collapsed += 1
                continue
            yield to_record(feature, keys)
        if collapsed:
            logger.info("%s: %d parts were too small to keep their shape", self.source.key, collapsed)


def plain_text(text: object) -> str:
    """HTML or text with non-breaking spaces as one line of plain text."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One part of an archaeological priority area as a record."""
    properties = feature.properties
    assert feature.geometry is not None, "the caller skips features with no shape"
    tier = str(properties["designatio"] or "").strip()
    reference = str(properties["primary_re"] or "").strip()
    name = tier or "Archaeological Priority Area"
    return RecordIn(
        external_id=keys.key(
            [str(properties["resourcein"] or ""), reference], feature.geometry, native=feature.native
        ),
        name=f"{name} (HER reference {reference})" if reference else name,
        geom=feature.geometry,
        summary=plain_text(properties["descriptio"]) or None,
        record_type=name,
        raw=json_ready(properties, drop_empty=True),
    )
