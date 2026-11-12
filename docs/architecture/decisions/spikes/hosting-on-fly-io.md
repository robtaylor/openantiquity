# Spike — Hosting on Fly.io

**Status:** Resolved (2026-11-11) — YES; Fly.io with Managed Postgres 17 over its direct address and Tigris kept every guarantee tested, with machines suspended rather than stopped when idle.

## Question

Can OpenAntiquity run on Fly.io, with Fly's Managed Postgres and Tigris object storage, keeping every guarantee it has on Google Cloud today?

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

- 2026-11-11: the owner made the Fly organisation `openantiquity`. The spike's resources are in it: the app `openantiquity-spike` with no public address, the Managed Postgres cluster `openantiquity-spike` (Basic plan, 10 GB, London) and the Tigris bucket `openantiquity-spike-mirror`. Creating the bucket accepted Tigris's terms of service on the owner's behalf, which the owner was told afterwards.
- 2026-11-11, Q1: moot. `fly mpg create` offers PostgreSQL 16 and 17, and the spike's cluster runs 17.11. Fly's documentation page still describes 16.
- 2026-11-11, Q1 step 1, run anyway: the whole backend suite passed against a local PostgreSQL 16.10 with PostGIS 3.5.3 (5,125 passed, 5 skipped). The application doesn't depend on 17. Step 2 wasn't run, since 17 is on offer.
- 2026-11-11, Q2 step 1: Tigris passed every check, run from a machine in London with boto3 1.44. A second create-only write was refused with 412 and the first value kept. Of twelve writers racing to create one object, exactly one won, three times out of three. A replace and a delete carrying a stale tag were each refused with 412, and a delete with the current tag removed the object. Forty writes were each read back at once with no stale read, and 25 new objects were all listed at once.
- 2026-11-11, Q2 step 2: GDAL 3.12.2 read a real 24 MB elevation tile (LERC_ZSTD, 512-pixel blocks, three overviews) through `/vsis3/` with `AWS_S3_ENDPOINT` set to Tigris and virtual hosting off. One 512-pixel window took 38 ms at the median and 216 ms at worst, against 7 ms from local disk. A 64 KB range of an 8 MB object took 20 ms at the median. No figure from Google Cloud Storage was taken to compare.
- 2026-11-11, Q2 step 3: the bucket accepted a rule that expires objects under a prefix after a number of days. Whether objects are then removed on time wasn't waited for.
- 2026-11-11, Q3 step 1: the app's login is not a superuser. It created `pg_trgm` and `citext` itself and was refused `postgis`. After `fly mpg databases extensions enable postgis`, PostGIS 3.6.4 was there, and the login made a table with a geometry column and a GiST index.
- 2026-11-11, Q3 step 2: the connection string Fly attaches to an app points at `pgbouncer.<cluster>.flympg.net`. A `LISTEN` on it received nothing. The same string with `direct` in place of `pgbouncer` delivered the notification. A session advisory lock survived commits on both, which on the pooled one may have been luck.
- 2026-11-11, Q3 step 3: `max_connections` is 112 on the Basic plan, and sixty connections from one machine were all accepted.
- 2026-11-11, Q3 step 4: Managed Postgres is offered in London (`lhr`) and Amsterdam, not Paris. Backups and a restore weren't tried.
- 2026-11-11: one `fly deploy` failed after the image was pushed, with an internal error from Fly's machines API, and worked when run again.
- 2026-11-11, Q4 step 1: the application's own image, built on Fly's builder from `infra/Dockerfile`, ran as the app `openantiquity-spike-web` with no public address. Its schema job created the 28 tables on Managed Postgres, with `CREATE EXTENSION IF NOT EXISTS postgis` passing because Fly had already enabled it. Through Fly's proxy on the private address, `/meta` answered in about 30 ms. A stopped machine took 20.8 s to answer its first request, during which the proxy logged refused connections. A suspended machine answered its first request in 0.53 s.
- 2026-11-11, Q4 step 2: the event stream stayed open through the proxy for the 600 s it was held, with the longest silence 15 s, and the machine was neither stopped nor suspended under it. Whether the database `LISTEN` connection is still alive after a suspend and resume wasn't tested.
- 2026-11-11, Q4 step 3: a small echo server was given a public address for a few minutes. Fly's proxy set `Fly-Client-IP` to the visitor's address and overwrote a forged one. It appended two entries to `X-Forwarded-For`, the visitor's address and then its own edge address, leaving anything the visitor sent to the left of them. So the visitor is the second entry from the right, not the first, and `Fly-Client-IP` is the plainer source. The machine itself has only a private address.
- 2026-11-11, Q4 step 4: about 320 MB of a 1 GB machine was in use at idle. A photo upload during a tile render wasn't tried.
- 2026-11-11, Q5 step 1: not run. Putting Defra's login into Fly's secret store needs the owner's say-so, which was asked for. It no longer gates the move: the converted elevation being copied into Google Cloud Storage that night can be copied to Tigris without Defra.
- 2026-11-12, Q5 step 1, after the outcome below was written: the owner agreed that values may be piped from `.env` into a secret store, and the check was run from the spike's machine in London. Defra's server accepted two connections at once with the pinned host key, each made in about 0.1 s, listed all 5,877 tiles, and was read at 17 to 22 MiB a second on one connection in 8 MiB windows. A share of the copy itself wasn't run. The same day, `fly secrets import` was found to strip a pair of quotes from around a value, while `fly secrets set NAME=-` keeps quotes, symbols and line breaks and trims only white space at the ends.
- 2026-11-11, Q5 step 2: Fly lists a machine with 16 GB of memory (`performance-8x`). Not run.
- 2026-11-11, Q5 steps 3 and 4: design questions, left to the decision and the move.
- 2026-11-11, Q6: Fly's pricing page gives machine prices for its US east region only and says they vary by region; London's weren't found. Its cost page says "We don't support billing alerts (yet)" and describes no spending cap. Managed Postgres Basic is $38 a month plus $0.28 a GB, a 1 GB shared machine $6.70 a month in US east, data out $0.02 a GB in Europe, and the first ten certificates are free. Tigris's own prices weren't read.

## Outcome

Yes. The two things that could have stopped the move both hold: Tigris honours the three conditional writes the elevation mirror depends on, under a race as well, and Managed Postgres runs PostgreSQL 17 with PostGIS and offers a direct address on which `LISTEN` works. Three workarounds go with it: the application uses the direct database address, never the pooled one Fly attaches by default; PostGIS is enabled through Fly before the schema job runs; and idle machines are suspended, not stopped. The visitor's address is read from `Fly-Client-IP`, or from the second entry from the right of `X-Forwarded-For`. Left untested and carried into the move: the `LISTEN` connection across a suspend, memory under load, London's prices, and whether Defra's server accepts Fly's addresses. Fly has no billing alert, so the move has to supply its own. Decision 0018 follows from this spike.
