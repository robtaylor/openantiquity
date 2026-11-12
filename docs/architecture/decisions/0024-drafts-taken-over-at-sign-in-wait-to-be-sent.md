# Decision 0024 — Drafts taken over at sign-in wait to be sent

**Status:** Proposed.

**Current architecture:** [Frontend in the build contract](../../ARCHITECTURE.md#frontend).

<!--
Status words and their meaning: see README.md § Status legend.

This record is immutable once accepted. Only the Status line and the
Current architecture link change. When the code moves, edit the area doc.
When the decision changes, write a new record and archive this one:
  uv run docs/scripts/doctool.py archive docs/architecture/decisions/NNNN-<name>.md

Write the body in past tense, as the state at decision time. While this is
Proposed, open the Context with one line on what the code does today.
-->

**TL;DR.** In the context of a shared computer where one person leaves a tab open with drafts in it and the next signs in from that tab, facing those drafts being saved under the next person's name without anyone being asked, we chose to hold every draft taken over at sign-in until the person says to send it, so that nobody's work is published as someone else's, accepting one more press after signing in for the drafts a person made a minute before.

## Context

When this was written `adoptDraftsAfterSignIn` in `features/drafts/store.ts` took over the drafts a tab's visit had made signed out once a sign-in started and finished in that tab (Decision 0022). Findings and squares were then saved without asking, and only a second look was held until the person sent it.

A review of the security fixes on 2026-11-12 showed with a test against the real store that the case the first review began with was still open. Someone marks a finding signed out in a library or a family's browser and walks away leaving the tab open. Six hours later the next person signs in from that tab, and the finding is saved under their name and licence. A sign-in the first person started and abandoned did the same for whoever finished it. Decision 0022 had accepted this, since nothing in the browser can tell two people at one tab apart. The reviewer disagreed, because one question closes it.

## Decision

1. Every draft taken over at sign-in is `held`, whatever its kind, and is saved only when the person presses "Send" on it, or "Send all" in the drafts bar, or "Send it and see how it compares" on a second look's card.
2. The drafts bar says how many are waiting, and why: they were made in this tab before the sign-in, and someone else may have used it first.
3. Everything else in Decision 0022 stands: which drafts can be taken over, by which sign-in, and how other people's drafts are shown.

## Alternatives considered

- **Taking over only drafts made shortly before the sign-in started** was rejected because a person who walks away and the next who sits down within that window still share the drafts, and the window had to be long enough for someone to finish a draft and then sign in.
- **Asking the question as a dialog straight after the sign-in** was rejected because a dialog over the page the person came back to would hide the work they had signed in to save. The drafts bar and a toast with "Show" say it without blocking.
- **Keeping Decision 0022's rule** was rejected because it left the original case open whenever the tab was left open, which on a shared computer is usual.

## Consequences

- No draft is published under an account unless the person signed in to it says it is theirs.
- Decision 0002's "try before joining" now ends with one press after signing in, for findings and squares as well as second looks.
- The end-to-end tests that sign in with drafts waiting press "Send" as a person would.

## Walk-back options

- **If people miss the extra press and lose drafts**, open the drafts bar by itself after a sign-in that took drafts over, rather than only showing a toast.
- **If the hold puts people off joining**, send without asking a draft made after the sign-in started (on the page the provider returned to), and hold only those made before.

## Links

- Decision 0002 — accounts are required to save, and drafts carry work through sign-in.
- Decision 0008 — second looks are blind, and an answer is final.
- Decision 0022 — signed-out drafts belong to the tab that made them. This record replaces its fourth point.
