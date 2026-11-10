"""The City of York Historic Environment Record's monuments, from the council's map server.

Work-list key `york-her-monuments`. The record is published as three layers of one
map service, `LV_LeisureCulture`: points (layer 3, 3,555 features), lines (layer 4,
3,648) and areas (layer 5, 2,459). That is 9,662 features, the figure the work-list
expects, but the layers are not records. One monument often has several parts, a
point and an outline, or ten stretches of one road, and each part is a feature
carrying the same `MonUID`. In the data of 10 November 2026 the 9,662 features
belong to about 5,200 monuments.

So a record here is a monument, and its geometry is all its parts together: one
part as it is, several as a geometry collection. The external id is `MonUID`, the
HER's own number. The parts of a monument carry the same name and type, which
`fetch()` checks. A partial run by area finds the monuments in the box, then
reads every part of them, so it never stores a monument cut short at the box's edge.

The layers are read by ranges of object ids, not by offset. The area layer is a view of
every kind of shape in the record, and its offsets count rows it then hides: a page of
1,000 comes back with 64 features while more remain, so reading by offset stops at
2,064 of 2,459. Ranges of ids ask for each part by its own number.

The work-list names `FeatureDescr` as the summary. The map service doesn't serve
it, and the Hub download that does holds a description for two features in 3,507,
so there is no summary. The data is published under the Open Government Licence.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from shapely import GeometryCollection
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, Polite, text_of
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

SERVICE = "https://maps.york.gov.uk/arcgis/rest/services/Public/LV_LeisureCulture/MapServer"
# Layer number and the shape it should hold.
LAYERS = (
    (3, "esriGeometryPoint"),
    (4, "esriGeometryPolyline"),
    (5, "esriGeometryPolygon"),
)
FIELDS = ("MonUID", "RecordType", "Name", "MonType", "URL")
# The kinds of record the HER's own codes stand for. Other codes are kept as they are.
RECORD_TYPES = {"MON": "Monument", "BLD": "Building"}
# How many monuments one query for their parts names.
ID_CHUNK = 100
MONUMENT_ID = re.compile(r"[A-Za-z0-9_-]+")


@dataclass
class Monument:
    """All the parts of one `MonUID`, as the layers gave them."""

    properties: dict[str, Any]
    parts: list[BaseGeometry] = field(default_factory=list)


@register
class YorkHerMonuments(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="york-her-monuments",
        name="City of York HER monuments (points, lines, areas)",
        publisher="City of York Council",
        licence=(
            "OGL v3.0 ('The licensing for this dataset is listed as Derived data exemption - streamlined "
            "process... Open Government Licence (OGL v3.0)'); data.gov.uk licence OGL-UK-3.0"
        ),
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution=(
            "© Crown copyright and database rights 2016 Ordnance Survey 100020818; "
            "City of York Council, OGL v3.0"
        ),
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://her.york.gov.uk/",
        coverage="City of York",
    )

    # Tests give it one that doesn't wait. A real run leaves a second between requests.
    polite: Polite | None = None

    def _layers(self, polite: Polite) -> list[ArcGISLayer]:
        layers = [
            ArcGISLayer(f"{SERVICE}/{number}", client=self.http, polite=polite, by_object_id=True)
            for number, _ in LAYERS
        ]
        for layer, (_, shape) in zip(layers, LAYERS, strict=True):
            layer.require(FIELDS, geometry_type=shape)
        return layers

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        # One `Polite` for every layer, so the gap between requests holds from one layer to the next.
        polite = self.polite or Polite()
        monuments: dict[str, Monument] = {}
        # Built and checked once: each layer fetches its metadata the first time it is used.
        layers = self._layers(polite)
        if bbox is None:
            self._read(layers, None, monuments)
        else:
            # Find the monuments with a part in the box, then read all of every one of them.
            found: dict[str, Monument] = {}
            self._read(layers, bbox, found)
            names = sorted(found)
            for start in range(0, len(names), ID_CHUNK):
                where = "MonUID IN ({})".format(
                    ",".join(f"'{name}'" for name in names[start : start + ID_CHUNK])
                )
                for layer in layers:
                    layer.where = where
                self._read(layers, None, monuments)
        for monument_id, monument in monuments.items():
            yield to_record(monument_id, monument)

    @staticmethod
    def _read(layers: list[ArcGISLayer], bbox: BBox | None, into: dict[str, Monument]) -> None:
        for layer in layers:
            for feature in layer.features(bbox=bbox):
                add_part(into, feature)


def add_part(monuments: dict[str, Monument], feature: Feature) -> None:
    """File one feature under its `MonUID`, checking that it names the same monument as the others."""
    properties = feature.properties
    monument_id = text_of(properties, "MonUID")
    if not MONUMENT_ID.fullmatch(monument_id):
        raise UpstreamFormatError(f"A York monument has the id {properties['MonUID']!r}.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"York monument {monument_id} has a part with no geometry.")
    monument = monuments.setdefault(monument_id, Monument(properties))
    for name in ("Name", "MonType"):
        if properties[name] != monument.properties[name]:
            raise UpstreamFormatError(
                f"York monument {monument_id} has parts with different values of {name}: "
                f"{monument.properties[name]!r} and {properties[name]!r}."
            )
    monument.parts.append(feature.geometry)


def to_record(monument_id: str, monument: Monument) -> RecordIn:
    """One monument, with all its parts, as a record."""
    properties = monument.properties
    parts = monument.parts
    types = dict.fromkeys(term.strip() for term in text_of(properties, "MonType").split(";") if term.strip())
    code = text_of(properties, "RecordType")
    return RecordIn(
        external_id=monument_id,
        name=text_of(properties, "Name"),
        geom=parts[0] if len(parts) == 1 else GeometryCollection(parts),
        record_type=RECORD_TYPES.get(code, code) or None,
        monument_types=list(types),
        url=text_of(properties, "URL") or None,
        # The layer's own object id changes when the layer is rebuilt, so it is not kept.
        raw={name: properties[name] for name in FIELDS} | {"parts": len(parts)},
    )
