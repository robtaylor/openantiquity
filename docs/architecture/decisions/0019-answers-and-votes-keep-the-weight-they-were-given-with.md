# Decision 0019 — Answers and votes keep the weight they were given with

**Status:** Proposed.

**Current architecture:** [Moderation in the build contract](../../ARCHITECTURE.md#moderation).

**TL;DR.** In the context of second looks that nobody who hasn't answered may tie to a person, facing a moderator who could change a named member's role or ban them and read each of their answers off the public score, we chose to fix an answer's and a vote's weight when it is given and to keep both counting through a ban, so that a change of standing never moves a score through someone's answers, accepting that a banned account's past answers and votes go on counting.

## Context

When this was written the confidence engine weighed every answer and vote by the person's current role, and a ban stopped their answers, votes, evidence and verifications counting. `services.moderation.change_role`, `ban` and `unban` each reassessed every finding the person had marked, answered, voted on or added evidence to, in one request, with no actor on the events. The ban's answer carried `findings_reassessed`, the number of those findings.

The security review before opening, on 2026-11-11, showed that this undid Decision 0008 for a named person. On an open finding where one member had said yes and another no, a moderator who had not answered changed the first to expert and back: the public score went 10, 23, 10. The same for the second went 10, 0, 10. Banning the second moved it from 10 to 16. A rise meant yes and a fall meant no. Decision 0013 says second looks are blind for moderators too.

A signed-out visitor could learn the same whenever a moderator did this for real. A role is public on a profile, a banned profile answers `user_not_found`, and at that moment a burst of tier and state changes with no actor appeared in the feed and the event stream, each on a finding the person had answered. Votes had the same flaw: an item gives its votes only as counts, and a count that moved when a named voter was banned said how they had voted.

The review offered three ways out: put the reassessment off into a batch with unrelated findings, freeze the public score whenever a moderator changes someone's standing, or apply a new weight only to answers given afterwards.

## Decision

1. An observation stores the answerer's role when it is given (`role_at_answer`), and a vote the voter's role when it is cast or changed (`role_at_vote`). The engine weighs each by that role, never by the person's role today.
2. A banned person's answers and votes keep counting while the ban lasts. Their evidence and verifications, which are named on each finding's page, stop counting as before, and their findings, comments and the rest stay as before.
3. A change of role, a ban and its lifting reassess only the findings the person's current role still bears on: their own findings, and findings with evidence they added or verified. Findings they only answered or voted on are left alone.
4. The ban and unban answers no longer say how many findings were reassessed.

## Alternatives considered

- **Putting the reassessment off into a batch** was rejected because a batch still moves exactly the findings the person answered, and anyone who reads the scores before and after it learns the same as before, a little later.
- **Freezing the public score after a change of standing until something else reassesses the finding** was rejected because a moderator could cause that something else, a vote added and taken away, and read the difference. It would also have needed a second, published copy of every assessment.
- **Keeping the ban's effect on answers, and accepting the leak for bans only** was rejected because a ban is the more visible change of the two: a profile that vanishes, at a moment anyone can note.
- **Hiding the role on profiles** was rejected because it closes only the onlooker's half. The moderator who flips the role still sees the score move.

## Consequences

- No change of role or standing moves a score through an answer or a vote, so a moderator who flips a role and flips it back learns nothing, and an onlooker sees no burst of events on the findings a person answered.
- A member made expert counts as an expert only on findings they answer from then on. An archaeologist who answered before being marked as one has to be credited by the next answers.
- A ring of accounts banned for answering each other's findings keeps the weight it gave them. A moderator deals with those findings directly, by hiding them or by asking for fresh second looks. This is the main cost.
- A finder's own role still weighs their feature class, so changing a finder's role can still move class agreement on their findings. That says something about how unnamed people classed the feature in aggregate, never who said what.
- Existing databases need the two columns filled from each person's role at the time of the change, since the role at answer time wasn't kept before.

## Walk-back options

- **If rings of banned accounts keep findings at a tier they shouldn't hold**, add a moderator action that sets aside a banned account's answers on one named finding at a time, logged, and accept that the moderator who does it sees that finding's score move.
- **If people expect a promotion to count backwards**, show on a profile that weight counts from the day of the change, rather than reweighing old answers.

## Links

- Decision 0008 — second looks are blind; this record covers how a change of standing keeps them so.
- Decision 0010 — people who answered are named only to those who may see answers.
- Decision 0013 — second looks are blind for moderators too.
- Decision 0003 — the role weights the engine uses.
