# Plan — v1 England: from LIDAR to corroborated findings

**Status:** Active.

## Goal

A deployed Open Antiquity covering England. People explore 1 m LIDAR in archaeological visualisations, mark findings, check each other's findings up the confidence ladder, and link them to England's open heritage records. This plan implements Decisions 0001 to 0009.

## Prerequisites

- The research pass of 2026-11-10 is complete. Its evidence is in the spikes under `architecture/decisions/spikes/` and the source catalogue under `sources/`.
- Decisions 0001 to 0009 are written. Each stays Proposed until its code is built and checked.
- The build contract in `ARCHITECTURE.md` describes the tables, API and confidence rules to build.

## Where things stand (2026-11-12)

- WS0 and WS1 are shipped in the first commits on `main`.
- The whole backend is on `main`: terrain, sign-in, findings with the confidence engine, the record index with its connectors, the collaboration and moderation routes, and the scheduled jobs. Its suite stood at 5,793 tests on 2026-11-12. Each track was built in its own worktree, reviewed adversarially, fixed, and rebased onto `main`, and the places where tracks meet were reviewed twice more.
- The whole interface is on `main`: joining, Explore, marking, a finding's page with its two-step second look, mentions and timeline, help wanted, records, search, layers and the terrain tools, investigations, scan a square, activity, notifications and live updates, profiles, reporting, moderation, the guide and the draft notices. Its suites stood at 1,277 unit tests, 268 browser tests against stand-in answers and 34 against a real backend on 2026-11-12.
- The development database holds about 1.45 million records from 31 sources, a gazetteer of 273,525 place names, and the nation and county boundaries.
- Decisions 0010 to 0024 were written during the build, each from a review finding, a seam between tracks or an owner's choice. All are Proposed until WS9 checks them against the code.
- The security and privacy review of the finished code ran on 2026-11-12, and its fixes are on `main` (WS9).
- The project was renamed from Field Club to Open Antiquity on 2026-11-11, and `openantiquity.org` was registered (Decision 0017). The internal identifier is still `fieldclub`.
- The Google Cloud project `fieldclub-uk` runs the service and its jobs, held back from the public (`service_public = false`), since 2026-11-11. The tables exist, and the whole-country elevation copy finished at 01:58 UTC on 2026-11-12: 5,877 converted tiles, 126.4 GB. The deployment is moving to Fly.io (WS8), and an image built from `main` no longer runs on Google. On Fly, since 2026-11-12, the web app answers on openantiquity.org with its database, and the elevation and the national overview are in their Tigris bucket. Nobody can sign in yet.
- Defra supplied England's 2022 composite DTM in bulk on the day it was asked, ticket DSP3-11967. See `owner-actions.md` and `../sources/lidar-england-bulk-supply.md`. Eleven tiles around Avebury and Stonehenge are in the local mirror folder for development.

## Workstreams

### WS0 — Foundation

**Status:** Shipped 2026-11-10 in the first commits on `main`.

The backend core and the frontend shell that every later workstream builds on.

**Deliverables:**

- Backend package with settings, database schema, models for every table, sessions, the activity service, the ingest runner and the test fixtures.
- Frontend shell with the design system, the map module, layer control, compare, 3D and permalinks.

**Exit criteria:**

- Backend and frontend check suites pass after two independent reviews and a fix pass each.

### WS1 — Rename and contract sync

**Status:** Shipped 2026-11-10 in the first commits on `main`.

One audited rename from the working name to `fieldclub` across directories, imports, settings, cookie and header names, database names, Docker volumes and docs. Then the foundation code is brought into line with the contract changes made after it was built: the age band and terms acceptance, three sensitivity levels with a stored public position, and photo approval.

**Deliverables:**

- No trace of the working name left anywhere in the repo, with both check suites passing.
- The foundation's models, vocabularies and services match `ARCHITECTURE.md` as it now stands, with tests.
- Every dependency the later workstreams need is installed, so parallel work doesn't contend for the lock file.

**Exit criteria:**

- Both check suites pass and a search for the old name finds nothing.
- The first commit is made.

### WS2 — Terrain

**Status:** Shipped 2026-11-11. The exit criteria are met: the synthetic-terrain and seam tests pass, Avebury's bank and ditch are clear with no seams in every view in the running app, and a cached tile is served from the cache alone. Two things remain and are tracked elsewhere: the whole-country copy into a bucket (WS8), and the 351 km² gap over the North York Moors, which needs Defra's post-2022 tiles and is deferred.

England's elevation behind one interface, the visualisations, and the tile endpoints. See Decision 0006 and `sources/lidar.md`.

**Deliverables:**

