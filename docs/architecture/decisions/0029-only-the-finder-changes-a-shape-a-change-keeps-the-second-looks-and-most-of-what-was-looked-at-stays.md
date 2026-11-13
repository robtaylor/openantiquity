# Decision 0029 — Only the finder changes a shape, a change keeps the second looks, and most of what was looked at stays

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of shapes that can be extended and reshaped after others have given second looks, facing a finder who could reset the ladder or carry a corroborated finding to ground nobody looked at, we chose to let only the finder change a shape, keep every answer through any change, move points and never whole shapes, and refuse an edit that leaves less than three-quarters of what was looked at within 250 m, accepting that an answer about a road's first stretch counts for the whole road.

## Context

When this was written only the finder could edit a finding, and could move it anywhere in the British Isles. An edit left every second look and the tier standing, and a move was recorded nowhere. So a finder could wait for others to confirm a feature, then move the finding elsewhere with its step intact. Lines widen that gap: a line may run 600 km (Decision 0028), so it could be extended somewhere new and the looked-at part deleted, and moving every point in turn moves the whole shape.

The owner answered on 2026-11-12:

- On others adding to someone's line: "I think for a start lets keep them seperate for simplicity. We could add a way to 'join' multiple users work later, but this is best left until we actually hit the need."
- On answers before an extension standing, with the extension recorded and shown: "yes your assumption seems correct!" Asked whether a reshape is treated the same way: "yes".
- On how far a finding with second looks may move: "I think the best thing here is that you can only move points, not the whole shape".
- Told that this would stop a finder shortening a looked-at line: "I'd also suggest that users should be able to make small tweaks to points, e.g. shortening lines."

The owner later raised other people's changes as suggestions the owner accepts or declines, ownership that can be handed on, and a way for admins to remove orphaned markings that cause trouble. That isn't decided here. The owner confirmed it as a second phase with a plan of its own, in which "found by" stays the credit and "kept by" is who may change a marking.

## Decision

1. Only the finder changes, extends or removes a finding's shape. Joining different people's lines waits until there is a need. An edit names the revision it started from, so one tab can't silently undo another.
2. Every change is recorded with the path before it, where the shape had one, and is classed as an extension when the old points stay unchanged and in order with new points only at the ends.
3. A change of shape never moves the tier. The tier, every answer and its weight stand under Decision 0019, and each answer records the shape revision it saw. The finding is assessed again only so that it starts or stops asking for a look at a new part (point 4).
4. The finding page tells exact viewers how much was added since the second looks and lists every change. What was added is the part of the shape more than 250 m from what was looked at, measured from the ground and not from the kind of each change, so a nudged end with more line beyond counts and an extension later cut away doesn't. More than 200 m of it invites fresh looks without moving the tier. A change that stays within what was looked at is shown with its date and no invitation. A square-only viewer learns only that the shape changed and when.
5. Nobody but those who may see answers under Decision 0010 learns how many there were. "Added since the last second look" does tell other viewers that some answer came before a date. This was weighed and accepted, since the score already moves when answers come in.
6. The tool has no way to move a whole shape. It moves, adds and deletes single points. Until a second look stands the finder may still redraw the shape freely, as they could by withdrawing the finding and marking it again. From then on point 7 bounds every change, however it is sent.
7. The finding keeps the ground its second looks were given on, which only grows. An edit must keep every looked-at point, and at least three-quarters of the looked-at length, within 250 m of the new shape. The mechanics are in the plan's section "Once looked at, most of it stays".
8. So a finder may extend anywhere, move points, shorten a looked-at line by up to a quarter, and move a point-only finding up to 250 m. Anything more means withdrawing the finding and marking it again from the first step.

## Alternatives considered

- **Letting anyone extend a finding, or joining lines** — not taken. The owner kept each person's markings separate.
- **Answers before a change stop counting** — rejected because a finder could wipe unwelcome answers by adding a metre to a line.
- **A 1 km cap on moving the anchor** — rejected because a line can be extended elsewhere and its looked-at part deleted.
- **Counting only the changes classed as extensions** — rejected because a strict classifier calls a nudged end with 20 km more a reshape, which the one-flow drawing tool makes the usual case, and kept counting an extension after it was cut away.
- **A cap per edit, or comparing each edit with the last** — rejected because edits can be chained. The looked-at ground only grows, so a chain is held as one edit is.
- **Holding all of what was looked at within 250 m** — rejected after the owner asked that shortening a line stay possible.
- **Leaving moves alone** — rejected because a step on the ladder says others saw a feature at this place.

## Consequences

- An answer about a road's first stretch counts for the whole road. The owner accepted this, and the invitation asks for looks at what was added.
- The quarter is spent over the finding's life, not per edit, because the looked-at ground doesn't shrink.
- A marker placed 300 m out and already answered about can't be put right by its finder, who has to mark it again.
- 250 m and three-quarters are judgements, which the owner agreed. They allow fixing points against the terrain and trimming a line.
- The looked-at ground stays when every second look is withdrawn, so a finding stays held to ground nobody now vouches for.
- Only the finder can change a marking, so a finding whose finder has left can't be changed until the later plan for suggestions and ownership lands.

## Walk-back options

- **If extensions carry a tier to ground nobody looked at** — drop answers older than a change from the assessment, using the revision each answer stored.
- **If people need to join lines** — record a join as a new kind of change.
- **If 250 m or three-quarters stops honest corrections** — raise it. Each is one constant.
- **If others need to change a marking** — take up the owner's idea of suggestions, transferable ownership and admin removal in a plan of its own. The change record already says who made each change.
- **If the looked-at ground should follow withdrawn answers** — rebuild it from the shapes the remaining answers saw.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Extending, and what it does to second looks", "Once looked at, most of it stays" and "Left out of the first version".
- Decision 0003 — the confidence ladder.
- Decision 0008 — second looks are blind.
- Decision 0010 — people who answered are named only to those who may see answers.
- Decision 0019 — answers and votes keep the weight they were given with.
- Decision 0028 — the path, its limits and the anchor.
