# Running Field Club on Google Cloud

This is the runbook for the deployment in this folder: what the owner does once, what a deploy is afterwards, how to roll back, and what to watch. It also records the sizing and cost reasoning behind the defaults.

Nothing here has been applied to a real project. Every command that touches Google Cloud names its project with `--project`, so the gcloud configuration's own default project is never used. Set `P` to the Field Club project id first, in every shell:

```
export P=<field-club-project-id>
```

## What is in this folder

| Path | What it is |
|---|---|
| `Dockerfile` | One image for the service and every job, built from the repository root |
| `docker-compose.yml` | The local PostGIS for development and tests |
| `bootstrap.sh` | Makes the bucket that holds Terraform's state |
| `jobs/mirror_shard.py` | One task's share of the whole-country elevation copy |
| `terraform/` | The project's resources. `example.tfvars` lists the inputs |
| `terraform/modules/cdn/` | The optional load balancer and CDN, off by default |
| `terraform/tests/` | Offline checks with the Google provider mocked |
| `../.github/workflows/ci.yml` | Checks on every push and pull request |
| `../.github/workflows/deploy.yml` | Run by hand: build, push and plan. It doesn't apply |

## What gets built

- **Cloud Run service `fieldclub`** serves the API, the tiles and the built frontend from one image. It scales to zero.
- **Cloud Run jobs** run the same image with another command: `fieldclub-schema`, `fieldclub-ingest`, `fieldclub-scan-channels`, `fieldclub-refresh-sources`, `fieldclub-elevation-copy` and `fieldclub-national-build`.
- **Cloud Scheduler** starts any ingest listed in `ingest_schedules`. The channel scan and the source refresh are left unscheduled until the image has their `fieldclub-jobs` command; then set `schedules` (its description gives the intended times).
- **Cloud SQL** for PostgreSQL 17, Enterprise edition, `db-g1-small`, 20 GB SSD that grows by itself, seven daily backups.
- **Three private buckets**: `<project>-elevation` (the mirror), `<project>-cache` (rendered tiles, cached elevation and ingest downloads, with deletion rules) and `<project>-photos` (uploads, kept). Terraform refuses to destroy the elevation bucket (`prevent_destroy`), no workload may delete or replace a file in the mirror, and anything deleted by hand is kept for seven days by soft delete. Tearing the project down means removing the `prevent_destroy` line first.
- **Secret Manager** holds twelve secrets, all created empty.
- **One service account per workload**, a scheduler account, and a deployer account that GitHub's `deploy.yml` reaches through workload identity federation.
- **Artifact Registry** repository `fieldclub`, keeping the five newest images and anything younger than 30 days.
- **A monthly budget alert**, by default £40.

The database is reachable only by the service and the jobs. It has a public address but no authorised networks, and `connector_enforcement = REQUIRED` refuses anything that doesn't come through the Cloud SQL connector, which checks the caller holds `roles/cloudsql.client`. Only the five workloads that use the database hold it. A public address with no networks saves the VPC, Private Service Access and VPC egress a private address would need.

## Once: setting up the project

Each step says where its values come from. Steps 1 to 3 need the owner's own Google account with Owner on the project and Billing Account Administrator, or Billing Account User plus budget permissions, on the billing account.

Steps 2 and 5 run from the repository root. Step 3 moves into `infra/terraform`, and the Terraform and gcloud commands of the other steps run from there. Step 4 reads a file kept only in the main checkout, so also set `MAIN` to that checkout's absolute path:

```
export MAIN=<absolute path of the main checkout>
```

### 1. Make the project and turn on billing

Create a project in the console. Note its id, then link it to a billing account under Billing, Account management, and note the billing account id, which looks like `012345-6789AB-CDEF01`. Record both in the deployment workstream of `docs/plans/v1-england.md`, as WS2 of `docs/plans/owner-actions.md` asks.

### 2. Sign in and make the state bucket

gcloud needs the owner signed in, and Terraform's state backend and Google provider need application default credentials as well:

```
gcloud auth login
gcloud auth application-default login
bash infra/bootstrap.sh "$P"
```

