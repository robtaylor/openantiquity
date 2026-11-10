"""DOIs that the Archaeology Data Service registered with DataCite, for the ones with a position.

Work-list key `datacite-ads-dois`. DataCite's REST API holds about 147,000
DOIs for client `bl.ads`, most of them grey-literature reports. Only those
with a point or a small box in `geoLocations` can be put on a map, about
14,600, and the query asks for just those, so the records table doesn't fill
with documents it can't place. A DOI is the record's own identifier and never
changes. The abstract is the summary. The report's licence is in
`raw["rightsList"]`: it is the true per-report licence, and the ADS catalogue's
blanket label is wrong for some.

Older records have latitude and longitude the wrong way round, as strings:
`pointLatitude: "1.35"` and `pointLongitude: "52.22"` for Framlingham. A
position is taken as written when that falls in Britain and Ireland, and the
other way round when only that does, which can't be mistaken because the two
ranges don't overlap. `raw["axes_swapped"]` says when it happened. A box wider
or taller than `MAX_BOX_DEGREES` is a region, not a site, and is left out, as is
any position outside Britain and Ireland.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar

from shapely.geometry import MultiPoint, Point, box
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters.common import Polite, UpstreamFormatError
from fieldclub.ingest.adapters.rest import RestJson, dig
from fieldclub.ingest.base import BRITISH_ISLES, BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

DOIS_URL = "https://api.datacite.org/dois"
HAS_POSITION = (
    "_exists_:geoLocations.geoLocationPoint.pointLatitude "
    "OR _exists_:geoLocations.geoLocationBox.eastBoundLongitude"
)
PAGE_SIZE = 1000
# DataCite allows 3,000 requests in five minutes. A second apart is far inside that.
DELAY_S = 1.0
DOI_URL = "https://doi.org/{doi}"
# A box larger than this in either direction covers a region, not a site. About 28 km of latitude.
MAX_BOX_DEGREES = 0.25
MAX_SUMMARY = 1500


@register
class AdsDois(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="datacite-ads-dois",
        name="DataCite metadata for ADS DOIs (prefix 10.5284)",
        publisher="DataCite (records supplied by ADS, client bl.ads)",
        licence=(
            "CC0 ('All metadata contained in the file is freely available under a CC0 waiver', "
            "DataCite public data file page). The reports themselves keep their own licence in rightsList."
        ),
        attribution="None required for CC0 metadata; cite DOIs",
        category=RecordCategory.DOCUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://support.datacite.org/docs/api",
        coverage="UK and wider; only DOIs with a position in Britain and Ireland are stored",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        pages = RestJson(self.http, polite=Polite(delay_s=DELAY_S), where="DataCite")
        params = {
            "client-id": "bl.ads",
            "query": HAS_POSITION,
            "page[cursor]": "1",
            "page[size]": str(min(PAGE_SIZE, limit) if limit else PAGE_SIZE),
        }
        skipped = 0
        for item in pages.items(
            DOIS_URL, params=params, items="data", total="meta.total", next_url="links.next", id_path="id"
        ):
            record = to_record(item)
            if record is None:
                skipped += 1
                continue
            yield record
        if skipped:
            logger.info(
                "DataCite: %d DOIs had a position outside Britain and Ireland, or a region-sized box", skipped
            )


def _number(value: Any) -> float | None:
    """A coordinate given as a number or as text, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _in_bounds(lon: float, lat: float) -> bool:
    west, south, east, north = BRITISH_ISLES
    return west <= lon <= east and south <= lat <= north


def _oriented(first: float, second: float) -> tuple[float, float, bool] | None:
    """Longitude and latitude from a latitude and longitude as written, whichever way round they are right."""
    if _in_bounds(second, first):
        return second, first, False
    if _in_bounds(first, second):
        return first, second, True
    return None


def _points(locations: list[Any]) -> tuple[list[Point], bool]:
    found: list[Point] = []
    swapped = False
    for location in locations:
        point = dig(location, "geoLocationPoint")
        lat, lon = _number(dig(point, "pointLatitude")), _number(dig(point, "pointLongitude"))
        if lat is None or lon is None:
            continue
        oriented = _oriented(lat, lon)
        if oriented is not None:
            found.append(Point(oriented[0], oriented[1]))
            swapped = swapped or oriented[2]
    return found, swapped


def _boxes(locations: list[Any]) -> tuple[list[BaseGeometry], bool]:
    found: list[BaseGeometry] = []
    swapped = False
    for location in locations:
        edges = dig(location, "geoLocationBox")
        south, north, west, east = (
            _number(dig(edges, name))
            for name in (
                "southBoundLatitude",
                "northBoundLatitude",
                "westBoundLongitude",
                "eastBoundLongitude",
            )
        )
        if south is None or north is None or west is None or east is None:
            continue
        lower, upper = _oriented(south, west), _oriented(north, east)
        if lower is None or upper is None or lower[2] != upper[2]:
            continue
        west_lon, south_lat, was_swapped = lower
        east_lon, north_lat, _ = upper
        if west_lon > east_lon or south_lat > north_lat:
            continue
        if east_lon - west_lon > MAX_BOX_DEGREES or north_lat - south_lat > MAX_BOX_DEGREES:
            continue
        found.append(box(west_lon, south_lat, east_lon, north_lat))
        swapped = swapped or was_swapped
    return found, swapped


def position(locations: Any) -> tuple[BaseGeometry, bool] | None:
    """Where a DOI's `geoLocations` put it, and whether its axes were swapped. None when nowhere useful."""
    if not isinstance(locations, list):
        return None
    points, swapped = _points(locations)
    if points:
        return (points[0] if len(points) == 1 else MultiPoint(points)), swapped
    boxes, swapped = _boxes(locations)
    return (boxes[0], swapped) if boxes else None


def _first_text(items: Any, key: str) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        text = dig(item, key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _updated(attributes: dict[str, Any]) -> datetime | None:
    text = attributes.get("updated")
    if not isinstance(text, str):
        return None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


def to_record(item: Any) -> RecordIn | None:
    """One DataCite DOI as a record, or None when it has no position worth storing."""
    doi = item.get("id") if isinstance(item, dict) else None
    attributes = item.get("attributes") if isinstance(item, dict) else None
    if not isinstance(doi, str) or not doi.strip() or not isinstance(attributes, dict):
        raise UpstreamFormatError(f"A DataCite item has no id or attributes: {str(item)[:120]!r}.")
    placed = position(attributes.get("geoLocations"))
    if placed is None:
        return None
    geometry, swapped = placed
    name = _first_text(attributes.get("titles"), "title") or doi
    summary = _first_text(attributes.get("descriptions"), "description")
    if summary and len(summary) > MAX_SUMMARY:
        summary = summary[: MAX_SUMMARY - 1].rstrip() + "…"
    types = attributes.get("types")
    types = types if isinstance(types, dict) else {}
    creators = [
        creator["name"]
        for creator in _as_list(attributes.get("creators"))
        if isinstance(creator, dict) and isinstance(creator.get("name"), str)
    ]
    return RecordIn(
        external_id=doi.strip(),
        name=name,
        geom=geometry,
        summary=summary,
        record_type=types.get("resourceType") or types.get("resourceTypeGeneral"),
        url=DOI_URL.format(doi=doi.strip()),
        source_updated_at=_updated(attributes),
        raw={
            "doi": doi,
            "creators": creators,
            "publicationYear": attributes.get("publicationYear"),
            "rightsList": attributes.get("rightsList") or [],
            "geoLocations": attributes.get("geoLocations"),
            "landingPage": attributes.get("url"),
            "axes_swapped": swapped,
        },
    )
