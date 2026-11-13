# Handoff — Hosting on Fly.io (answering on openantiquity.org, with OpenStreetMap and Google sign-in)

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

**Goal of this thread:** move the deployment from Google Cloud to Fly.io (Decision 0018). On 2026-11-12 steps 1 to 11 of the runbook were carried out. The web app runs on Fly and answers on `openantiquity.org`, with Managed Postgres, the whole elevation mirror and the national overview, and it draws terrain. The hourly machine runs, and its first nightly refresh, on 2026-11-13, loaded every bulk source but two (follow-up 1). OpenStreetMap and Google sign-in are on.

**Next session should pick up:** follow-ups 1 to 3 in order. Do every cloud step in the main session: sub-agents and workflow agents don't touch Fly, Google or Gandi and don't read `.env`.

**Verification command:**

```sh
git status --short && git log --oneline -1
# Expect: clean, and a commit dated 2026-11-12 or later
cd backend && uv run pytest -q tests/infra tests/test_config.py tests/test_storage.py
# Expect: all pass. tests/infra/test_fly_config.py starts the application with fly.toml's settings
fly apps list --org openantiquity
# Expect: openantiquity and openantiquity-jobs alone
fly machine list --app openantiquity
# Expect: three machines in lhr, shared-cpu-2x with 2 GB, stopped, suspended or started, on the image of commit db914b9 or later
fly ips list --app openantiquity
# Expect: the private address, the shared IPv4 address 66.241.124.216 and the IPv6 address 2a09:8280:1::1fe:8e38:0
fly machine list --app openantiquity-jobs
# Expect: one machine, `due`, stopped, with the schedule hourly and the volume jobs_var at /data
fly mpg list --org openantiquity
# Expect: the cluster openantiquity, d2gznoqz2n8opkm8, ready, attached to both apps
fly storage list --org openantiquity
# Expect: openantiquity-elevation, openantiquity-cache and openantiquity-photos
uv run infra/fly_jobs.py --commit de016fa0cab563898c0bf73f2a98c26d51fac572 run fieldclub-terrain info
fly logs --app openantiquity-jobs --no-tail | grep -e mirrored -e overview
# Expect: mirrored 5877 tiles (100.00%), and overview c2a8a0e49f2f, 5877 tiles
```

The last pair names the jobs image that exists. `fly_jobs.py` looks for the image of the commit at `HEAD` unless told, and commits made since haven't been built.

## Done so far

| Commit | Subject | Notes |
|---|---|---|
| `28b794b` and the seven before it | The Fly move | `S3Storage`, `S3Folder`, the object lock, `database_address()`, `Fly-Client-IP`, `fly.toml`, `infra/fly/jobs.toml`, `infra/fly_jobs.py`, `infra/fly-secrets.sh`, `deploy.yml`, the runbook. Built in a worktree, reviewed twice, fixed |
| `b7682bc` | Send each Fly secret on standard input, and name the database flags | `fly secrets import` strips a pair of quotes from around a value, so each secret goes through `fly secrets set NAME=-` |
| `2a6f347` | Join the security fixes to the Fly move, and widen the crash guard | The per-address stream limit Fly needs to start, and the hourly machine deleting old sign-ins |
| `c730199`, `b0f754a` | Copy the elevation into Tigris, and record the spend check | Step 1, the elevation bucket and the copy of step 8. Decision 0025. The spike's cluster, apps and bucket deleted |
| `85ad12a` | Keep tiles inside a Fly machine's soft limit, and give the jobs no session key | Two of the security review's hosting items closed |
| `9041d2c` | Publish the code under the AGPL version 3, with a README | The repository is public at `github.com/robtaylor/openantiquity`. Decision 0026 |
| `e7c0794` | Draw terrain on Fly, and check the mirror before each deploy | The first commit to draw terrain on Fly. Decision 0027 |
| The commit that last changed this file | Record step 10 | The hourly machine, and what the deploy of `e7c0794` showed |
| `22ab922` | Pass over an activity kind or next step a later version stored | Decision 0033, so a later version can be deployed beside it or rolled back to it |
| `7175a31` | Keep an ingest run's lock connection in use while records flow | Found by the first nightly refresh |
| `a0d74e6` | Run the end-to-end tests on the real backend in CI | `pnpm e2e:full` has a CI job of its own |
| `3958ced` | Lines and curves, 115 commits | Its release added columns and a table, and the shapes backfill was run afterwards and found nothing to fill |
| `945e33a` | The first point follows the chosen kind, and an index of shaped findings | The index steadies the map query's plan, which had failed a plan test on one CI run |
| `de016fa` | The restricted level's code removed | The commit the hourly machine runs, since nothing in the backend has changed after it. Its release made the check on `findings.sensitivity` again with two values |
| `25a218d` | Terrain tiles that wait, and the map switch first in the layer panel | The map asks again for a tile the server answers 503 with a `Retry-After`. Found by the owner on the live site |
| `db914b9` | The drawing guide, midpoint dots, an unsaved marking kept, and a map that stays put | The commit the web app runs since 2026-11-13. Frontend only |