It checks the project and its billing, enables the three APIs Terraform needs to begin, and makes `gs://$P-tfstate` with versioning. It is safe to run again. A second argument puts the bucket in another region than `europe-west2`; keep it the same as `region` in `terraform.tfvars`.

### 3. First apply: everything except the workloads

```
cd infra/terraform
cp example.tfvars terraform.tfvars        # fill in project_id, billing_account, contact
terraform init -backend-config="bucket=$P-tfstate"
terraform apply
```

With `run_workloads = false` this makes the registry, buckets, database, empty secrets, service accounts and budget. It takes about ten minutes, most of it the database.

Leave `github_repository` empty for now: the federation is set up in step 12. `budget.currency` must be the billing account's own currency, shown on its overview page, or the budget is refused.

This apply turns on the APIs it then uses at once, and Google takes a minute or two to make a newly enabled API usable. If it stops with an error saying an API is not enabled or has not been used in the project, wait a few minutes and run `terraform apply` again. It carries on from where it stopped.

### 4. Make the database login and add each secret

The database login is made with gcloud, so its password never passes through Terraform. The whole database URL goes into one secret:

```
password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
gcloud sql users create fieldclub --instance=fieldclub --project="$P" --password="$password"
printf 'postgresql+psycopg://fieldclub:%s@/fieldclub?host=/cloudsql/%s' \
  "$password" "$(terraform output -raw sql_connection_name)" |
  gcloud secrets versions add fieldclub-database-url --project="$P" --data-file=-
unset password
```

The session key is any long random value:

```
python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' |
  gcloud secrets versions add fieldclub-secret-key --project="$P" --data-file=-
```

Every other secret is added the same way, with `--data-file=-` reading the value from standard input so it never appears in the shell history:

```
printf '%s' "$VALUE" | gcloud secrets versions add fieldclub-<id> --project="$P" --data-file=-
```

| Secret id | Where the value comes from | Needed |
|---|---|---|
| `database-url` | Built above | Always |
| `secret-key` | Generated above | Always |
| `defra-sftp-host`, `defra-sftp-user`, `defra-sftp-password` | Defra's email under ticket DSP3-11967, also in the untracked `.env` as `DEFRA_SFTP_*` | Always, before step 6: the elevation copy job is always given them |
| `defra-sftp-known-hosts` | The pinned host key, `var/defra_known_hosts` in the main checkout: `--data-file="$MAIN/var/defra_known_hosts"` | Always, with the three above |
| `google-client-secret` | Google Cloud console, APIs & Services, Credentials, the OAuth client of type Web application | When `google_client_id` is set |
| `microsoft-client-secret` | Microsoft Entra admin centre, App registrations, Certificates & secrets | When `microsoft_client_id` is set |
| `apple-private-key` | Apple Developer, Keys, the Sign in with Apple key's `.p8` file: `--data-file=AuthKey_XXXX.p8` | When the three Apple ids are set |
| `facebook-app-secret` | Meta for Developers, the app's Settings, Basic | When `facebook_app_id` is set |
| `osm-client-secret` | openstreetmap.org/oauth2/applications, shown once at registration | When `osm_client_id` is set |
| `smtp-password` | The mail provider's SMTP credentials | When `mail.host` and `mail.username` are set |

Register each sign-in provider with the redirect address `<public_url>/api/v1/auth/oauth/<provider>/callback`, where `<provider>` is `google`, `microsoft`, `apple`, `facebook` or `osm`. `terraform output public_url` gives the address. OpenStreetMap only accepts https, which the run.app address is.

Each secret named in `extra_secrets` needs a value before step 6 too.

A provider is offered only when its id is in `terraform.tfvars` and its secret has a value. Add the secret first, then the id, then apply. Cloud Run refuses to deploy a revision that names a secret with no version, so Terraform only wires a secret once its provider is configured.

### 5. Push the first image

From a machine with Docker, at the repository root (`cd "$(git rev-parse --show-toplevel)"`). The deploy workflow can't do this yet, because its federation comes in step 12.

```
repository=$(terraform -chdir=infra/terraform output -raw image_repository)
gcloud auth configure-docker "${repository%%/*}"
tag=$(git rev-parse --short=12 HEAD)
docker buildx build -f infra/Dockerfile --platform linux/amd64 \
  -t "$repository:$tag" --push .
```

