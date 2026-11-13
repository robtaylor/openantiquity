# Plan — Two sensitivity levels: take `restricted` out

**Status:** Active.

## Goal

A finding is `open` or `protected`, as Decision 0032 chose, and nothing in the code, the tests, the interface or the present-tense documents still speaks of a `restricted` level.

## Prerequisites

- Decision 0032, proposed.
- For WS2: lines and curves has landed on `main`. That branch touches the same services and leak tests, so the sweep runs once over the whole tree after it.

## Where things stand (2026-11-13)

- WS1 is live since 2026-11-13.
- WS2 is built on branch `chore/drop-restricted-level`, not yet merged or deployed. It waited for lines and curves, which landed on 2026-11-13 as `3958ced`.
- The live site holds no restricted finding. Asked signed out on 2026-11-12, its API listed one finding, and it was open.

## Workstreams

### WS1 — Nothing can be set to `restricted`

**Status:** Shipped, commits `639e4f7` to `da60c5a`, deployed 2026-11-13.

This closes the fault Decision 0032 describes on the live site. It changes the edge of the application and leaves the inside alone.

**Deliverables:**

- The three request models that take a level refuse `restricted`: creating a finding, changing its level, and a moderator's change.
- `/api/v1/meta` lists `open` and `protected` only, and the two choosers in the interface offer those.
- A test walks the API's schema and fails if any request admits `restricted`.
- A test pins that every active signed-in member sees a finding of every offered level exactly, which is what keeps Decision 0023's distance rule from giving a place away.
- A finding a moderator has hidden is left out when what is drawn near it is judged. A review of this workstream found it still held views back, which said something hidden was there.
- `DESIGN.md`, `ARCHITECTURE.md`, `UI.md`, the interface's copy and the changelog say two levels.

**Exit criteria:**

- Both full suites and the end-to-end tests pass. Met on `da60c5a`: 5,830 backend tests, 1,282 frontend tests and 268 end-to-end tests.
- It is deployed, and the live API offers two levels. Met: `/api/v1/meta` on openantiquity.org lists `open` and `protected`. The refusal of `restricted` is proved by the suite for a member, the finder, a trusted member and a moderator. It wasn't tried against the live API, which needs a signed-in session.

### WS2 — The sweep

**Status:** Built on `chore/drop-restricted-level` and reviewed, not merged or deployed.

What was done: `Sensitivity` has two values, `OfferedSensitivity`, `OFFERED_SENSITIVITIES` and `EXACT_LOCATION_ROLES` are gone, and `sees_exact` is true for an open finding or any signed-in reader. `create_schema` moves a finding stored at the dropped level to `protected` before it makes the check again (`db._DROPPED_VALUES`), and looks for one only while the stored check still admits the level. Moderation log entries naming the level stay as written, and the interface shows the stored word. With every editor seeing every finding exactly, the guard's exemption for a reader's own items and its `held_back` refusal had no reader left and were removed, so Decision 0023's sixth and seventh points no longer apply (its status line says so). `findings.require_exact` stays as a service-level check that no route can now fail. A review of the branch added one refusal that `main` lacked too: the text of a finding item whose finding isn't shown can't be changed (409 `item_unavailable`).

**Deliverables:**

- `Sensitivity.RESTRICTED` and everything that branches on it are gone from the backend and the frontend, with the tests and fixtures that build a restricted finding.
- The schema's check on `findings.sensitivity` allows two values, and any row stored as `restricted` becomes `protected` first. Only a development database can hold one.
- What a trusted member and an expert may do is stated once, for two levels, in `vocab.py`'s words and the interface.
- Decisions 0021 and 0023 are read against the code, and their status lines say so if a point no longer applies.

**Exit criteria:**

- `git grep -i restricted` finds the word only in decision records, the changelog and where it means something else. Met on the branch, with three more places that name the stored value on purpose: the schema step that moves it (`backend/src/fieldclub/db.py`), its test (`backend/tests/findings/test_stored_levels.py`) and the moderation log's test of a stored word (`frontend/src/features/moderation/describe.test.ts`). The hosting handoff still says the sweep comes next.
- Both full suites and the end-to-end tests pass. Met on the branch: 5,992 backend tests, 1,440 frontend tests, 299 end-to-end tests and 40 full end-to-end tests.

## Phase exit criteria

When all of these are true, this plan closes:

- [x] WS1 shipped and deployed.
- [ ] WS2 shipped.

## References

- `architecture/decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md` — the decision this carries out.
- `architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md` — the three levels it replaced.
- `architecture/decisions/0023-what-is-drawn-near-a-protected-finding-is-judged-by-distance-and-shown-as-whole-squares.md` — the distance rule that stays.
- `archive/lines-and-curves.md` on `feat/lines-and-curves` — the work the sweep waits for.
