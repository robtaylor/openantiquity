# Decision 0039 — Other people's changes to a marking are suggestions its keeper accepts or declines

**Status:** Proposed.

**Current architecture:** [Findings, "Suggestions"](../findings.md#suggestions).

**TL;DR.** In the context of markings only their keeper may change, facing other members who can see a line runs further or sits wrongly, we chose suggestions kept in a table of their own that the keeper accepts or declines, held to the same rules as an edit and shown only to signed-in members, accepting that every improvement waits on one person.

## Context

When this was written someone who wasn't a finding's finder had no way to propose a change to its line or shape. They could comment, or mark a finding of their own beside it.

The owner decided that someone else's change is a suggestion the keeper accepts or declines, and that joining different people's lines into one finding waits until there is a need. The second phase wasn't to change how the first was built.

A finding keeps the ground its second looks were given on, and an edit must keep most of it (Decision 0029). Second looks are blind (Decision 0008), and who answered, and when, is kept from other members (Decision 0010).

## Decision

1. A suggestion is a whole proposed path, stored in `shape_suggestions` with the revision it was made on. It isn't a row of the table of changes with a state: that table is unique on the revision a change made, which a pending suggestion doesn't have, and every reader of it would have needed a new filter.
2. Any member who sees the finding exactly may suggest, except its keeper. A person has one pending suggestion on a finding, and a new one replaces it. A finding holds at most 20 pending, and a member makes at most 30 an hour.
3. A suggestion is held to the limits of an edit when it is made. It is held to the looked-at rule only when the keeper accepts it, and one that breaks the rule then is refused and stays pending.
4. The keeper may accept a suggestion made on an earlier shape. The request names the revision the keeper was shown, so a change made while they looked is refused, and accepting replaces the changes since.
5. An accepted change names who suggested it and tells the finding's followers. Declining carries no reason, since a notification carries none (Decision 0009).
6. Pending suggestions are sent only to signed-in members who see the finding exactly, on open findings too. The public sees a suggestion only once it is accepted and part of the shape.
7. A suggester isn't sent the ground second looks covered, and making a suggestion doesn't test it against that ground. Any member may suggest, so even an answer of yes or no, to shapes sent one after another, would map it. The keeper, who may see that ground, is told how much would be left when an accept is refused.
8. A banned or deleted person's pending suggestions leave every list and count and can't be accepted. A decided suggestion is "not found" to anyone but its suggester and the keeper.
9. A replaced suggestion doesn't tell the keeper again while their notification of the earlier one is unread.

## Alternatives considered

- **Anyone may change any marking, with a history to go back through** — set aside by the owner's decision that a change by someone else is a suggestion.
- **A pending change as a row in the table of changes** — rejected for the reasons in point 1. It would have changed how the first phase was built.
- **Show pending suggestions to everyone on an open finding** — rejected because they are unreviewed, and nothing a signed-out reader does needs them.
- **Check a suggestion against the looked-at ground when it is made** — built first, answering with how much would be left and then with one fixed message, and rejected in review for the reason in point 7.
- **Only suggestions made on the current shape may be accepted** — rejected because a keeper who tidies a line would void every suggestion waiting on it.

## Consequences

- An improvement waits on the keeper. A marking whose keeper is away gathers suggestions nobody decides, up to the cap.
- A suggester isn't told when their suggestion can't be accepted. The keeper finds out on accepting it, and declines it.
- The hourly limits are counted on each machine, so the real ceiling is the figure times the machines serving.
- A signed-out reader of a protected finding sees an accepted suggestion only as the date of a change.

## Walk-back options

- **If suggestions go undecided** — let a suggestion lapse after a time, or tell an admin of a keeper who has many waiting.
- **If suggestions that can't be accepted waste keepers' time** — tell the suggester after the keeper's refused accept, which tells them once and only by the keeper's act.
- **If joining lines is needed** — that is a new plan, as the owner said.

## Links

- [Decision 0038](0038-found-by-is-the-credit-kept-by-is-who-may-change-a-marking-and-keeping-passes-by-offer-and-acceptance.md) — who the keeper is.
- [Decision 0029](0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md) — the looked-at rule a suggestion is held to.
- [Decision 0008](0008-second-looks-are-blind.md) and [Decision 0010](0010-people-who-answered-are-named-only-to-those-who-may-see-answers.md) — what is kept from members about second looks.
- [Decision 0005](0005-sensitive-findings-are-generalised-by-viewer.md) — who sees a protected finding's place.
- [Lines phase 2 plan](../../plans/lines-phase-2.md) — the design, the API's codes and the tests.
