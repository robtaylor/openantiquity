# Decision 0036 — Once a finding has second looks, what was looked at stays where it was

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings whose finder can move their points and extend their shapes after other people have given second looks, facing a finder who could carry a corroborated finding to ground nobody looked at and keep its step, we chose to move points one at a time and never a whole shape, and to refuse any edit that takes what was looked at more than 250 m from the finding, to keep a step on the ladder attached to the ground it was earned on, accepting that a finder can't remove or redraw the part of a finding that others have answered about without withdrawing it and marking again.

## Context

When this was written `PATCH /findings/{public_id}` let the finder replace a finding's point and outline with anything inside the British Isles. An edit left every second look standing and the tier where it was, and a move was recorded nowhere. So a finder could mark a spot, wait for others to confirm they could see a feature there, and then move the finding somewhere else with its step intact.

The plan for lines and curves raised this as an open question, and recommended refusing a move of more than 1 km once a finding had answers. Lines made the gap wider: Decision 0031 lets a finder extend a line as far as 600 km and keep its step, so a rule about the anchor alone could be walked round by extending a line to somewhere new and then deleting the part that was looked at.

The owner was asked on 2026-11-12 and replied: "I think the best thing here is that you can only move points, not the whole shape".

Moving every point in turn is a move of the whole shape by another route, so the rule also needed something the server could check.

## Decision

1. Nothing moves a whole shape. The drawing tool moves, adds and deletes single points, and has no action that carries a shape elsewhere. The API takes a path, and a change of `location` alone never carries a shape with it (Decision 0030).
2. A finding keeps the ground that second looks were given on: `findings.looked_at`, a geometry. When a second look is given, the finding's shape at that moment, or its point when it has no shape, is added to it.
3. While a finding has a `looked_at`, an edit is refused when any part of `looked_at` would be more than 250 m from the finding's new shape, or from its new point when it would have no shape. The refusal is 422 `looked_at_moved`.
4. Adding to a shape is always allowed, since what was looked at stays where it was. Moving a point is allowed while the shape still passes within 250 m of everything that was looked at.
5. Removing a shape, or the part of one that was looked at, is refused the same way. A finder who needs to do that withdraws the finding and marks it again, and the new finding starts at the first step.
6. The rule holds for a finding that is only a point: it can be moved up to 250 m from where it was when it was looked at.

## Alternatives considered

- **A cap on how far the anchor may move, at 1 km** — rejected because a line can be extended to anywhere and the looked-at part then deleted, which moves the finding without the anchor going far.
- **A cap on how far each point may move in one edit** — rejected because edits can be chained, each inside the cap.
- **Comparing each edit with the shape before it** — rejected for the same reason. `looked_at` only grows, so a chain of edits is held to the same ground as one.
- **Dropping second looks when a finding moves** — rejected because a finder could then wipe unwelcome answers by moving a finding, which is the reason Decision 0031 keeps them.
- **Leaving it alone** — rejected because a step on the ladder says other people saw a feature at this place.

## Consequences

- A finding's step stays attached to the ground it was earned on.
- A finder can't shorten a line past what others looked at, or redraw it somewhere else, without starting again at the first step.
- A marker placed 300 m out and already answered about can't be put right by its finder. They withdraw it and mark again.
- 250 m is a judgement. It allows putting points right against the terrain and keeps a finding on the feature people saw.
- `looked_at` stays when every second look on a finding is withdrawn, so the finding stays held to ground nobody now vouches for.
- An edit costs one more distance test, against one stored geometry.

## Walk-back options

- **If 250 m stops honest corrections** — raise it. It is one constant.
- **If finders need to shorten lines that were looked at** — let a moderator approve the change, recorded in `finding_shape_changes`.
- **If `looked_at` should follow withdrawn answers** — rebuild it from the shapes that the remaining answers saw, which `finding_shape_changes` and each answer's `shape_revision` allow.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Once looked at, it stays".
- Decision 0003 — the confidence ladder.
- Decision 0019 — answers and votes keep the weight they were given with.
- Decision 0030 — the anchor stays put while the shape grows.
- Decision 0031 — only the finder changes a shape, and extending keeps its step.
