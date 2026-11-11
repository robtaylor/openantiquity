# Spike — Hosting on Fly.io

**Status:** Open. Time-box: one working day once the owner has made the Fly.io organisation; stop and stay on Google Cloud if Q1 or Q2 fails.

## Question

Can Open Antiquity run on Fly.io, with Fly's Managed Postgres and Tigris object storage, keeping every guarantee it has on Google Cloud today?

## Why this is in question

The owner chose on 2026-11-11 to move hosting from Google Cloud to Fly.io. The reasons were three: data sent to visitors costs $0.02 a GB there against $0.12, which matters for a site that is mostly map tiles; a custom domain with a certificate is free, where Cloud Run in London needs a load balancer at about $18 a month; and the owner wants to stop using Terraform.

The application is one container, a PostGIS database and object storage, so the move looks cheap. Four things it relies on are not portable by default, and each was read from the code on 2026-11-11:

- The elevation mirror and the national overview use three conditional writes on Google Cloud Storage (`terrain/blobs.py`): create only if absent, replace only if unchanged, and delete only if unchanged. They are what make two fetchers of one tile safe and what protect the overview's manifest.
- GDAL reads each elevation tile by byte range through `/vsigs/`. Tile latency depends on how the object store answers range requests.
- The live event stream holds one `LISTEN` connection per process (`services/events.py`), and the ingest runner holds a session-level advisory lock on a connection of its own (`ingest/runner.py`). Neither survives a pooler that hands a connection back after each transaction.
- The schema job creates the `postgis`, `pg_trgm` and `citext` extensions itself, and development and Cloud SQL both run PostgreSQL 17. Fly's Managed Postgres documentation describes PostgreSQL 16 and extensions switched on through Fly.

## Approach

Sub-questions, cheapest first. A later one is only attempted if the earlier ones pass.

- **Q1. Does the application run on PostgreSQL 16?** No Fly account needed.
  - Step 1: run the whole backend suite against a local PostGIS 16.
  - Step 2: create the schema there and load a copy of the development records; compare the search timings with PostGIS 17.
- **Q2. Does Tigris give the mirror what it needs?**
  - Step 1: against a Tigris bucket, prove or disprove each of the three conditional writes, including two writers racing for one object, and reading an object straight after writing it.
  - Step 2: read a real elevation tile through GDAL's `/vsis3/` from a machine in London and time a screenful of map tiles against the same from Google Cloud Storage.
  - Step 3: check that a bucket can expire objects by age, which the tile cache relies on.
- **Q3. Does Managed Postgres give the application what it needs?**
  - Step 1: can the application's own login create the three extensions, or must Fly enable them first?
  - Step 2: do `LISTEN`/`NOTIFY` and a session advisory lock work on the connection Fly gives an app, and if that connection is pooled, is a direct one offered?
  - Step 3: how many connections does the smallest plan allow, against three instances with eight each?
  - Step 4: is it offered in London, and what do backups and a restore look like?
- **Q4. Does the service behave behind Fly's proxy?**
  - Step 1: deploy the image, held back from the public, and time a cold start.
  - Step 2: hold the event stream open for ten minutes; see whether an instance is stopped while streams are open.
  - Step 3: find which header carries the visitor's address, and whether the app can be reached without passing the proxy. Rate limits and bans rest on it.
  - Step 4: confirm 1 GB of memory is enough for a photo upload while a tile renders, or measure what is.
- **Q5. Do the jobs fit?**
  - Step 1: run one share of the elevation copy as a machine that exits when done; confirm Defra's server accepts connections from Fly's addresses, two at a time.
  - Step 2: the national overview build needs about 8 GB of working space and 16 GB of memory today; find the machine and volume that hold it, and what an hour costs.
  - Step 3: Fly's own schedules run hourly, daily, weekly or monthly. Decide how the six-hourly channel scan runs.
  - Step 4: keep Defra's login away from the public service: a separate app with its own secrets.
- **Q6. What does it cost in London?** Read Fly's regional prices for the machine sizes Q4 and Q5 settle on, and find what Fly offers for a spending alert.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| Q1 fails | The application needs PostgreSQL 17 | Stay on Google Cloud unless Fly offers 17 or the dependence is one small fix |
| Q2 fails | The mirror's safety rules can't be kept on Tigris | Stay on Google Cloud, or redesign the mirror's locking around the database, as a decision of its own |
| Q1 and Q2 pass, Q3 fails | Fly's managed database doesn't fit | Consider Fly for the service with another managed PostGIS, as a narrower decision |
| Q1 to Q3 pass, Q4 or Q5 needs a workaround | The move works with changes | Write the decision to move, naming each workaround |
| All pass | The move is sound | Write the decision to move; the spike resolves YES |

## Findings

(Filled in as the spike runs.)

## Outcome

(Filled in at resolution.)
