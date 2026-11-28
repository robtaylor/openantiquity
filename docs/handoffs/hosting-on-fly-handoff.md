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

**Goal of this thread:** move the deployment from Google Cloud to Fly.io (Decision 0018). On 2026-11-12 steps 1 to 11 of the runbook were carried out. The web app runs on Fly and answers on `openantiquity.org`, with Managed Postgres, the whole elevation mirror and the national overview, and it draws terrain. The hourly machine runs, and its first nightly refresh, on 2026-11-13, loaded every bulk source but two. From 2026-11-21 to 2026-11-24 the nightly refresh failed, because the machine's volume was full. The fix is on the hourly machine since 2026-11-24, and the refresh of 2026-11-25 completed on it: all 13 sources that were due refreshed, and the volume went from 9,437 MB used to 5,237. Since 2026-11-27 the site reports how the refresh is going, and a scheduled workflow raises a GitHub issue when it is behind (Decision 0044). The deploy workflow has its token since the same day and has deployed the web app twice (step 12). OpenStreetMap and Google sign-in are on, and the owner has signed in the whole way with each.

**Next session should pick up:** follow-up 1 first, which is to see the first refresh to be written down, on 2026-11-29, close issue 23. Once it has, lengthen the nightly sources' interval, as that follow-up says. Then 2 and 3, which wait on the owner. Do every cloud step in the main session: sub-agents and workflow agents don't touch Fly, Google or Gandi and don't read `.env`.

**Verification command:**

