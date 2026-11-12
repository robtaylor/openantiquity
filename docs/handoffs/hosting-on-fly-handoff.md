# Handoff — Hosting on Fly.io (running on a private address with terrain and the hourly jobs, not yet open)

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

**Goal of this thread:** move the deployment from Google Cloud to Fly.io (Decision 0018). On 2026-11-12 steps 1 to 10 of the runbook were carried out. The web app runs on Fly on a private address, with Managed Postgres, the whole elevation mirror and the national overview, and it draws terrain. The hourly machine exists. Nothing is public, and only the scheduled monuments have been ingested.

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
# Expect: three machines in lhr, shared-cpu-2x with 2 GB, stopped, suspended or started, on the image of commit e7c0794 or later
fly ips list --app openantiquity
# Expect: one private address and no public one, until step 11
fly machine list --app openantiquity-jobs
# Expect: one machine, `due`, stopped, with the schedule hourly and the volume jobs_var at /data
fly mpg list --org openantiquity
# Expect: the cluster openantiquity, d2gznoqz2n8opkm8, ready, attached to both apps
fly storage list --org openantiquity
# Expect: openantiquity-elevation, openantiquity-cache and openantiquity-photos
uv run infra/fly_jobs.py --commit e7c0794710157b5672fdf1b80c1424c0ec89adc4 run fieldclub-terrain info
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
| `e7c0794` | Draw terrain on Fly, and check the mirror before each deploy | The commit the web app and the jobs image are of. Decision 0027 |
| The commit that last changed this file | Record step 10 | The hourly machine, and what the deploy of `e7c0794` showed |

## Open follow-ups (priority-ordered)

### 1. Read the first nightly refresh (minutes, on 2026-11-13)

The hourly machine `due` was made on 2026-11-12 with its 10 GB volume, from the jobs image of commit `e7c0794`, and its first run found nothing due. Its 03:00 UTC run on 2026-11-13 is the first refresh of every bulk source from Fly, 34 connectors, under a six-hour limit. Read it with `fly logs --app openantiquity-jobs`, or ask the database for the runs, and run by hand any source that failed: `uv run infra/fly_jobs.py --commit e7c0794710157b5672fdf1b80c1424c0ec89adc4 ingest <key>`. Then look at `fly volumes list --app openantiquity-jobs` for how much of the volume the downloads took.

### 2. Take the jobs key's read access off two buckets (the owner, minutes)

The owner made `openantiquity-photos` and set the keys' roles in Tigris's dashboard on 2026-11-12. Each key was then probed from its own app's machine, by listing, by writing and deleting one probe object, and by asking for an object that isn't there.

- The web app's key is as intended: it lists and reads all three buckets, writes the cache and the photos, and is refused a write to the elevation bucket.
- The jobs app's key writes the elevation bucket alone, as intended, but it can also list and read `openantiquity-cache` and `openantiquity-photos`. Step 3 of the runbook gives it no other bucket. Photos are what members upload, and the jobs app holds Defra's login and parses other publishers' files, so the owner should remove both roles in the dashboard. The owner was told on 2026-11-12.

### 3. Wake the machines after a deploy, or accept the first slow request (a choice, minutes)

A deploy leaves the three web machines stopped, and the first request afterwards took 32 seconds on 2026-11-12. The runbook says to ask for `/healthz` once after a deploy. The deploy workflow doesn't do it yet, and can't reach the private address until step 11 gives the app a public one.

### 4. Step 12: the deploy workflow (minutes)

The GitHub environment `production` and a deploy token for the web app alone. The repository is `robtaylor/openantiquity` on GitHub, public since 2026-11-12, and this checkout's `origin`.

### 5. Point the domains and open the site (an hour, after the owner says so)

Step 11. The DNS records are commented in `infra/dns.toml` and applied with `infra/dns.py`. Check the certificates and that each of the five other names redirects. The sign-in providers have to be registered first with the callback `https://openantiquity.org/api/v1/auth/oauth/<provider>/callback` ([`owner-actions.md`](../plans/owner-actions.md), WS3), and the site stays closed until the owner opens it.

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
- The private address answers plain HTTP with a redirect. Reach the app through `fly proxy 8443:443 openantiquity.flycast --app openantiquity` and `curl --resolve openantiquity.fly.dev:8443:127.0.0.1 https://openantiquity.fly.dev:8443/...`.

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
