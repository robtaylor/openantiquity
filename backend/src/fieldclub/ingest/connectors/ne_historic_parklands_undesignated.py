"""England's Historic Parklands (undesignated), from Natural England's ArcGIS Online layer.

Work-list key `ne-historic-parklands-undesignated`. About 4,500 polygons mapped from
the Ordnance Survey's second edition and Hills Edition historic maps, for parks and
gardens that are not on Historic England's register. Each polygon is one part of a
park, so a park in two pieces is two features, told apart by `Part_N`.

A record is a park, not a part (see "A record is a thing" in ARCHITECTURE.md), so
`fetch()` joins the parts of a park into one MultiPolygon, as the York connector does.
The parts of one park share a name and a Historic Environment Record (HER). Two
things keep parts of the same name and HER apart as separate parks: a gap of more
than `MAX_GAP_M` between their outlines (in the recorded data the parts of one park
lie within about a kilometre of each other, and same-named parks in one HER can be
tens of kilometres apart), and a comment on any of them saying the parks are distinct.

The layer has no identifier. The external id is a hash of the park's name, the
lowest part number of its parts and the HER's name. Two parks of one name and HER
that both start at part 1 get a `#2`, `#3` after the part number, in order of position.
`GlobalID` would be shorter, but the publisher doesn't say it survives a rebuild of
the layer. A partial run by area finds the parks with a part in the box, then reads
every part of them, so it never stores a park cut short at the box's edge.

The layer also holds the initials of the contractor who drew each polygon and the
editor's. They say nothing about the park and are not kept. Its `Comment` field holds
mapping notes ("Captured from OS Hills Edition historic map"), not a description of
the park, so it stays in `raw` and the record has no summary.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import numpy as np
import shapely
from shapely import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from fieldclub.gridref import transformer
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
# Parts of one name and HER further apart than this, in metres, are different parks.
MAX_GAP_M = 2000.0
# A comment such as "Two distinct parklands with the name 'The Grove' present within Suffolk HER."
# The layer has spelled it "disctinct" once, so the pattern takes any word between dis and nct.
DISTINCT = re.compile(r"\bdis\w*nct\b", re.IGNORECASE)
# How many names one query for their parts lists.
NAME_CHUNK = 50
# Left out of the joined record: ids that belong to one part, and the part number, which `Parts` replaces.
PART_FIELDS = ("OBJECTID", "GlobalID", "Part_N")


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
        groups: dict[tuple[str, str], list[Feature]] = {}
        for feature in layer.features(bbox=bbox):
            groups.setdefault(group_key(feature), []).append(feature)
        if bbox is not None:
            # Read every part of the parks found in the box, so none is cut short at its edge.
            found = set(groups)
            names = sorted({text_of(part.properties, "Name") for parts in groups.values() for part in parts})
            groups = {}
            for start in range(0, len(names), NAME_CHUNK):
                chunk = ",".join(
                    "'{}'".format(name.replace("'", "''")) for name in names[start : start + NAME_CHUNK]
                )
                layer.where = f"Name IN ({chunk})"
                for feature in layer.features():
                    if (key := group_key(feature)) in found:
                        groups.setdefault(key, []).append(feature)
        for parts in groups.values():
            yield from to_records(parts)


def group_key(feature: Feature) -> tuple[str, str]:
    """What the parts of one park share: its name and the HER that supplied it, ignoring case and spacing."""
    properties = feature.properties
    name = " ".join(text_of(properties, "Name").lower().split())
    if not name:
        raise UpstreamFormatError("A parkland has no name.")
    return name, " ".join(text_of(properties, "HER_Name").lower().split())


def external_id(name: str, part: str, her: str) -> str:
    """The id of a park: a hash of what names it, which the publisher doesn't change."""
    key = "|".join(" ".join(value.split()).lower() for value in (name, part, her))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _date(value: Any) -> datetime | None:
    """A date field, which ArcGIS gives as milliseconds since 1970."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value / 1000, UTC)


def _part_order(part: Feature) -> tuple[int, str]:
    """Part numbers in the order a person would give them: 1, 1B, 2, 10."""
    number = text_of(part.properties, "Part_N")
    digits = re.match(r"\d+", number)
    return (int(digits.group()) if digits else 0, number)


def _geometry(part: Feature) -> BaseGeometry:
    assert part.geometry is not None, "a part without geometry was refused when it was read"
    return part.geometry


def _position(part: Feature) -> tuple[float, float]:
    centroid = _geometry(part).centroid
    return centroid.x, centroid.y


def _clusters(parts: list[Feature]) -> list[list[Feature]]:
    """The parts of one name and HER, grouped into parks.

    A comment saying the parks are distinct makes every part its own park. Otherwise parts
    whose outlines lie within `MAX_GAP_M` of each other, directly or through other parts, are one.
    """
    if any(DISTINCT.search(text_of(part.properties, "Comment")) for part in parts):
        return [[part] for part in parts]
    to_grid = transformer(4326, 27700)
    shapes = [
        shapely.transform(_geometry(part), lambda xy: np.column_stack(to_grid.transform(xy[:, 0], xy[:, 1])))
        for part in parts
    ]
    owner = list(range(len(parts)))

    def root(index: int) -> int:
        while owner[index] != index:
            owner[index] = owner[owner[index]]
            index = owner[index]
        return index

    for first in range(len(parts)):
        for second in range(first + 1, len(parts)):
            if shapely.distance(shapes[first], shapes[second]) <= MAX_GAP_M:
                owner[root(second)] = root(first)
    clusters: dict[int, list[Feature]] = {}
    for index, part in enumerate(parts):
        clusters.setdefault(root(index), []).append(part)
    return list(clusters.values())


def _outline(parts: list[Feature]) -> BaseGeometry:
    """The parts' polygons as one geometry: the polygon itself for one part, else a MultiPolygon."""
    polygons: list[Polygon] = []
    for part in parts:
        geometry = part.geometry
        if isinstance(geometry, Polygon):
            polygons.append(geometry)
        elif isinstance(geometry, MultiPolygon):
            polygons.extend(geometry.geoms)
        else:
            raise UpstreamFormatError(f"Parkland {text_of(part.properties, 'Name')} has no polygon.")
    return polygons[0] if len(polygons) == 1 and len(parts) == 1 else MultiPolygon(polygons)