- An elevation reader over a mirror of cloud-optimised files, in a local folder or a bucket, that fetches a missing source tile from Defra's bulk supply on first use and converts it.
- numpy implementations of hillshade, multi-direction hillshade, slope, local relief, sky-view factor, openness and the combined blend, with the published presets.
- Rendered tiles, Terrarium elevation tiles, the height profile endpoint, and a coverage layer with capture year.
- A command that mirrors named 5 km tiles or all of England, reading in windows and resuming after a dropped connection.
- A national overview for zooms below 13, built from the 8 m copies inside our own mirrored tiles. Defra's national 10 m composite can't be downloaded: its server cuts every response at about 1.08 GB and ignores range requests.

**Exit criteria:**

- Tests on synthetic terrain show each visualisation responds to a known mound and ditch as expected, and adjacent tiles match at their shared edge to within one grey level.
- A screenshot of Avebury in the combined blend shows the henge bank and ditch clearly and has no visible tile seams.
- A cached tile is served without calling the publisher.

### WS3 — Accounts

**Status:** Shipped 2026-11-11. Each provider flow passes against a mocked provider, and `frontend/e2e-full/findings.spec.ts` marks a finding signed out, signs in through the development sign-in and finds the draft saved once. Provider credentials are an owner action, so no real provider has been exercised.

Provider sign-in, the emailed link, the welcome sheet and account deletion. See Decisions 0002 and 0009.

**Deliverables:**

- A server-side sign-in flow for Google, Apple, Microsoft, Facebook and OpenStreetMap, each enabled by its settings, plus the emailed one-time link.
- The welcome sheet: handle, age band and contributor terms.
- Browser drafts for signed-out work, the sign-in sheet, and saving the drafts after sign-in.

**Exit criteria:**

- Each provider flow passes tests against a mocked provider, including a forged state, a replayed code and an unverified email.
- An end-to-end test marks a finding signed out, signs in through the development login, and finds the draft saved.

### WS4 — Findings and confidence

**Status:** Shipped 2026-11-11. The engine has its boundary, invariant and adversarial tests, `frontend/e2e-full/finding.spec.ts` takes a finding from spotted to corroborated with three accounts, and `backend/tests/test_routes.py` fails for any route that carries a position without a leak test.

The core loop. See Decisions 0003, 0005 and 0008.

**Deliverables:**

- Findings, observations, evidence, votes, comments and follows, with the confidence engine recomputing on every change.
- The three sensitivity levels, enforced in one place and tested for every viewer type.
- The blind second-look queue, the help-wanted list, reputation events, and exports.

**Exit criteria:**

- The confidence function has a test for every tier and state boundary, and a set of cases built to break it.
- An end-to-end test takes a finding from spotted to corroborated with three accounts and shows each tier change to its finder.
- No route returns an exact location to a viewer who shouldn't have it. A test tries every route.

### WS5 — Records

**Status:** Shipped 2026-11-11 for the sources that are records. Thirty-one sources hold records, with counts equal to the research's wherever a source is stored whole, and three more fill the gazetteer and the boundaries. Sources that turned out not to be records have no connector and are listed in `ARCHITECTURE.md` under Ingest: access land, the landscape characterisation grid, the woodland opportunity map, Defra's survey indexes and the monument-type thesaurus. Wikidata is stored as a cross-walk and kept off the map (Decision 0011).

England's open records, stored, searchable and linked. See Decision 0007 and `sources/records-england.md`.

**Deliverables:**

- A connector for each England source cleared for storage, run against the live source, with a recorded fixture for tests.
- Record search, nearby records, record pages, vector tiles, and suggested records for a finding.
- Live queries from the browser for the sources that may not be stored, and deep links for the rest.
- The place-name gazetteer and the nation and county lookup.

**Exit criteria:**

- The development database holds every cleared England source, with counts within 2% of the counts the research recorded.
- A finding marked on Silbury Hill is offered its scheduled monument record as the first suggestion.

### WS6 — Collaboration

**Status:** Shipped 2026-11-11 on the server: investigations, mentions and the channel scan, field follow-ups as evidence, the activity feed, notifications, the event stream, scan a square, reports, moderation and photo approval. A mention notifies the finder and the helpers once, and hidden content is gone from every read route for everyone but its owner and moderators. The screens for these are part of WS7.

Investigations, mentions, follow-ups, activity and moderation. See Decision 0009.

**Deliverables:**

- Investigations with items, members and exports, with private ones limited to one member.
- Mentions with fetched titles and thumbnails, and the job that scans listed channels for links back to findings.
- Field follow-ups as dated evidence, the activity feed, notifications, the event stream, scan-a-square coverage, reports and the moderation queue, and photo uploads held for approval.

