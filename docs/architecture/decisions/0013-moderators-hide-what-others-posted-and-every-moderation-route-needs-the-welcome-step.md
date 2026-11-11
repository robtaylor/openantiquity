# Decision 0013 — Moderators hide what others posted, and every moderation route needs the welcome step

**Status:** Proposed.

**Current architecture:** [Moderation in the build contract](../../ARCHITECTURE.md#moderation).

**TL;DR.** In the context of ten tracks built side by side, facing a mentions track that let a moderator delete someone else's mention with no reason and no log entry, we chose one rule for every kind of contribution: only its author deletes it, and a moderator hides it through `/mod` with a logged reason, so that the moderation log can't be skipped, accepting that a hidden mention keeps its row and its address on the finding for as long as it stays hidden.

## Context

The code today follows this record. When it was written, the second wave had just been combined. The moderation track had made only authors delete comments and evidence, and had moderators hide them through `/mod/{kind}/{id}/hide`, which needs a reason and writes a `moderation_actions` row. The mentions track, written beside it, let a moderator remove anyone's mention through `DELETE /mentions/{id}`, recorded only as `removed_by`, and made that removal block the address from being added again (`blocks_readding`). `tests/moderation/test_the_log_cannot_be_skipped.py` carried a row saying this broke the moderation rule.

The same review found that a moderator who had not finished the welcome step could read the report queue, the photo queue, the eligible list and the log, because the route table tied the welcome step to writes only. The welcome step is where a person accepts the contributor terms, which moderators act under.

Investigations held free text and members, but couldn't be reported or hidden.

## Decision

1. Only the person who added a mention removes it, through `DELETE /mentions/{id}`. A moderator, a mention found by the channel scan included, hides it through `/mod/mentions/{id}/hide` with a reason, and it is logged.
2. A hidden mention holds its address on the finding while it stays hidden, even after its adder removes it. Neither a member nor the scan can add that address to that finding again (`mention_hidden`). `removed_by` and `blocks_readding` went.
3. A hidden mention, like a hidden comment, is listed only for its adder and moderators, and leaves `mention_count` for everyone.
4. Investigations can be reported and hidden. A hidden one is found only by its members and moderators.
5. Everything under `/mod`, reads included, needs the welcome step. The route table in `tests/test_routes.py` says so of each read with `welcome`.
6. Every read route states in the route table how it leaves hidden things out, or why it holds nothing that can be hidden.

## Alternatives considered

- **Keeping a moderator's removal of mentions, and logging it** was rejected because it left two ways to take down someone else's work, one of them a delete that can't be undone, where comments and evidence have one way that can.
- **Freeing a hidden mention's address once its adder removes it** was rejected because the adder could then delete a hidden spam link and add it again, visible, at once.
- **Letting moderators read the queues before the welcome step** was rejected because the queues show reported content and personal notes, which a moderator reads under the terms that step accepts.

## Consequences

- The moderation log records every moderator action on someone else's work, with no exception left in the log test.
- A hidden mention's row stays for as long as it is hidden, so a hidden one that its adder removed can't be shown again, as with comments.
- A moderator who skipped the welcome step sees `onboarding_required` on every `/mod` route and has to finish it first.
- A new read route can't be added without saying how it treats hidden things.

## Walk-back options

- **If moderators need to free a hidden mention's address**, add an unhide that works on a removed mention, logged as any unhide is.
- **If the welcome step is ever split from accepting the terms**, tie `/mod` to the terms alone.

## Links

- Decision 0009 — no private channel; moderators can read unlisted investigations.
- Decision 0008 — second looks are blind, for moderators too.