```sh
git status --short && git log --oneline -1
# Expect: clean, and a commit dated 2026-11-12 or later
cd backend && uv run pytest -q tests/infra tests/test_config.py tests/test_storage.py
# Expect: all pass. tests/infra/test_fly_config.py starts the application with fly.toml's settings
fly apps list --org openantiquity
# Expect: openantiquity and openantiquity-jobs alone
fly machine list --app openantiquity
# Expect: three machines in lhr, shared-cpu-2x with 2 GB, stopped, suspended or started, on the image of commit 32f62d6 or later
fly ips list --app openantiquity
# Expect: the private address, the shared IPv4 address 66.241.124.216 and the IPv6 address 2a09:8280:1::1fe:8e38:0
fly machine list --app openantiquity-jobs
# Expect: one machine, `due`, stopped, on the image of commit 32f62d6, with the schedule hourly and the volume jobs_var at /data
curl -s https://openantiquity.org/api/v1/sources/refresh-state
# Expect: the refresh `current` and every source `current`, once the refresh of 2026-11-29 has finished
gh issue list --label refresh-failed --state open
# Expect: none, once the check of 2026-11-29 has run at 10:23 UTC
fly mpg list --org openantiquity
# Expect: the cluster openantiquity, d2gznoqz2n8opkm8, ready, attached to both apps
fly storage list --org openantiquity
# Expect: openantiquity-elevation, openantiquity-cache and openantiquity-photos
uv run infra/fly_jobs.py --commit 32f62d65a8a0eee14f12157456e13da7679604e8 run fieldclub-terrain info
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
| `de016fa` | The restricted level's code removed | The commit the hourly machine ran until 2026-11-13. Its release made the check on `findings.sensitivity` again with two values |
| `25a218d` | Terrain tiles that wait, and the map switch first in the layer panel | The map asks again for a tile the server answers 503 with a `Retry-After`. Found by the owner on the live site |
| `db914b9` | The drawing guide, midpoint dots, an unsaved marking kept, and a map that stays put | Frontend only |
| `d8f42e0` | Large records passed over, and pages that arrive once | Frontend only |
| `416f8f7` | Towns named again, Multi-direction shade as the view the map opens on, and a linked record that opens its source | A record of a source with no page for each record is served with the address of the viewer that holds its material |
| `d82679f` | Read a stored class this version has no name for as "Not sure" | Decision 0035, released by itself. The schema step now only widens a vocabulary's check, so going back to this commit or a later one doesn't narrow one. Both apps ran it before the next release |
| `770cadc` | A "Building or ruin" class | Its release added the value to the three class checks |
| `ac70989` | Zoom in to 22, and a right-click left alone while a tool has the map | Frontend only |
| `3fd51cb` | An unfinished marking kept in sight and asked about, not jumped to | Frontend only |
| `06bbdc6` | The map puts findings first, and record counts are a switch | Decision 0036. Frontend only. With counts off, no record tile is asked for further out than zoom 12 |
| `0f16806` | "Change the shape" asks before it discards something unsaved, and focus is left where it has moved to | Frontend only |
| `170f381` | A link to the code on GitHub at the foot of the rail and under "More" | Frontend only |
| `0eab403` | "Report a problem": a form that shows what it sends, a request id on every answer and log line, and the running commit in `/meta` | Decision 0037. The web app's log lines now come in the app's own format, each with its request's id |
| `64fbb0b` | The moderation log leaves out a row a later version wrote | The first step of lines phase 2, released by itself ahead of the action that phase adds |
| `464d7ef` | Lines phase 2, the backend: keepers, suggestions and an admin's removal of an orphaned marking | The commit the hourly machine runs since 2026-11-14. Decisions 0038 to 0041. Its release added three columns to `findings` and the table `shape_suggestions`, and widened two vocabulary checks. The step was rehearsed first on a database built by the version before, and took half a second. The interface for it isn't released yet, so nobody is a keeper but a finder and no suggestion exists. The hourly machine ran once on it at 07:45 UTC and exited 0 |
| `4aba94d` | Lines phase 2, the interface: the keeper's byline, suggesting and deciding a change, handing a marking on, and the admins' list and removal | The commit the web app runs since 2026-11-14. Decision 0042: nothing drawn and not sent is replaced without asking, which also changed "Change the shape". Its one backend change is a comment, so the jobs image wasn't rebuilt |
| `8be0564` | The long line's save is timed as the fastest of five | A test alone, after one red run of the Backend job on `main`. Nothing was released |
| `0f33f0f` | A download removes the copy it replaces before it fetches, and what it fetched when the disk fills | Decision 0043, the owner's choice of remedy for the full volume. Jobs code alone |
| `53493cf` | The deploy workflow asks `/healthz` as its last step | The commit the hourly machine runs since 21:54 UTC on 2026-11-24. One source was run from its image first, on a machine of its own, and completed. The web app wasn't deployed and still runs `4aba94d`: nothing it serves changed |
| `3ef1c7f` | Step 12 is recorded: the deploy workflow's environment and token | Made on 2026-11-27 at the owner's word: the environment `production`, limited to `main`, and a 90-day deploy token for the web app alone, which expires on 2027-02-25. The workflow's first run deployed `73f6f46`, and every step passed, the last one that wakes a machine among them |
| `32f62d6` | The refresh writes down each of its runs, the site reports how it is going, and a scheduled workflow raises an issue when it is behind | Decision 0044, at the owner's asking. The commit the web app runs since 2026-11-27 and the hourly machine since 19:05 UTC on 2026-11-28. Its release added the table `refresh_runs`. The deploy workflow deployed it |

## Open follow-ups (priority-ordered)

### 1. See the first refresh to be written down close issue 23 (minutes)

The refresh check went live on 2026-11-27 (Decision 0044, and `infra/README.md`, "What to watch"). Tried by hand that evening, it opened issue 22 while no refresh had been written down, and closed it once one had.

The release wasn't finished that evening. The hourly machine stayed on the image of `53493cf` until 19:05 UTC on 2026-11-28, so the refresh of 2026-11-28 ran as usual and wasn't written down. The first scheduled check, at 10:25 UTC that morning, opened issue 23, which is a false alarm and has a comment that says so. All 30 sources were current.

The refresh the machine starts at about 03:41 UTC on 2026-11-29 is the first to be written down, and the check at 10:23 UTC that morning should close issue 23. Read all three:

- `curl -s https://openantiquity.org/api/v1/sources/refresh-state`: the refresh `current`, started in the hour of 03:00 on 2026-11-29 and finished, and every source `current`.
- `gh issue list --label refresh-failed --state all`: 23 closed, with the workflow's comment.
- `gh run list --workflow refresh-check.yml`: a successful run with the event `schedule` on 2026-11-29.

