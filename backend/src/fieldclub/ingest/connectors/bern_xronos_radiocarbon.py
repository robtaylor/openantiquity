"""Radiocarbon dates in Britain and Ireland, from the XRONOS database at the University of Bern.

Work-list key `bern-xronos-radiocarbon`. XRONOS answers one request per
country label with every measurement as JSON, 35 MB for `GB`. Its country
labels are not consistent: `GB` holds 23,190 dates, `England/Wales` 13,970,
`Scotland` 1,729 and `IE` (the island of Ireland) 24,454, and none of them
overlaps another. The work-list warned that `GB` alone undercounts. The four
are read one after another, each kept under `var/ingest/` for a day.

A measurement has no stable code of its own, and lab numbers repeat, because
the database merges several others and keeps each source's copy. The
measurement's own `id` is the identifier XRONOS gives it, and is unique across
all four answers. A repeated id fails the run.

Dates with no coordinates, or coordinates outside Britain and Ireland, are not
stored. A few in the `IE` answer have the sign of the longitude wrong and land
in the North Sea. They are left out, not repaired.

`periods` in the answer repeats each name many times over and mixes site and
culture labels, so the names are deduplicated, and only those that say plainly
which period they are (`Neolithic`, `Middle Bronze Age`, `Iron Age`) are mapped
onto `vocab.Period`. The two-letter codes (`UN`, `UBA`, `EN`) are not decoded.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, ClassVar

from shapely.geometry import Point

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Polite
from fieldclub.ingest.adapters.rest import RestJson
from fieldclub.ingest.base import BRITISH_ISLES, BBox, Connector, RecordIn, SourceInfo, point_in_bbox
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

DATA_URL = "https://xronos.ch/api/v1/data"
# Every label the database uses for the islands, found by trying country names.
COUNTRIES = ("GB", "England/Wales", "Scotland", "IE")
DELAY_S = 2.0
# What every measurement must carry. The rest is optional and kept in `raw`.
REQUIRED = ("id", "labnr", "site", "lat", "lng")

# Period names that say what they are, as patterns on the lower-cased name.
_PERIOD_WORDS = (
    (re.compile(r"neolith"), Period.NEOLITHIC),
    (re.compile(r"bronze"), Period.BRONZE_AGE),
    (re.compile(r"iron age|^ia$"), Period.IRON_AGE),
    (re.compile(r"mesolith|paleolith|palaeolith|epipal"), Period.PREHISTORIC),
    (re.compile(r"roman"), Period.ROMAN),
    (re.compile(r"medieval"), Period.MEDIEVAL),
)


@register
class XronosRadiocarbon(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="bern-xronos-radiocarbon",
        name="XRONOS radiocarbon dates (GB)",
        publisher="University of Bern / XRONOS",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        attribution=(
            "XRONOS: 'This work is licensed under a Creative Commons Attribution 4.0 International License.'"
        ),
        category=RecordCategory.EVENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://xronos.ch/",
        coverage="World; only Britain and Ireland are stored",
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        pages = RestJson(self.http, polite=Polite(delay_s=DELAY_S), where="XRONOS")
        directory = cache_dir(self.settings, self.source.key)
        seen: set[str] = set()
        for country in COUNTRIES:
            dest = directory / f"{country.replace('/', '-').lower()}.json"
            body, obtained = pages.document(
                DATA_URL, dest=dest, params={"query_country": country}, max_age=self.max_age
            )
            self.obtained_at = obtained if self.obtained_at is None else min(self.obtained_at, obtained)
            if not isinstance(body, list):
                raise UpstreamFormatError(f"XRONOS answered {country!r} with something other than a list.")
            kept = 0
            for item in body:
                record = to_record(item)
                if record is None:
                    continue
                if record.external_id in seen:
                    raise UpstreamFormatError(f"XRONOS measurement {record.external_id} appears twice.")
                seen.add(record.external_id)
                kept += 1
                yield record
            logger.info("XRONOS %s: %d measurements, %d stored", country, len(body), kept)


def _coordinate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def period_names(items: Any) -> list[str]:
    """The distinct period names a measurement lists, as written. `periods` repeats them many times over."""
    names = {
        entry["periode"].strip()
        for entry in items or []
        if isinstance(entry, dict) and isinstance(entry.get("periode"), str) and entry["periode"].strip()
    }
    return sorted(names)


def periods_from(names: list[str]) -> list[str]:
    """`vocab.Period` values for the names that say plainly which period they are, in a steady order."""
    found = {period for name in names for pattern, period in _PERIOD_WORDS if pattern.search(name.lower())}
    return [period.value for period in Period if period in found]


def _summary(m: dict[str, Any]) -> str:
    age = f"{m['bp']} ± {m['std']} BP" if m.get("bp") is not None and m.get("std") is not None else None
    material = m.get("material") if m.get("material") not in (None, "", "NA") else None
    species = f" ({m['species']})" if m.get("species") not in (None, "", "NA") else ""
    parts = [part for part in (age, f"{material}{species}" if material else None) if part]
    return f"{m['labnr']}: " + ", ".join(parts) if parts else str(m["labnr"])


def to_record(item: Any) -> RecordIn | None:
    """One measurement as a record, or None when it has no position inside Britain and Ireland."""
    m = item.get("measurement") if isinstance(item, dict) else None
    missing = [name for name in REQUIRED if not isinstance(m, dict) or name not in m]
    if missing:
        raise UpstreamFormatError(f"An XRONOS measurement changed shape: missing {missing}.")
    assert isinstance(m, dict)
    lat, lon = _coordinate(m["lat"]), _coordinate(m["lng"])
    if lat is None or lon is None or not point_in_bbox(BRITISH_ISLES, lon, lat):
        return None
    labnr = str(m["labnr"]).strip()
    site = m["site"].strip() if isinstance(m["site"], str) else ""
    site_type = m.get("site_type")
    names = period_names(m.get("periods"))
    references = [
        r["reference"] for r in m.get("reference") or [] if isinstance(r, dict) and r.get("reference")
    ]
    return RecordIn(
        external_id=str(m["id"]),
        name=site or labnr,
        geom=Point(lon, lat),
        summary=_summary({**m, "labnr": labnr}),
        record_type=site_type if isinstance(site_type, str) and site_type.strip() else None,
        periods=periods_from(names),
        raw={
            key: m.get(key)
            for key in (
                "id",
                "labnr",
                "bp",
                "std",
                "cal_bp",
                "cal_std",
                "delta_c13",
                "material",
                "species",
                "feature_type",
                "country",
                "lat",
                "lng",
                "lab_name",
                "source_database",
            )
        }
        | {"reference": references, "period_names": names},
    )
