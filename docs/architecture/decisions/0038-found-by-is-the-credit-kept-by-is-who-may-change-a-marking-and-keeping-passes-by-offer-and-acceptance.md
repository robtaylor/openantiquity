# Decision 0038 — Found by is the credit, kept by is who may change a marking, and keeping passes by offer and acceptance

**Status:** Proposed.

**Current architecture:** [Findings, "Keeping and suggestions"](../findings.md#keeping-and-suggestions).

**TL;DR.** In the context of findings whose finder alone could change them, facing markings that outlive their finder's interest and other people who want to improve them, we chose to split the finder's credit from a keeper's right to edit and to pass keeping on by an offer the other person takes up, accepting that a marking whose keeper's account goes is left with nobody to change it until an admin acts.

## Context

When this was written only the finder could change a finding's shape or its words (Decision 0029, point 1), and nothing let them pass that on.

The owner decided the outline. Someone else's change is a suggestion the marking's keeper accepts or declines. A marking can be handed on. "Found by" is the credit and never changes, and "kept by" is who may edit and is what transfers. Keeping covers the whole edit, so a new keeper changes the title, the description, the kind of feature and the period as well as the shape, and the finder keeps only withdrawing. When a keeper's account is deleted the marking is orphaned and the admins are told: "lets just orphan, and alert the admin".

A deploy changes the schema before it swaps the machines, so an earlier version serves beside this one for some minutes and can be gone back to.

## Decision

1. A finding has a keeper, `findings.keeper_id`. Null means its finder keeps it, so no existing row was changed and a version that doesn't know the column goes on working.
2. The keeper may change everything an edit changes. The finder keeps the credit, withdrawing, seeing the finding while it is hidden, raising its level and exact downloads. A keeper who isn't the finder sees a hidden finding no more than any member does.
3. Keeping passes by an offer and its acceptance. A finding holds one offer at a time, and a new one replaces it. Nobody is made a keeper unasked.
4. An offer to a banned account, a deleted one and a handle nobody has are answered alike, so an offer can't be used to learn who is banned.
5. When a keeper's account is deleted, every marking it kept is orphaned, whether or not its finder is still a member, and each admin is told once how many. A ban changes nothing stored about what the person keeps, and lifting it gives that back. A ban clears every offer made to the person, so it reads to a keeper as a refusal, and lifting it clears any offer made meanwhile on what that person keeps.
6. An admin may offer an orphaned marking to any member. Nothing sent to anyone but an admin says a marking is orphaned, since that would say its keeper is banned.
7. A keeper who isn't the finder can't give a second look on the marking they keep, as the finder can't on their own finding. This was added after review and put to the owner.
8. Every route for keeping answers "not found" to anyone who can't see a hidden finding, and never a code that says it is hidden.

## Alternatives considered

- **Keeping goes back to the finder when the keeper's account is deleted** — put to the owner, who chose to orphan and tell the admins.
- **Hand a marking over without the other person's agreement** — rejected because keeping is a duty, and a handle typed wrongly would give it to a stranger.
- **Fill `keeper_id` for every existing finding** — rejected because an earlier version doesn't know the column and would leave it stale on its own edits. Null meaning the finder needs no backfill.
- **Say on the page that a marking has no keeper** — rejected because it tells every reader that the keeper is banned or gone.

## Consequences

- A finder who hands a marking on can no longer change it, and can still withdraw the finding.
- An orphaned marking can't be changed by anyone until an admin offers it and someone takes it up.
- A keeper can't change the note on a second look they gave before they took the marking on, since the rule that refuses a new answer guards changing one too.
- An earlier version doesn't know keepers. While it serves, or if a release is gone back, a finder can again edit a marking they handed on and its keeper can't. Nothing is sent to anyone who shouldn't see it.

## Walk-back options

- **If the owner prefers a keeper to give second looks** — take the keeper out of the check on answering. Nothing stored changes.
- **If orphaned markings pile up** — let keeping fall to the finder when they are still a member, which the owner weighed.
- **If offers are used to pester** — an offer already tells its person only once while unread. Limit who may be offered to people who follow the finding.

## Links

- [Decision 0029](0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md) — its point 1, that only the finder changes a shape, is replaced by this record. Its other points stand.
- [Decision 0005](0005-sensitive-findings-are-generalised-by-viewer.md) — who sees a protected finding's place.
- [Decision 0033](0033-a-version-passes-over-stored-values-a-later-one-added.md) — what an earlier version does with what a later one stored.
- [Lines phase 2 plan](../../plans/lines-phase-2.md) — the design, the API's codes and the tests.
