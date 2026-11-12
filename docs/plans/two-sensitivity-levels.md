# Plan — Two sensitivity levels: take `restricted` out

**Status:** Active.

## Goal

A finding is `open` or `protected`, as Decision 0032 chose, and nothing in the code, the tests, the interface or the present-tense documents still speaks of a `restricted` level.

## Prerequisites

- Decision 0032, proposed.
- For WS2: lines and curves has landed on `main`. That branch touches the same services and leak tests, so the sweep runs once over the whole tree after it.

## Where things stand (2026-11-12)

- WS1 is being built on `feat/two-sensitivity-levels`.
- WS2 hasn't started and waits for lines and curves.
- The live site holds no restricted finding. Asked signed out that day, its API listed one finding, and it was open.

## Workstreams

### WS1 — Nothing can be set to `restricted`

**Status:** In flight.

This closes the fault Decision 0032 describes on the live site. It changes the edge of the application and leaves the inside alone.

**Deliverables:**

- The three request models that take a level refuse `restricted`: creating a finding, changing its level, and a moderator's change.
- `/api/v1/meta` lists `open` and `protected` only, and the two choosers in the interface offer those.
- A test walks the API's schema and fails if any request admits `restricted`.
- A test pins that every active signed-in member sees a finding of every offered level exactly, which is what keeps Decision 0023's distance rule from giving a place away.
- `DESIGN.md`, `ARCHITECTURE.md`, `UI.md`, the interface's copy and the changelog say two levels.

**Exit criteria:**

- Both full suites and the end-to-end tests pass.
- It is deployed, and a request to the live API that sets `restricted` is refused.

### WS2 — The sweep

**Status:** Not started. Waits for lines and curves.

**Deliverables:**

- `Sensitivity.RESTRICTED` and everything that branches on it are gone from the backend and the frontend, with the tests and fixtures that build a restricted finding.
- The schema's check on `findings.sensitivity` allows two values, and any row stored as `restricted` becomes `protected` first. Only a development database can hold one.
- What a trusted member and an expert may do is stated once, for two levels, in `vocab.py`'s words and the interface.
- Decisions 0021 and 0023 are read against the code, and their status lines say so if a point no longer applies.

**Exit criteria:**

- `git grep -i restricted` finds the word only in decision records, the changelog and where it means something else.
- Both full suites and the end-to-end tests pass.

## Phase exit criteria

When all of these are true, this plan closes:

- [ ] WS1 shipped and deployed.
- [ ] WS2 shipped.

## References

- `architecture/decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md` — the decision this carries out.
- `architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md` — the three levels it replaced.
- `architecture/decisions/0023-what-is-drawn-near-a-protected-finding-is-judged-by-distance-and-shown-as-whole-squares.md` — the distance rule that stays.
- `lines-and-curves.md` on `feat/lines-and-curves` — the work the sweep waits for.
