# Plan — Say more about a heritage record: fuller summaries and photographs

**Status:** Proposed.

## Goal

A record's page, and its card on a finding, say enough to judge the record without leaving: what it is, when it was protected, a few sentences about it, and a photograph where one may be shown. The owner asked for this on 2026-11-13, with a listed church as the example: our page gave its name, grade and grid reference, and the list entry gave an overview, a statutory address and photographs.

## Prerequisites

- The owner's answers to "Open questions for the owner".
- For the list entry's own words and photographs: Historic England's answer, which nobody has asked for yet.

## What exists (2026-11-13)

- **What a record holds.** A record holds what its source's open data holds, and the whole row is kept in `records.raw`. For a listed building that is the name, the grade, the date it was listed, the date the entry was amended, a grid reference and the address of its list entry. `summary` is one phrase built from the grade, such as "Grade II listed building".
- **What the open data leaves out.** Historic England's open data has no description, no address and no photographs for a list entry, only the link to it. This was tested on 2026-11-10 and is recorded in [Records in England](../sources/records-england.md).
- **Where the rest is.** The list entry's page has an overview, the statutory address, the full description and photographs. That site answers a script with a refusal: the research met it on 2026-11-10, and on 2026-11-13 its terms page answered 403 the same way. The server can't read those pages, and nothing here should try to get round a publisher's refusal.
- **What may be reused of that page is not established.** The government's API catalogue gives the Open Government Licence for the list's data service. Nothing read first-hand says the same of the description's text or of the photographs. Search results quote Historic England's page for people who add photographs to a list entry as saying they keep the copyright and that the images are "available for use under licence with an acknowledgement". That page couldn't be opened to check.
- **Open sources that know a list entry.** Wikidata records the list entry number on about 400,000 of its items, with a photograph on Wikimedia Commons and a Wikipedia article where they exist. The Wikidata loader here stores only the items that carry another identifier too, for joining records. Wikimedia Commons is already in the catalogue of sources the browser asks by place (`wikimedia-commons-geosearch`), with each file's licence and credit. Geograph has over 7 million photographs under CC BY-SA 2.0 and its API needs a key. Both are described in [Thematic sources and gazetteers](../sources/thematic-and-gazetteers.md).
- **The card on a finding.** A linked record's card gives its category, type, source and licence, and the first three lines of its summary.

## Design

Proposed. Nothing here is built.

### Say all we already hold

A record's summary and its page say every plain fact its row has. For a listed building: "Grade II listed building. First listed on 8 December 2017." and, where the entry was amended, when. The same for scheduled monuments, parks and gardens, battlefields and wrecks, each with the dates its layer has. This needs no new source and nothing fetched. It takes effect at each source's next refresh.

### Photographs from open collections

A record's page shows photographs of the thing from collections that license them openly, asked for by the browser and never copied to our servers, as the catalogue of live sources already works (Decision 0007).

- **By list entry number.** Wikimedia Commons' files for the Wikidata item that carries the record's number. This finds pictures of the building itself.
- **By place.** Commons' files within a short distance of the record, and Geograph's once a key is held. This finds pictures of the place, and is marked as such.

Every photograph carries its photographer, its licence and a link to its page, as its licence requires. A record with no photograph shows none, and says nothing.

### A few sentences

Where the record's Wikidata item has a Wikipedia article, the page shows the article's opening sentences under the heading "From Wikipedia", with the link and the licence. Where it has none, the page keeps to the facts above and the link to the original.

### Historic England's own words and photographs

The list entry's overview, address and description are the best account there is, and they are Historic England's to give. The project asks. A request for the open data, the aerial photograph footprints and stable service names was drafted on 2026-11-10 and never sent, and [Owner actions](owner-actions.md) has Historic England's letter as work still to do. The question of the list descriptions joins that letter. Until there is an answer, the page says what we hold and "See the original record" opens the list entry in another tab.

## Workstreams

### WS1 — Say all we hold

**Status:** Not started.

Each list layer's loader writes the dates it has into the summary. The record's page sets them out as facts beside the period and the recorded types.

**Exit criteria:** a listed building's page says its grade and the date it was listed, from a recorded fixture, and no loader fetches anything it didn't before.

### WS2 — Photographs by list entry number

**Status:** Not started. Needs the owner's answer to question 2.

The browser finds the Wikidata item for a record's list entry number and shows its Commons photographs with their credits. A `sources` row and its place in `docs/sources/` come first.

**Exit criteria:** a record with a photograph on Commons shows it with photographer, licence and link, a record without shows nothing, and a refused or slow answer leaves the page as it was.

### WS3 — Photographs by place

**Status:** Not started. Needs WS2.

Commons' files near the record, marked as pictures of the place. Geograph's follow once the owner holds a key.

**Exit criteria:** the photographs near a record are shown apart from those of the record itself, each with its credit.

### WS4 — Sentences from Wikipedia

**Status:** Not started. Needs the owner's answer to question 3.

**Exit criteria:** a record whose item has an article shows its opening sentences with the link and licence, and one without shows nothing.

### WS5 — Ask Historic England

**Status:** Not started. The owner sends it.

The list descriptions, the statutory addresses and the photographs join the letter in [Owner actions](owner-actions.md).

**Exit criteria:** the letter is sent, and the answer is recorded in `docs/sources/records-england.md`.

## Phase exit criteria

- [ ] A record's page says every fact its source's open data gives.
- [ ] A record with an openly licensed photograph shows it, credited.
- [ ] Historic England has been asked for its list descriptions and photographs.
- [ ] All workstreams shipped or deferred to a successor plan.

## Decisions to write

- **Photographs and sentences from outside collections are shown beside a record, credited, and never stored.** Which collections, how a photograph is tied to a record, what is shown when a licence can't be read, and why the list entry's own words wait for permission.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| A photograph of the wrong building is shown as the record's | Medium | Only files tied to the list entry number are shown as the record's. Files found by place are marked as the place |
| A file's licence can't be read, or forbids reuse | Medium | A file without a readable open licence isn't shown |
| Wikimedia's services are slow or refuse | Low | The browser asks, with a short wait, and the page is whole without the answer |
| Historic England says no, or doesn't answer | Medium | The page already says what the open data gives and links to the list entry |

## Left out

- Reading Historic England's pages by script, in any form.
- Copying any photograph to our servers.
- Photographs added by members to a record. Photographs belong to findings.
- Records from sources other than the national lists, until these are done.

## Open questions for the owner

1. **Shall the list descriptions join the letter to Historic England, and will you send it?** Recommended: yes. The draft is yours to send, from your address.
2. **Are credited photographs from Wikimedia Commons, and later Geograph, right for a record's page while the list's own aren't ours to show?** Recommended: yes, for files tied to the list entry number first.
3. **Should a record show Wikipedia's opening sentences where there is an article?** Recommended: yes, under their own heading, never mixed with the source's words.

## References

- [Records in England](../sources/records-england.md) — what Historic England's open data holds and leaves out.
- [Thematic sources and gazetteers](../sources/thematic-and-gazetteers.md) — Wikimedia Commons and Geograph.
- [Owner actions](owner-actions.md) — the letters still to send.
- [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md) — what is stored, what the browser asks for, and what is only linked.
