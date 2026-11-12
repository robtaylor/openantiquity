# Decisions

A decision record captures a choice worth understanding later: the context, the options considered, and the rationale for the one taken. It's the *why* behind a piece of the architecture. The *what the code does now* lives in the [architecture reference](../README.md), one doc per area. Each decision links forward to the area doc it shaped, and each area doc links back to the decisions behind it.

For the full convention, see [Claude Project Discipline — Decision records](https://robtaylor.github.io/claude-project-discipline/decisions.html).

## The rule: immutable and past-tense

A decision record is a record of a choice at the moment it was made, not a description of the system now. Its body is **never rewritten** when the code moves; edit the area doc instead. Only two lines change after acceptance: the `**Status:**` line and the `**Current architecture:**` forward-link.

When a decision itself changes, **write a new record that supersedes the old one**. Set the old one's status to `Superseded by Decision NNNN (YYYY-MM-DD)` and move it to [`archive/`](archive/):

```sh
uv run docs/scripts/doctool.py archive docs/architecture/decisions/NNNN-<name>.md
```

No dated `## Amendment` blocks. A change to *what the code does* is an area-doc edit; a change to *why* is a new decision.

## Three kinds of claim, aged differently

1. **Why the decision was made.** Past tense, as the state at decision time. Lives here, never rewritten.
2. **What the current architecture is.** Present tense, kept in step with the code. Lives in the area doc.
3. **What's decided but not built yet.** Lives in the area doc's `## Implementation status`, with a plan or issue, and drains into (2) as each piece lands.

Write all three in the same present tense and a reader can't tell *why we did it* from *what the code does* from *what we still intend*.

## Status legend

- **Proposed** — drafted, not yet ratified. Open the body with what the code does today, so the proposal can't be mistaken for reality.
- **Accepted (YYYY-MM-DD)** — the decision is in effect in the code.
- **Accepted (partial) (YYYY-MM-DD)** — ratified and partly built; the area doc's Implementation status says which parts.
- **Superseded by Decision NNNN (YYYY-MM-DD)** — replaced; lives in `archive/`.
- **Withdrawn (YYYY-MM-DD)** — abandoned without replacement; lives in `archive/`.

**Status must match the code.** A Status line is a claim about the codebase. Verify it against the implementation before setting it; don't trust the previous status or that a feature "shipped". Don't bump Proposed → Accepted just because a design merged.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-synchronous-endpoints.md) | Plain synchronous endpoints | Proposed |
| [0002](0002-accounts-required-to-save.md) | Accounts are required to save | Proposed |
| [0003](0003-confidence-ladder.md) | Confidence is a ladder of rules | Proposed |
| [0004](0004-field-club-is-non-commercial.md) | Field Club is non-commercial | Proposed |
| [0005](0005-sensitive-findings-are-generalised-by-viewer.md) | Sensitive findings are generalised by viewer | Proposed |
| [0006](0006-terrain-tiles-are-rendered-from-raw-elevation.md) | Terrain tiles are rendered from raw elevation | Proposed |
| [0007](0007-the-record-index-stores-only-what-licences-allow.md) | The record index stores only what licences allow | Proposed |
| [0008](0008-second-looks-are-blind.md) | Second looks are blind | Proposed |
| [0009](0009-contributors-are-16-or-over-and-there-is-no-private-messaging.md) | Contributors are 16 or over and there is no private messaging | Proposed |
| [0010](0010-people-who-answered-are-named-only-to-those-who-may-see-answers.md) | People who answered are named only to those who may see answers | Proposed |
| [0011](0011-the-wikidata-cross-walk-is-stored-but-kept-off-the-map.md) | The Wikidata cross-walk is stored but kept off the map | Proposed |
| [0012](0012-the-national-overview-is-built-from-our-own-mirror.md) | The national overview is built from our own mirror | Proposed |
| [0013](0013-moderators-hide-what-others-posted-and-every-moderation-route-needs-the-welcome-step.md) | Moderators hide what others posted and every moderation route needs the welcome step | Proposed |
| [0014](archive/0014-a-second-look-s-detail-is-asked-before-it-is-sent.md) | A second look's detail is asked before it is sent | Superseded by Decision 0008 (2026-11-11), before acceptance: the API took the answer alone and its detail after it (point 8). |
| [0015](0015-records-are-hidden-during-a-blind-second-look.md) | Records are hidden during a blind second look | Proposed |
| [0016](0016-terrain-requests-never-wait-for-elevation-and-tiles-draw-on-threads-of-their-own.md) | Terrain requests never wait for elevation and tiles draw on threads of their own | Proposed |
| [0017](0017-the-public-name-is-open-antiquity-and-internal-identifiers-stay-fieldclub.md) | The public name is Open Antiquity and internal identifiers stay fieldclub | Proposed |
| [0018](0018-hosting-moves-to-fly-io-with-managed-postgres-and-tigris.md) | Hosting moves to Fly.io with Managed Postgres and Tigris | Proposed |
| [0019](0019-answers-and-votes-keep-the-weight-they-were-given-with.md) | Answers and votes keep the weight they were given with | Proposed |
| [0020](0020-sign-in-providers-pictures-are-not-shown.md) | Sign-in providers' pictures are not shown | Proposed |
| [0021](0021-what-is-written-and-drawn-beside-a-protected-finding-is-generalised-for-each-reader.md) | What is written and drawn beside a protected finding is generalised for each reader | Proposed |
| [0022](0022-signed-out-drafts-belong-to-the-tab-that-made-them.md) | Signed-out drafts belong to the tab that made them | Proposed |
| [0023](0023-what-is-drawn-near-a-protected-finding-is-judged-by-distance-and-shown-as-whole-squares.md) | What is drawn near a protected finding is judged by distance and shown as whole squares | Proposed |
| [0024](0024-drafts-taken-over-at-sign-in-wait-to-be-sent.md) | Drafts taken over at sign-in wait to be sent | Proposed |

(`new decision` appends rows for you. `uv run docs/scripts/doctool.py lint` checks this table against the files.)

## Adding a new decision

```sh
uv run docs/scripts/doctool.py new decision "Short title"
```

That copies `0000-template.md` to the next free number and adds the index row. The four-digit number is a stable ID, cited as "Decision NNNN" from docs, code, and commits. Never reuse or renumber it, including after a record moves to `archive/`. Then add the `**Current architecture:**` link to the area doc this decision shapes, and a link back from that area doc's "Decisions behind this" section.