Left in the database on the evening of 2026-11-28, and expected to clear at that refresh: a refresh started by hand at 19:05 UTC found `he-aim-monument-extents` due, a run of about an hour, and was stopped after four minutes, because `fly_jobs.py run` gives a command one hour. Its `refresh_runs` row has no end, and that source's `ingest_runs` row is `running`, so the report gives the source as failed from about 01:20 UTC until the night's refresh runs it again.

What this left:

- Once the check is seen working, the owner wants the sources refreshed less often (2026-11-28: "archeological records probably don't change very often"). Thirteen sources are refreshed nightly, with a `max_age` of 20 hours, because their publishers rebuild their exports daily and not because the records change daily: the National Heritage List layers, the conservation areas, Pleiades, XRONOS, RIB and the Roman roads. `he-nhle-listed-buildings-points` alone is 380,000 records and half an hour a night. A week for each was proposed to the owner, with one question: whether any, the scheduled monuments for one, should stay nightly. The job itself stays nightly. It takes seconds when nothing is due, and the check counts on a refresh being written down each night and reads each source's own interval, so it needs no change.
- `fly_jobs.py` has no job for a refresh by hand with the six hours a refresh gets. `run fieldclub-jobs refresh-sources` has one hour, which is enough only when no long source is due. A `refresh` job beside `ingest` would be a few lines and a test.
- The deploy token expires on 2027-02-25 (`infra/README.md`, step 12).
- One frontend test fails now and then on a busy machine: in `FindingPanel.test.tsx`, "reminds people of the rules before a site visit is logged", which waits a second for the form's heading to take focus. It failed twice running on 2026-11-27 with this Mac under load, and passed six times after, on `main` too.

Also seen in the runs of 2026-11-13 to 2026-11-25:

- `he-nhle-world-heritage-sites` failed on 2026-11-18 and 19 with `UpstreamFormatError`, because one entry had no Notes, and completed on the 20th. One odd record upstream stops the whole source.
- `bern-xronos-radiocarbon` failed once, on 2026-11-18, when the publisher answered 522.
- The lock fix of `7175a31` held at the length that failed: `he-aim-monument-extents` completed on 2026-11-21 in 62 minutes, the first run of over an hour to complete on the hourly machine.
- A night that refreshes `he-aim-detailed-mapping` is a long one. On 2026-11-25 the refresh ran from 03:41 to 05:52 UTC, about an hour and a half of it on that source and half an hour on `he-nhle-listed-buildings-points`. The machine's command allows six hours.
- One empty `.part.json` note is left on the volume, in `he-nhle-protected-wreck-sites`, from the nights that failed. That source was run on 2026-11-24 on a machine of its own, to try the new image, so its folder on the volume wasn't touched. An empty note holds no room and is read as no note, and the source's next refresh on the volume removes it.

To run a source by hand: `uv run infra/fly_jobs.py --commit 32f62d65a8a0eee14f12157456e13da7679604e8 ingest <key>`, which downloads afresh on a disk of its own and doesn't touch the volume.

The hourly machine `due` wasn't started by its schedule at 22:41 or 23:41 on 2026-11-12, after it was first moved to a new image. That was seen once and the reason isn't known, so `schedule` now starts it once after updating it, and it has run every hour since. After the move to `53493cf` its schedule started it at 22:41 UTC on 2026-11-24, the first hour after. Starting it by hand to read the volume, at 06:18 UTC on 2026-11-25, didn't put the schedule off: it started again at 06:41.

### 2. Sign-in, and what opening to the public still needs (the owner)

The domains were pointed at Fly on 2026-11-12 at the owner's word ("noone will be looking yet"). The site answers on `openantiquity.org` and anyone can look at the map.

