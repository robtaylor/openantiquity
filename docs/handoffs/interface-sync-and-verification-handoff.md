# Handoff — Interface sync and verification (security fixes landed; wave f3 and WS9's documents still to do)

**Created:** 2026-11-12
**Working tree:** clean
**Branch:** main

<!--
Reminder: a handoff is ephemeral. At resolution, every load-bearing piece
below migrates into a docs/architecture/ (area doc, decision, spike) or
docs/plans/ home, and this file is then `git rm`'d in the same commit as the migration.

See docs/handoff-discipline.md for the migration table.
-->

## Goal & next-up

**Goal of this session:** run WS9's security review of the finished code and fix what it found. That is done and on `main`: the review's findings, the fixes, two adversarial reviews of the fixes and a last fix pass, with Decisions 0019 to 0024.

**Next session should pick up:** wave f3 of the interface work ([`v1-england.md`](../plans/v1-england.md), WS7, "Left"), then WS9's documents. The steps are under the follow-ups.

**Verification command:**

```sh
git status --short && git log --oneline -1 && git worktree list
# Expect: clean, one worktree (the main checkout), a commit dated 2026-11-12 or later
docker compose -f infra/docker-compose.yml up -d db
cd backend && uv run pytest -q
# Expect: 5793 passed, 5 skipped, in about ten minutes
cd ../frontend && pnpm test && pnpm typecheck && pnpm lint && pnpm build
# Expect: 1277 unit tests pass
FIELDCLUB_E2E_PORT=8465 pnpm e2e
# Expect: 268 passed, 48 skipped. markers.spec's 3D test can time out when the machine is busy; run it alone before believing a failure
FIELDCLUB_E2E_API_PORT=8471 FIELDCLUB_CONTACT=fieldclub@shape.build pnpm e2e:full
# Expect: 34 passed, with no Content-Security-Policy violation
uv run docs/scripts/doctool.py lint
# Expect: 0 errors, and D005 warnings for decisions without a forward-link
```

Port 8000 on this machine belongs to an unrelated service: never use it for the API.

## Done this session

| Commit | Subject | Notes |
|---|---|---|
| `34a43d7` to `ae50893` | The security and privacy review's fixes | Eight commits from `sec/fix`: backend, interface, the production headers in the browser suite, the reviewers' findings, Decisions 0019 to 0024 |
| `2a6f347` | Join the security fixes to the Fly move, and widen the crash guard | Where the security fixes met the Fly move, and the crash guard widened |

## Open follow-ups (priority-ordered)

### 1. Wave f3: the interface adopts what the API gained (a workflow of seven agents, some hours)

The interface still holds its own copies of rules and words the API now gives (`/meta`'s labels, credits and levels, the terrain's "being prepared" answers, the evidence filter on help wanted), and has had no pass for duplicated code. The workflow script for it is written and passes a dry run: `var/handoff/workflows/f-frontend.js`, wave `f3`, one track `sync` on port 5271 with stages `sync-map`, `sync-finding`, `sync-people` and `simplify`, then two reviews and a fix pass.

Before launching:

1. Set `S` on line 12 of the script to the new session's scratchpad folder.
2. Read the three `SYNC_*` briefs and the `SIMPLIFY` brief against `main`. They were written before the security fixes, which changed the drafts store, the sign-in pages, the notices and the mention and investigation views. Correct any brief that describes code as it was.
3. Make the worktree: `git worktree add .claude/worktrees/f3-sync -b f3/sync main`, then link `var` and `.env` into it from the main checkout, as every earlier track did.
4. Run it with `Workflow({scriptPath: "<the script>", args: {wave: "f3"}})`.

When it finishes: read each agent's report from the run's journal, rebase `f3/sync` onto `main`, run every suite in the verification block yourself with real exit codes, fast-forward `main`, and remove the worktree and branch. The owner has given standing approval for that rebase and fast-forward of a finished, reviewed track.

### 2. WS9's documents (a day)

[`v1-england.md`](../plans/v1-england.md), WS9. The security review is done. Left:

- Area docs under `docs/architecture/` for every area, each written from the code and checked against it. They replace `docs/ARCHITECTURE.md`, which has grown to hold everything.
- A status for each of Decisions 0001 to 0024 set from what the code does, and a forward-link on each. The docs lint's D005 warnings list the ones without.
- An end-to-end run of the whole loop on a clean database.
- `CHANGELOG.md` and the plan brought up to date.

### 3. Upstream reports (minutes each, when there is a reply)

- [libgeos/geos#1604](https://github.com/libgeos/geos/issues/1604) was filed on 2026-11-12 under the owner's account: a polygon with an empty hole crashes `contains`, `covers`, `within` and `relate`. Answer the maintainers if they ask. `schemas/shapes.py` and `ingest/runner.py` keep such a shape from GEOS whatever version is installed, and stay when it is fixed.
- Not filed: the abort in LERC when `pyogrio`'s GDAL loads before `rasterio`'s (`ingest/adapters/ogr.py` works round it, and `tests/ingest/adapters/test_ogr.py` reproduces it). It needs reducing to a few lines without this project's code first. The owner wants upstream bugs reported.

## Critical context

- The development database on port 54329 is shared and holds real records. Never drop or truncate it. Its schema matched the models on 2026-11-12, after the security fixes' new columns and tables were added. The tables for accounts, findings and investigations are empty there.
- A draft made signed out belongs to the browser tab that made it, and every draft taken over at sign-in waits for the person to press Send (Decisions 0022 and 0024). The browser tests press it.
- `pnpm e2e:full` builds the interface and has the backend serve it under the production security headers. A test fails on any Content-Security-Policy violation, so a new host for tiles, images or live records has to be in `layers.py` or `data/live_sources.json` before the interface uses it.
- The session's working notes, the workflow scripts, the security review's findings and each agent's report are in `var/handoff/` (ignored by git). `var/handoff/security/reports/fix.md` lists what the last fix pass did and what it left unsure.
- Models: the main session plans and lands; Opus agents make judgements and do every review; Sonnet agents do patterned work. Each parallel track gets its own worktree and branch.

## References

- [`v1-england.md`](../plans/v1-england.md): WS7 and WS9
- [`hosting-on-fly-handoff.md`](hosting-on-fly-handoff.md): the other open thread
- Decisions [`0019`](../architecture/decisions/0019-answers-and-votes-keep-the-weight-they-were-given-with.md) to [`0024`](../architecture/decisions/0024-drafts-taken-over-at-sign-in-wait-to-be-sent.md): what the security review decided

## Migration note

- Follow-up 1 → `docs/plans/v1-england.md`, WS7, when f3 is on `main`
- Follow-up 2 → the area docs themselves, and WS9's status
- Follow-up 3 → a comment beside each workaround, and nothing else
- Critical context → the area docs for accounts, drafts and testing
- Then `git rm docs/handoffs/interface-sync-and-verification-handoff.md` in the migration commit
