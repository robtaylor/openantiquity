# Decision 0028 — A finding's shape is its tapped points under one fixed curve, within size caps, around an anchor that stays put

**Status:** Proposed.

**Current architecture:** [Findings, "Shapes"](../findings.md#shapes).

**TL;DR.** In the context of findings drawn as curved or straight lines and shapes, as long as a Roman road and extended later, facing outlines that can't be reopened, limits in degrees that refuse any long line, and a restricted line a square-only viewer mustn't trace, we chose to store the tapped points and derive the shape on the server with one named curve, to cap closed shapes at 25 km across and lines at 600 km, and to keep an anchor point that stays put, accepting a curve implemented twice and an anchor that drifts from a line's middle.

## Context

When this was written a finding's outline was straight segments between tapped corners, stored as any geometry with no index. Limits were in degrees: an outline more than 0.05° across was refused, which refuses any line longer than a few kilometres and means a different distance at each latitude. A finding's required point placed it for its grid reference, its public square and every map match. A viewer who sees a restricted finding only as its 1 km square sees the square that holds the point (Decision 0005).

On 2026-11-12 the owner asked for this: "I think interaction should be smooth curves *or* straight lines through tapped points, with the ability to make a closed curve/polygon by joining the end points - Think adobe illustrator type interaction. A line could be very long (e.g. if you mark all of Watling Street!) so it should be possible to add points to an existing marking."

Extending a shape a month later needs the tapped points and which were smooth, not a dense line of vertices. The browser would draw the curve as a preview and the server would store it.

The owner asked why a size limit was needed. An unlimited shape would be drawn in every map view it crosses, be "here" in every nearby list inside it, let a restricted scribble hold back every investigation view across a county under Decision 0023, cost about 800 KB per 50,000 vertices, and make a second look meaningless, since a 100 km enclosure can't be seen in one view. The owner replied: "Agreed we probably just shouldn't accept closed areas larger than 25km".

The caps were sized against Stanwick's ramparts at about 2.5 km, Watling Street at about 440 km, the Fosse Way at about 370 km and Ermine Street at about 320 km. These sizes are inferences from general knowledge, not measured.

## Decision

1. A finding's shape is stored as its path: the tapped points in order, each a corner or a smooth point, whether it is closed, and the name of its curve. The path is the source of truth, and an old outline reads as an all-corner path.
2. The server derives the stored and served geometry from the path with one curve, `catmull-rom-centripetal-1`, defined in [the findings area doc](../findings.md#the-curve-catmull-rom-centripetal-1). A segment depends only on its own ends and neighbours, so an extension never changes a segment more than one away from the new point. The browser's preview only has to look the same, and shared test vectors keep the two in step.
3. Another curve can only come in under a new name, and any path can be re-derived from its points.
4. A closed shape may be at most 25 km across. A line has no limit across and may be at most 600 km long, which leaves room for a line that wanders and a road followed into its continuation. A path may have at most 5,000 points and its derived shape at most 50,000 vertices. [The findings area doc](../findings.md#limits) lists them with their error codes.
5. A finding keeps a required point, its anchor, and everything that places a finding by one point goes on using it.
6. An anchor the finder placed never moves by itself, and the shape must come within 1,000 m of it. When a shape is drawn first, the server places the anchor near the middle of the line or inside the area, as [the findings area doc](../findings.md#the-anchor) sets out.
7. A derived anchor stays put while the shape still passes close to it, so extending a line never moves it. When an edit takes the shape away, the anchor moves to the nearest point on the new shape, not to the new middle, and the finding's square follows.

## Alternatives considered

- **The browser sends flattened geometry alone** — rejected because the smooth points would be lost and the path couldn't be reopened.
- **The browser sends both path and geometry** — rejected because the server would still derive the geometry to check them, the same work with one more way to be wrong.
- **Bézier handles** — left out of the first version. Because a path names its curve, they can come later under a new name.
- **No size limit** — rejected for the five reasons in the Context, which the owner agreed with.
- **One limit across for lines and shapes alike** — rejected because a cap that takes Watling Street would let an enclosure cover a county.
- **A density rule against scribbles** — not taken, since nothing yet shows it is needed.
- **Re-deriving the anchor as the middle after every change** — rejected because each new middle can fall in a new square, showing a square-only viewer a trail of squares along a restricted line.

## Consequences

- If the two curve implementations drift, only the preview changes. The server's geometry stays the truth.
- An old multi-part outline or polygon with holes, which only a hand-made request could have sent, can be replaced but not changed.
- Someone can still scribble 600 km back and forth inside one parish. That is left to moderation and the rate limits.
- A square-only viewer sees one square for a finding's whole life, however often its line is extended. A reshape away from a derived anchor moves the square, and that viewer sees it move.
- After extensions at one end, the anchor's marker sits far from the line's middle, and suggested records still start from it, so records along the rest of a long line aren't suggested.
- A finder whose placed point is near one end has to move it before reshaping the far end more than 1,000 m away.

## Walk-back options

- **If the curve must change or finders want handles** — define it under a new name and re-derive old paths only when next saved.
- **If a real feature is refused** — raise the constant. The frontend follows.
- **If dense scribbles appear** — add a rule on vertices per square kilometre and hide those already made.
- **If a drifting anchor confuses people** — let the finder place it on a derived shape.

## Links

- [Plan: lines and curves for marking findings](../../plans/archive/lines-and-curves.md) — the path, the curve, the limits, the anchor and the API contract.
- Decision 0005 — sensitive findings are generalised by viewer to a 1 km square.
- Decision 0023 — the 1.5 km privacy guard.
- Decision 0029 — who may change a shape, and what a change does to second looks.
- Decision 0030 — measuring the privacy guard to the whole shape.