def to_records(parts: list[Feature]) -> Iterator[RecordIn]:
    """The parks that one name and HER's parts make, as records."""
    for part in parts:
        if part.geometry is None:
            raise UpstreamFormatError(f"Parkland {text_of(part.properties, 'Name')} has no geometry.")
    ordered = [sorted(cluster, key=_part_order) for cluster in _clusters(parts)]
    # Parks that both start at the same part number are told apart by where they are.
    ordered.sort(key=lambda cluster: (_part_order(cluster[0]), _position(cluster[0])))
    started: dict[str, int] = {}
    for cluster in ordered:
        first = text_of(cluster[0].properties, "Part_N")
        started[first] = started.get(first, 0) + 1
        suffix = f"#{started[first]}" if started[first] > 1 else ""
        yield to_record(cluster, first + suffix)


def to_record(parts: list[Feature], part_number: str) -> RecordIn:
    """One park, from all of its parts, as a record. `part_number` is what makes its id."""
    properties = parts[0].properties
    name = text_of(properties, "Name")
    dates = [
        date
        for part in parts
        for date in (_date(part.properties["C_Date"]), _date(part.properties["E_Date"]))
        if date
    ]
    comments = list(dict.fromkeys(c for part in parts if (c := text_of(part.properties, "Comment"))))
    raw = {
        key: value
        for key, value in json_ready(properties).items()
        if key not in NOT_KEPT and key not in PART_FIELDS
    }
    areas = [part.properties["Area_m2"] for part in parts]
    raw["Area_m2"] = (
        sum(areas) if all(isinstance(area, int | float) for area in areas) else raw.get("Area_m2")
    )
    raw["Comment"] = " ".join(comments)
    if not raw["Comment"]:
        del raw["Comment"]
    raw["Parts"] = [text_of(part.properties, "Part_N") for part in parts]
    return RecordIn(
        external_id=external_id(name, part_number, text_of(properties, "HER_Name")),
        name=name,
        geom=_outline(parts),
        record_type=RECORD_TYPE,
        source_updated_at=max(dates) if dates else None,
        raw=raw,
    )
