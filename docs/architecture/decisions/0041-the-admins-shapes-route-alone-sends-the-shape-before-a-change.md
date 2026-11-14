# Decision 0041 — The admins' shapes route alone sends the shape before a change

**Status:** Proposed.

**Current architecture:** [Findings, "Removing an orphaned marking"](../findings.md#removing-an-orphaned-marking).

**TL;DR.** In the context of an admin choosing which earlier shape to put back, facing a rule that no route sent the shape a marking had before a change, we chose one route for admins that sends those earlier shapes and to leave every other reader as they were, accepting that the rule now has an exception.

## Context

When this was written each change of shape stored the path before it, and no route sent it. The model said so. A reader of a finding was told that a change happened, when, of what kind, and how long the shape then was.

An earlier shape can hold parts since cut away, which the keeper chose to take off the map.

An admin removing an orphaned marking puts back an earlier revision (Decision 0040), and has to see the earlier shapes to choose one.

## Decision

1. `GET /mod/findings/{id}/shapes` sends each revision's shape, the path before each change included, to admins.
2. Anyone else, moderators included, is refused with a code that says only that the route is for admins.
3. No other route gained the earlier shapes. The timeline every other reader gets is as it was.

## Alternatives considered

- **Send earlier shapes to the keeper as well** — rejected because nothing a keeper does needs them, and it would widen who sees what was cut away.
- **Let the admin name a revision without seeing it** — rejected because an admin would be choosing blind which shape to put on the map.
- **Send only each earlier shape's simplified outline** — rejected because the put-back restores the full path, and the admin should see what will be restored.

## Consequences

- Admins see every shape a marking has had. They already see every finding exactly.
- The model's note that no route sends the earlier path now names this one.

## Walk-back options

- **If moderators take on removal** — the route follows the same check as the removal.
- **If earlier shapes are wanted on the page** — that is a new decision, since it shows every reader what a keeper took away.

## Links

- [Decision 0040](0040-an-admin-takes-back-an-orphaned-marking-s-shape-and-never-deletes-the-finding.md) — the removal this route serves.
- [Decision 0029](0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md) — what a change records.
- [Lines phase 2 plan](../../plans/lines-phase-2.md) — the design, the API's codes and the tests.