**Exit criteria:**

- A mention added to a finding notifies its finder and everyone who helped.
- A reported comment can be hidden by a moderator and disappears for other viewers at once.

### WS7 — Interface

**Status:** Shipped 2026-11-11. Every screen in the deliverables is on `main` with end-to-end tests at both widths, and the three exit journeys run against a real backend in `frontend/e2e-full/`. Left, and tracked here until done: adopting the API fields added after the screens were built (the terrain's "being prepared" answers, labels and credits from `/meta`, the evidence filter on help wanted), and one pass over the whole interface for duplicated code.

Findings track (`f1/findings`), as of 2026-11-11: built are marking a finding, Explore's list of the findings in view, a finding's page with its second look, evidence, discussion and the finder's controls, the blind second-look queue at `/review`, and help wanted at `/help`. Its full-stack tests take a finding from spotted to corroborated with three accounts (`e2e-full/finding.spec.ts`), and have a second account, starting signed out, answer a finding through the queue and see the reveal (`e2e-full/review.spec.ts`).

Every screen over the map. See `UI.md`.

**Deliverables:**

- The mark-a-finding flow, the finding panel with its meter and next steps, evidence and record linking.
- Second look, scan a square, help wanted, record pages, investigations, profiles, activity and notifications, mentions and follow-ups, moderation.
- The map layers from `sources/map-layers.md`, the guide with paired examples of real and false features, and the legal notices.

**Exit criteria:**

- Each flow has an end-to-end test at desktop and phone width.
- Screenshots of each screen have been looked at against `UI.md`.

### WS8 — Deployment

**Status:** In progress, moving from Google Cloud to Fly.io.

On Google Cloud: the owner gave standing permission for the deployment on 2026-11-11, and steps 1 to 7 of the Google runbook (now `git show 28488dd:infra/README.md`) were carried out that day in the project `fieldclub-uk`. Billing is linked, the database login and the six required secrets have values, the schema job created the 28 tables, and the image built from the renamed code runs as the service and the jobs. The service is held back from the public with `service_public = false`: an anonymous request gets 403, and the owner's gets the API and the interface. The elevation copy (step 8) was started at 19:23 on 2026-11-11 and finished at 01:58 UTC the next morning, with all 5,877 tiles, 126.4 GB, under `gs://fieldclub-uk-elevation/england/mirror/`. The domains are registered and their DNS is managed from `infra/dns.toml`; nothing points at the service yet. The exit criterion of that deployment, `terraform plan` succeeding against the named project with nothing applied without the owner's go-ahead, was met for the first stage that day. A plan shows the volumes of two jobs changing order on every run, which changes nothing and goes with the Terraform.

The move: later on 2026-11-11 the owner chose Fly.io, with Managed Postgres and Tigris, and no Terraform (Decision 0018, after the spike `hosting-on-fly-io`). The application now speaks only S3 and reads Fly's database address and visitor header, so an image built from main can no longer run on the Google deployment, which keeps the image it has. The deployment for Fly is written and tested offline: `fly.toml` for the web app, `infra/fly/jobs.toml` and `infra/fly_jobs.py` for the jobs app, `infra/fly-secrets.sh`, the tile cache's expiry rule, the redirects from the other names, `deploy.yml` deploying with a token, and the runbook in `infra/README.md`. On 2026-11-12 the security fixes were joined to it: `fly.toml` carries the per-address stream limit the application now insists on, and the hourly machine deletes expired sessions and old sign-in links. What is in flight, and one choice that waits on the owner, are in [the hosting handoff](../handoffs/hosting-on-fly-handoff.md).

On Fly, on 2026-11-12: the apps `openantiquity` and `openantiquity-jobs` were made, with no machines yet, and the bucket `openantiquity-elevation`. The mirror was copied into it from Google's bucket by rclone on a Fly machine in 12.5 minutes, and checked against Google's by size and MD5: 5,877 tiles, 126.4 GB, no differences. The temporary Google key the copy used was deleted afterwards. The owner chose a weekly look at the bill and fixed limits in place of an automatic check of spend (Decision 0025). The spike's cluster, apps and bucket were deleted the same day.

The owner then weighed Managed Postgres against a Postgres on a machine of our own and kept Managed Postgres, as Decision 0018 has it. Steps 2 to 7 and step 9 of the runbook followed that day. The cluster `openantiquity`, PostgreSQL 17 with PostGIS 3.6.4, is attached to both apps. The bucket `openantiquity-cache` has its 180-day rule. The web app holds its session key and the jobs app Defra's login. The web app was deployed from commit `85ad12a`: three machines on a private address, the schema's 30 tables, health checks passing. The jobs app's image is of commit `2399ceb`, and its `sources` job wrote the two LIDAR rows. `fieldclub-terrain info` on a jobs machine counted 5,877 of 5,877 tiles in the mirror, and the national overview was built from them in 13 minutes, 3.08 GB. The owner then finished step 3 in Tigris's dashboard: the bucket `openantiquity-photos` and the keys' roles. A probe from each app's machines found the web app's key as intended, and the jobs app's key able to read the cache and the photos, which it shouldn't.

With the elevation readable, no terrain tile drew: GDAL had the Tigris endpoint on one thread only, and tiles are drawn on others. The fix went out the same day in commit `e7c0794`, with a check of the mirror that every deploy now runs first (Decision 0027). Tiles over Avebury then drew from the 1 m mirror, the overview and the height data. Step 10 followed: `he-nhle-scheduled-monuments` loaded 20,006 records in 19 seconds, and the hourly machine `due` exists with its 10 GB volume and ran once. Its first refresh of every bulk source is the 03:00 UTC run of 2026-11-13.

The same evening the owner had the domains pointed at Fly (step 11). `openantiquity.org` answers over https, and `www`, the `.com`, the `.co.uk` and their `www` names answer 308 to it, each with its certificate. Anyone can now look at the map. No sign-in method is configured, so nobody can join or save anything yet. The repository is public on GitHub under the AGPL version 3 (Decision 0026).

Left: taking the jobs key's read access off the cache and the photos; reading the first nightly refresh's log; the deploy workflow (step 12); the sign-in providers' credentials (`owner-actions.md`, WS3), registered with the openantiquity.org redirect address; taking the Google project down with `infra/terraform` once the site on Fly has passed its checks; and opening the site, which waits on the owner.

**Deliverables:**

- A container image, run as Fly Machines in London: the web app, and a jobs app that alone holds Defra's login and runs only images its owner built.
- Fly's configuration files and small tested scripts for the apps, the jobs, the secrets and the bucket rules, and a CI workflow that deploys by hand from main.
- England's converted elevation in a Tigris bucket, copied from Google Cloud Storage once.
- The runbook, with sizing, cost and the manual spend check Fly's missing billing alert needs.

**Exit criteria:**

- The web app answers `/healthz` on openantiquity.org, and the other names redirect to it.
- The mirror in Tigris holds all 5,877 tiles and the national overview is built from it.
- CI runs both check suites and the docs lint on every push.
- The Google project is taken down, with nothing of the application left running there.

### WS9 — Verification

**Status:** In progress. The security review is done; the documents and the clean-database run are not started.

The security and privacy review ran on 2026-11-12 over the whole of `main`: sign-in and sessions, what each viewer may see, hostile input, the browser, and the platform. Its findings were fixed in one worktree, the fixes were reviewed twice by agents told to break them, and a last pass closed what those found. It produced Decisions 0019 to 0024. Each decision records the limits it accepts. One finding was a fault in GEOS that let a single request end the API process, reported upstream as [libgeos/geos#1604](https://github.com/libgeos/geos/issues/1604) and guarded against here whatever GEOS is installed. The review's hosting findings went to WS8. What is left of this workstream is in [the interface and verification handoff](../handoffs/interface-sync-and-verification-handoff.md).

**Deliverables:**

- An end-to-end run of the whole loop on a clean database.
- A security review of the finished code.
- Area docs under `architecture/` for every area, each written from the code and checked against it, with anything unbuilt under Implementation status. They replace the build contract.
- Every decision carries its forward-link, and each status is set from what the code does.

**Exit criteria:**

- Every decision is Accepted, or Accepted (partial) with its gaps listed in an area doc.
- `doctool.py lint` reports no errors and no forward-link warnings.

## Phase exit criteria

When all of these are true, this plan closes:

- [ ] Someone can open the deployed site, explore England's LIDAR, sign in, save a finding and see it climb the ladder with help from two other accounts.
- [ ] Every England source cleared for storage is indexed, with its licence and attribution shown.
- [ ] Both check suites and the docs lint pass in CI.
- [ ] All workstreams are shipped or explicitly deferred to a successor plan.

Deferred to a successor plan: LIDAR and records for Wales, Scotland and Northern Ireland, the surface-model comparison layer, calibration against known monuments, and automatic feature suggestions.

## References

- `../architecture/decisions/README.md` for Decisions 0001 to 0009.
- `../ARCHITECTURE.md` for the build contract, until the area docs replace it.
- `../DESIGN.md` and `../UI.md` for what the product does and how it looks.
- `owner-actions.md` for the letters and accounts only the owner can provide.
