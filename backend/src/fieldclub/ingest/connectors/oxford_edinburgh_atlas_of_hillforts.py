"""The Atlas of Hillforts of Britain and Ireland, from its ArcGIS Online feature layer.

Work-list key `oxford-edinburgh-atlas-of-hillforts`. The layer holds about 4,100
hillforts as points, with 253 fields each, and is a snapshot of the research
database as it stood in October 2016. It is hosted on a university ArcGIS Online
account, so a run keeps nothing but the records: the work-list notes that the
account has moved once.

The external id is the Atlas number, the project's own identifier for a
hillfort, not the layer's object id. The licence is share-alike (CC BY-SA 4.0).
The `sources` row carries it and the work-list's attribution, and the runner
keeps both with every record.

Hillfort types and dating evidence are columns of "Yes" and "No", one per type
and one per span of years. They become `monument_types` and `periods`. The
spans are wider than the periods in `vocab.Period` and do not line up with
them, so a span that straddles two periods gives both.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, Polite, json_ready, text_of
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

LAYER = (
    "https://services1.arcgis.com/PTDJItLzolyiewT6/arcgis/rest/services/Atlas_of_Hillforts/FeatureServer/0"
)

# The layer's own names are cut at 31 characters, which is why some end oddly.
HILLFORT_TYPES = {
    "Hillfort_Type__Contour_Fort": "Contour fort",
    "Hillfort_Type__Partial_Contour_": "Partial contour fort",
    "Hillfort_Type__Promontory_Fort": "Promontory fort",
    "Hillfort_Type__Hillslope_Fort": "Hillslope fort",
    "Hillfort_Type__Level_Terrain_Fo": "Level terrain fort",
    "Hillfort_Type__Marsh_Fort": "Marsh fort",
    "Hillfort_Type__Multiple_Enclosu": "Multiple enclosure fort",
}
# Each span of years in the dating evidence, and the periods it touches.
DATING_PERIODS = {
    "Dating_Evidence__Pre_1200BC": (Period.PREHISTORIC,),
    "Dating_Evidence__1200BC___800BC": (Period.BRONZE_AGE,),
    "Dating_Evidence__800BC___400BC": (Period.IRON_AGE,),
    "Dating_Evidence__400BC___AD50": (Period.IRON_AGE,),
    "Dating_Evidence__AD50___AD400": (Period.ROMAN,),
    "Dating_Evidence__AD400___AD800": (Period.EARLY_MEDIEVAL,),
    "Dating_Evidence__Post_AD800": (Period.EARLY_MEDIEVAL, Period.MEDIEVAL),
    "Dating_Evidence__Unknown": (Period.UNKNOWN,),
}
FIELDS = (
    "Atlas_Number",
    "Name",
    "Site_Name",
    "Display_Name",
    "Summary_Description",
    "Record_URL",
    *HILLFORT_TYPES,
    *DATING_PERIODS,
)


@register
class AtlasOfHillforts(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="oxford-edinburgh-atlas-of-hillforts",
        name="Atlas of Hillforts of Britain and Ireland",
        publisher="Universities of Oxford and Edinburgh (AHRC)",
        licence="CC BY-SA 4.0",
        licence_url=None,
        attribution=(
            "Lock, Gary and Ralston, Ian. 2024. Atlas of Hillforts of Britain and Ireland. "
            "Available at: https://hillforts.arch.ox.ac.uk"
        ),
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.SHARE_ALIKE,
        homepage="https://hillforts.arch.ox.ac.uk",
        coverage="Britain and Ireland",
    )

    # Tests give it one that doesn't wait. A real run leaves a second between requests.
    polite: Polite | None = None

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER, client=self.http, polite=self.polite)
        layer.require(FIELDS, geometry_type="esriGeometryPoint")
        seen: set[str] = set()
        for feature in layer.features(bbox=bbox):
            record = to_record(feature)
            if record.external_id in seen:
                raise UpstreamFormatError(f"Atlas number {record.external_id} is used by two hillforts.")
            seen.add(record.external_id)
            yield record


def _yes(properties: dict[str, Any], field: str) -> bool:
    return str(properties.get(field) or "").strip().lower() == "yes"


def to_record(feature: Feature) -> RecordIn:
    """One hillfort of the layer as a record."""
    properties = feature.properties
    number = properties["Atlas_Number"]
    if not isinstance(number, int) or number <= 0:
        raise UpstreamFormatError(f"A hillfort has Atlas number {number!r}.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"Hillfort {number} has no position.")
    name = (
        text_of(properties, "Name") or text_of(properties, "Display_Name") or text_of(properties, "Site_Name")
    )
    periods = dict.fromkeys(
        period for field, spans in DATING_PERIODS.items() if _yes(properties, field) for period in spans
    )
    return RecordIn(
        external_id=str(number),
        name=name,
        geom=feature.geometry,
        record_type="Hillfort",
        monument_types=[label for field, label in HILLFORT_TYPES.items() if _yes(properties, field)],
        periods=list(periods),
        summary=text_of(properties, "Summary_Description") or None,
        url=text_of(properties, "Record_URL") or None,
        # 253 columns, most of them empty for most hillforts. Blanks say nothing, so they are not kept.
        raw={
            key: value
            for key, value in json_ready(properties).items()
            if value is not None and (not isinstance(value, str) or value.strip())
        },
    )
