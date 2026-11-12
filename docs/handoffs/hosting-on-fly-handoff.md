# Handoff — Hosting on Fly.io (written and tested offline, nothing deployed yet)

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

**Goal of this session:** move the deployment from Google Cloud to Fly.io (Decision 0018): make the application speak S3 and read Fly's database address and visitor header, write the Fly configuration, scripts and runbook, and check as much as possible against the real platform with the spike apps. That is done and on `main`. Nothing of the real deployment exists on Fly yet.

**Next session should pick up:** ask the owner the two questions under follow-up 1, delete the spike's database cluster (follow-up 2), then carry out [`infra/README.md`](../../infra/README.md) from step 1. Do every cloud step in the main session: sub-agents and workflow agents don't touch Fly, Google or Gandi and don't read `.env`.

**Verification command:**

```sh
git status --short && git log --oneline -1
# Expect: clean, and a commit dated 2026-11-12 or later
cd backend && uv run pytest -q tests/infra tests/test_config.py tests/test_storage.py
# Expect: all pass. tests/infra/test_fly_config.py starts the application with fly.toml's settings
fly apps list --org openantiquity
# Expect: only openantiquity-spike and openantiquity-spike-web until step 1 of the runbook is run
fly mpg list --org openantiquity
# Expect: only the cluster openantiquity-spike, until follow-up 2 deletes it
gcloud storage ls --project fieldclub-uk 'gs://fieldclub-uk-elevation/england/mirror/**' | wc -l
# Expect: 5877 or a little more (the converted tiles, 126.4 GB, copied by 2026-11-12 01:58 UTC)
```

## Done this session

| Commit | Subject | Notes |
|---|---|---|
| `28b794b` and the seven before it | The Fly move | `S3Storage`, `S3Folder`, the object lock, `database_address()`, `Fly-Client-IP`, `fly.toml`, `infra/fly/jobs.toml`, `infra/fly_jobs.py`, `infra/fly-secrets.sh`, `deploy.yml`, the runbook. Built in a worktree, reviewed twice, fixed |
| `b7682bc` | Send each Fly secret on standard input, and name the database flags | `fly secrets import` strips a pair of quotes from around a value, so each secret goes through `fly secrets set NAME=-` |
| `e818793` | Record that Defra's supply answers a Fly machine, in the hosting spike | Two connections at once from `lhr`, 17 to 22 MiB/s each |
| `2a6f347` | Join the security fixes to the Fly move, and widen the crash guard | The per-address stream limit Fly needs to start, and the hourly machine deleting old sign-ins |

## Open follow-ups (priority-ordered)

### 1. Two choices for the owner (a question each)

Neither blocks the runbook. Each needs a decision record once answered, numbered 0025 or later.

- **The spend check.** Decision 0018, point 9, promised an automatic check on spend. Fly has no billing alert and no API to build one on. What `main` has instead: a weekly look at the dashboard (`infra/README.md`, "Spend"), a time limit on every job, and at most three web machines. The owner either accepts that, or asks for something more, such as a scheduled job that adds up machine hours from `fly machine list`. The record supersedes point 9 of Decision 0018.
- **Tiles that aren't in the mirror.** On Fly the web app can't fetch a missing elevation tile, because only the jobs app holds Defra's login (`FIELDCLUB_TERRAIN_API_FETCH = "false"`). A square whose tile is missing answers `elevation_unavailable` for a minute, where Decision 0016 has it answer "being prepared" while the tile is fetched. Once the copy of all 5,877 tiles is in Tigris this only matters if a tile is lost or Defra publishes new ones. The options put to the owner on 2026-11-12: (1) accept it, which is the recommendation; (2) have the hourly machine in the jobs app fetch whatever the web app found missing; (3) give the web app Defra's login, which Decision 0018 rules out. The owner asked for the explanation and hasn't chosen.

### 2. Delete what the spike left on Fly (minutes)

The spike's resources still exist and the database cluster is billed: `openantiquity-spike` (Managed Postgres Basic, id `w867508pyykr3pk4`, $38 a month pro rata), the apps `openantiquity-spike` and `openantiquity-spike-web`, and the Tigris bucket `openantiquity-spike-mirror`. The app `openantiquity-spike` holds Defra's login as secrets. Nothing in the runbook uses any of them. Delete the cluster first. Keep the apps only if a first-time check from the runbook's last section is easier to run on them than on the real apps.

### 3. Carry out the runbook, steps 1 to 7 (half a day)

