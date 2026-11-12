# Handoff — Hosting on Fly.io (apps and elevation in place, nothing deployed yet)

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

**Goal of this thread:** move the deployment from Google Cloud to Fly.io (Decision 0018). The application, the Fly configuration, the scripts and the runbook are on `main`, tested offline. On 2026-11-12 the two apps and the elevation bucket were made, and England's converted elevation was copied from Google into Tigris and checked. No machine of the real deployment exists yet, and Fly has no database for it.

**Next session should pick up:** ask the owner the question under follow-up 1 and the one under follow-up 2, then carry out [`infra/README.md`](../../infra/README.md) from step 2. Do every cloud step in the main session: sub-agents and workflow agents don't touch Fly, Google or Gandi and don't read `.env`.

**Verification command:**

```sh
git status --short && git log --oneline -1
# Expect: clean, and a commit dated 2026-11-12 or later
cd backend && uv run pytest -q tests/infra tests/test_config.py tests/test_storage.py
# Expect: all pass. tests/infra/test_fly_config.py starts the application with fly.toml's settings
fly apps list --org openantiquity
# Expect: openantiquity and openantiquity-jobs, pending, and the spike's two apps until follow-up 2 deletes them
fly machine list --app openantiquity-jobs
# Expect: none, until step 7 of the runbook starts a job
fly storage list --org openantiquity
# Expect: openantiquity-elevation, and openantiquity-spike-mirror until follow-up 2
fly mpg list --org openantiquity
# Expect: only the cluster openantiquity-spike, until follow-up 2 deletes it and step 2 makes `openantiquity`
fly secrets list --app openantiquity-jobs
# Expect: the five names `fly storage create` set and no RCLONE_ name
gcloud storage ls --project fieldclub-uk 'gs://fieldclub-uk-elevation/england/mirror/**' | wc -l
# Expect: 5877, the tiles the Tigris bucket was checked against
```

## Done so far

| Commit | Subject | Notes |
|---|---|---|
| `28b794b` and the seven before it | The Fly move | `S3Storage`, `S3Folder`, the object lock, `database_address()`, `Fly-Client-IP`, `fly.toml`, `infra/fly/jobs.toml`, `infra/fly_jobs.py`, `infra/fly-secrets.sh`, `deploy.yml`, the runbook. Built in a worktree, reviewed twice, fixed |
| `b7682bc` | Send each Fly secret on standard input, and name the database flags | `fly secrets import` strips a pair of quotes from around a value, so each secret goes through `fly secrets set NAME=-` |
| `e818793` | Record that Defra's supply answers a Fly machine, in the hosting spike | Two connections at once from `lhr`, 17 to 22 MiB/s each |
| `2a6f347` | Join the security fixes to the Fly move, and widen the crash guard | The per-address stream limit Fly needs to start, and the hourly machine deleting old sign-ins |
| The commit that last changed this file | Copy the elevation into Tigris, and record the spend check | Runbook step 1, the elevation bucket of step 3 and the copy of step 8, done on Fly. Decision 0025. The runbook and the plan say what the platform did |

## Open follow-ups (priority-ordered)

### 1. One choice for the owner: tiles that aren't in the mirror

The spend check is settled: Decision 0025 records the weekly look and the limits.

Still open. On Fly the web app can't fetch a missing elevation tile, because only the jobs app holds Defra's login (`FIELDCLUB_TERRAIN_API_FETCH = "false"`). A square whose tile is missing answers `elevation_unavailable` for a minute, where Decision 0016 has it answer "being prepared" while the tile is fetched. The answer needs a decision record, 0026 or later.

What the owner said on 2026-11-12, in order: asked whether the reasoning was recorded; proposed checking for and fetching missing tiles at each deployment; then asked for the data to be moved from Google once, which is done. The owner hasn't said whether the check at each deployment is still wanted now that the mirror is whole.

What was found while answering, for the record to carry:

- The fetcher knows only the 5,877 tiles of the 2022 composite, a list packaged with the code (`backend/src/fieldclub/terrain/catalogue.py`). All 5,877 are in Tigris. So a fetch on demand could only replace a tile that had gone from the bucket. New tiles from Defra need a change to the code either way.
- `fieldclub-terrain mirror` lists the bucket once and fetches only what the catalogue has and the bucket lacks. With nothing missing it never connects to Defra. `uv run infra/fly_jobs.py mirror 1 2 3 4` is therefore already a check that repairs.
- A check at each deployment can't run from GitHub, whose token reaches only the web app, so it would be a third command by hand in the runbook's "A deploy". It shouldn't gate the web deploy. Against an empty bucket it would fetch the whole country from Defra, so it wants a cap on how many tiles it will fetch unasked.
- No document says why the web app holds no supply login. Decision 0018, point 7, states the rule alone. The Google deployment had a switch for it, `service_fetches_elevation`, applied as false. The record should give the reason: the login was issued to the owner under a Defra ticket, a public service has no use for it once the mirror is whole, and the web app's key can't write the elevation bucket.

### 2. Delete what the spike left on Fly (minutes, once the owner says so)

The owner was asked on 2026-11-12 and hasn't answered. The spike's resources still exist and the database cluster is billed: `openantiquity-spike` (Managed Postgres Basic, id `w867508pyykr3pk4`, $38 a month pro rata, about $1.30 to $1.45 a day with its storage), the apps `openantiquity-spike` and `openantiquity-spike-web`, and the Tigris bucket `openantiquity-spike-mirror`. The app `openantiquity-spike` runs a 1 GB machine and holds Defra's login as secrets. Nothing in the runbook uses any of them, and the checks made on 2026-11-12 ran on the real jobs app. The recommendation put to the owner is to delete all four, the cluster first.

