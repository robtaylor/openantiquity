"""Roman road segments in Britain and Ireland, from the Itiner-e nightly export.

Work-list key `aarhus-itinere-roman-roads`. The export is one newline-delimited
GeoJSON file of about 17,000 route segments across the whole Roman Empire,
58 MB, rebuilt nightly. It is fetched at most once a day and kept under
`var/ingest/`. Only segments that lie wholly inside Britain and Ireland are
kept, about 1,500, none of them certain: `segmentCertainty` is Conjectured or
Hypothetical, so the summary says which, and the lines often sit off the agger
that LIDAR shows.

The work-list has no id field. The segment's feature `id` is the number in the
address of its page on itiner-e.org, which the site links to, so it is the
identifier the publisher gives it. A repeated id fails the run.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, ClassVar

from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature, Polite, json_ready
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_ndjson
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

EXPORT_URL = "https://itiner-e.org/route-segments/download"
SEGMENT_URL = "https://itiner-e.org/route-segment/{id}"
# The work-list's gotchas ask for the static version to be cited too.
STATIC_VERSION = "Static version: https://doi.org/10.5281/zenodo.17122148."
DELAY_S = 1.0
# Britain and Ireland without Normandy: south of Cherbourg's latitude and east of Calais's longitude are out.
ISLES: BBox = (-11.5, 49.9, 1.8, 61.5)
# Fields a segment must carry. The others are optional and kept in `raw`.
REQUIRED = ("name", "type", "segmentCertainty", "lowerDate", "upperDate")

# Years each period covers, as `vocab.PERIODS` describes them. Only the ones a
# road in Britain and Ireland can fall in.
_PERIOD_YEARS = (
    (Period.IRON_AGE, -800, 43),
    (Period.ROMAN, 43, 410),
    (Period.EARLY_MEDIEVAL, 410, 1066),
    (Period.MEDIEVAL, 1066, 1540),
)


@register
class ItinerERoads(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="aarhus-itinere-roman-roads",
        name="Itiner-e Roman roads (nightly export)",
        publisher="Aarhus University and UAB",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        attribution=(
            "Itiner-e: the digital atlas of ancient roads © 2024 by Brughmans, Pažout, de Soto and "
            "Bjerregaard Vahlstrup is licensed under CC BY 4.0 " + STATIC_VERSION
        ),
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://itiner-e.org/",
        coverage="Roman Empire; only Britain and Ireland are stored",
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        path = cache_dir(self.settings, self.source.key) / "route-segments.ndjson"
        fetched = download(
            EXPORT_URL, path, client=self.http, polite=Polite(delay_s=DELAY_S), max_age=self.max_age
        )
        self.obtained_at = fetched.fetched_at
        seen: set[str] = set()
        for feature in read_ndjson(path):
            if feature.geometry is None or not in_britain_or_ireland(feature.geometry):
                continue
            record = to_record(feature)
            if record.external_id in seen:
                raise UpstreamFormatError(f"Itiner-e segment {record.external_id} appears twice.")
            seen.add(record.external_id)
            yield record


def in_britain_or_ireland(geometry: BaseGeometry) -> bool:
    """Whether a segment lies wholly in Britain or Ireland rather than in the Empire's other provinces.

    The runner's own box for the islands also holds Normandy and the coast
    of Picardy, so this one stops short of them. A segment from Britain to
    Gaul, such as a sea lane across the Channel, is left out.
    """
    west, south, east, north = geometry.bounds
    inside = west >= ISLES[0] and south >= ISLES[1] and east <= ISLES[2] and north <= ISLES[3]
    # Nothing in Kent lies wholly south of Dover's latitude, so this is Boulogne's coast.
    return inside and not (east > 1.35 and north < 51.0)


def periods_between(lower: Any, upper: Any) -> list[str]:
    """The periods a date range in years (BC negative) overlaps.

    Nothing when either end is missing, and nothing for 0 to 0, which the
    export writes for 11,776 of its segments that have no date at all.
    """
    if isinstance(lower, bool) or isinstance(upper, bool):
        return []
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        return []
    if lower == upper == 0:
        return []
    if lower > upper:
        lower, upper = upper, lower
    return [period.value for period, start, end in _PERIOD_YEARS if lower < end and upper > start]


def to_record(feature: Feature) -> RecordIn:
    """One route segment as a record."""
    properties = feature.properties
    missing = [name for name in REQUIRED if name not in properties]
    if missing or not isinstance(feature.id, (int, str)) or feature.geometry is None:
        raise UpstreamFormatError(f"An Itiner-e segment changed shape: id {feature.id!r}, missing {missing}.")
    segment_id = str(feature.id)
    certainty = properties["segmentCertainty"]
    road_type = properties["type"]
    description = properties.get("description")
    summary = " ".join(
        part
        for part in (
            f"{certainty} line." if certainty else None,
            description.strip() if isinstance(description, str) else None,
        )
        if part
    )
    name = properties["name"]
    return RecordIn(
        external_id=segment_id,
        name=name.strip() if isinstance(name, str) and name.strip() else f"Roman road segment {segment_id}",
        geom=feature.geometry,
        record_type=road_type if isinstance(road_type, str) else None,
        monument_types=[road_type] if isinstance(road_type, str) else [],
        periods=periods_between(properties["lowerDate"], properties["upperDate"]),
        summary=summary or None,
        url=SEGMENT_URL.format(id=segment_id),
        raw=json_ready(properties),
    )