### 6. Second apply: the service and jobs

First check that every secret Cloud Run will be given has a value: the database URL, the session key, all four `defra-sftp-*` secrets and any in `extra_secrets`. Cloud Run refuses a revision that names a secret with no version, and the apply fails part-way. This lists the secrets still empty:

```
for secret in $(terraform output -json secrets | python3 -c 'import json,sys; print(*json.load(sys.stdin))'); do
  gcloud secrets versions list "$secret" --project="$P" --filter=state:ENABLED --limit=1 \
    --format='value(name)' | grep -q . || echo "$secret"
done
```

A provider's or the mail relay's secret may stay empty while its id is unset. Then set `run_workloads = true` and `image_tag` to the tag just pushed, and `terraform apply`. The service starts on `terraform output service_url`.

The service is public from this moment, but the tables don't exist until step 7, so until then the API answers with errors. Nobody has the address yet; run step 7 straight away.

### 7. Create the schema

```
gcloud run jobs execute fieldclub-schema --region=europe-west2 --project="$P" --wait
```

It runs `python -m fieldclub.db`, which creates the extensions, the tables and the extras, and is safe to run again. Until the first release there is no migration history (`docs/ARCHITECTURE.md`, Conventions), so a change to an existing table needs the database rebuilt or Alembic, which starts at the first deploy.

Then write the `sources` rows of the elevation, which must exist before any of it is stored or shown. The elevation jobs have no database, so they pass `--skip-sources` and leave this to the same job, which runs another module when asked:

```
gcloud run jobs execute fieldclub-schema --region=europe-west2 --project="$P" --wait \
  --args=-m,fieldclub.terrain.cli,sources
```

It is safe to run again.

### 8. Copy England's elevation into the bucket

```
gcloud run jobs execute fieldclub-elevation-copy --region=europe-west2 --project="$P"
```

