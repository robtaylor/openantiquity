"""Radiocarbon dates in Britain and Ireland, from the XRONOS database at the University of Bern.

Work-list key `bern-xronos-radiocarbon`. XRONOS answers one request per
country label with every measurement as JSON, 35 MB for `GB`. Its country
labels are not consistent: `GB` holds 23,190 dates, `England/Wales` 13,970,
`Scotland` 1,729 and `IE` (the island of Ireland) 24,454, and none of them
overlaps another. The work-list warned that `GB` alone undercounts. The four
are read one after another, each kept under `var/ingest/` for a day.

XRONOS merges several databases (RADON, EUROEVOL, IRDD, p3k14c, CalPal and
others) and keeps each one's copy of a measurement, so nearly half its rows
repeat another. The copies are merged into one record. The key is the lab
number with punctuation and case removed, plus the age and its error, so it
names the measurement itself and does not depend on XRONOS's row numbers,
which the publisher does not say are stable. 293 rows have the lab number
`Lab ID not given`: those are keyed on the age, the error, the site name and
the position to four places as well. The external id is a hash of that key. A
repeated XRONOS id across the answers fails the run.
`raw` keeps every copy's XRONOS id and reference. Of the copies, the one with
the lowest id supplies the name and position, and the first that has a value
supplies the material, species and site type (`NA` is no value).

Dates with no coordinates, or coordinates outside Britain and Ireland (the
Continent's coast is left out too), are not stored. A few in the `IE` answer
have the sign of the longitude wrong and land in the North Sea, and one in
Jersey lands in France. They are left out, not repaired.

`periods` in the answer repeats each name many times over and mixes site and
culture labels, so the names are deduplicated, and only those that say plainly
which period they are (`Neolithic`, `Middle Bronze Age`, `Iron Age`, `Beaker`)
are mapped onto `vocab.Period`, by whole word, so `Post-medieval` and
`Pre-Roman Iron Age` are not taken for `medieval` and `Roman`. The two-letter
codes (`UN`, `UBA`, `EN`) are not decoded.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, ClassVar

from shapely.geometry import Point

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Polite
from fieldclub.ingest.adapters.rest import RestJson
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo, in_britain_and_ireland
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

DATA_URL = "https://xronos.ch/api/v1/data"
# Every label the database uses for the islands, found by trying country names.
COUNTRIES = ("GB", "England/Wales", "Scotland", "IE")
DELAY_S = 2.0
# What every measurement must carry. The rest is optional and kept in `raw`.
REQUIRED = ("id", "labnr", "site", "lat", "lng")
# Values that say a lab number, or a field, is not known.
_NO_VALUE = (None, "", "NA")
_NO_LAB_NUMBER = ("", "na", "labidnotgiven")

# Period names that say what they are, as patterns on the lower-cased name.
# Whole words, with the longer names first: `Post-medieval` and `Early
# medieval` are not `medieval`, and `Pre-Roman Iron Age` is not `Roman`.
_PERIOD_WORDS = (
    (re.compile(r"\bneolith"), Period.NEOLITHIC),
    (re.compile(r"\bbronze\b|\b(bell )?beaker\b|\bglockenbecher\b"), Period.BRONZE_AGE),
    (re.compile(r"\biron age\b|^ia$|\beisenzeit\b"), Period.IRON_AGE),
    (re.compile(r"\bmesolith|\bpaleolith|\bpalaeolith|\bepipal"), Period.PREHISTORIC),
    (re.compile(r"(?<!pre-)(?<!pre )\broman\b"), Period.ROMAN),
    (re.compile(r"\bearly[- ]medieval\b|\banglo-saxon\b"), Period.EARLY_MEDIEVAL),
    (re.compile(r"\bpost[- ]medieval\b"), Period.POST_MEDIEVAL),
    (re.compile(r"(?<!early )(?<!early-)(?<!post )(?<!post-)\bmedieval\b"), Period.MEDIEVAL),
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
        seen_ids: set[str] = set()
        # The copies of each measurement, found by its key. Merging needs them all.
        copies: dict[str, list[dict[str, Any]]] = {}
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
                m = measurement_in_islands(item)
                if m is None:
                    continue
                if str(m["id"]) in seen_ids:
                    raise UpstreamFormatError(f"XRONOS measurement {m['id']} appears twice.")
                seen_ids.add(str(m["id"]))
                copies.setdefault(measurement_key(m), []).append(m)
                kept += 1
            logger.info("XRONOS %s: %d measurements, %d in the islands", country, len(body), kept)
        logger.info("XRONOS: %d copies merged into %d measurements", len(seen_ids), len(copies))
        used: set[str] = set()
        for key, group in copies.items():
            record = merge_copies(key, group)
            if record.external_id in used:
                raise UpstreamFormatError(f"XRONOS measurements {key!r} give a key that is already taken.")
            used.add(record.external_id)
            yield record


def _coordinate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _known(value: Any) -> bool:
    return value not in _NO_VALUE


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
    material = m.get("material") if _known(m.get("material")) else None
    species = f" ({m['species']})" if _known(m.get("species")) else ""
    parts = [part for part in (age, f"{material}{species}" if material else None) if part]
    return f"{m['labnr']}: " + ", ".join(parts) if parts else str(m["labnr"])


def measurement_in_islands(item: Any) -> dict[str, Any] | None:
    """The measurement in an answer's item with numeric coordinates, or None outside Britain and Ireland."""
    m = item.get("measurement") if isinstance(item, dict) else None
    missing = [name for name in REQUIRED if not isinstance(m, dict) or name not in m]
    if missing:
        raise UpstreamFormatError(f"An XRONOS measurement changed shape: missing {missing}.")
    assert isinstance(m, dict)
    lat, lon = _coordinate(m["lat"]), _coordinate(m["lng"])
    if lat is None or lon is None or not in_britain_and_ireland(lon, lat):
        return None
    return {**m, "lat": lat, "lng": lon, "labnr": str(m["labnr"]).strip()}


