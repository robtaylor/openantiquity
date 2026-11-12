# Decision 0032 — Findings are open or protected, and the restricted level is dropped

**Status:** Proposed.

**Current architecture:** [DESIGN.md, "Protecting sites"](../../DESIGN.md#protecting-sites).

**TL;DR.** In the context of a live site with three sensitivity levels, facing a proof that the strictest level's own guard let a member find a restricted finding's exact place, and a level nobody could yet use, we chose to drop `restricted` and keep `open` and `protected`, to remove the fault by construction and the cost of guarding every feature against members, accepting that a free account is all that stands between anyone and a protected finding's place.

## Context

When this was written Decision 0005 gave a finding one of three levels. `open` showed its place to everyone. `protected` showed it exactly to anyone signed in and as a 1 km square to signed-out visitors. `restricted` showed it exactly to its finder, trusted members, experts and moderators, and as a square to ordinary members. The site had been answering at openantiquity.org since 2026-11-12, with sign-in open to anyone with an OpenStreetMap or Google account.

Decision 0023 held back whatever was drawn in an investigation within 1.5 km of a finding the reader didn't see exactly, measured to the finding's exact point. It was written against someone who knows a hidden place and publishes it. A review of the lines-and-curves backend on 2026-11-12 found the answer could be read back, and a test against `main` that day showed how far that went: a member who saved views at places they chose and read them signed out placed a restricted round barrow to within 6 m in 43 requests.

The fault needed someone who could draw and who was kept from the exact place. Only `restricted` made such a person. A member already saw every `protected` finding exactly, and a signed-out visitor couldn't draw. The live site held one finding that day, and it was open, so nothing had been exposed.

A fix was begun that judged what was drawn against the finding's public square in place of its point. It would have closed the fault and held back about twice the ground round every hidden finding.

The level also had no users. There were no trusted members, so a restricted finding could be seen exactly by its finder and the moderators and checked by nobody else. Every feature still had to be reviewed for what it told a member about a restricted place, and lines and curves had roughly doubled that work.

The owner was given the recorded reasons for the level and what dropping it would lose, and said on 2026-11-12: "I really think a solution would be to not have restricted items... I'm not sure what the use case for this is", and then: "Metal detectorists are quite capable of finding things on their own, so i don't think we should take a huge hit to protect against that misuse".

## Decision

1. A finding is `open` or `protected`. The `restricted` level is dropped. This replaced points 1, 3 and 6 of Decision 0005, and what its points 2 and 8 said about restricted findings. The rest of that decision stood.
2. No request may set `restricted`, and the interface doesn't offer it. This was done first, by itself, because it closed the fault on the live site.
3. The level's code and tests come out in one sweep after lines and curves lands, with any finding stored as `restricted` becoming `protected`.
4. A site that shouldn't be shown at all is hidden by a moderator, which takes it off the map for everyone but its finder and the moderators. Withdrawing a finding doesn't do this: a withdrawn finding is left out of lists by default and can still be asked for.
5. A hidden finding takes no part in judging what is drawn near it. A review of the first step found that views near a hidden protected finding were still held back from signed-out readers, which told a member that something hidden was there and how near. An investigation that holds or has held the finding still counts it, as Decision 0023's second point has it.
6. Decision 0023's distance rule stays as it was, measured to the exact place. It is safe while everyone who can add or draw anything sees every finding exactly, and a test pins that.
7. The fix that judged by the public square was stopped and not landed.

## Alternatives considered

- **Keeping three levels and judging what is drawn by the public square** — not taken. It closed the fault, but it kept a level nobody could use, held back more round every protected finding, and left every later feature to be checked against members.
- **Dropping `protected` as well, so every place is exact for everyone** — not proposed. Decision 0005's reasons for keeping places from signed-out visitors, search engines and scrapers stood, and the owner's doubt was about `restricted`.
- **Keeping `restricted` but meaning "off the map"** — rejected because a moderator's hide already does that.
- **Limiting how fast anyone can ask** — rejected because 43 requests is an afternoon at any limit that leaves investigations usable.

## Consequences

- Nobody who can add or draw anything is kept from a finding's exact place, so nothing they draw can be used to find one.
- A protected finding's place is one free sign-up away from anyone. Sign-in still gives an identity to limit, log and ban.
- A finder or a moderator can no longer keep one site from members while it stays on the map. The choices are `protected`, or hidden.
- A view saved beside a hidden finding by someone who knew of it is shown as it was saved. Nothing says a finding is there.
- In an investigation that held a finding before it was hidden, what is drawn near it is still held back from signed-out readers. Someone who can edit that investigation and joined after the hide could read the guard's answer there. The investigation's other editors were shown the place while it was held.
- Trusted members and experts no longer see anything on the page that a member doesn't. A trusted member's downloads still carry exact places (Decision 0005, point 8).
- Decision 0005's first walk-back option, raising a finding to `restricted` when a heritage body reports damage, is gone. The answer to such a report is to hide the finding.
- Lines and curves keeps its guard measured along a line's whole length, and the question of a hidden road's far parts no longer arises for members.
- Until the sweep, the code still handles a level nothing can reach.

## Walk-back options

- **If a heritage body or a record holder needs sites kept from members** — add a level back, designed against probing from the start: whatever is drawn is judged against the public square, and the exact place is used only to judge what was drawn by someone who sees it.
- **If protected findings are harvested by throwaway accounts** — Decision 0005's second walk-back option stands: require an account's age or a first accepted contribution before exact places are shown.

## Links

- Decision 0005 — the three levels. This record replaced its points 1, 3 and 6.
- Decision 0021 and Decision 0023 — what is written and drawn beside a hidden finding. Unchanged.
- [The plan for the sweep](../../plans/two-sensitivity-levels.md).
