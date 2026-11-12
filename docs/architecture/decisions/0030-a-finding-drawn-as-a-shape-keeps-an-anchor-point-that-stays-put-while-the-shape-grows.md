# Decision 0030 — A finding drawn as a shape keeps an anchor point that stays put while the shape grows

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings drawn as long lines that can be extended later, facing a required point that places every finding by one position, and a restricted line that someone seeing only its 1 km square must not be able to trace, we chose to keep the point as the finding's anchor, derive it from the shape when the line is drawn first, and leave it where it is while the shape grows, so that such a viewer sees one square for the finding's whole life, accepting an anchor that drifts away from the middle of a line extended at one end.

## Context

When this was written a finding's `location` was required, and the marking flow placed it before any outline. It anchored `location_public`, `grid_ref`, `nation`, the suggested title, the activity square and every `bbox` match. `PATCH /findings/{public_id}` could replace it, and `activity.relocate` then moved the finding's activity rows to the new square.

A finding drawn as a line first has no placed point, so the server has to choose one. A line can also be extended at either end later (Decision 0031). A viewer who sees a restricted finding only as its 1 km square sees the square that holds the point (Decision 0005).

The first idea was to put the point at the middle of the line and work it out again after every change.

## Decision

1. A finding keeps its required point, called its anchor. Everything that places a finding by one point goes on using it: `location_public`, `grid_ref`, `nation`, the suggested title, the activity square, the obscured square, search and suggested records.
2. When the finder places the point, it stays where they put it, and the shape must come within 1,000 m of it (Decision 0029).
3. When a `POST /findings` carries a path and no `location`, the server chooses the anchor. For a line it is the derived vertex nearest to half the line's length. For an area it is the centroid when that lies inside, and otherwise shapely's `point_on_surface`. `location_derived` records that the server chose it.
4. A derived anchor stays where it is while the new shape passes within 25 m of it. Extending a line at its ends never moves it, because the part of the line it sits on doesn't change.
5. When an edit takes the shape more than 25 m from a derived anchor, the anchor moves to the point on the new shape nearest to where it was, not to the new middle.
6. A placed anchor never moves by itself. An edit that takes the shape more than 1,000 m from it is refused with `outline_too_far`, and the finder moves the point.
7. When the anchor moves, `grid_ref`, `nation`, `location_public`, a suggested title and the activity rows follow, as they do when a finder moves a point.

## Alternatives considered

- **Working out the middle again after every change** — rejected because each new middle can fall in a new 1 km square. Someone who sees a restricted line only as a square would see a trail of squares along it, one for each extension.

## Consequences

- A viewer who sees a finding only as its square sees one square for its whole life, as for a point finding, however often the line is extended.
- After extensions at one end, the anchor and its marker sit far from the middle of the line. The marker names the tier and can be tapped wherever it is.
- Search and suggested records still start from the anchor, so records along the rest of a long line aren't suggested. That is left out of the first version.
- A reshape that moves the line away from its anchor moves the square, and a square-only viewer sees the finding move.
- A finder whose placed point is near one end of a line has to move the point before reshaping that end more than 1,000 m away.

## Walk-back options

- **If a drifting anchor confuses people** — let the finder place the anchor where they want it on a derived shape. `PATCH` already accepts a new `location`.
- **If suggested records along whole lines are wanted** — suggest from the shape for viewers who see it exactly, and keep the anchor for everyone else.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "The point a line finding keeps".
- Decision 0005 — sensitive findings are generalised by viewer to a 1 km square.
- Decision 0029 — the 1,000 m limit between a shape and a placed point.
- Decision 0031 — who may extend a shape.
