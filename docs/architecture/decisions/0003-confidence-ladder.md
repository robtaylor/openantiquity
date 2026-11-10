# Decision 0003 — Confidence is a ladder of rules

**Status:** Proposed.

**TL;DR.** In the context of findings whose worth depends on independent checking, facing the need for a confidence measure people can read and act on, we chose a ladder of named tiers with explicit rules to make every unmet condition a concrete task for the next person, accepting thresholds that are judgement calls until real data can tune them.

## Context

Nothing was built when this was written.

The product's promise was that collaboration raises confidence in a finding. That needed a model of confidence that people could read, that resisted pile-ons, and that told the next visitor what would help.

Earlier LIDAR portals validated findings through a second tier of experienced volunteers or staff. That produced good data and a queue, and contributors rarely saw their own help count.

## Decision

1. Confidence is a ladder of six named tiers: spotted, seen by others, corroborated, probable, checked on the ground, on record.
2. Each desk tier has a rule made of explicit conditions on four things: how many other people can see the feature, how many independent kinds of evidence support it, whether people agree what it is, and whether ordinary explanations have been ruled out.
3. The top two tiers depend on fieldwork and official recording, and can be reached without the desk tiers.
4. Opinions are weighted by role. The finder's own opinion never counts towards visibility.
5. Evidence counts only when it's independent of the finder.
6. A finding's state (open, known, disputed, ruled out, withdrawn) is tracked separately from its tier.
7. The rules are one pure function with its thresholds in a single dataclass. The 0 to 100 meter is derived from the tier for display. No rule reads it.
8. The unmet conditions of the next tier are published on the finding as its next steps, and the same list drives the help-wanted queue.

## Alternatives considered

- **Up and down votes** were rejected because they measure popularity. Ten people agreeing that a pin looks interesting says nothing about whether the feature appears on an 1888 map.
- **A single computed probability** was rejected because the inputs don't support that precision, and nobody can tell from "63%" what would move it.
- **Expert review only** was rejected because it creates a queue and removes the reward of watching your own help count. Expert opinion is kept as a heavier weight and as the gate on the official tier.

## Consequences

- Anyone can see why a finding sits where it does.
- The rules that score a finding also produce the list of ways to help, so there's no separate task system to keep in step.
- Thresholds can be tuned without touching logic.
- The thresholds are judgement calls until there's real data. The rules interact, so the function needs thorough tests, including cases built to break it.
- A group of colluding accounts could still walk a finding up the desk tiers. Requiring distinct observers, weighting by role and requiring a trusted reviewer for "probable" raise the cost. Moderation handles the rest.

## Walk-back options

- **Once enough findings have been checked on the ground**, compare their desk tier with the outcome. If tier predicts outcome poorly, refit the thresholds against those cases. That's a change to the dataclass and the area doc, not a new decision.
- **If the rule set proves too rigid for some feature types**, add per-class thresholds to the same dataclass before considering a different model.

## Links

- Decision 0002 fixes who can contribute and so which role weights exist.
