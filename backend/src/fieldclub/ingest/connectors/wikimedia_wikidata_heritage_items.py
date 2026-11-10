"""Wikidata items that carry a national heritage identifier and a position, as a cross-walk.

Work-list key `wikimedia-wikidata-heritage-items`. Wikidata links one thing to
the identifiers that different national records give it, so an item here says
that Canmore's record, Coflein's and the Atlas of Hillforts' entry are the same
place, and where its Wikipedia and Commons pages are. Use it to join records,
not as a record in its own right: every item duplicates a record another
source holds. The source is therefore declared `enabled=False`, which keeps
its rows out of the map, the tiles, search and the attribution list while the
items stay in `records` for joining (Decision 0011). A `sources` row that
already exists keeps the `enabled` it has, so one made before that decision is
switched off by hand.

One SPARQL query is asked per identifier property (the work-list says so: a
query for all of them at once times out), and the answers are merged by item in
memory, so a hillfort that Canmore and Coflein both know becomes one record
with both numbers in `raw["identifiers"]`, keyed by property (`P718` Canmore,
`P4658` Coflein, `P4102` Atlas of Hillforts, `P709` Historic Environment
Scotland, `P1459` and `P3007` Cadw, `P1460` Northern Ireland, `P4117` Historic
England research records, `P8169` Heritage Gateway, and `P1216` NHLE where the
item has one). The NHLE number is asked for only alongside another identifier,
because 400,000 of Wikidata's items have one and nearly all are listed
buildings, which the Historic England connectors already cover.

Wikidata writes the Atlas number of Cissbury Ring as `3749` but pads others
(`0095` where the Atlas's own file has `95`), so a number made only of digits
is stored without its leading zeros, which is how the other sources write it.
`raw["published"]` keeps the forms that changed.

Each property's rows are counted first and the read fails when fewer arrive,
which costs one more request. Wikidata allowed one request a minute on
2026-11-10 and answered a second request inside the minute with 429 and a
`Retry-After` of 1,000 seconds, so requests here are a minute apart and the
wait it asks for is honoured. A full run takes about twenty minutes. Wikimedia
asks for a contact in the `User-Agent`, so the source is skipped unless
`FIELDCLUB_CONTACT` (or `FIELDCLUB_USER_AGENT`) is set. Each property's
rows are kept under `var/ingest/` for a day once the read has passed its
count, so a run that fails at the twentieth request starts again at that
property, not the first. A partial run (`--limit`) reads only the first
property's first rows, so it has no merge to do and keeps nothing. The id is
the item's Q number, which never changes. Items with no English label, or with
a position outside Britain and Ireland, are left out.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters.common import Feature, Polite, Tally, UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.sparql import SparqlQuery, wkt_literal
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo, in_britain_and_ireland
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
ITEM_URL = "https://www.wikidata.org/wiki/{qid}"
ENTITY_PREFIX = "http://www.wikidata.org/entity/"
# Wikidata's allowance on 2026-11-10 was one request a minute.
DELAY_S = 60.0
PAGE_SIZE = 25_000
# A query may run for a minute. This leaves the answer time to arrive.
QUERY_TIMEOUT_S = 120.0
# Data moves between the count and the last page.
TOLERANCE = 0.01
# Identifier properties, smallest first so the first rows come quickly.
PROPERTIES = ("P4102", "P1460", "P4117", "P8169", "P709", "P1459", "P3007", "P4658", "P718")
NHLE = "P1216"

WHERE = """\
?item wdt:{prop} ?id ; wdt:P625 ?coord .
  OPTIONAL {{ ?item wdt:P1216 ?nhle }}
  OPTIONAL {{ ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en") }}"""
SELECT = (
    "SELECT ?item ?itemLabel ?coord ?id ?nhle WHERE {{\n  " + WHERE + "\n}}\nORDER BY ?item ?id ?nhle ?coord"
)
COUNT = "SELECT (COUNT(*) AS ?rows) WHERE {{\n  " + WHERE + "\n}}"


@dataclass
class Item:
    label: str | None = None
    geometry: BaseGeometry | None = None
    identifiers: dict[str, set[str]] = field(default_factory=dict)
    # Identifiers whose published form had leading zeros, as `{property: {normalised: published}}`.
    published: dict[str, dict[str, str]] = field(default_factory=dict)


@register
class WikidataHeritageItems(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="wikimedia-wikidata-heritage-items",
        name="Wikidata UK heritage items with national identifiers",
        publisher="Wikimedia Foundation",
        licence="CC0 1.0",
        attribution="None required",
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://www.wikidata.org/",
        coverage="UK and Ireland, items with a heritage identifier and a position",
        # A cross-walk, not a map record (Decision 0011).
        enabled=False,
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def is_configured(self) -> bool:
        """Wikimedia asks for a contact in the `User-Agent` and answers a client without one with 429."""
        return bool(self.settings.contact or self.settings.user_agent)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        polite = Polite(delay_s=DELAY_S, retries=2, max_backoff_s=1800.0)
        items: dict[str, Item] = {}
        for prop in PROPERTIES[:1] if limit else PROPERTIES:
            self._read_property(prop, polite, items, limit)
        skipped = 0
        for qid in sorted(items, key=lambda q: int(q[1:])):
            record = to_record(qid, items[qid])
            if record is None:
                skipped += 1
                continue
            yield record
        if skipped:
            logger.info("Wikidata: %d items had no English label or a position outside the isles", skipped)

    def _read_property(self, prop: str, polite: Polite, items: dict[str, Item], limit: int | None) -> None:
        if limit:
            query = f"{SELECT.format(prop=prop)}\nLIMIT {limit}"
            reader = SparqlQuery(
                ENDPOINT, query, client=self.http, polite=polite, geometry="coord", timeout=QUERY_TIMEOUT_S
            )
            for feature in reader.features():
                merge(items, prop, feature)
            return
        path = cache_dir(self.settings, self.source.key) / f"{prop}.json"
        cached = read_cached_rows(path, self.max_age)
        if cached is not None:
            rows, obtained = cached
            logger.info("Wikidata %s: %d rows from the copy on disk", prop, len(rows))
        else:
            rows, obtained = self._ask_rows(prop, polite), datetime.now(UTC)
            write_cached_rows(path, rows)
        self.obtained_at = obtained if self.obtained_at is None else min(self.obtained_at, obtained)
        for row in rows:
            merge(items, prop, Feature(row, wkt_literal(row["coord"]) if "coord" in row else None))

    def _ask_rows(self, prop: str, polite: Polite) -> list[dict[str, str]]:
        """Every row of one property, once the count agrees."""
        reader = SparqlQuery(
            ENDPOINT, SELECT.format(prop=prop), client=self.http, polite=polite,
            page_size=PAGE_SIZE, timeout=QUERY_TIMEOUT_S,
        )  # fmt: skip
        counter = SparqlQuery(
            ENDPOINT, COUNT.format(prop=prop), client=self.http, polite=polite, timeout=QUERY_TIMEOUT_S
        )
        tally = Tally(f"Wikidata {prop}", expected_rows(counter), TOLERANCE, what="rows")
        rows = list(reader.rows())
        for row in rows:
            tally.add((row.get("item"), row.get("id"), row.get("nhle"), row.get("coord")))
        tally.check()
        logger.info("Wikidata %s: %d rows", prop, tally.distinct)
        return rows


def read_cached_rows(path: Path, max_age: timedelta) -> tuple[list[dict[str, str]], datetime] | None:
    """A property's rows from an earlier run and when they were read, or None if missing, old or unusable."""
    try:
        stat = path.stat()
        if time.time() - stat.st_mtime > max_age.total_seconds():
            return None
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return rows, datetime.fromtimestamp(stat.st_mtime, UTC)


def write_cached_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(rows), encoding="utf-8")
    part.replace(path)


def expected_rows(counter: SparqlQuery) -> int:
    rows = list(counter.rows())
    try:
        return int(rows[0]["rows"])
    except (IndexError, KeyError, ValueError):
        raise UpstreamFormatError("Wikidata did not answer a count query with a number.") from None


def qid_of(iri: str) -> str:
    qid = iri.removeprefix(ENTITY_PREFIX)
    if iri == qid or not qid.startswith("Q") or not qid[1:].isdigit():
        raise UpstreamFormatError(f"{iri!r} is not a Wikidata item.")
    return qid


def merge(items: dict[str, Item], prop: str, feature: Feature) -> None:
    """Fold one row into the item it describes."""
    p = feature.properties
    if "item" not in p or "id" not in p:
        raise UpstreamFormatError(f"A Wikidata row changed shape: {sorted(p)}.")
    item = items.setdefault(qid_of(p["item"]), Item())
    item.label = item.label or p.get("itemLabel")
    item.geometry = item.geometry or feature.geometry
    for key, value in ((prop, p["id"]), (NHLE, p.get("nhle"))):
        if value is None:
            continue
        normalised = normalise_identifier(value)
        item.identifiers.setdefault(key, set()).add(normalised)
        if normalised != value:
            item.published.setdefault(key, {})[normalised] = value


def normalise_identifier(value: str) -> str:
    """The identifier without leading zeros when it is only digits: `0095` is the Atlas's `95`."""
    value = value.strip()
    return (value.lstrip("0") or "0") if value.isdigit() else value


def to_record(qid: str, item: Item) -> RecordIn | None:
    """One merged item as a record, or None without an English label or a position in the isles."""
    if not item.label or item.geometry is None:
        return None
    x, y = item.geometry.bounds[0], item.geometry.bounds[1]
    if not in_britain_and_ireland(x, y):
        return None
    return RecordIn(
        external_id=qid,
        name=item.label.strip(),
        geom=item.geometry,
        record_type="Wikidata item",
        url=ITEM_URL.format(qid=qid),
        raw={
            "item": qid,
            "identifiers": {prop: sorted(ids) for prop, ids in sorted(item.identifiers.items())},
            "published": {
                prop: dict(sorted(forms.items())) for prop, forms in sorted(item.published.items())
            },
        },
    )