### 3. Carry out the runbook, steps 2 to 7 (half a day)

[`infra/README.md`](../../infra/README.md), "Once: setting up". Step 1 is done. In step 3 the elevation bucket is done: don't run that `fly storage create` again. Say what a step costs before creating anything with a monthly charge. The runbook's "Estimated monthly cost" puts the whole deployment at about $51 to $62 a month at rest, of which Managed Postgres Basic is $38 and its storage $8 to $20. The owner asked for the database's costs on 2026-11-12 and hasn't yet said to create it. The runbook's last section, "What can only be checked on the real platform", lists each command and flag not yet run for real. Check each as it is first used and correct the runbook where the platform differs. Secrets go to Fly with `bash infra/fly-secrets.sh`, which reads `.env` itself and hands each value to `fly` on standard input. Nobody prints, reads or pastes a secret. `fly storage create` prints the new key: send its output through a filter that drops any line naming a key.

### 4. The national overview, the first ingests and the hourly machine (some hours)

Steps 9 and 10. The elevation is in Tigris. Google's bucket held no national overview, so step 9 builds it on Fly, on a `performance-8x` machine for a dollar or two. Both need the jobs app's image from step 7 and the database from step 2.

### 5. Point the domains and open the site (an hour, after the owner says so)

Step 11. The DNS records are commented in `infra/dns.toml` and applied with `infra/dns.py`. Check the certificates and that each of the five other names redirects. The sign-in providers have to be registered first with the callback `https://openantiquity.org/api/v1/auth/oauth/<provider>/callback` ([`owner-actions.md`](../plans/owner-actions.md), WS3), and the site stays closed until the owner opens it.

### 6. Take the Google project down (an hour)

`infra/README.md`, "Taking the Google project down", once the site on Fly has passed its checks. Its first check, that Tigris lacks none of Google's tiles, was made on 2026-11-12. Then delete `infra/terraform` and the Google paragraphs of the runbook. Until then the Google deployment keeps image `2a3d8eee8b4b`: an image built from `main` can't run there.

### 7. What the security review left for hosting (small, alongside step 3)

- The session secret goes only to the web app. Check the jobs app starts without it, and never set it there.
- One database login serves both apps. Separate roles for the web app and the jobs were asked for by the review and aren't set up. Decide when the database is made.
- Look at what each Tigris key may do across the three buckets once `fly storage create` has made them.
- The review asked that the tile render queue be sized below a machine's request slots. `fly.toml` allows 30 requests, 26 of them streams, and the defaults are 4 render threads and a queue of 64 (`FIELDCLUB_TERRAIN_RENDER_WORKERS`, `FIELDCLUB_TERRAIN_RENDER_QUEUE`). Set the queue for Fly, or record why the default stands.

## Critical context

- The Fly organisation is `openantiquity` and the region `lhr`. The `personal` organisation holds the owner's unrelated apps: never list, name or touch them, and pass `--app` or `--org openantiquity` on every command.
- Never read, print, edit or delete `.env`. It holds Defra's SFTP login and the Gandi token. The owner has allowed piping its values to this project's own secret stores, on standard input only.
- A new access grant or key on Google needs the owner's word each time. The standing permission for gcloud didn't cover the temporary read-only account the copy used: the owner allowed that one by name, and it has been deleted.
- The owner dislikes Terraform. `infra/terraform` stays only until Google is taken down, and nothing new is written in it.
- The application refuses to start when `FIELDCLUB_EVENTS_MAX_PER_ADDRESS` is more than a quarter of `FIELDCLUB_EVENTS_MAX_STREAMS`. `fly.toml` sets 6 and 26. Change the two together, with the request limits.
- `fieldclub-jobs due`, on the hourly machine, deletes expired sessions and old sign-in links every run. The privacy notice says they are deleted, so the hourly machine has to exist before the site opens.
- Scripts used for the spike, and the working notes of the session that wrote the move, are in `var/handoff/` (ignored by git): `fly-spike/put_defra_on_fly.py` and `fly-spike/q5_sftp.py` among them, and `notes.md`.

## References

- [`v1-england.md`](../plans/v1-england.md), WS8: the workstream's state
- [`0018`](../architecture/decisions/0018-hosting-moves-to-fly-io-with-managed-postgres-and-tigris.md): the decision to move
- [`0025`](../architecture/decisions/0025-spend-on-fly-is-watched-by-hand-each-week-and-bounded-by-limits.md): the spend check, in place of point 9 of 0018
- [`hosting-on-fly-io`](../architecture/decisions/spikes/hosting-on-fly-io.md): what the spike checked on the platform
- [`0016`](../architecture/decisions/0016-terrain-requests-never-wait-for-elevation-and-tiles-draw-on-threads-of-their-own.md): the "being prepared" answer the open choice touches

## Migration note

- Follow-up 1 → one decision record, and the area doc for hosting when WS9 writes it
- Follow-ups 3 to 6 → `docs/plans/v1-england.md`, WS8, as each is done; corrections to commands → `infra/README.md`
- Follow-up 7 → `infra/README.md` where a step changes, or a decision record for the database roles
- Critical context → `infra/README.md` and the hosting area doc
- Then `git rm docs/handoffs/hosting-on-fly-handoff.md` in the migration commit
