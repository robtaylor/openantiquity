# Decision 0005 — Sensitive findings are generalised by viewer

**Status:** Proposed.

**TL;DR.** In the context of a public map of possible unrecorded sites, facing the risk that it becomes a shopping list for illegal metal detecting, we chose three sensitivity levels that coarsen a finding's location to a 1 km square depending on who is looking, to protect vulnerable sites while still letting members check each other's findings, accepting that a signed-in member can see the exact position of most findings.

## Context

Nothing was built when this was written.

Illegal metal detecting on archaeological sites, known as nighthawking, is a recognised heritage crime in the UK. The Portable Antiquities Scheme publishes findspots no finer than a 1 km square and parish for that reason. The research pass on 2026-11-10 recommended a written sensitivity policy with tiers set by feature type, and enforcement in the database instead of the client.

Two facts pulled against each other. The features people mark were already visible to anyone in public LIDAR, so a marker added little risk for an ordinary field boundary. And checking a finding needed its exact position: a member asked to take a second look can't do it from a 1 km square.

The first design had two levels, open and restricted, with restricted findings hidden from everyone except the finder and trusted users. That would have stopped ordinary members corroborating any barrow.

## Decision

1. A finding has one of three sensitivity levels: `open`, `protected` or `restricted`.
2. Signed-out visitors see `protected` and `restricted` findings as a 1 km grid square, with no outline.
3. Signed-in members see `protected` findings exactly and `restricted` findings as a 1 km square.
4. The finder, trusted users, experts and moderators always see the exact location.
5. The default level comes from the feature class. Classes that suggest burials, rich occupation or ritual use default to `protected`: round barrow, long barrow, ritual monument and settlement earthworks. Everything else defaults to `open`.
6. The finder, a trusted user or a moderator can raise a finding to `restricted`. Only a moderator can lower a level.
7. The generalised position is stored in its own column and written when the finding is saved. Queries for signed-out visitors run against that column only. One service function picks the column for a viewer, and every route goes through it.
8. Downloads use the generalised position for `protected` and `restricted` findings unless the person downloading is the finder or trusted.
9. Field Club doesn't accept artefact findspots. Where someone mentions a find, the tool shows the reporting route for that nation and stores nothing about the find.
10. A member becomes trusted only when a moderator promotes them. Fifty reputation points make a member eligible. Points alone never promote anyone.

## Alternatives considered

- **Exact locations for everyone** was rejected because a list of probable barrows and Roman settlements, filtered and exported, is the list a nighthawk wants.
- **Exact locations for trusted users only**, which the research favoured for looting-prone types, was rejected because new members couldn't then corroborate those findings, and a new service has no trusted users at all.
- **Jittering points** inside a cell was rejected in favour of showing the cell. A jittered point looks exact and invites a visit to the wrong field.
- **Generalising everything until reviewed** was rejected for the same cold-start reason, and because most findings are field boundaries and trackways that nobody loots.
- **Automatic promotion to trusted at fifty points** was the first design. Review of the built code on 2026-11-10 showed that three accounts working together could take two findings to "checked on the ground" among themselves, which earned the finder 54 points and with them the exact position of every `restricted` finding. It was rejected in favour of a moderator's decision, with the points as the signal that someone is worth considering.

## Consequences

- A signed-out visitor, a search engine and a scraper never receive the exact position of a `protected` or `restricted` finding.
- Anyone willing to sign in can see `protected` findings exactly. Sign-in gives an identity to rate-limit, log and ban, and it's the price of members being able to check each other's work.
- The class-based default will sometimes be wrong in both directions, so people need the manual override.
- Every query path has to choose the right column. A missed path is a leak, so the choice lives in one function with tests that try each viewer type against each level.
- Nobody is trusted until a moderator has promoted them. On a new service, `restricted` findings can be checked only by their finder, experts and moderators, and promotion is a task moderators have to keep up with.

## Walk-back options

- **If a heritage body reports damage** linked to a finding, raise that finding to `restricted` at once, and consider moving its whole feature class to `restricted` by default.
- **If `protected` findings are harvested by throwaway accounts**, require a minimum account age or a first accepted contribution before exact positions are shown.

## Links

- Decision 0002 makes every viewer either signed out or an accountable account.
- Decision 0003 gives the trusted role its meaning.
