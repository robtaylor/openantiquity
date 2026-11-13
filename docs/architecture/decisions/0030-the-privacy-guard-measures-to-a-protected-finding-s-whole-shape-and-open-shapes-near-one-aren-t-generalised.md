# Decision 0030 — The privacy guard measures to a protected finding's whole shape, and open shapes near one aren't generalised

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings drawn as lines and areas many kilometres long, facing a guard on investigations that measured only from a protected finding's anchor, and open roads drawn past barrows other people protected, we chose to measure the 1.5 km guard to a protected finding's whole shape and to show an open finding's shape by its own level alone, so that no view beside a protected road reaches a square-only reader and most roads stay visible to signed-out visitors, accepting more held-back views along protected lines and a line drawn to point at a protected finding saying where it is until a moderator raises it.

## Context

When this was written `sensitivity.hidden_near` and `PositionGuard.near` measured distance from `Finding.location` alone. Decision 0023, point 1, had them hold back a saved view or height profile within 1.5 km of any finding the reader doesn't see exactly. Every finding then was a point with at most a small outline near it, because `check_outline` refused an outline more than 0.05° across.

A finding was generalised by its own sensitivity level and no other, and the default level for the classes `road`, `trackway` and `linear` is open (Decision 0005). Nothing refused an open point finding placed on someone else's protected barrow, so a member could already mark that barrow's place openly. No frontend code drew a saved outline.

A shape finding keeps one anchor point, and a line may run 600 km (Decision 0028). A height profile 1.4 km from a restricted road is beside the road even when the road's anchor is 30 km away. Measured from the anchor, that profile would be served exactly to a reader who sees the road only as its square, and the profile would say where the road runs.

An open road drawn past somebody else's protected barrow shows the road, not the barrow. Nothing in the line says the barrow is there unless the line was drawn to point at it. Barrows line Roman roads. The plan asked the owner on 2026-11-12 whether to generalise such lines, as an open question with a recommended answer of no. They replied: "no".

## Decision

1. A saved view's centre, a height profile's line and an investigation's area are judged by their distance to the anchor, or to the whole line or area, of a finding the reader doesn't see exactly, whichever is nearer. `hidden_near` tests `ST_DWithin` against `location` or `outline`, using the spatial index on `outline`, and `PositionGuard.near` measures to the exact shape. The distance stays 1.5 km. A finding a moderator has hidden takes no part (Decision 0032, point 5).
2. This replaces point 1 of Decision 0023 in that one respect, what the distance is measured to. Points 2 to 8 of Decision 0023 stand as they were.
3. An open finding's line or area is shown by the finding's own level, to everyone who may see it exactly, whatever protected findings it passes near. This is an accepted limit, the same one that already applies to an open point finding placed on a protected site.

## Alternatives considered

- **Measuring from the anchor alone, as before** — rejected because a view or profile anywhere along a protected line more than 1.5 km from its anchor would be served exactly and would trace the line.
- **Generalising every open line near a protected finding** — rejected because it would hide most Roman roads from signed-out visitors, since barrows line them. It would also put a spatial guard on every finding read, list and map page.

## Consequences

- No view or profile beside any part of a shape reaches a reader who sees that finding only as its square.
- More views and profiles are held back along protected lines. Because linear classes default to open, this touches few findings.
- A long line holds back views all along it from every reader who sees it only as its square. Moderators can hide a scribble made to do that, and closed shapes stop at 25 km across (Decision 0028).
- The guard's spatial test now runs against shapes as well as points, which needs the new index on `outline`.
- Open roads, trackways and boundaries are drawn in full for signed-out visitors.
- A line drawn on purpose to point at someone else's protected finding says where it is to anyone who may see the line, until someone notices it.
- Reads of findings, lists and map pages stay free of a test against other people's protected findings, and adding one later would cost what rejected it.

## Walk-back options

- **If the test against full shapes is slow** — judge views against the simplified `outline_low` alone, which is accurate to about 35 to 55 m.
- **If readers miss the held-back views** — show them at the zoom of the 1 km square, centred on the square, as Decision 0023 already names as its walk-back.
- **If open lines are used to point at protected sites** — moderators raise such a finding to protected, as Decision 0005 lets them. From then on, anyone who sees it only as its 1 km square gets no line.
- **If that happens often** — generalise an open line within 1.5 km of a protected finding, and accept the guard on every finding read and the roads it hides.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Sensitivity: every place a shape leaves".
- Decision 0023 — what is drawn near a protected finding is judged by distance and shown as whole squares. This record replaces the first point, as to what the distance is measured to.
- Decision 0005 — sensitive findings are generalised by viewer, each by its own level.
- Decision 0021 — what is written and drawn beside a protected finding is generalised for each reader.
- Decision 0028 — the anchor a shape finding keeps and the limits on a shape's size.