def measurement_key(m: dict[str, Any]) -> str:
    """What names a measurement whichever database's copy it is: lab number, age and error.

    A copy with no lab number has nothing else to name it, so its site and
    position to four places go in the key too.
    """
    labnr = re.sub(r"[^a-z0-9]", "", m["labnr"].lower())
    key = f"{labnr}|{m.get('bp')}|{m.get('std')}"
    if labnr in _NO_LAB_NUMBER:
        site = re.sub(r"[^a-z0-9]", "", str(m["site"]).lower())
        key += f"|{site}|{m['lat']:.4f}|{m['lng']:.4f}"
    return key


def _first_known(group: list[dict[str, Any]], field: str) -> Any:
    return next((m[field] for m in group if _known(m.get(field)) and str(m[field]).strip()), None)


def merge_copies(key: str, group: list[dict[str, Any]]) -> RecordIn:
    """One record from every copy of a measurement. The copy with the lowest XRONOS id leads."""
    group = sorted(group, key=lambda m: int(m["id"]))
    lead = group[0]
    labnr = lead["labnr"]
    site = next((m["site"].strip() for m in group if isinstance(m["site"], str) and m["site"].strip()), "")
    material, species, site_type = (_first_known(group, f) for f in ("material", "species", "site_type"))
    names = sorted({name for m in group for name in period_names(m.get("periods"))})
    references = sorted(
        {
            r["reference"]
            for m in group
            for r in m.get("reference") or []
            if isinstance(r, dict) and r.get("reference")
        }
    )
    return RecordIn(
        external_id="xr-" + hashlib.sha256(key.encode()).hexdigest()[:20],
        name=site or labnr,
        geom=Point(lead["lng"], lead["lat"]),
        summary=_summary({**lead, "material": material, "species": species}),
        record_type=site_type.strip() if isinstance(site_type, str) else None,
        periods=periods_from(names),
        raw={
            field: lead.get(field)
            for field in (
                "labnr",
                "bp",
                "std",
                "cal_bp",
                "cal_std",
                "delta_c13",
                "feature_type",
                "country",
                "lat",
                "lng",
                "lab_name",
            )
        }
        | {
            "material": material,
            "species": species,
            "xronos_ids": [m["id"] for m in group],
            "source_databases": sorted({m["source_database"] for m in group if m.get("source_database")}),
            "reference": references,
            "period_names": names,
        },
    )


def to_record(item: Any) -> RecordIn | None:
    """One measurement on its own as a record, or None when it has no position inside Britain and Ireland."""
    m = measurement_in_islands(item)
    return None if m is None else merge_copies(measurement_key(m), [m])
