# Decision 0033 — A version passes over stored values a later one added

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Conventions"](../../ARCHITECTURE.md#conventions).

**TL;DR.** In the context of a live site whose deploys change the database first and swap the web machines afterwards, facing a version that answered 500 wherever it met an activity kind or a next step a later version had stored, we chose to have every version pass over the kinds and steps it has no name for, so that two versions can serve side by side and a deploy can be gone back from, accepting that the earlier version shows a feed and a finding without what the later one added.

## Context

When this was written a deploy ran `fieldclub-release` once, which changed the schema, and then replaced the web machines one at a time (`strategy = "rolling"` in `fly.toml`). For some minutes the earlier version served beside the later one, on a database the later one had already widened. Going back to an earlier image left every row the later version had written.

Enumerations were stored as text and read back strictly. An activity row's kind went through `ActivityKind(kind)` on its way into the feed, a notification and the event stream. A finding's stored assessment was decoded field by field, and a next step whose code wasn't in `NextStepCode` raised.

A review of the lines-and-curves branch on 2026-11-13 found that it added one activity kind and one next step. Had it been deployed over the version then live, one such row would have made that version answer 500 on the public feed, on followers' notifications, on the finding's own page and on the help-wanted list, during the swap and after any rollback. Nothing removed such rows on going back.

## Decision

1. A version lists no activity row and no notification whose kind it has no name for. The shared filter behind the feed, the notifications, the unread count and the event stream's check keeps only known kinds.
2. A version reads a stored assessment without the next steps it has no name for. Such a step is left out before any of its fields is read.
3. This covers the two vocabularies that grow when a feature is added: activity kinds and next steps. A new value in any other stored vocabulary, or a new field on a stored step, changes what an earlier version must understand, and takes a new `ASSESSMENT_VERSION` or a deploy of its own first.
4. The passing-over is deployed before the first version that needs it, so it goes to the live site ahead of lines and curves.

## Alternatives considered

- **Raising `ASSESSMENT_VERSION` for every new next step** — rejected because an earlier version reads an assessment of another version as none, and a saved finding is asserted to have one, so its page would still fail. It also does nothing for activity kinds.
- **Two deploys for every new value, the first only teaching readers its name** — rejected as the standing rule because it depends on someone remembering each time, and the cost of forgetting is a public page that answers 500.
- **Stopping every earlier machine before a later one starts** — rejected because the site would be down for part of every deploy, and going back would still meet the later version's rows.
- **Leaving the strict reading as it was** — rejected because one row took down pages for every reader, signed in or not.

## Consequences

- A deploy that adds an activity kind or a next step can run with both versions serving, and can be gone back from.
- An earlier version's feed and notifications are silently without the later version's rows, and its unread count doesn't count them. They show again when the later version is back.
- When an earlier version reassesses a finding it stores the assessment without the later step. The later version puts the step back the next time it assesses the finding, not before.
- Nothing is logged when a row is passed over. The database's own check on `activity.kind` refuses a kind the newest schema doesn't list, so an unknown kind can only have come from a later version.
- Tiers, states, strands, checks, feature classes and evidence kinds are still read strictly.

## Walk-back options

- **If another stored vocabulary starts to grow with features** — give it the same passing-over in the one place that decodes it, one deploy ahead of its first new value.
- **If rows passed over in silence hide a fault** — count them at start-up and log the count.

## Links

- Decision 0018 — hosting on Fly, where the release command and the rolling swap come from.
- Decision 0019 — answers and votes keep the weight they were given with, which is why a stored assessment is read back and not always worked out afresh.
