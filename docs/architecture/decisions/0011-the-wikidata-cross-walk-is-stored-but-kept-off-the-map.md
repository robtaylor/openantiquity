# Decision 0011 — The Wikidata cross-walk is stored but kept off the map

**Status:** Proposed.

**TL;DR.** In the context of a Wikidata connector whose items each duplicate a record another source already holds, facing a map and a search that would show every hillfort twice or more, we chose to store the items under a source marked `enabled = false`, which every map, tile, search and attribution query already leaves out, to keep the identifier cross-walk without a change to the records model, accepting that the cross-walk lives in `records.raw` until a purpose-built table is worth the work.

## Context

The connector read Wikidata items that carry a national heritage identifier and stored each as a monument record. On the development database, all 49 stored items joined one to one with an Atlas of Hillforts record and lay within 500 m of it, so a search for Cissbury returned the Atlas's entry and Wikidata's. A full run would have added about 4,100 duplicate hillforts and then the Canmore, Coflein and HER duplicates. The work-list's first gotcha for the source says to use it as a cross-walk between national identifiers, not as a primary record.

Identifier formats differ between sources. Wikidata wrote the Atlas number as `0095` where the Atlas's own file has `95`, so a join on the raw text fails.

## Decision

1. The Wikidata connector's `SourceInfo` has `enabled = False`. The runner creates the `sources` row disabled, and records, tiles, search, nearby, the source list and the attribution list read only enabled sources.
2. An identifier made only of digits is stored without leading zeros, with the published form kept in `raw["published"]`, so identifiers join across sources as text.
3. The cross-walk stays in `records.raw["identifiers"]`, keyed by Wikidata property.

## Alternatives considered

- **A table of identifiers keyed by source and external id** was rejected for now because the runner stores `RecordIn` objects only, and a second output type means a change to the runner and the models for a source nothing reads yet. It is the right shape when a feature needs the join.
- **Leave the items on the map** was rejected because it shows one place several times.
- **Leave the connector unregistered** was rejected because the rows are useful as data to join and a disabled source costs nothing.

## Consequences

- The map, tiles and search never show a Wikidata item.
- The items can still be read from `records` by anything that wants the cross-walk.
- A `sources` row that existed before this decision keeps `enabled = true`, because the runner leaves `enabled` alone once the row exists. It has to be switched off by hand: `UPDATE sources SET enabled = false WHERE key = 'wikimedia-wikidata-heritage-items'`.

## Walk-back options

- **If a feature needs to join records by identifier**, add the identifier table and have the runner fill it, then stop storing the items as records.
- **If Wikidata's own coverage becomes worth showing** (items with no other record), enable the source and exclude items whose identifiers match another source's records.

## Links

- Decision 0007 says what the record index stores.
