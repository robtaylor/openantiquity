# Decision 0028 — A finding's shape is stored as the points its finder tapped, and the server derives it with one fixed curve

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings to be drawn as straight or curved lines and closed shapes and extended later, facing a stored outline that keeps only straight corners and can't be reopened as it was drawn, we chose to store the points the finder tapped, each a corner or a smooth point, and to have the server derive the shape from them with one named curve checked against shared test vectors, so that a shape can be reopened, changed and extended and every reader gets the same geometry, accepting a curve that two code bases must implement alike.

## Context

When this was written a finding's outline was a run of straight segments between tapped corners. `MarkForm.tsx` had an optional Outline step after the point was placed. Taps added corners, a tap within 14 px of the first corner closed the shape, and "Finish as a line" ended it open. `findings.outline` held any geometry, with no spatial index, and `OUTLINE_TYPES` allowed `Polygon`, `MultiPolygon`, `LineString` and `MultiLineString`. Every outline the interface had ever sent was a `LineString` or a single-ring `Polygon`. Nothing checked that a polygon was valid, and no frontend code drew a saved outline.

On 2026-11-12 the owner asked for this: "I think interaction should be smooth curves *or* straight lines through tapped points, with the ability to make a closed curve/polygon by joining the end points - Think adobe illustrator type interaction. A line could be very long (e.g. if you mark all of Watling Street!) so it should be possible to add points to an existing marking."

A shape that can be extended has to be reopened as it was drawn. A finder adding to a road a month later needs the points they tapped and which of them were smooth, not a dense line of vertices. Two programs would draw the same curve: the browser, as a preview while the finder drew, and the server, which would store and serve it.

## Decision

1. A finding's shape is stored as its path in `findings.path`: the tapped points in order, each a `corner` or a `smooth` point, whether the path is closed, and the name of its curve. The path is the source of truth.
2. The server derives the stored geometry from the path. An open path becomes a `LineString` and a closed one a one-ring `Polygon`, in `findings.outline`, with two simplified copies beside it for lower zooms. The server's geometry is what is stored and served. The browser's preview only has to look the same.
3. The curve is `catmull-rom-centripetal-1`. It is a centripetal Catmull–Rom spline in the Barry–Goldman form. A segment between two corners is straight, a corner or an open end gets a phantom neighbour so the curve leaves it heading for the next point, each segment is projected with a scale set by its own mid latitude, and each segment is sampled in 2 to 16 steps, about one every 33 m. The full definition is in the plan.
4. Only a segment's own two ends set its projection, so extending a path never changes a segment more than one away from the new point.
5. A request may leave out the curve's name and the server writes it. A request naming any other curve is refused with 422 `unknown_curve`. A later curve can be added under a new name, and every path can be re-derived from its points.
6. One file of test vectors, `docs/architecture/curve-vectors.json`, is read by a pytest test and a Vitest test. They compare to 1e-7 degrees and don't need byte equality.
7. An old `LineString` or one-ring `Polygon` outline is read as an all-corner path, which derives to the shape that was stored.

## Alternatives considered

- **The browser flattens the curve and sends the geometry alone** — rejected because the smooth and corner points would be lost, so the path couldn't be reopened or extended.
- **The browser sends both the path and its flattened geometry** — rejected because the server would still have to derive the geometry to check that the two agreed. That is the same work with one more way to be wrong.
- **Keeping the stored outline as the only record** — rejected because a list of vertices can't say which points were smooth, which is the owner's request.
- **Bézier handles that the finder drags** — left out of the first version. A smooth point takes its curve from its neighbours alone. Because a path names its curve, handles could come later under a new name.

## Consequences

- A finder can reopen, change and extend a shape, and an old outline opens in the same tool.
- Every reader gets the server's geometry. If the two implementations drift, only the preview changes.
- The curve exists twice, in Python and in TypeScript, and the shared vectors are the only thing that keeps them in step.
- Each finding with a shape stores its path, the derived geometry and two simplifications.
- A stored shape can only be something the curve produces. An old `MultiLineString`, `MultiPolygon` or polygon with holes, which only a hand-made request could have sent, can be replaced in the tool but not changed. Several parts and holes are left out of the first version.

## Walk-back options

- **If the preview and the stored shape visibly differ** — add the path that shows it to the vectors and fix whichever side is wrong. The server's geometry stays the truth.
- **If the curve has to change, or finders ask for handles** — define it under a new name, keep old paths on the old name, and re-derive them only when they are next saved.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — the full curve definition, the path's JSON and the API contract.
- Decision 0029 — the limits on a path and its derived shape.
- Decision 0030 — the anchor point a shape finding keeps.
