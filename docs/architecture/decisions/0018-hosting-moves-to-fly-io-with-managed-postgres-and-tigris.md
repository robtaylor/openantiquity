# Decision 0018 — Hosting moves to Fly.io with Managed Postgres and Tigris

**Status:** Proposed. Its ninth point is replaced by Decision 0025.

**Current architecture:** [infra/README.md](../../../infra/README.md).

**TL;DR.** In the context of a tile-heavy, non-commercial site deployed on Google Cloud but not yet open, facing a charge of $0.12 for every gigabyte sent to visitors, a load balancer needed only to carry a custom domain, and an owner who wanted to stop using Terraform, we chose to host on Fly.io with its Managed Postgres and Tigris object storage, accepting a rewritten deployment, a younger managed database and no billing alert from the platform.

## Context

When this was written the application ran on Google Cloud Run in London with Cloud SQL and Cloud Storage, created by Terraform in `infra/terraform` and held back from the public (`service_public = false`). Steps 1 to 7 of the runbook had been carried out that day, and the copy of England's elevation into a bucket was running. No decision record had chosen Google Cloud: it was the owner's instruction at the start.

Three things came up on 2026-11-11.

- Cloud Run offers no custom domain in London, so `openantiquity.org` needed a load balancer at about $18 a month, or Firebase Hosting with a reworked session cookie, requests cut off at 60 seconds and a second way in that couldn't be closed.
- Google charges $0.12 a gigabyte for data sent to visitors. The site is mostly map tiles: about 675 GB a month at a thousand visits a day, by the runbook's own assumptions.
- The owner had "not had happy experiences" with Terraform.

Fly.io's published prices that day were $0.02 a gigabyte in Europe, no charge for a shared address or the first ten certificates, $38 a month for the smallest Managed Postgres plan plus $0.28 a gigabyte, and $6.70 a month for a 1 GB shared machine in its US east region.

The spike [hosting-on-fly-io](spikes/hosting-on-fly-io.md) tested the parts of the application that weren't portable by default and resolved YES.

## Decision

1. The service and its jobs ran as Fly Machines in London (`lhr`), in the Fly organisation `openantiquity`, from the same image.
2. The database was Fly Managed Postgres, PostgreSQL 17 with PostGIS. The application connected to its direct address, never the pooled one Fly attaches by default, because the event stream's `LISTEN` and the ingest runner's session lock need a connection of their own. PostGIS was enabled through Fly before the schema job ran.
3. Elevation, the tile cache and photos were kept in Tigris buckets through the S3 interface. The mirror's three conditional writes (create only if absent, replace only if unchanged, delete only if unchanged) were kept as they were, on the S3 preconditions that the spike proved Tigris honours.
4. Idle machines were suspended, not stopped: a suspended machine answered in half a second and a stopped one in twenty.
5. The visitor's address, which rate limits and bans rest on, was taken from the `Fly-Client-IP` header that Fly's proxy sets and a visitor can't forge.
6. The deployment was described by Fly's own configuration files and small tested scripts in `infra/`, as `infra/dns.py` already was. Terraform was removed.
7. Defra's supply login was given only to the app that copies elevation, never to the public service.
8. The elevation already converted into Google Cloud Storage was copied across once the copy there had finished, in preference to asking Defra for the country a second time.
9. Fly had no billing alert, so the deployment supplied its own check of the month's spend.
10. Google Cloud stayed as it was, held back, until the service on Fly had passed its checks. The project was then taken down.

## Alternatives considered

- **Stay on Google Cloud with the load balancer** — rejected by the owner: it kept Terraform and the dearer data transfer, and added a monthly charge for the domain alone.
- **Stay on Google Cloud behind Firebase Hosting** — rejected because the run.app address could not be closed, which left the visitor's address forgeable on that route, and because the sign-in cookies would have had to be merged.
- **Fly.io with a Postgres we run ourselves** — rejected because the database holds members' accounts, and a volunteer project shouldn't be its own database administrator. It would have cost roughly $25 a month less.
- **Fly.io for the service with a managed PostGIS elsewhere** — not needed once the spike showed Managed Postgres fitted.
- **Stay on Google Cloud until traffic made transfer the largest cost** — this was the recommendation first given to the owner, who preferred to move while nothing was public and the move was cheapest.

## Consequences

- A custom domain costs nothing extra, and the question of how the domain reaches the service is closed.
- Data sent to visitors costs a sixth as much.
- At rest the two cost about the same once a managed database is counted, so the saving only shows with traffic.
- The storage layer was rewritten for the S3 interface, the deployment and its runbook were rewritten, and the Terraform, its tests and the work of 2026-11-11 on Google Cloud were set aside.
- Access is coarser than Google's: secrets belong to an app, so keeping Defra's login from the public service means a separate app, where Google gave each job its own identity.
- Fly's Managed Postgres is a newer product than Cloud SQL. One deploy during the spike failed with an internal error from Fly's API and passed when repeated.
- There is no platform billing alert. A fault in the deployment's own check would leave spend unwatched.
- Tigris's terms of service were accepted for the organisation when the first bucket was made.

## Walk-back options

- **If Managed Postgres proves unreliable** — move the database to another managed PostGIS and keep the service on Fly. The application needs only a PostgreSQL address.
- **If Tigris loses or corrupts an object** — the elevation can be rebuilt from Defra's supply, and the conditional writes are plain S3 preconditions that other stores also offer.
- **If Fly as a whole disappoints** — the application is still one container, a PostgreSQL database and an S3-style store. The spike's findings list what any other host would have to offer.

## Links

- [spikes/hosting-on-fly-io.md](spikes/hosting-on-fly-io.md) — the spike this rests on.
- Decision 0006 — how terrain is served and mirrored, which the storage change must keep.
- Decision 0017 — the public name; the Fly organisation uses it.
