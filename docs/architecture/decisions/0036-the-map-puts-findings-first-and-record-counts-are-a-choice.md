# Decision 0036 — The map puts findings first, and record counts are a choice

**Status:** Proposed.

**Current architecture:** [UI.md, "Markers"](../../UI.md#markers).

**TL;DR.** In the context of a map that had just gone live with heritage records drawn at every zoom and findings only from zoom 9, facing an owner who found the zoomed-out view busy with records and empty of findings, we chose to draw findings at every zoom with markers that stand out, to draw records only from zoom 12 where they are single records, and to make the zoomed-out counts of records a switch that starts off, so that the map shows first what people have found, accepting that someone zoomed out sees no sign of the records unless they ask.

## Context

When this was written the findings overlay asked the server for nothing below zoom 9. The reason given in the code was that a county-wide view held more than a map of markers could show and more than the server should be asked for on every drag. The records overlay drew at every zoom: counts of records by area below zoom 12, as numbered squares every sixty pixels or so, and single records from zoom 12. So the view of the country was a grid of record counts, most of them counting listed buildings, with no findings on it.

Findings were already drawn above records. They didn't read that way. A finding at the first tier was a small grey circle, and its line or area a thin grey shape, while records were squares in saturated category colours.

On 2026-11-13 the owner, using the live site, said: "I think it would be good to front findings over heritage records. at the moment finding dissapear after a certain zoom. The heritage records on by default make the view quite busy." He was torn between switching records off by default and grouping them more coarsely. He agreed to what is decided here when it was proposed.

The site then held a handful of findings. The server answered at most 500 for a box, and said when there were more.

## Decision

1. Findings are drawn on the map, and listed in Explore, at every zoom. When the answer for the map is cut short the map says so, and says that zooming in shows the rest.
2. A finding's marker is larger and has a light ring inside its dark outline, and a record's square is smaller and fainter. Shape, not size or colour, still tells the two apart.
3. Records are on by default and drawn from zoom 12, where a tile holds single records.
4. The counts of records by area, which a tile holds further out, are drawn only while a switch in the Layers panel is on. It starts off, and the address carries it so a shared link keeps it.
5. A tile at zoom 12 or closer that holds too many records to send carries counts in their place. Those are always drawn while records are on, switch or no switch, or a town centre would show no records at any zoom.
6. The two kinds of count come from two sources over the same tiles, one that never asks for a tile further out than zoom 12 and one that never asks for a closer one, because a layer chosen by the map's zoom alone drew far tiles' counts in a tilted view.

## Alternatives considered

- **Records off by default** — rejected because records are wanted exactly when someone is zoomed in asking whether a thing is already known, and a newcomer wouldn't find the switch.
- **Coarser grouping of the counts** — rejected because fewer, bigger numbers still cover the country with a figure that says little: there are records everywhere.
- **Keeping the zoom 9 rule and drawing counts of findings below it** — rejected for now because it needs the server to count findings by area as it does records. With the findings there are, the plain answer serves.
- **Marking busy counts on the server and filtering on the mark** — rejected because two sources over the same tiles needed no change to the tiles or their cached copies.

## Consequences

- The view of the country shows findings and no records. Someone who wants to see where records are thick turns the counts on.
- With records on and counts off, nothing of the records shows further out than zoom 12, and no record tile is asked for there. The Layers panel says records are shown from closer in.
- A view that holds more findings than one answer carries draws 500 of them and says so. That will be the usual case zoomed out once findings number in the thousands.
- Every drag of a zoomed-out view asks for the findings in view. The box asked for is snapped to coarser steps the further out the map is, so small drags ask for the same box.
- A shared link made before this, which names a place or a view, opens with counts off.

## Walk-back options

- **If zoomed-out views often hold more findings than are drawn** — have the server count findings by area, as the record tiles do, and draw counts where the answer would be cut short.
- **If people miss the records when zoomed out** — start the switch on, which is one default.
- **If the larger markers crowd where findings are dense** — bring the sizes back towards the old ones below a zoom, keeping the ring.

## Links

- Decision 0031 — how overlapping findings are picked, which the larger markers leave as it was.
- [Findings](../findings.md) — how findings are drawn on the map.