The job splits the 5,877 tiles into four shares of 88.4 GB each, by size, and runs two shares at a time, one SFTP connection each. At the 8 MB/s per connection measured on 2026-11-10 a share takes about 3.1 hours to download and 0.8 hours to convert, so the copy takes about eight hours. See [The elevation copy](#the-elevation-copy) for why it runs like this.

While `service_fetches_elevation` is true, every service instance can open a connection of its own for a tile someone is looking at, so Defra may see the job's two plus up to `service_max_instances` more. The job and the instances share a lock object per tile under `england/mirror/locks/`, so only one of them fetches a given tile; were two ever to upload it, the second upload would be dropped. To keep Defra at two connections during the copy, set `service_fetches_elevation = false` and apply before starting the job, and set it back afterwards if the copy is incomplete.

Progress is the number of files in the mirror:

```
gcloud storage ls "gs://$P-elevation/england/mirror/" | wc -l
```

A task that fails is retried twice. A task stops at once if Defra refuses the login or shows a host key other than the pinned one, and after five tiles fail in a row, so a broken supply costs a handful of attempts rather than one per tile. Running the job again fetches only what is still missing. When all 5,877 are there, set `service_fetches_elevation = false` and apply, so the service no longer holds Defra's credentials.

### 9. Build the national overview

```
gcloud run jobs execute fieldclub-national-build --region=europe-west2 --project="$P" --wait
```

It runs `fieldclub-terrain national build --skip-sources` (`national_build_args`), which mosaics the 8 m copies inside the mirrored tiles into one cloud-optimised file under `england/national/`, uploads it and points `england/national/national.json` at it (Decision 0012). The service reads `national.json`, so nothing needs applying afterwards. Until the first build, zooms below 13 are drawn from the mirrored tiles' own overviews, uncached. Run it again whenever tiles have been added: a build that already holds every mirrored tile stops at once. It exits 0 when the overview is current and 1 on an error, including when another build holds the overview's lock. Its work folder, about 8 GB for all of England, is in the instance's memory, so the job has 16 GiB.

### 10. Run the first ingests

```
gcloud run jobs execute fieldclub-ingest --region=europe-west2 --project="$P" --wait --args=list
gcloud run jobs execute fieldclub-ingest --region=europe-west2 --project="$P" --wait \
  --args=run,he-nhle-scheduled-monuments
```

One execution runs one source. Downloads are kept in the cache bucket under `ingest/` for 90 days, so the next run can ask the publisher whether a file changed. To ingest a source on a schedule, add it to `ingest_schedules`, for example `{ "he-nhle-scheduled-monuments" = "0 3 1 * *" }`.

### 11. Point the domain

Cloud Run's own domain mapping isn't offered in europe-west2. On 2026-11-10 Google listed it for ten regions, none of them London. There are two ways to use a custom domain:

- **The load balancer module.** Set `cdn = { enabled = true, domain = "fieldclub.example.org" }` and apply. Point the domain's A record at `terraform output site_address`. The managed certificate is issued once the record resolves, which can take an hour. This also closes the run.app address and tells the app it is behind two proxies. It costs about $18 a month before traffic.
- **Firebase Hosting** in front of Cloud Run is free at this size, but it strips every cookie except one named `__session`, so the `fieldclub_session` cookie would never arrive. It doesn't work without renaming the cookie.

Until a domain is needed, the run.app address is stable and on https, and every provider accepts it. After moving to a domain, change each provider's redirect address and set `public_url`.

### 12. Set up the deploy workflow

Set `github_repository = "<owner>/<name>"` and `github_repository_id` to the number `gh api repos/<owner>/<name> --jq .id` prints, then `terraform apply` to make the federation. It trusts only `deploy.yml` started by hand on `main` in the repository with that id, so another workflow, another branch, or a new repository given the same name later gets nothing. Then, in the repository's Settings, Secrets and variables, Actions, Variables, set:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | The project id |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `terraform output -raw workload_identity_provider` |
| `GCP_DEPLOYER_SERVICE_ACCOUNT` | `terraform output -raw deployer_service_account` |
| `TFVARS` | The contents of `terraform.tfvars`, which hold no secret |

The plan reads the budget, which lives on the billing account, not the project. Grant the deployer Billing Account Viewer on the billing account in the console, or the plan stops there.

The deployer can read the Terraform state but not write it, so the workflow plans with `-lock=false`. A plan run while the owner is applying may show a state that is about to change; plan again afterwards.

## A deploy

1. Merge to `main`. CI runs both check suites, the docs lint, the Terraform checks and an image build.
2. In GitHub, Actions, "Build and plan", run the workflow on `main`. It pushes the image tagged with the commit and lists in the run's summary which resources the plan would change, without their values: if the repository is public, anyone can read a run's summary and log.
3. Read the list. A deploy that changes only code shows the service and each job being updated and nothing else. `terraform apply` in step 4 prints the whole plan before it asks to go ahead.
4. Put the commit in `image_tag` in `terraform.tfvars` (and in the `TFVARS` variable), then from `infra/terraform` run `terraform apply`.
5. If the models gained a table, run the schema job (step 7).

Cloud Run starts the new revision, waits for `/healthz` to answer, then moves all traffic to it. New requests go to the new revision. Requests already open on the old one, such as event streams, are not cut off when traffic moves: they run on until they end or reach the 600 s request timeout, which wasn't checked on a real project. When Cloud Run stops an old instance it sends SIGTERM and kills the process ten seconds later; the server ends its event streams at once and closes whatever else it still holds after five seconds (`FIELDCLUB_SHUTDOWN_GRACE_S`), so it stops before it is killed. Until the old instances stop, they still hold their database connections (see [Sizing](#sizing)).

## Rolling back

The quick way moves traffic back to the revision before, without building anything:

```
gcloud run revisions list --service=fieldclub --region=europe-west2 --project="$P"
gcloud run services update-traffic fieldclub --region=europe-west2 --project="$P" \
  --to-revisions=<previous-revision>=100
```

Then set `image_tag` back to that revision's commit and apply, so Terraform agrees with what is running. Otherwise the next apply moves traffic forward again.

A schema change can't be rolled back this way. `create_schema` only adds what is missing, so an older image runs against a newer schema as long as nothing it uses was removed.

The database has seven daily backups. Restoring one replaces the whole instance's data with that day's:

```
gcloud sql backups list --instance=fieldclub --project="$P"
gcloud sql backups restore <backup-id> --restore-instance=fieldclub --project="$P"
```

## What to watch

- **The budget emails.** At 50%, 90% and 100% of the month's amount, and when the forecast passes it.
- **Cloud Run, the service's Metrics tab.** Request latency, instance count and billable instance time. Billable time that stays high with few requests means event streams are holding instances open (see [Cost](#estimated-monthly-cost)).
- **Cloud SQL, the instance's overview.** CPU, memory and disk. Sustained CPU above 80% or memory near 1.7 GB is the sign to move up a tier (`db_tier = "db-custom-1-3840"`).
- **Job executions.** Cloud Run, Jobs shows each run's outcome. A scheduled job that fails twice in a row is worth a look in its logs.
- **Errors.** Logs Explorer with `severity>=ERROR` and the resource set to the service or a job.

## Sizing

### The service: 1 vCPU, 1 GiB, 20 requests per instance, 0 to 3 instances

Endpoints are synchronous and run on FastAPI's thread pool (Decision 0001). A terrain tile is CPU work: ARCHITECTURE.md's terrain section has the combined blend at about 75 ms of numpy per 512 px tile, and about 100 ms with encoding.

The image was measured on 2026-11-10 on the arm64 build with Docker limiting the CPUs, rendering 144 uncached zoom-15 tiles over Avebury from the local mirror:

| CPUs | Requests at once | Tiles a second | Median | 95th percentile |
|---|---|---|---|---|
| 1 | 1 | 4.9 | 193 ms | 279 ms |
| 1 | 4 | 7.7 | 502 ms | 603 ms |
| 1 | 16 | 5.8 | 2,715 ms | 3,209 ms |
| 2 | 1 | 5.3 | 181 ms | 265 ms |
| 2 | 4 | 15.5 | 268 ms | 303 ms |
| 2 | 16 | 11.5 | 1,369 ms | 1,610 ms |

The process peaked at about 370 MiB. A cached tile is a read from the cache bucket and costs almost no CPU.

One vCPU renders about 8 new tiles a second at best, so a fresh screen of 12 to 20 tiles takes 2 to 3 seconds on one instance. Two vCPUs halve that for the same CPU-seconds per tile. They were not chosen because request-based billing charges for every vCPU for as long as any request is open, and the event stream (`GET /events/stream`) holds a request open for as long as someone has the page open. An instance held open by one idle stream costs twice as much at 2 vCPUs. `service_cpu = "2"` is the first change to make if tile latency matters more than that.

Concurrency is 20, not 4, because most requests wait rather than compute: cached tiles, JSON, and open event streams that each take a slot. At 4, three open streams would leave one slot and force a new instance for every visitor. Cloud Run also adds instances when CPU passes 60%, so a burst of renders spreads out anyway.

That sets a ceiling. Three instances of 20 slots are 60 requests at once, and each open tab holds one slot with its event stream, so about 60 open tabs fill the service and further requests wait or are refused. Raise `service_max_instances` or `service_concurrency` before that, minding the database connections below.

1 GiB holds the 370 MiB measured plus a source tile fetched from Defra while the copy is incomplete. A fetch stages up to 90 MB on the in-memory disk and its 1.8 s conversion peaked at 236 MiB.

Three instances at most caps cost and connections: each instance holds up to 8 database connections, so 24 at most, inside the 50 that `db-g1-small` allows. The four jobs that use the database hold up to 4 each, 16 more, so 40 with everything busy. During a deploy the old revision's instances keep their connections until they stop, so for a short while the service can hold up to 48 and, with the jobs, pass 50. A connection refused then is an error for that request. Avoid starting jobs during a deploy, or move up a tier before raising `service_max_instances`.

Startup took 2.1 s to the first `/healthz` answer natively on arm64, and 5.6 s for the amd64 image under emulation on the same machine. Cloud Run adds the image fetch, about 280 MB compressed, and startup CPU boost is on. Expect a cold start of several seconds; with scale to zero, the first visitor after a quiet spell waits for it.

### The database: db-g1-small

`db-g1-small` is the smallest shared-core tier with a usable amount of memory, 1.7 GB, at $0.035 an hour in the published table ($25.55 a month).

The development database holds 20,006 scheduled monuments in 137 MB: 76 MB of rows, 29 MB of indexes and the rest outlines kept out of line. That is 6.8 KB a record, and scheduled monuments are the heaviest kind because each has a polygon. Most of the ten million records expected are points, so the estimate is 2 to 3 KB each, 20 to 30 GB in all, and up to 70 GB if every record were like a scheduled monument. The disk starts at 20 GB and grows by itself up to 100 GB.

Ten million records won't fit in 1.7 GB of memory, so searches and nearby queries read their indexes from SSD. For a few people at once that is fast enough. `db-f1-micro` at 0.6 GB is too small to build a trigram index over ten million names, and allows 25 connections. The next step up is `db-custom-1-3840`, one dedicated vCPU and 3.75 GB, at $0.0676 an hour ($49 a month). Shared-core tiers aren't covered by the Cloud SQL SLA.

A Cloud SQL instance can't scale to zero. It is most of the bill at rest.

### The elevation copy

The copy has 5,877 files, 353.6 GB, from one SFTP server that Defra offered freely, at about 8 MB/s per connection. Defra's server dropped whole-file reads at 52 MiB, which the SFTP client already handles by reading in 8 MiB windows. Whether it tolerates several connections at once wasn't tested. One connection would take about 12.3 hours.

It runs as a Cloud Run job with four tasks, two at a time, rather than on a temporary machine:

- **It is polite by construction.** Each task holds one connection, so the job's parallelism is the number of connections the job opens: 2, which can be lowered to 1 or raised in `elevation_copy`. The service adds its own while it fetches missing tiles (step 8). A read that hears nothing for 60 seconds gives up, a failed attempt waits 2 seconds before the next, doubling each time up to a minute, and a refused login or a run of five failed tiles stops the task.
- **It resumes.** A tile already in the mirror is skipped, so a failed task, or the whole job run again, fetches only what is missing.
- **Nothing to forget.** A machine has to be made, given credentials on its disk, watched and deleted. The job uses the same image, identity and secrets as everything else, and stops costing when it ends.
- **It is cheap.** Converting a tile took 1.8 s and peaked at 236 MiB, so the work is waiting on the network. Four tasks of about four hours at 1 vCPU and 2 GiB come to about 58,000 vCPU-seconds, inside the jobs free tier of 240,000 a month, and $1.27 at the published rate beyond it.

A task may run for up to five hours (`elevation_copy.timeout`), an hour more than one should need, so a task that stalls is stopped then and retried. Cloud Run allows up to 168.

The converted mirror is about half the source: SU16nw went from 48 MB to 24 MB. The bucket ends at about 177 GB.

### Content delivery network: off at launch

A CDN in front of Cloud Run needs a global external Application Load Balancer, whose forwarding rule is $0.025 an hour, $18.25 a month, before any traffic. The load balancer also charges $0.008 a GB in each direction.

Cloud CDN's cache egress to Europe is $0.08 a GB against $0.12 a GB for the service's own premium-tier egress. The saving of $0.04 a GB pays for the standing charge at about 460 GB a month served from cache. The light use estimated below is about 70 GB. The service already caches every tile in the bucket, so a CDN would save CPU only on tiles rendered once and fetched again from another instance.

It becomes worth having when either the monthly tile traffic reaches several hundred GB, or a custom domain is wanted, because the load balancer is also the only way to put a domain on Cloud Run in London. Turning it on is one variable.

## Estimated monthly cost

Prices were read from Google's published pricing pages on 2026-11-10. Those pages show only their default region's prices without running the page's script, which is us-central1 (Iowa) for Cloud Run, Cloud SQL and Cloud Storage. London is Tier 2 for Cloud Run and is dearer than Iowa for Cloud SQL and Cloud Storage, by an amount these pages didn't show. Treat each figure as the floor of what London charges. The Cloud Run free tier is applied at Tier 1 rates, so it is worth slightly less in London than it looks.

Assumptions for light use: 50 visits a day of ten minutes each, 300 tile requests a visit with half already cached, 150 KB a tile, and each visit holding the event stream open for its ten minutes, one visit at a time.

| Item | Price used | At rest | Light use |
|---|---|---|---|
| Cloud SQL `db-g1-small` | $0.035 an hour | $25.55 | $25.55 |
| Cloud SQL SSD, 30 to 70 GB once the records are in | $0.17 a GB-month | $5.10 to $11.90 | $5.10 to $11.90 |
| Cloud SQL backups, about 20 to 50 GB | $0.08 a GB-month | $1.60 to $4.00 | $1.60 to $4.00 |
| Elevation mirror, 177 GB | $0.020 a GB-month | $3.54 | $3.54 |
| Tile cache and photos, 6 GB | $0.020 a GB-month | $0.12 | $0.12 |
| Artifact Registry, 1.4 GB, 0.5 GB free | $0.10 a GB-month | $0.09 | $0.09 |
| Secret Manager, 12 versions, 6 free | $0.06 a version-month | $0.36 | $0.36 |
| Cloud Scheduler, up to 3 jobs, 3 free | $0.10 a job-month | $0 | $0 |
| Cloud Run jobs, scan and refresh | Inside the free tier | $0 | $0 |
| Cloud Run service, 900,000 s of instance time | $0.000024 a vCPU-s, $0.0000025 a GiB-s, after the free tier | $0 | $18.63 at least |
| Cloud Run requests, 450,000 | 2 million free | $0 | $0 |
| Internet egress, 68 GB | $0.12 a GB | $0 | $8.10 |
| Storage operations, 225,000 writes and about 2.5 million reads | $0.005 and $0.0004 a thousand | $0 | $2.13 |
| Budget alert | Free | $0 | $0 |
| **Total** | | **about $36 to $46** | **about $65 to $75** |
| With the CDN module on | $0.025 an hour plus $0.008 a GB | +$18.25 | +$19.35 |

The disk starts at 20 GB but grows by itself as the records arrive and never shrinks, so it is priced at the 30 to 70 GB the ten million records are expected to need (see [The database](#the-database-db-g1-small)). The Cloud Run line is Iowa's Tier 1 rate less a free tier that is itself counted at Tier 1 rates, so in London, Tier 2, it can only be higher.

The light-use Cloud Run line depends almost entirely on the event stream. Without it, the same visits keep an instance busy for about 45,000 s a month, inside the free tier, and light use comes to about $46 to $55. The web client closing the stream while its tab is hidden is the cheapest saving available.

What these figures leave out, because it couldn't be priced from the pages read:

- London's own rates for Cloud SQL, Cloud Storage and Cloud Run.
- Cloud Logging and Monitoring. The first 50 GB of logs a month are free, and nothing here should come near it.
- Cloud SQL's network egress to the service, free within the region, and its IP address, which these pages didn't price separately for a running instance.
- Defra's side. Ingress into Google Cloud is free.
- A real traffic pattern. The light-use row is a guess with its working shown.
- The national overview build: its time and its peak memory over all 5,877 tiles, with its work folder in the instance's memory.

## What can only be checked in a real project

- That the first apply succeeds, including the budget, which needs permissions on the billing account.
- That `terraform plan` from the deploy workflow succeeds through federation, with the deployer's read-only roles.
- That GDAL reads `gs://` through `/vsigs/` with the service account Cloud Run lends it, with no key file. The image sets `CPL_MACHINE_IS_GCE=YES` so that GDAL asks the metadata server for it, as GDAL's documentation says a container must.
- That an upload with `if_generation_match=0` from an account holding only `objectCreator` is answered with a failed precondition, or a refusal, when the tile is already there. The mirror accepts either.
- That the Cloud SQL connector, the unix socket at `/cloudsql` and `connector_enforcement = REQUIRED` work together, and that the `fieldclub` login may create the PostGIS, pg_trgm and citext extensions.
- That the Cloud Storage volume mounts for the ingest job, and that the ingest downloader's partial files and renames behave on it.
- The cold start on Cloud Run, and real tile latency with the mirror in a bucket.
- That Defra's server accepts two connections at once from Google's addresses.
- That Cloud Scheduler starts each job, and the ingest job with its overridden arguments.
- The managed certificate and the load balancer, if the CDN module is turned on.
