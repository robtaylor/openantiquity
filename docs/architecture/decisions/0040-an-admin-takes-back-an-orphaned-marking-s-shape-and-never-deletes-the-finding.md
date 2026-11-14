# Decision 0040 — An admin takes back an orphaned marking's shape and never deletes the finding

**Status:** Proposed.

**Current architecture:** [Findings, "Removing an orphaned marking"](../findings.md#removing-an-orphaned-marking).

**TL;DR.** In the context of markings whose keeper's account is deleted or banned, facing ones left in a state that causes trouble, we chose to let an admin put the shape back to an earlier revision or take it away, leaving the finding and everyone's work on it, accepting that the rule holding a shape to the ground second looks covered is set aside for that one act.

## Context

When this was written nobody but a finding's finder could change its shape, and a moderator's only tool for a troublesome finding was to hide all of it.

The owner asked that admins can remove "orphaned markings that cause trouble", and that removing is for admins alone: "admin - they can always pass it over to a moderator. we can adjust once we have real behaviour and issues to address".

A finding carries other people's second looks, evidence and comments. `delete_account` keeps those on purpose, because they were published under an open licence.

## Decision

1. A marking is orphaned when its keeper's account is deleted or banned. Removal is for orphaned markings and for admins.
2. Removal takes back the marking alone. An admin puts the shape back to an earlier revision, or takes it away so the finding is a spot. The finding, its tier, every answer and all evidence stay.
3. The rule that an edit keeps most of the looked-at ground is set aside for a removal, because an earlier shape may lie outside ground looked at since. The ground itself is kept, so later edits are still held to it.
4. A removal goes through the same tail as every change of shape. The finding is assessed again when what lies beyond the looked-at ground changed, and its events and a default title follow it when its square changes.
5. A put-back keeps the finding's point where it is when the earlier shape lies within the limit of it. When it doesn't, the put-back isn't refused: the server places the point by the restored shape. So a marking whose point was dragged away can always be recovered, whatever was done first.
6. The moderation log records the removal with its reason and the two revisions, and never a shape, because the log's data is also written to the host's log.
7. The version before this one was released first with a log that passes over an action it has no name for.

## Alternatives considered

- **Delete the finding** — rejected because it takes other people's second looks, evidence and comments with it.
- **Withdraw it** — rejected because withdrawing is the finder's own claim that nothing is there.
- **Hide it** — already possible, and takes the whole finding off the map with everyone's work on it.
- **Refuse a put-back that lies too far from the point** — built first, and found in review to leave an admin unable to recover a marking once its point had been dragged away or its shape removed.
- **Moderators too** — put to the owner, who chose admins alone for now.

## Consequences

- A finding can be left as a spot where it had a line. Its second looks stand, given on a shape it no longer has.
- A put-back can move a finding's point, and with it the square a protected finding is shown as. Its events and default title move too, so only one square is ever shown.
- A marking whose keeper is active can't be removed. A moderator hides the finding, and banning a keeper who is the trouble makes the marking orphaned.
- An admin must give a reason, which the log keeps.
- A removal isn't announced. Nothing a member or the public is sent names the admin, because a removal is only possible on an orphaned marking and would say that its keeper is banned or gone.

## Walk-back options

- **If moderators need it** — widen the check from admins to moderators. Nothing stored changes.
- **If removals leave findings that mislead** — say on the page that the marking was taken back, which needs a new activity kind.
- **If a keeper who is active causes trouble often** — allow removal on a hidden finding, which a moderator can already hide.

## Links

- [Decision 0038](0038-found-by-is-the-credit-kept-by-is-who-may-change-a-marking-and-keeping-passes-by-offer-and-acceptance.md) — keepers and what orphaned means.
- [Decision 0029](0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md) — the looked-at rule set aside here.
- [Decision 0028](0028-a-finding-s-shape-is-its-tapped-points-under-one-fixed-curve-within-size-caps-around-an-anchor-that-stays-put.md) — the point a shape is held near.
- [Decision 0041](0041-the-admins-shapes-route-alone-sends-the-shape-before-a-change.md) — how an admin sees the earlier shapes.
- [Lines phase 2 plan](../../plans/lines-phase-2.md) — the design, the API's codes and the tests.
