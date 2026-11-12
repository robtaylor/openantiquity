# Decision 0033 — An open finding's shape isn't generalised when it passes near someone else's protected finding

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of open lines, such as Roman roads, drawn past protected barrows that other people marked, facing the question of whether such a line gives the barrow away, we chose to show an open finding's shape by its own level alone, as an open point finding is shown, to keep most roads visible to signed-out visitors, accepting that a line drawn to point at a protected finding says where it is until a moderator raises it.

## Context

When this was written a finding was generalised by its own sensitivity level and no other (Decision 0005). Nothing refused an open point finding placed on someone else's protected barrow, so a member could already mark that barrow's place openly. No frontend code drew a saved outline.

Lines change the size of the question. An open road drawn past somebody else's protected barrow shows the road, not the barrow. Nothing in the line says the barrow is there unless the line was drawn to point at it. Barrows line Roman roads.

The plan put this to the owner as an open question, with a recommended answer of no. They replied: "no".

## Decision

1. An open finding's line or area is shown by the finding's own level, to everyone who may see it exactly, whatever protected or restricted findings it passes near.
2. This is an accepted limit, the same one that already applies to an open point finding placed on a protected site.

## Alternatives considered

- **Generalising every open line near a protected finding** — rejected because it would hide most Roman roads from signed-out visitors, since barrows line them. It would also put a spatial guard on every finding read, list and map page.

## Consequences

- Open roads, trackways and boundaries are drawn in full for signed-out visitors.
- A line drawn on purpose to point at someone else's protected finding says where it is to anyone who may see the line, until someone notices it.
- Reads of findings, lists and map pages stay free of a test against other people's protected findings.
- The cost of changing this later is high, for the reasons that rejected it.

## Walk-back options

- **If open lines are used to point at protected sites** — moderators raise such a finding to protected or restricted, as Decision 0005 lets them. From then on, anyone who sees it only as its 1 km square gets no line.
- **If it happens often** — generalise an open line within 1.5 km of a protected finding, and accept the guard on every finding read and the roads it hides.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "An open line passing a protected finding", and open question 2.
- Decision 0005 — sensitive findings are generalised by viewer, each by its own level.
- Decision 0032 — what is drawn near a protected finding is judged against its whole shape.
