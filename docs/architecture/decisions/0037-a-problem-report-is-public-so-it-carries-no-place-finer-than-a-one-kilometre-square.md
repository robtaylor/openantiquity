# Decision 0037 — A problem report is public, so it carries no place finer than a one-kilometre square

**Status:** Proposed.

**Current architecture:** [UI.md, "Reporting a problem"](../../UI.md#reporting-a-problem).

**TL;DR.** In the context of a "Report a problem" form whose text is posted to a public issue tracker, facing members who see a protected finding's exact place on its page, we chose to keep coordinates out of every report and to offer the map's position only as a one-kilometre square, and only on pages that show no finding, draft or investigation, accepting that a report says less about where a fault was seen.

## Context

When this was written the form had been built and not released. It let the person add where the map was by ticking a box, and the report then carried the map's centre to five decimal places and its zoom. The box was unavailable where the page showed a place kept back from the person looking, which the server said: a finding's `location.obscured`, and a new `places_kept_back` on an investigation.

Two things were wrong with that. Any signed-in member sees a protected finding exactly on its page (`sensitivity.sees_exact`), so for a member the box was live there, and a report made from that page put the finding's place on a public tracker to about a metre. Decision 0005 doesn't let an ordinary member's download carry that place. And `places_kept_back` told a signed-out reader that an investigation had once held a protected finding, where the page said nothing of it.

An independent review found both before release. The plan the owner had agreed carried the rule as built: the fault was in the plan.

A report also carries the id of each request that failed. The server's log holds the same id beside the address asked for, and only the people who run the site read the log. So the exact place of a fault can be found without the report saying it.

## Decision

1. A report never carries coordinates, whatever the person chooses and whoever they are.
2. The position a person may add is the one-kilometre grid square the map was centred on, as a four-figure reference, and the zoom as a whole number. That is the size of square a protected finding is shown as to the public.
3. The option is offered only on pages named in a list as showing no finding, draft or investigation of their own. A page not on the list doesn't offer it, a page added later included. It is the same for everyone, signed in or not.
4. The page, whether the option is offered, and the square are taken when the form opens and don't follow the page afterwards.
5. Nothing is asked of the server to decide this. `places_kept_back` and the store that listened for it were taken out.
6. A test builds a report by each way out, as a signed-out reader and as a member served the exact place, and searches its text for the finding's id, its coordinates and any grid reference finer than four figures.

## Alternatives considered

- **Turn the box off wherever a protected finding is on screen, for members too, and keep coordinates elsewhere** — rejected because the map stays where it was when someone leaves a finding's page, so a report from the next page would carry the same centre.
- **Round the coordinates to two decimal places** — rejected because such a cell isn't the square a protected finding is shown as. Two overlapping cells narrow a place to where they cross.
- **No position at all** — weighed, and the simplest. Set aside because a square and a zoom are still enough to find which terrain a fault was seen on when no request failed. It is the first walk-back.
- **Keep the rule and send reports somewhere private** — rejected because the owner had chosen not to store reports: a prefilled issue and a copy-and-email route covered the need, and a table of reports would have added moderation and personal data to look after.

## Consequences

- A member can't publish a protected finding's place through a report, by choice or by mistake.
- A report from a finding's page, a draft or an investigation never says where the map was. Someone reporting a fault there says it in words, and the request ids lead to the rest.
- A fault that depends on the exact spot and fails no request, such as a tile that draws wrongly, is narrowed only to a square.
- The list of pages has to be kept: a new page that is safe doesn't offer the option until it is added.
- The map's centre can lie in the square next to a finding's own, since a panel shifts what is in view. A report from a page on the list isn't tied to any finding, so this was accepted.
- The map stays where it was when someone leaves a page. A report made from the bare map just after leaving a draft, or a finding the public map doesn't show, can carry that square. Nothing in the report ties the square to it, so this was accepted too.

## Walk-back options

- **If the square proves no use in finding faults** — take the option out. Decision 1 stands without it.
- **If reports move to a private place** — coordinates could be allowed there for the people a place isn't kept back from. That needs its own record, since Decision 0005 binds what leaves the app.
- **If a page on the list comes to show a finding of its own** — take it off the list in the same change.

## Links

- [Decision 0005](0005-sensitive-findings-are-generalised-by-viewer.md) — who sees a protected finding's place, and what may leave the app.
- [Decision 0026](0026-the-code-is-published-under-the-agpl-version-3.md) — the code and its tracker are public.
- [Decision 0032](0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md) — the two levels a finding has.
- [Report a problem plan](../../plans/report-a-problem.md) — what was built.