## Open follow-ups (priority-ordered)

### 1. Read the refresh of 2026-11-21 (minutes)

The first refresh of every bulk source from Fly ran on 2026-11-13 from 03:41 to 07:42 UTC: 27 sources refreshed, 1 already current, 4 skipped and 2 failed. The two that failed, `he-aim-detailed-mapping` (497,629 records, 87 minutes) and `he-aim-monument-extents` (197,372 records, 62 minutes), stored every record and then stopped at their last step, because the connection holding each run's lock had been closed. The runbook's "What can only be checked on the real platform" has what was measured.

Commit `7175a31` keeps the lock's connection in use, and the hourly machine has run an image with it since that day. Both sources were then run by hand on that image and completed, in 54 and 56 minutes. Neither run lasted the 62 minutes at which a lock's connection was seen closed, so they don't show the fix by themselves. The 78-minute test in the runbook does, and no run of over an hour has completed on Fly yet.

The two fall due again at the 03:41 UTC refresh of 2026-11-21, with the other sources refreshed weekly. Read that night with `fly logs --app openantiquity-jobs`, or ask the database for the runs. To run a source by hand: `uv run infra/fly_jobs.py --commit de016fa0cab563898c0bf73f2a98c26d51fac572 ingest <key>`.

Still to look at: how much of the 10 GB volume the downloads took. `fly volumes list` doesn't say, so it needs `df` from a machine with the volume mounted.

The hourly machine `due` wasn't started by its schedule at 22:41 or 23:41 on 2026-11-12, after it was first moved to a new image. That was seen once and the reason isn't known, so `schedule` now starts it once after updating it, and it has run every hour since.

### 2. Sign-in: OpenStreetMap works, Google is on and untried the whole way (the owner, minutes)

Both providers' ids and secrets are in `.env`, as `OSM_AUTH2_ID`, `OSM_AUTH2_SECRET`, `GOOGLE_OAUTH2_ID` and `GOOGLE_OAUTH2_SECRET`, and were piped to the web app's secrets by `var/handoff/tools/env_to_fly_secrets.py`, which shows none of them.

- **OpenStreetMap.** The owner signed in the whole way on 2026-11-12, and saved a finding.
- **Google.** The application is in production in a Google project of its own, not `fieldclub-uk`, which is to be deleted. `/api/v1/meta` gives Google as enabled, the start of the sign-in sends the registered redirect address and `openid email profile`, and Google answers with its sign-in page. Nobody has yet signed in with Google the whole way. If it fails, `fly logs --app openantiquity` has the reason, though it keeps only the last minute or two.
- That first real sign-in found a fault, fixed the same day in `a527988`: "Save finding" on the form of a draft made before signing in did nothing, because the draft was held and only the drafts bar lifted the hold.

The jobs app's Tigris key was put right by the owner the same day: tried from a jobs machine, it lists, reads and writes the elevation bucket and is refused all three on the cache and the photos.

### 3. Wake the machines after a deploy, or accept the first slow request (a choice, minutes)

A deploy leaves the three web machines stopped, and the first request afterwards took 32 seconds on 2026-11-12. The runbook says to ask for `/healthz` once after a deploy. The deploy workflow doesn't do it yet. Since step 11 it could: `curl --fail https://openantiquity.org/healthz` as its last step.

### 4. Step 12: the deploy workflow (minutes)

The GitHub environment `production` and a deploy token for the web app alone. The repository is `robtaylor/openantiquity` on GitHub, public since 2026-11-12, and this checkout's `origin`.

### 5. Sign-in, and what opening to the public still needs (the owner)

The domains were pointed at Fly on 2026-11-12 at the owner's word ("noone will be looking yet"). The site answers on `openantiquity.org` and anyone can look at the map.

