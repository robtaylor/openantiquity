# Decision 0021 — What is written and drawn beside a protected finding is generalised for each reader

**Status:** Proposed.

**Current architecture:** [Location sensitivity in the build contract](../../ARCHITECTURE.md#location-sensitivity).

**TL;DR.** In the context of investigations that hold protected and restricted findings beside saved map views, height profiles, an area and notes, facing those giving away the place that the finding itself shows only as a 1 km square, we chose to generalise them for each reader when they are read, and to refuse a map link only where a finding's own text is refused, so that items saved earlier are covered too, accepting that a reader sees fewer views and a coarser area than the writer drew.

## Context

When this was written `sensitivity.visible_text` hid positions only in text about a finding: its title and description, answer notes, comments, evidence and mention titles and notes, and the title and note of an investigation item that held it. Everything else in an investigation was served as stored, on its page, in the investigation list and in its GeoJSON, spreadsheet and printable report: a saved view's centre, a height profile's line, the area, the notes and summary, note items and references. The report even turned a view's centre into an eight-figure grid reference.

The security review on 2026-11-11 proved two paths. The finder of a restricted barrow saved the view they were looking at in a public investigation holding it, and a signed-out visitor read the exact position beside the obscured finding. A member did the same with a protected barrow, which members see exactly. A mention's address and an evidence link carried the place the same way, as an OpenStreetMap or Google Maps link, and `text_positions` missed several map-link forms (`mlat=`, Bing's `cp=lat~lon`, percent-escaped degrees).

The review asked for one of two approaches for investigations: generalise for the reader, or refuse at save time any view, profile or area inside a held finding's square. Refusing would also have had to run when a finding was added to an investigation, when an investigation was made public, and when a finding's level was raised, and would still have left items already saved.

## Decision

1. When an investigation holds a finding the reader doesn't see exactly (or, for a download, doesn't download exactly), its title, summary, notes and every item's title and note lose the positions written in them, a reference's link that holds a position is dropped, a saved view or a height profile within 1.5 km of that finding is held back as `near_protected`, and an area within 1.5 km is shown, and found by a box search, as its bounding box widened to cells of about a kilometre. This is decided when the investigation is read (`sensitivity.PositionGuard`), so it covers what was saved before, and what was saved while the finding was open.
2. A web address someone attached to a protected or restricted finding, an evidence link or a mention, goes only to people who see the finding exactly. Others get a video's or a DOI's address rebuilt from its identifier alone, or nothing (`sensitivity.visible_url`).
3. A map link is refused when it is added to a finding that isn't open, as a position in its title is (`position_in_text`), and `text_positions` reads the forms map sites use and reads escaped text decoded.

## Alternatives considered

- **Refusing views, profiles and areas at save time** was rejected because it had to run at four moments, could still be dodged by saving while the finding was open, and left every item already saved in place.
- **Matching geometry against the finding's 1 km square** was rejected because a view centred just outside the square still frames the feature, and a profile can cross it with both ends outside. Distance from the exact point catches both.
- **Dropping every reference link and every investigation's area** for such readers was rejected as more than the risk needs: a reference to a book or a paper rarely holds a position, and a parish's area far from the finding says nothing about it.
- **Judging mention and evidence addresses by `text_positions` alone** was rejected because an address is the member's own text and can carry a place in forms no pattern lists.

## Consequences

- No reader learns more about a finding's place from what surrounds it than from the finding itself, on the page or in a download.
- Readers who see a finding only as a square see fewer saved views and profiles and a coarser area in investigations holding it, and mention links on such findings that aren't videos or DOIs show only their titles.
- A view or profile saved in an investigation that doesn't hold the finding it looks at isn't generalised. A member can still save a view over a protected site in an unrelated public investigation. That is an accepted limit, as typing a site's description without its position always was.
- Every investigation read loads the findings it holds, one query more.

## Walk-back options

- **If readers miss the held-back views**, show them at the zoom of the 1 km square, centred on the square, rather than not at all.
- **If unrelated investigations are used to publish protected places**, check saved views and profiles against every protected and restricted finding the writer sees exactly, not only those the investigation holds.

## Links

- Decision 0005 — sensitive findings are generalised by viewer.
- Decision 0009 — investigations are public, unlisted or private.
