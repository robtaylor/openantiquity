# Decision 0032 — What is drawn near a protected finding is judged against its whole shape

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of protected and restricted findings drawn as lines and areas many kilometres long, facing a guard on investigations that measured only from a finding's anchor point, we chose to measure the 1.5 km distance to the finding's whole line or area, so that a view or profile beside any part of a protected road is held back, accepting more held-back views along protected lines and a spatial test against shapes on every guarded read.

## Context

When this was written `sensitivity.hidden_near` and `PositionGuard.near` measured distance from `Finding.location` alone. Decision 0023, point 1, had them hold back a saved view or height profile within 1.5 km of any finding the reader doesn't see exactly. Every finding then was a point with at most a small outline near it, because `check_outline` refused an outline more than 0.05° across.

A shape finding keeps one anchor point (Decision 0030), and a line may run 600 km (Decision 0029). A height profile 1.4 km from a restricted road is beside the road even when the road's anchor is 30 km away. Measured from the anchor, that profile would be served exactly to a reader who sees the road only as its square, and the profile would say where the road runs.

The default level for the classes `road`, `trackway` and `linear` is open (Decision 0005), so most long lines aren't protected at all.

## Decision

1. A saved view's centre, a height profile's line and an investigation's area are judged by their distance to a protected or restricted finding's anchor or to its whole line or area, whichever is nearer. `hidden_near` tests `ST_DWithin` against `location` or `outline`, using the spatial index on `outline`, and `PositionGuard.near` measures to the exact shape. The distance stays 1.5 km.
2. This replaces point 1 of Decision 0023 in that one respect, what the distance is measured to. Points 2 to 8 of Decision 0023 stand as they were.

## Alternatives considered

- **Measuring from the anchor alone, as before** — rejected because a view or profile anywhere along a protected line more than 1.5 km from its anchor would be served exactly and would trace the line.

## Consequences

- No view or profile beside any part of a protected or restricted shape reaches a reader who sees that finding only as its square.
- More views and profiles are held back along protected lines than a point would hold back. Because linear classes default to open, this touches few findings.
- A long restricted line holds back views all along it. Moderators can hide a scribble made to do that, and closed shapes stop at 25 km across (Decision 0029).
- The guard's spatial test now runs against shapes as well as points, which needs the new index on `outline`.

## Walk-back options

- **If the test against full shapes is slow** — judge views against the simplified `outline_low` alone, which is accurate to about 35 to 55 m.
- **If readers miss the held-back views** — show them at the zoom of the 1 km square, centred on the square, as Decision 0023 already names as its walk-back.

## Links

- Decision 0023 — what is drawn near a protected finding is judged by distance and shown as whole squares. This record replaces the first point, as to what the distance is measured to.
- Decision 0005 — sensitive findings are generalised by viewer.
- Decision 0021 — what is written and drawn beside a protected finding is generalised for each reader.
- Decision 0029 — the limits on a shape's size.
- Decision 0030 — the anchor a shape finding keeps.
