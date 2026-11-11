# Plan — v1 England: from LIDAR to corroborated findings

**Status:** Active.

## Goal

A deployed Field Club covering England. People explore 1 m LIDAR in archaeological visualisations, mark findings, check each other's findings up the confidence ladder, and link them to England's open heritage records. This plan implements Decisions 0001 to 0009.

## Prerequisites

- The research pass of 2026-11-10 is complete. Its evidence is in the spikes under `architecture/decisions/spikes/` and the source catalogue under `sources/`.
- Decisions 0001 to 0009 are written. Each stays Proposed until its code is built and checked.
- The build contract in `ARCHITECTURE.md` describes the tables, API and confidence rules to build.

## Where things stand (2026-11-10)

- WS0 and WS1 are shipped in the first commits on `main`: the backend core, the frontend shell on MapLibre 6, the rename to Field Club, and the contract sync.
- The backend halves of WS2 to WS5 are on `main`: terrain tiles, sign-in, findings with the confidence engine, and the record index with its first connector. Each was built in its own worktree, reviewed adversarially, fixed, and rebased onto `main`. The backend suite stood at about 2,500 tests when they were combined.
- Combining them showed that `rasterio` and `pyogrio` each bundle their own GDAL, and that the process aborts when `pyogrio`'s loads first. `ingest/adapters/ogr.py` is the one place `pyogrio` is imported, and it loads `rasterio` first.
- Review changed two rules, both now in the decision records. An answer to a second look is final (Decision 0008). Promotion to trusted is a moderator's call (Decision 0005).
- Next: the remaining connectors, the collaboration and moderation API, the terrain follow-ups, and the interface. Each track is built in its own worktree and branch under `.claude/worktrees/` and rebased onto `main` when it has been reviewed.
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

**Status:** In progress. The mirror, the visualisations, the tile endpoints, the height profile, the coverage layer and the mirror command shipped on 2026-11-10. The national overview (Decision 0010), capture years on the coverage layer, the LIDAR `sources` rows, the bucket lock and the resumable whole-country mirror job followed the same day. Left: running the mirror job and the overview build in the cloud (WS8), and the browser screenshot. Known artefact: the 2022 composite has no tiles over 351 km² of the North York Moors, so the DEM there draws a sea-level pit with cliffs of 200 to 400 m at its edge, in 3D terrain and DEM hillshade. The remedy is Defra's post-2022 tiles, which cover it; until then the gap stays.

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

**Status:** In progress. The server side shipped on 2026-11-10: provider sign-in, account linking and the emailed link. Left: the sign-in sheet, the welcome sheet and browser drafts in the interface. Provider credentials are an owner action.

Provider sign-in, the emailed link, the welcome sheet and account deletion. See Decisions 0002 and 0009.

**Deliverables:**

- A server-side sign-in flow for Google, Apple, Microsoft, Facebook and OpenStreetMap, each enabled by its settings, plus the emailed one-time link.
- The welcome sheet: handle, age band and contributor terms.
- Browser drafts for signed-out work, the sign-in sheet, and saving the drafts after sign-in.

**Exit criteria:**

- Each provider flow passes tests against a mocked provider, including a forged state, a replayed code and an unverified email.
- An end-to-end test marks a finding signed out, signs in through the development login, and finds the draft saved.

### WS4 — Findings and confidence

**Status:** In progress. The server side shipped on 2026-11-10: the confidence engine, findings, second looks, evidence, discussion, the review queue, reputation and exports. Left: the end-to-end test through the interface.

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

**Status:** In progress. The shared ingest adapters, the scheduled monuments connector (20,006 records, the count the research recorded), search, nearby records, record pages, vector tiles, suggestions and the live-source and deep-link catalogues shipped on 2026-11-10. Left: connectors for the other 47 sources, the place-name gazetteer, and the nation and county lookup.

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

**Status:** Not started.

Investigations, mentions, follow-ups, activity and moderation. See Decision 0009.

**Deliverables:**

- Investigations with items, members and exports, with private ones limited to one member.
- Mentions with fetched titles and thumbnails, and the job that scans listed channels for links back to findings.
- Field follow-ups as dated evidence, the activity feed, notifications, the event stream, scan-a-square coverage, reports and the moderation queue, and photo uploads held for approval.

**Exit criteria:**

- A mention added to a finding notifies its finder and everyone who helped.
- A reported comment can be hidden by a moderator and disappears for other viewers at once.

### WS7 — Interface

**Status:** Not started. Follows the API of WS3 to WS6.

Every screen over the map. See `UI.md`.

**Deliverables:**

- The mark-a-finding flow, the finding panel with its meter and next steps, evidence and record linking.
- Second look, scan a square, help wanted, record pages, investigations, profiles, activity and notifications, mentions and follow-ups, moderation.
- The map layers from `sources/map-layers.md`, the guide with paired examples of real and false features, and the legal notices.

**Exit criteria:**

- Each flow has an end-to-end test at desktop and phone width.
- Screenshots of each screen have been looked at against `UI.md`.

### WS8 — Deployment

**Status:** Not started. Blocked on the owner naming a Google Cloud project.

**Deliverables:**

- A container image, Terraform for Cloud Run, Cloud SQL, buckets, secrets and scheduled jobs, and a CI workflow.
- The job that copies England's LIDAR from Defra's bulk supply into a bucket, run from a temporary machine in the project.

**Exit criteria:**

- `terraform plan` succeeds against the named project. Nothing is applied without the owner's go-ahead.
- CI runs both check suites and the docs lint on every push.

### WS9 — Verification

**Status:** Not started. Runs last.

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