- OpenStreetMap and Google sign-in are on since 2026-11-12 (follow-up 2). So anyone with an account at either can now join and post.
- Since 2026-11-13 a finding is open or protected, and no request can set the restricted level (Decision 0032, `docs/plans/archive/two-sensitivity-levels.md`). The level's code came out the same day (`de016fa`).
- The app has no gate. The owner was told on 2026-11-12, and that [`owner-actions.md`](../plans/owner-actions.md) holds a public launch until an operator is named and the terms, the privacy notice and the Online Safety Act assessment exist (WS14 to WS17). A setting that limits sign-up to named accounts was offered and not yet asked for.
- The other providers and the mail relay are in `owner-actions.md`, WS3.

### 6. Take the Google project down (an hour)

`infra/README.md`, "Taking the Google project down", once the site on Fly has passed its checks. Its first check, that Tigris lacks none of Google's tiles, was made on 2026-11-12. Then delete `infra/terraform` and the Google paragraphs of the runbook. Until then the Google deployment keeps image `2a3d8eee8b4b`: an image built from `main` can't run there.

### 7. What the security review left for hosting

- Done: the jobs app has no session key, and its jobs start without one. The tile render queue on Fly is 16, inside the soft limit.
- Open: one database login, `fly-user` with the role `schema_admin`, serves both apps. Managed Postgres offers the roles `schema_admin`, `writer` and `reader` (`fly mpg users create`). The web app's release command creates the schema, so the web app's login needs `schema_admin` as things are. Giving the web app `writer` means moving the schema command to the jobs app, a change to how a deploy runs. It can be done later without making the cluster again. The owner was told on 2026-11-12.
- Open: `timeout` stopping a job that runs past its limit hasn't been seen on Fly.

### 8. Check Managed Postgres's backups before relying on them (an hour)

How long Fly keeps backups wasn't found, and no restore has been tried. `fly mpg backup list d2gznoqz2n8opkm8`, then restore one into a new cluster, look, and destroy it. The owner kept Managed Postgres for its backups and failover, so this is worth doing before the site holds anything a member wrote.

## Critical context

- The Fly organisation is `openantiquity` and the region `lhr`. The `personal` organisation holds the owner's unrelated apps: never list, name or touch them, and pass `--app` or `--org openantiquity` on every command.
- Never read, print, edit or delete `.env`. It holds Defra's SFTP login and the Gandi token. The owner has allowed piping its values to this project's own secret stores, on standard input only.
- `fly storage create`, `fly mpg create` and `fly mpg attach` print a key or a connection string. Send their output through a filter that drops any line naming one.
- A new access grant or key on Google needs the owner's word each time. The standing permission for gcloud didn't cover the temporary read-only account the copy used: the owner allowed that one by name, and it has been deleted.
- The owner dislikes Terraform. `infra/terraform` stays only until Google is taken down, and nothing new is written in it.
- The application refuses to start when `FIELDCLUB_EVENTS_MAX_PER_ADDRESS` is more than a quarter of `FIELDCLUB_EVENTS_MAX_STREAMS`. `fly.toml` sets 6 and 26. Change the two together, with the request limits and the tile render queue.
- `fieldclub-jobs due`, on the hourly machine, deletes expired sessions and old sign-in links every run. The privacy notice says they are deleted, so the hourly machine has to exist before the site opens.
- The site is public at `https://openantiquity.org`. The private address still works through `fly proxy 8443:443 openantiquity.flycast --app openantiquity` and `curl --resolve openantiquity.fly.dev:8443:127.0.0.1 https://openantiquity.fly.dev:8443/...`.

## References

- [`v1-england.md`](../plans/v1-england.md), WS8: the workstream's state
- [`0018`](../architecture/decisions/0018-hosting-moves-to-fly-io-with-managed-postgres-and-tigris.md): the decision to move
- [`0025`](../architecture/decisions/0025-spend-on-fly-is-watched-by-hand-each-week-and-bounded-by-limits.md): the spend check, in place of point 9 of 0018
- [`hosting-on-fly-io`](../architecture/decisions/spikes/hosting-on-fly-io.md): what the spike checked on the platform
- [`0027`](../architecture/decisions/0027-the-web-app-never-fetches-elevation-and-a-deploy-checks-the-mirror-first.md): the web app never fetches, and a deploy checks the mirror first

## Migration note

- Follow-ups 1 to 6 → `docs/plans/v1-england.md`, WS8, as each is done; corrections to commands → `infra/README.md`
- Follow-up 7 → `infra/README.md` where a step changes, or a decision record for the database roles
- Follow-up 8 → `infra/README.md`, "Rolling back"
- Critical context → `infra/README.md` and the hosting area doc
- Then `git rm docs/handoffs/hosting-on-fly-handoff.md` in the migration commit
