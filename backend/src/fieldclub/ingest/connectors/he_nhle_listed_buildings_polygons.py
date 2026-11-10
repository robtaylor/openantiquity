"""Listed buildings as outlines, from NHLE layer 3 of the Open Data Hub export.

Work-list key `he-nhle-listed-buildings-polygons`. The layer has a row for
every listed building, but only 10,080 of the 379,685 hold a real outline. The
rest are placeholder triangles about 2.5 m across with `area_ha` empty, so this
connector reads only the rows where `area_ha` is set.

The same list entries are in the points layer, which holds every one of them.
The source is therefore registered disabled: its records are stored when it is
run, and hidden from search, lists and tiles, so no listed building is found
twice. Enable it, and filter the points layer, if outlines are wanted.
"""

from __future__ import annotations

from typing import ClassVar

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, hub_export_url, nhle_source
from fieldclub.ingest.connectors.he_nhle_listed_buildings_points import ListedBuildingPoints
from fieldclub.ingest.registry import register


@register
class ListedBuildingPolygons(ListedBuildingPoints):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-listed-buildings-polygons", "NHLE: Listed buildings (polygons)", enabled=False
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 3)
    file_name: ClassVar[str] = "listed-buildings-polygons"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPolygon", "Polygon")
    extra_fields: ClassVar[tuple[str, ...]] = ("Grade", "area_ha")
    where: ClassVar[str | None] = "area_ha IS NOT NULL"