[`infra/README.md`](../../infra/README.md), "Once: setting up". Say what a step costs before creating anything with a monthly charge. The runbook's "Estimated monthly cost" puts the whole deployment at about $52 to $63 a month at rest, of which Managed Postgres Basic is $38 and its storage $8 to $20. The runbook's last section, "What can only be checked on the real platform", lists each command and flag not yet run for real. Check each as it is first used and correct the runbook where the platform differs. Secrets go to Fly with `bash infra/fly-secrets.sh`, which reads `.env` itself and hands each value to `fly` on standard input. Nobody prints, reads or pastes a secret.

### 4. Copy the elevation from Google to Tigris (about $15 of Google egress, some hours)

Step 8, and `infra/README.md`, "Copying the elevation from Google". Copy the converted tiles from `gs://fieldclub-uk-elevation/england/mirror/` with rclone. Don't fetch them from Defra again. Then steps 9 and 10: the national overview, the first ingests and the hourly machine.

### 5. Point the domains and open the site (an hour, after the owner says so)

Step 11. The DNS records are commented in `infra/dns.toml` and applied with `infra/dns.py`. Check the certificates and that each of the five other names redirects. The sign-in providers have to be registered first with the callback `https://openantiquity.org/api/v1/auth/oauth/<provider>/callback` ([`owner-actions.md`](../plans/owner-actions.md), WS3), and the site stays closed until the owner opens it.

### 6. Take the Google project down (an hour)

`infra/README.md`, "Taking the Google project down", once the site on Fly has passed its checks. Then delete `infra/terraform` and the Google paragraphs of the runbook. Until then the Google deployment keeps image `2a3d8eee8b4b`: an image built from `main` can't run there.

### 7. What the security review left for hosting (small, alongside step 3)

- The session secret goes only to the web app. Check the jobs app starts without it, and never set it there.
- One database login serves both apps. Separate roles for the web app and the jobs were asked for by the review and aren't set up. Decide when the database is made.
- Look at what each Tigris key may do across the three buckets once `fly storage create` has made them.
- The review asked that the tile render queue be sized below a machine's request slots. `fly.toml` allows 30 requests, 26 of them streams, and the defaults are 4 render threads and a queue of 64 (`FIELDCLUB_TERRAIN_RENDER_WORKERS`, `FIELDCLUB_TERRAIN_RENDER_QUEUE`). Set the queue for Fly, or record why the default stands.

## Critical context

- The Fly organisation is `openantiquity` and the region `lhr`. The `personal` organisation holds the owner's unrelated apps: never list, name or touch them, and pass `--app` or `--org openantiquity` on every command.
- Never read, print, edit or delete `.env`. It holds Defra's SFTP login and the Gandi token. The owner has allowed piping its values to this project's own secret stores, on standard input only.
- The owner dislikes Terraform. `infra/terraform` stays only until Google is taken down, and nothing new is written in it.
- The application refuses to start when `FIELDCLUB_EVENTS_MAX_PER_ADDRESS` is more than a quarter of `FIELDCLUB_EVENTS_MAX_STREAMS`. `fly.toml` sets 6 and 26. Change the two together, with the request limits.
- `fieldclub-jobs due`, on the hourly machine, deletes expired sessions and old sign-in links every run. The privacy notice says they are deleted, so the hourly machine has to exist before the site opens.
- Scripts used for the spike, and this session's working notes, are in `var/handoff/` (ignored by git): `fly-spike/put_defra_on_fly.py` and `fly-spike/q5_sftp.py` among them, and `notes.md`.

## References

- [`v1-england.md`](../plans/v1-england.md), WS8: the workstream's state
- [`0018`](../architecture/decisions/0018-hosting-moves-to-fly-io-with-managed-postgres-and-tigris.md): the decision to move
- [`hosting-on-fly-io`](../architecture/decisions/spikes/hosting-on-fly-io.md): what the spike checked on the platform
- [`0016`](../architecture/decisions/0016-terrain-requests-never-wait-for-elevation-and-tiles-draw-on-threads-of-their-own.md): the "being prepared" answer the second choice touches

## Migration note

- Follow-up 1 → two decision records, and the area doc for hosting when WS9 writes it
- Follow-ups 3 to 6 → `docs/plans/v1-england.md`, WS8, as each is done; corrections to commands → `infra/README.md`
- Follow-up 7 → `infra/README.md` where a step changes, or a decision record for the database roles
- Critical context → `infra/README.md` and the hosting area doc
- Then `git rm docs/handoffs/hosting-on-fly-handoff.md` in the migration commit
