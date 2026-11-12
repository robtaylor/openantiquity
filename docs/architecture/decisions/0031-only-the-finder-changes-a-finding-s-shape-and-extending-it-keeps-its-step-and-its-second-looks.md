# Decision 0031 — Only the finder changes a finding's shape, and extending it keeps its step and its second looks

**Status:** Proposed.

**Current architecture:** [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md).

**TL;DR.** In the context of findings drawn as lines that can be extended long after others have given second looks, facing the choice of who may extend a line and what an extension does to answers about its first part, we chose to let only the finder change a shape, to keep the tier and every answer at its weight, and to record each change and invite fresh looks at what was added, so that the ladder can't be reset by a change of shape, accepting that an answer about a road's first stretch counts for the whole road and that a viewer who hasn't answered learns that some answer came before a date.

## Context

When this was written `PATCH /findings/{public_id}` was the only route that edited a finding, and `findings.check_finder` let only the finder use it. It could replace `location` and `outline`. An edit left every second look standing and the tier where it was. Only a change of class reassessed. A move was recorded nowhere, except that `activity.relocate` moved the finding's activity rows to its new square. Nothing limited how far a finding with answers could be moved within the British Isles.

On 2026-11-12 the owner was asked whether other people could add to someone's line. They replied: "I think for a start lets keep them seperate for simplicity. We could add a way to 'join' multiple users work later, but this is best left until we actually hit the need."

They were then told the assumption that answers given before an extension stand, with the extension recorded and shown, and replied: "yes your assumption seems correct!"

Whether a reshape that moves points reviewers looked at is treated the same way was put to the owner as an open question, with a recommended answer of yes. They replied: "yes".

## Decision

1. Only the finder changes, extends or removes a finding's shape. Anyone else gets 403 `not_finder`. Joining different people's lines into one finding is left out until there is a need for it.
2. An edit sends the whole path with `path_revision`, which must equal the finding's `shape_revision`. Otherwise it is refused with 409 `shape_changed`, so an edit in one tab can't silently undo an extension made in another.
3. The server classifies each change as `drawn`, `extended`, `reshaped`, `closed`, `opened` or `removed`. It is `extended` when the old points appear unchanged and in order as one run inside the new path, the new path adds points only before or after that run, and `closed` is unchanged.
4. Every change raises `shape_revision` and writes a `finding_shape_changes` row. The row keeps the path before the change for moderators and for a later undo, and is never served whole.
5. A change of shape never reassesses. The tier, every answer and its weight stand, under Decision 0019's rule. Each answer stores the finding's `shape_revision` when it is given.
6. The finding page tells everyone who sees the finding exactly how much was added since the newest live second look, with a button that opens the map on the added part, and lists each change on its timeline.
7. An extension that leaves more than 200 m added since the last look adds the next step `look_at_new_part`. It appears in help wanted and in the review queue framed on the added part, never moves the tier, and clears when a second look is given after the extension.
8. A reshape is recorded and shown the same way, with the date it happened and no invitation, since nothing was added.
9. An extension records the activity `shape_extended` at the finding's square and notifies the finding's followers. Answerers aren't notified separately. The finder follows their own finding by default, and anyone who answered can follow it.
10. A viewer who sees the finding only as its square learns that the shape changed and when, and nothing of its size, kind or place.
11. People who may see answers under Decision 0010 also see which answers came before each change. Nobody else is told how many answers there were. "Added since the last second look" does tell a viewer who hasn't answered that some answer came before that date. This was weighed and accepted: the score already moves when answers come in, so that an answer exists isn't new to them, and the date adds only a little.

## Alternatives considered

- **Letting anyone extend a finding, or joining lines from different people** — not taken. The owner chose to keep each person's markings separate for simplicity and to add a join when there is a need for one.
- **Answers given before an extension stop counting** — rejected because a finder could then wipe unwelcome "can't see it" answers by adding a metre to a line.

## Consequences

- No change of shape moves the tier, the score or an answer's weight, so the ladder can't be reset by editing a line.
- An answer about a road's first stretch counts for the whole road. The owner accepted this, and `look_at_new_part` asks for looks at what was added.
- A viewer who hasn't answered learns that some answer came before a given date.
- This decision alone doesn't limit how far a finding with answers can be moved or reshaped. Decision 0036 does.
- A finder who edits in two tabs meets 409 `shape_changed` in the second and has to reload.

## Walk-back options

- **If extensions are used to carry a tier to ground nobody looked at** — drop answers older than a change from the assessment. Each answer's stored `shape_revision` allows it with no new data, for past changes too.
- **If people need to join their lines** — record a join as a new kind of change in `finding_shape_changes`.

## Links

- [Plan: lines and curves for marking findings](../../plans/lines-and-curves.md) — "Extending, and what it does to second looks", and open questions 1 and 3.
- Decision 0003 — the confidence ladder.
- Decision 0008 — second looks are blind.
- Decision 0010 — people who answered are named only to those who may see answers.
- Decision 0019 — answers and votes keep the weight they were given with.
- Decision 0030 — the anchor stays put while the shape grows.
- Decision 0036 — what was looked at stays where it was.
