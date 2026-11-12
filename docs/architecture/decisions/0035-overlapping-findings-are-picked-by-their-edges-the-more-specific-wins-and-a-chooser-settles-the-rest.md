# Decision 0035 — Overlapping findings are picked by their edges, the more specific wins, and a chooser settles the rest

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of a map where points sit inside enclosures, roads cross and roads run through field systems, facing taps that today hit only a marker under the exact tap position, we chose to pick areas by their edges, to let markers beat lines and lines beat area edges, to open a chooser when two candidates are alike, and to keep the Explore list as the keyboard route, so that every finding stays reachable and a tap never guesses between equals, accepting that a road hides the edge of a field system it crosses.

## Context

When this was written `findingPointAt` in `map/findingHits.ts` asked MapLibre for rendered finding points at the exact tap position, with no tolerance, and Explore opened the first. Findings won over records. An obscured square was an outline only, and a square holding several obscured findings brought Explore to it (`ExploreLayer.tsx`). While marking, taps belonged to the mark tool. No saved line or area was drawn on the map.

Once findings are drawn as lines and areas they overlap. On 2026-11-12 the owner asked: "how do users select when there are overlapping shapes?" They were offered these rules: pick by the edge, the more specific wins, a chooser for what remains, a hover hint on a computer, a wider reach for a finger, and the Explore list for the keyboard. They replied: "that all sounds very sensible, lets record and go ahead with that".

Fitting the rules to the code showed one gap. "The smaller of two alike wins" gives no test for when two candidates are alike enough that the chooser should open.

## Decision

1. An area is picked by its edge, never its inside, so a point or record inside a large area stays reachable.
2. Candidates are finding markers, lines and area edges within reach of the tap: 6 px for a mouse or pen and 16 px for a finger, chosen from `PointerEvent.pointerType` and queried as a box round the tap. A marker under the pointer is always in reach, as before.
3. Markers beat lines, and lines beat area edges. Among candidates of the same kind the smaller wins: the shorter line, or the area with the smaller extent.
4. The smaller wins only when it is clearly smaller, under half the other's length or extent. Two roads crossing, or two markers within a finger's reach, are alike, and they open the chooser.
5. The chooser says how many findings are there and lists each with its tier badge, class and title, in the order above. Hovering or focusing an entry highlights that shape on the map. It's a popover beside the pointer on a computer and a short sheet on a phone that never covers the spot tapped. It holds at most 8 entries and then "Show all in Explore". Arrow keys move through it, Enter opens an entry, and Escape closes it and returns focus to the map.
6. On a computer, a frame-throttled query highlights what a click would open as the pointer moves, or says how many findings a click would offer.
7. Findings still win over records, and records behave as before when no finding is in reach. Obscured squares are unchanged and aren't candidates.
8. The Explore list stays the keyboard route to every finding in view. Focusing an entry highlights its shape.
9. While drawing, taps belong to the drawing tool and other findings don't take them. The finder's own points are picked by their handles, the nearest handle winning where several are in a finger's reach, and "Previous point" and "Next point" reach the rest.

## Alternatives considered

- **Picking an area anywhere inside it** — rejected because a point or record inside a large area would then be out of reach.
- **"The smaller of two alike wins" with no threshold** — rejected because between two crossing roads or two close markers a silent choice would be a guess. The half-size test keeps the owner's rule and gives "more than one candidate remains" a definite meaning.
- **Opening the chooser for every overlap** — not taken, because the owner chose that the more specific candidate wins when one is clearly more specific.

## Consequences

- Every finding stays reachable by a tap, by its anchor marker, by zooming in, or by the Explore list.
- A road drawn through a field system wins over the field system's edge. The field system stays reachable by its anchor marker, which every shape finding keeps (Decision 0030), and on a computer the hover hint names what else is in reach.
- A finger and a mouse at the same spot can open different things, because their reach differs.
- Hover runs a query on each frame the pointer moves on a computer.
- The chooser is a new component on both a computer and a phone.

## Walk-back options

- **If the chooser opens too often** — narrow the finger's reach or lower the half-size threshold, and measure how often it opens.
- **If people miss an area they tapped inside** — show the hover hint and the chooser's entries for areas whose inside was tapped, without letting them beat anything at their edge.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Picking one of overlapping shapes".
- `docs/UI.md` — the rule that a phone sheet never covers the place being looked at.
- Decision 0030 — the anchor marker every shape finding keeps.