- OpenStreetMap and Google sign-in are on since 2026-11-12, so anyone with an account at either can join and post. The owner signed in the whole way with OpenStreetMap on 2026-11-12 and with Google on 2026-11-27.
- Both providers' ids and secrets are in `.env`, as `OSM_AUTH2_ID`, `OSM_AUTH2_SECRET`, `GOOGLE_OAUTH2_ID` and `GOOGLE_OAUTH2_SECRET`, and were piped to the web app's secrets by `var/handoff/tools/env_to_fly_secrets.py`, which shows none of them. Google's application is in production in a Google project of its own, not `fieldclub-uk`, which is to be deleted.
- Since 2026-11-13 a finding is open or protected, and no request can set the restricted level (Decision 0032, `docs/plans/archive/two-sensitivity-levels.md`). The level's code came out the same day (`de016fa`).
- The app has no gate. The owner was told on 2026-11-12, and that [`owner-actions.md`](../plans/owner-actions.md) holds a public launch until an operator is named and the terms, the privacy notice and the Online Safety Act assessment exist (WS14 to WS17). A setting that limits sign-up to named accounts was offered and not yet asked for.
- The other providers and the mail relay are in `owner-actions.md`, WS3.

### 3. Take the Google project down (an hour)

`infra/README.md`, "Taking the Google project down", once the site on Fly has passed its checks. Its first check, that Tigris lacks none of Google's tiles, was made on 2026-11-12. Then delete `infra/terraform` and the Google paragraphs of the runbook. Until then the Google deployment keeps image `2a3d8eee8b4b`: an image built from `main` can't run there.

### 4. One way to read every stored vocabulary (a day)

Decision 0033 passes over an activity kind or a next step this version has no name for, and Decision 0035 reads a feature class it has no name for as "Not sure". Every other vocabulary stored as text is still read strictly, so a value added to one takes a release of its own first, as the building class did. A review on 2026-11-13 listed the strict reads: a second look's `visible`, an evidence item's kind and stance, a finding's period, tier, state and level, a mention's kind, a shape's kind, an investigation item's kind and a person's role. The evidence kind, the mention kind, the shape kind and the investigation item kind are the likeliest to grow. One helper that reads a stored value with a rule chosen for its vocabulary, and the response type that `ShownClass` is for classes, would replace both mechanisms. Until then, a new value in any of these needs the two releases.

### 5. What the day's map changes left (hours each)

- Multi-direction shade is three colour channels where Composite is one, so its tiles are about two and a half times the bytes: 360 to 450 KB against 140 to 170 KB, measured on the live site on 2026-11-13. It is now the view the map opens on. A palette or WebP encoding would cut that, and changes the pixels, so the style's version goes up with it.
- Marking a finding doesn't record itself as the tool that has the map (`map/tool.ts`), so each handler asks about marking in its own way: the records hook, the findings layer and the scan layer. Having the marking pages set the tool would leave one question to ask.
- A view zoomed out that holds more than 500 findings draws 500 and says so (Decision 0036). When that becomes usual, have the server count findings by area as the record tiles do.
- Terrain past zoom 16 was tried and gives a modest gain for Composite alone ([the spike](../architecture/decisions/spikes/deeper-terrain-tiles.md)).

### 6. What the security review left for hosting

- Done: the jobs app's Tigris key was put right by the owner on 2026-11-12. Tried from a jobs machine, it lists, reads and writes the elevation bucket and is refused all three on the cache and the photos.
- Done: the jobs app has no session key, and its jobs start without one. The tile render queue on Fly is 16, inside the soft limit.
- Open: one database login, `fly-user` with the role `schema_admin`, serves both apps. Managed Postgres offers the roles `schema_admin`, `writer` and `reader` (`fly mpg users create`). The web app's release command creates the schema, so the web app's login needs `schema_admin` as things are. Giving the web app `writer` means moving the schema command to the jobs app, a change to how a deploy runs. It can be done later without making the cluster again. The owner was told on 2026-11-12.
- Open: `timeout` stopping a job that runs past its limit hasn't been seen on Fly.

### 7. Check Managed Postgres's backups before relying on them (an hour)

How long Fly keeps backups wasn't found, and no restore has been tried. `fly mpg backup list d2gznoqz2n8opkm8`, then restore one into a new cluster, look, and destroy it. The owner kept Managed Postgres for its backups and failover, so this is worth doing before the site holds anything a member wrote.

### 8. What the report form left (minutes to hours each)

