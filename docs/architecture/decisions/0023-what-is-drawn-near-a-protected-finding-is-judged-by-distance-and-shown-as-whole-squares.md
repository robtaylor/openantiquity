# Decision 0023 — What is drawn near a protected finding is judged by distance and shown as whole squares

**Status:** Proposed. Its first point is replaced by Decision 0030. Its sixth and seventh points no longer apply, because with the restricted level dropped (Decision 0032) everyone who adds or edits sees every finding exactly, so nothing is held back from a member's own items or an editor's view.

**Current architecture:** [Location sensitivity in the build contract](../../ARCHITECTURE.md#location-sensitivity).

<!--
Status words and their meaning: see README.md § Status legend.

This record is immutable once accepted. Only the Status line and the
Current architecture link change. When the code moves, edit the area doc.
When the decision changes, write a new record and archive this one:
  uv run docs/scripts/doctool.py archive docs/architecture/decisions/NNNN-<name>.md

Write the body in past tense, as the state at decision time. While this is
Proposed, open the Context with one line on what the code does today.
-->

**TL;DR.** In the context of investigations whose views, profiles, area, notes and links sit beside protected and restricted findings, facing a guard that a reviewer could undo by taking the finding item off, by drawing in another investigation, by setting the coarsened area beside the public square, or by a short link, we chose to judge what is drawn by its distance from every finding the reader doesn't see exactly, to count every finding an investigation has ever held for its text, to show a nearby area as whole 1 km grid squares, and to give a reference's link only when it is rebuilt from an identifier, so that nothing beside a finding says more than its square, accepting more held-back views and coarser areas, and one more query on every read.

## Context

When this was written `services.investigations.position_guard` built a `sensitivity.PositionGuard` from the findings an investigation held at that moment. The guard redacted its text, dropped a reference link only when `text_positions` found a position in it, held back a view or profile within 1.5 km of a held finding, and widened an area near one to cells of a 0.016° by 0.01° longitude and latitude grid. Decision 0021 had chosen this on 2026-11-11.

Two reviews of the security fixes on 2026-11-12 proved five ways round it:

- Taking the finding item off an investigation took the finding out of the guard, and the view centred on it was then served exactly on the page, in the GeoJSON and in the printable report.
- A view in an investigation that never held the finding wasn't guarded at all. Decision 0021 had accepted this.
- The longitude and latitude grid didn't line up with the OS grid. Set beside the finding's public 1 km square, the shown cell left half the square or less for the median position, and under a twentieth for one in a hundred.
- A reference's link was judged by pattern, so a short map link (`maps.app.goo.gl/...`), a plus code or a geohash link reached readers who saw only the square, while mention and evidence links followed `visible_url`, which keeps only an address rebuilt from an identifier.
- The activity feed served an investigation's title unguarded.

They also found that an editor who saw the text with `[position hidden]` in it, or the coarsened area, saved that back over what the owner had written, and that a member who owned an investigation lost their own saved views near someone else's restricted finding.

## Decision

1. What is drawn, a saved view's centre, a height profile's line and the area, is judged against every finding the reader doesn't see exactly (or, for a download, doesn't download exactly) within 1.5 km of it, whichever investigation holds that finding or none. A view or profile near one is held back as `near_protected`.
2. The text of an investigation, its title, summary, notes and every item's title and note, loses the positions written in it when the investigation holds or has ever held such a finding, or when anything drawn in it comes near one. `investigation_held_findings` records every finding ever added, and keeps it when the item is taken off.
3. An area near such a finding is shown, and matched by a box search, as the whole 1 km squares of the grid under it that its bounding box covers (`investigations.area_squares`, stored with the area). A finding's public square is one of those squares or none of them, so the two together never narrow it.
4. A reference's link goes to such a reader only when it is a DOI's or a video's address rebuilt from its identifier, as `sensitivity.visible_url` gives a mention's.
5. Every place that shows an investigation's title, the activity feed among them, takes it through the same guard.
6. What a member added themselves is shown to them as they made it.
7. An editor can't write what they were shown over what was stored. Sending a field back as shown leaves it alone. Text they edited around its placeholders keeps what each placeholder hid, and needs as many placeholders as they were shown. Any other change to a field shown with a place hidden in it, an area or a held-back view, is refused with 409 `held_back`.
8. `text_positions` reads text as a person sees it (NFKC, without format characters, a run of spaces as one), finds plus codes, and counts any link into a map site as a position. Its time is in proportion to the text's length.

Points 2 and 3 of Decision 0021, the rules for addresses attached to a finding and the refusal of a map link on a finding that isn't open, stand as they were.

## Alternatives considered

- **Keeping the guard on the findings held now** was rejected because taking an item off is ordinary curation, and it published everything drawn beside the finding.
- **Recording held findings without the distance rule** was rejected because a view drawn in another investigation, or in one that never held the finding, still said where it was.
- **The bounding box of the coarsened cell and the public square together** was rejected because the edge of the box that came from the cell still told a reader on which side of the cell's grid line the drawing, and so the finding, lay.
- **Showing no area to such a reader** was rejected because a parish's area near one barrow then disappears from the map and from searches altogether. Whole squares say nothing the square doesn't.
- **Refusing every save by an editor who sees something hidden** was rejected because it would stop them editing the parts they see whole, an owner's own notes among them. Merging is safe while the placeholders are counted: an editor who adds or takes one away can't say which hid what, so that save is refused instead.

## Consequences

- No reader learns more about a finding's place from what is drawn or written near it, in any investigation, than from the finding itself.
- More views and profiles are held back than before, for every investigation near a protected or restricted finding, not only those that hold it.
- Every investigation read, every list page and every feed page runs one more query, a spatial one on findings near what was drawn.
- A development database made before this needs `investigations.area_squares` added and filled, and `investigation_held_findings` filled from the items.
- A reference to a web page that isn't a DOI or a video shows only its citation to such readers.
- An editor who sees a finding only as its square edits notes holding its position around the placeholders, and can't remove one. Anyone who sees the finding exactly can.

## Walk-back options

- **If held-back views are missed**, show them at the zoom of the 1 km square, centred on the square, rather than not at all.
- **If the spatial query is slow on large investigations**, keep the drawn shapes' union with the investigation and test against that alone.
- **If editors need to remove a hidden position**, let them delete a placeholder on purpose, with a separate control that says what it does.

## Links

- Decision 0005 — sensitive findings are generalised by viewer.
- Decision 0009 — investigations are public, unlisted or private.
- Decision 0021 — what is written and drawn beside a protected finding is generalised for each reader. This record replaces its first point.
