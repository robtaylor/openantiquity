# Decision 0007 — The record index stores only what licences allow

**Status:** Proposed.

**TL;DR.** In the context of wanting every public archaeological record in the UK beside the map, facing publishers whose terms range from open through research-only to no scripted access at all, we chose three access modes per source (stored, queried live from the browser, or linked) to show as much as possible without holding data we have no right to hold, accepting an uneven experience where England's undesignated sites are slower and patchier than everything else.

## Context

Nothing was built when this was written.

The research pass on 2026-11-10 found the four nations in different positions. Scotland, Wales and Northern Ireland each published their national site index and designations under the Open Government Licence. England published its designations and half a million features mapped from aerial photographs the same way, but not its 354,740 research records or most of its 83 local Historic Environment Records. Only Cornwall and York were openly licensed in bulk.

England's research records were reachable in two other ways. The Archaeology Data Service catalogue served 309,769 of them through a public API with open cross-origin access, under terms limiting use to teaching, learning and research and forbidding supply to a third party. Its own pages gave three different licences for that metadata. The relaunched Heritage Gateway held 1.3 million records behind a bot challenge.

Ten local records in south-west England were queryable on one public map server with no stated licence. The Portable Antiquities Scheme and Scotland's trove.scot refused scripted access entirely.

OpenStreetMap was thin for archaeology. It held 391 hill forts in the UK against 3,642 in the Atlas of Hillforts, and its share-alike database licence complicated storing it beside other sources.

## Decision

1. Every source has an access mode: `bulk`, `live` or `deeplink`.
2. A `bulk` source is downloaded and stored in the record index. Only sources whose licence clearly permits storage and display are bulk, and each is taken from its publisher, not from an aggregator's copy.
3. A `live` source is queried by the user's browser when they look at an area, shown with the publisher's name and a link, and never stored on our servers. The Archaeology Data Service catalogue and the public local-record map services are live.
4. A `deeplink` source is offered as a link that opens the publisher's own page at the same place. Heritage Gateway, the Portable Antiquities Scheme and trove.scot are deep links.
5. A finding linked to a live or deep-link record stores the record's identifier and address and nothing else.
6. OpenStreetMap is drawn as an overlay and is not indexed.
7. A source moves from live to bulk only when its publisher has said in writing that we may store it.

## Alternatives considered

- **Harvesting the Archaeology Data Service catalogue**, which was technically complete in a paging test, was rejected until they confirm which of their three stated licences governs it.
- **Working around the bot challenges** was rejected outright. A publisher that blocks scripts has answered the question.
- **Bulk-ingesting OpenStreetMap heritage features** was rejected because the data is thin and the licence handling isn't worth what it adds.
- **Leaving England's undesignated sites out** until an open source exists was rejected because "is this already recorded?" is the first question about any finding, and most of England would have had no answer.

## Consequences

- Nothing is stored that a publisher could ask us to delete.
- Live sources are slower, depend on someone else's server, and can't be searched or joined in our database. Suggested records for a finding in England will mix stored and live results.
- The map has to say, per area, whether local records are indexed, live, linked or absent, so that an empty map isn't read as "nothing recorded here".
- Coverage improves through letters, not code: to the Archaeology Data Service, Historic England and individual record offices.

## Walk-back options

- **If the Archaeology Data Service or Historic England grants an open licence**, switch that source to bulk and run the harvest that was already tested. Findings that hold a bare identifier pick up the stored record through it.
- **If a live service objects or disappears**, set it to deep link. The source row changes and nothing else does.

## Links

- Decision 0004 allows non-commercial sources, which is what makes live use of research-only terms defensible.