- The email link stays hidden until `FIELDCLUB_REPORT_EMAIL` is set on the web app, which waits for `help@openantiquity.org` to take mail.
- Fly's seven days of searchable log is its documented figure and hasn't been tried on this account. The first real report is the test: search the log for one of its request ids.
- A report too long for an address is also copied as the issue opens. No automated test can show that copy outliving the move to the other tab, since a page under test always counts as focused. Try it once by hand in Chrome, Firefox and Safari.
- The outline of the island of Ireland is drawn twice, in `services/gridref.py` and in the frontend's `map/gridref.ts`, and the two differ by a few hundredths of a degree along edges that look like open sea. A report's square and a protected finding's public square should come from one outline, with a test that sets them side by side.
- Nothing fails when `frontend/src/api/schema.d.ts` is stale against the backend. `paths.ts` has a test now. A step in CI that runs `pnpm gen:api` and fails on a difference would cover both.
- Finding duplicates among reports is the plan's third workstream, and waits on whether GitHub's own suggestions are on for the repository.

### 9. What lines phase 2 left for hosting (minutes each)

- Going back a version from `464d7ef` or later: the version before doesn't know keepers, so a finder could again edit a marking they handed on and a keeper who isn't the finder couldn't. Nothing is sent to anyone who shouldn't see it, and the earlier version's schema step leaves the new columns and table alone. This was rehearsed on a scratch database on 2026-11-14.
- The hourly limits on suggestions and offers are counted on each machine, so with three machines serving the real ceiling is three times the figure.
- The owner's answer on whether a keeper who isn't the finder may give a second look is still open in `docs/plans/lines-phase-2.md`. It is built as "no".

### 10. Making an admin is done by hand (an hour, if a command is wanted)

- The live site had no admin or moderator until 2026-11-20, so nobody could open the moderation screens or the admins' list of markings without a keeper. The owner asked for their account to be made an admin that day, and it was. It was the only account: nobody else had signed in.
- Admins are made outside the API (`services.moderation.check_role_change`), and no command does it. The change was made on a web machine through `fly ssh console`, in one transaction: set the role, then run `services.moderation.reassess_standing` for that account, as a role change through the API does, because a person's role weighs in the confidence of what they found. Setting the role alone would leave their findings scored at the old weight until each is next reassessed. It moved no score and added nothing to the feed.
- A second admin, or taking the role away, needs the same two steps. A `fieldclub-jobs` command with tests would make that one line.

### 11. Answers the owner owes (the owner)

Each question is written once, in its plan, with a recommendation. Nothing below is to be built before its answer.

- [`kinds-of-feature.md`](../plans/kinds-of-feature.md), "Open questions for the owner": whether to accept the 95 proposed kinds, all 18 classes at once, a kind under a class the thesaurus files it beside, and buildings by function.
- [`say-more-about-a-heritage-record.md`](../plans/say-more-about-a-heritage-record.md), "Open questions for the owner": three.
- [`junior-accounts.md`](../plans/junior-accounts.md), "Open questions for the owner": five that the readings of 2026-11-14 added. Its workstreams 2 to 5 also wait for the two assessments in [`owner-actions.md`](../plans/owner-actions.md).
- [`lines-phase-2.md`](../plans/lines-phase-2.md): whether a keeper who isn't the finder may give a second look. It is built as "no". The answer goes into the plan, and into Decision 0038 while that is still Proposed, and the plan is then archived.
- [`report-a-problem.md`](../plans/report-a-problem.md): whether a report keeps its option to send the map's one-kilometre square, and word that `help@openantiquity.org` takes mail (follow-up 8).
- Not written anywhere else: whether to drop the National Library of Scotland's three-light hillshade from the layers. It is the same technique as Multi-direction shade over the same survey, drawn by someone else, and its description says so since 2026-11-13.

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

- The refresh, sign-in, the deploy workflow, opening to the public and taking Google down → `docs/plans/v1-england.md`, WS8, as each is done; corrections to commands → `infra/README.md`
- The database roles → a decision record, and `infra/README.md` where a step changes
- Going back a version → `infra/README.md`, "Rolling back"
- Critical context → `infra/README.md` and the hosting area doc
- Then `git rm docs/handoffs/hosting-on-fly-handoff.md` in the migration commit
