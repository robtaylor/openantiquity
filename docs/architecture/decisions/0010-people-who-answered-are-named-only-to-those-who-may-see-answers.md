# Decision 0010 — People who answered are named only to those who may see answers

**Status:** Proposed.

**TL;DR.** In the context of a finding's public page, facing a score and tier that move with every second look, we chose to leave the people who answered out of the page's credits for anyone who may not see answers, so that nobody can tie a yes or a no to a named member, accepting that the page thanks fewer people and that the score and tier still say, without names, which way the answers lean.

## Context

When this was written, `FindingDetail.credits` listed everyone who had answered a finding to every viewer. For a viewer who may not see answers, the kind of each credit was replaced by `answered`, so the page didn't say how anyone answered. The page also showed `confidence`, the 0 to 100 score, and the tier, both worked out from the answers (Decision 0003).

The seam review on 2026-11-10 showed that this was enough to tie each answer to a person. A signed-out visitor who reloaded a page saw the score go from 10 to 16 as a credit for one named member appeared, and back to 10 as a credit for a second appeared. The first had said yes and the second no. A tier moving from Spotted to Seen with two new names showed that both had said yes. Decision 0008 says the other reviewers' individual answers stay hidden from anyone who hasn't answered, and that nobody who hasn't answered can work out who said what.

The score and tier are aggregates. Decision 0008 lets a finding's page show its tier, because the page is where a finding is discussed, and the score is the meter beside the tier. The help-wanted and review queues are ordered by how many answers a finding needs, which also follows from other people's answers.

## Decision

1. A finding's credits name the people who answered only to viewers who may see answers: the finder, and anyone who has answered that finding. Everyone else gets no credit for an answer at all, neither a name nor a count.
2. Credits for evidence, endorsements and verification stay public, because those aren't second looks and each is already shown on the page.
3. The score, the tier and the order of the review and help-wanted queues stay public. They follow from the answers in aggregate and carry no name.

## Alternatives considered

- **Keeping the names with the kind hidden** was the first-wave design. It was rejected because the score moves with each answer, so a name appearing beside a change in score says how that person answered.
- **A count of answers in place of names** was rejected because a count that goes up by one beside a change in score says how that one answer went, which is the thing being hidden.
- **Freezing the public score between tiers** for viewers who may not see answers was rejected for now. It would have had to reach every list, the map, sorting by score and every export, each with its own per-viewer test of whether the viewer had answered, to hide a movement that the public tier already shows in coarser steps. With no names on the page, the movement says that someone answered a certain way, not who.
- **Hiding the tier too** was rejected because Decision 0008 keeps the tier on the page, where findings are discussed and cited.

## Consequences

- Nobody who hasn't answered a finding can learn from its page who answered it.
- A reviewer who answers sees everyone who answered before them, so the page thanks second lookers once they can no longer be led by it.
- Someone who watches a page closely can still tell that an unnamed answer pushed the score up or down. Their next answer is less independent for it. That is a known limit, listed in `docs/ARCHITECTURE.md` under Second looks.
- The `answered` credit kind is gone from the API. Credits use `CreditKind` from `services/confidence.py` directly.

## Walk-back options

- **If watching the score turns out to lead reviewers**, for instance answers given after a recent score change agree with that change more often than blind-queue answers do, freeze the score between tiers for viewers who may not see answers.
- **If second lookers miss being thanked by name**, show the number of second looks once a finding has had several, and test that a single answer can't be read from the change.

## Links

- Decision 0008 — second looks are blind; this record covers the credits it didn't mention.
- Decision 0003 — the confidence ladder the score and tier come from.
