# Running Open Antiquity on Fly.io

This is the runbook for the deployment on Fly.io: what the owner does once, what a deploy is afterwards, how to roll back, and what to watch. It also records the sizing and cost reasoning behind the defaults. Decision 0018 chose Fly.io, and the spike `docs/architecture/decisions/spikes/hosting-on-fly-io.md` measured what it rests on.

Everything lives in the Fly organisation `openantiquity`, in London (`lhr`). Every command names its app with `--app`, so the directory a command runs in never chooses the app. Commands run from the main checkout, at the repository root, because the secrets script reads the untracked `.env` and `var/` there. What has been done so far is recorded in `docs/plans/v1-england.md`, WS8.

Nothing in this folder has been run against Fly. Each command below was written from Fly's and Tigris's documentation, cited beside it, or from the spike. Check each one with `--help` before running it, and correct this file where the platform differs.

## What is in this folder

| Path | What it is |
|---|---|
| `../fly.toml` | The web app `openantiquity`: the image, the release command, every non-secret setting, the HTTP service, its health check and machine size. At the repository root because `fly deploy` builds from the directory it runs in, and the image is built from the root |
| `Dockerfile` | One image for the service and every job, built from the repository root |
| `fly/jobs.toml` | The jobs app `openantiquity-jobs`: its non-secret settings and the hourly machine's volume. Read by `fly_jobs.py`. It is not a `fly.toml` and must never be given to `fly deploy` |
| `fly_jobs.py` | Starts each job as a machine in the jobs app, and keeps the hourly machine on the current image |
| `fly-secrets.sh` | Sets an app's secrets from `.env`, `var/` and a file of other secrets, without showing them |
| `jobs/mirror_shard.py` | Shares of the whole-country elevation copy, run inside the image |
| `jobs/cache_lifecycle.py` | The tile cache bucket's expiry rule, set through the S3 lifecycle interface, run inside the image |
| `dns.py`, `dns.toml` | The DNS record sets the project manages at Gandi, and the tool that applies them |
| `docker-compose.yml` | The local PostGIS for development and tests |
| `terraform/`, `bootstrap.sh`, `add-defra-secrets.sh` | The Google Cloud deployment, kept until the cut-over (see [Google Cloud until the cut-over](#google-cloud-until-the-cut-over)) |
| `../.github/workflows/ci.yml` | Checks on pushes to main and on pull requests, the scripts' tests and shellcheck among them |
| `../.github/workflows/deploy.yml` | Run by hand on main: deploys the web app to Fly with a deploy token |

The scripts' tests are in `backend/tests/infra/`. Each runs its script against a stand-in for the command it drives, so they never reach Fly. `test_fly_config.py` starts the application's settings from each configuration file as a Fly machine would see them.

## What gets built

- **The web app `openantiquity`** serves the API, the tiles and the built frontend from one image. Three machines, `shared-cpu-2x` with 2 GB, suspended when idle and resumed by Fly's proxy when a request comes. Its release command creates the schema once per deploy.
- **The jobs app `openantiquity-jobs`** runs the same image with other commands. Each job is a machine that runs once, exits and is removed. One machine named `due` is started by Fly every hour and runs `fieldclub-jobs due`, which runs the channel scan every six hours and the source refresh at 03:00 UTC. A 10 GB volume on it keeps ingest downloads between runs. This app alone holds Defra's login: the web app must never have it (Decision 0018). Fly keeps secrets per app, so a second app is the only way to keep a secret from the service.
- **Managed Postgres** cluster `openantiquity`, PostgreSQL 17 with PostGIS, Basic plan, in London, attached to both apps. The application connects to its direct address, never the pooled one Fly attaches (`config.database_address`).
- **Three private Tigris buckets.** `openantiquity-elevation` holds the mirror under `england/mirror/` and the national overview under `england/national/`. `openantiquity-cache` holds rendered tiles under `tiles/`, deleted 180 days after they were written. `openantiquity-photos` holds uploads, kept.
- **One Tigris access key per app.** Fly gives an app one key, in `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, so each app reaches all its buckets with that one key, given a role on each bucket. The web app's key is Editor on the cache and the photos and ReadOnly on the elevation. The jobs app's key is Editor on the elevation only.
- **Certificates** for the six names, from Let's Encrypt through Fly. The first ten are free.

## Once: setting up

Each step says where its values come from. The owner runs every step, with flyctl signed in as an account in the organisation `openantiquity`.

### 1. Sign in and make the two apps

```
fly auth login
fly apps create openantiquity --org openantiquity
fly apps create openantiquity-jobs --org openantiquity
```

### 2. The database

```
fly mpg create --name openantiquity --org openantiquity --region lhr --plan basic
```

`--name`, `--org`, `--region` and `--plan` are on Fly's [Managed Postgres page](https://docs.fly.io/mpg/create-and-connect/). It doesn't name a flag for the PostgreSQL version. During the spike the command offered 16 and 17: choose 17. The cluster starts with 10 GB and grows by itself.

PostGIS has to be enabled through Fly, because the app's login can't create it (the spike, Q3 step 1). The spike enabled it with the command below. Fly's page says the dashboard's Extensions page does the same.

```
fly mpg list                                   # note the cluster's id
fly mpg databases extensions enable postgis    # the spike's command; check --help for how it names the cluster
fly mpg attach <cluster-id> --app openantiquity
fly mpg attach <cluster-id> --app openantiquity-jobs
```

Each attach sets the secret `DATABASE_URL` on its app, with the pooled address. The application turns it into the direct one. The schema command creates `pg_trgm` and `citext` itself.

### 3. The buckets and their keys

`fly storage create`, run with an app, makes a bucket and sets four secrets on that app: `BUCKET_NAME`, `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` ([Fly's Tigris page](https://docs.fly.io/tigris)). Run it three times. The secrets never pass through the terminal.

```
fly storage create --app openantiquity-jobs --name openantiquity-elevation
fly storage create --app openantiquity --name openantiquity-photos
fly storage create --app openantiquity --name openantiquity-cache
```

The third replaces the web app's secrets from the second, so the web app ends up with the cache bucket's key. Give that key its two other buckets. Open Tigris's dashboard with `fly storage dashboard openantiquity-cache`, find the key under Access Keys, and give it Editor on `openantiquity-cache` and `openantiquity-photos` and ReadOnly on `openantiquity-elevation`. With Tigris's own CLI the same is

```
tigris access-keys assign <tid_ key id> --bucket openantiquity-cache,openantiquity-photos,openantiquity-elevation \
  --role Editor,Editor,ReadOnly
```

([`tigris access-keys assign`](https://www.tigrisdata.com/docs/cli/access-keys/assign/)). Tigris's page doesn't say whether this adds to a key's roles or replaces them, so name all three. Then, in the same dashboard:

- delete the key the second command made, which nothing uses now;
- check that the jobs app's key is Editor on `openantiquity-elevation` and has no other bucket;
- check that neither key is Admin, which bypasses the per-bucket roles ([Tigris access control](https://www.tigrisdata.com/docs/partner-integrations/access-control/)).

The application ignores `BUCKET_NAME`: the buckets are named in `fly.toml` and `fly/jobs.toml`. Making a bucket accepts Tigris's terms of service for the organisation, which the spike already did.

### 4. Secrets

```
bash infra/fly-secrets.sh web --session-key
bash infra/fly-secrets.sh jobs --session-key --defra
```

Each app gets its own session key; the jobs never sign anyone in, but production refuses to start without one. `--defra` reads `DEFRA_SFTP_HOST`, `DEFRA_SFTP_USER` and `DEFRA_SFTP_PASSWORD` from `.env` and the pinned host key from `var/defra_known_hosts`, and is refused for the web app. The host key is stored base64-encoded as `DEFRA_KNOWN_HOSTS_B64`, and `fly_jobs.py` has Fly write it as a file into each copy machine (`fly machine run --file-secret`, [flags](https://docs.fly.io/flyctl/machine-run/)).

The sign-in providers' secrets and the mail password go in an untracked file, one `NAME=VALUE` a line, such as `var/web-secrets.env`, and are set from it once they exist:

```
bash infra/fly-secrets.sh web --from var/web-secrets.env
```

It reads only `FIELDCLUB_GOOGLE_CLIENT_SECRET`, `FIELDCLUB_MICROSOFT_CLIENT_SECRET`, `FIELDCLUB_FACEBOOK_APP_SECRET`, `FIELDCLUB_OSM_CLIENT_SECRET`, `FIELDCLUB_APPLE_PRIVATE_KEY`, `FIELDCLUB_SMTP_PASSWORD`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from it, and ignores every other line. Add the provider's client id to `fly.toml` at the same time, then deploy. A provider is offered only when both are there.

The script sends everything in one `fly secrets import --stage`, which reads `NAME=VALUE` lines from standard input ([`fly secrets import`](https://docs.fly.io/flyctl/secrets-import/)). Fly's page says nothing of quoting or values over several lines, so the script refuses a value that spans lines or starts or ends with a space rather than risk it arriving changed. Apple's private key is a PEM file over several lines, so it can't be set this way yet: find how `fly secrets import` reads such a value first. `--stage` means a secret takes effect at the next deploy of the web app, and on each jobs machine started afterwards. A secret already set is left alone; `--replace` sends it again.

Register each sign-in provider with the redirect address `https://openantiquity.org/api/v1/auth/oauth/<provider>/callback`, where `<provider>` is `google`, `microsoft`, `apple`, `facebook` or `osm`.

### 5. The first deploy

From the repository root:

```
fly deploy --image-label "$(git rev-parse HEAD)"
fly scale count 3 --region lhr --app openantiquity
```

`fly deploy` reads `fly.toml`, builds the image on Fly's builder (`--remote-only` is the default), pushes it as `registry.fly.io/openantiquity:<commit>`, runs the release command `python -m fieldclub.db` on a machine of its own and then starts the service ([`fly deploy`](https://docs.fly.io/flyctl/deploy/), [`[deploy]`](https://docs.fly.io/reference/configuration)). The schema command creates the extensions, the tables and the extras, and is safe to run again. Until the first release there is no migration history (`docs/ARCHITECTURE.md`, Conventions), so a change to an existing table needs the database rebuilt or Alembic, which starts at the first public release.

The first deploy makes two machines (`--ha` is on by default) and `fly scale count` makes the third. One deploy during the spike failed after the image was pushed, with an internal error from Fly's API, and worked when run again.

An app with an HTTP service is given a shared IPv4 and an IPv6 address at its first deploy ([public network services](https://docs.fly.io/networking/services/)), so the site answers at `https://openantiquity.fly.dev` from then on. Nobody has that address. Sign-in won't work there, because every sign-in redirect and emailed link is built from `https://openantiquity.org`, which doesn't point at Fly until step 11. To keep the app private until then, release its public addresses (`fly ips list --app openantiquity`, then `fly ips release <address> --app openantiquity`) and give it a private Flycast address with `fly ips allocate-v6 --private --app openantiquity` ([Flycast](https://docs.fly.io/networking/flycast/)), which goes through Fly's proxy and so wakes a suspended machine. Step 11 allocates the public addresses again.

Check it answers:

```
curl --fail https://openantiquity.fly.dev/healthz
```

### 6. The tile cache's expiry rule

Tiles in `openantiquity-cache` are deleted 180 days after they were written, the rule the Google bucket had. A tile's key carries its style and data version, so a tile not rewritten for half a year is almost certainly one nobody asks for. Tigris takes an expiry by prefix through the S3 lifecycle interface, up to ten rules a bucket ([object lifecycle rules](https://www.tigrisdata.com/docs/buckets/object-lifecycle-rules/)). The script runs on a web machine, which holds the cache bucket's key:

```
fly ssh console --app openantiquity -C "python /app/jobs/cache_lifecycle.py"
```

It replaces the bucket's whole lifecycle configuration, so it is safe to run again, and prints the rule read back. `--check` only reads it. A suspended machine may need waking first: load the site once.

### 7. The elevation's sources rows

```
uv run infra/fly_jobs.py sources
```

The LIDAR `sources` rows must exist before any elevation is stored or shown. The copy and the overview build leave them to this job (`--skip-sources`). It is safe to run again.

`fly_jobs.py` runs the image of the commit at `HEAD`, `registry.fly.io/openantiquity:<commit>`, which step 5 pushed. `--commit <sha>` names another and `--image <reference>` gives a whole one. `--dry-run` prints the `fly machine run` command without running it. Each one-off job is `fly machine run` with `--rm` and `--restart no`: it runs once, exits and is removed, and is never restarted, so a failed one is seen in `fly logs --app openantiquity-jobs` and run again by hand.

### 8. England's elevation in the bucket

The converted elevation already in Google's bucket is copied across once, after Google's copy has finished (Decision 0018, point 8). Defra's server isn't asked for the country a second time. See [Copying the elevation from Google](#copying-the-elevation-from-google). The Fly copy below is for anything Google's copy lacks, or for a fresh start if the Google bucket is gone.

```
uv run infra/fly_jobs.py mirror 1 3
uv run infra/fly_jobs.py mirror 2 4
```

The 5,877 tiles are split into four shares of about 88 GB each, by size. Each command starts one machine that runs its two shares one after the other, each with one SFTP connection, so the two machines hold two connections to Defra's server at once, as the Google job did. A share that stops, because the supply refused the login, showed another host key or failed five tiles in a row, stops its machine, and the machine's last log lines name the share. Run a failed share again by naming it, for example `uv run infra/fly_jobs.py mirror 3`. A tile already in the mirror is skipped, so a rerun fetches only what is still missing. The spike didn't try Defra's server from Fly's addresses: start with one machine and watch its log before starting the second.

The web app doesn't fetch missing elevation, because it doesn't hold Defra's login. A tile that isn't mirrored answers its failure, as Decision 0016 describes, until a copy adds it.

Progress is what `fieldclub-terrain info` reports:

```
uv run infra/fly_jobs.py run fieldclub-terrain info
fly logs --app openantiquity-jobs
```

### 9. Build the national overview

```
uv run infra/fly_jobs.py national
```

It runs `fieldclub-terrain national build --skip-sources` on a `performance-8x` machine, the size Fly lists with 16 GB, with a 20 GB root file system (`--rootfs-size`). The build mosaics the 8 m copies inside the mirrored tiles into one cloud-optimised file under `england/national/`, uploads it and points `england/national/national.json` at it (Decision 0012). The service reads `national.json`, so nothing needs deploying afterwards. Its work folder, about 8 GB for all of England, is on the machine's disk here, where on Cloud Run it was in memory. Run it again whenever tiles have been added. It exits 0 when the overview is current and 1 on an error.

### 10. The first ingests and the hourly machine

```
uv run infra/fly_jobs.py run fieldclub-ingest list
uv run infra/fly_jobs.py ingest he-nhle-scheduled-monuments
```

Then make the volume and the hourly machine:

```
fly volumes create jobs_var --app openantiquity-jobs --region lhr --size 10 --yes
uv run infra/fly_jobs.py schedule
```

`schedule` makes a machine named `due` with `--schedule hourly`, the volume mounted at `/data` and `FIELDCLUB_VAR_DIR=/data/var`, running `fieldclub-jobs due`. Fly starts it once an hour at a time of its own choosing in the hour. `fieldclub-jobs due` decides from the database and the clock what is due (`backend/src/fieldclub/jobs/due.py`): the channel scan when some channel is watched and none has been checked for five hours, which keeps scans about six hours apart, and the source refresh when the hour is 03 UTC. The refresh runs every enabled bulk connector and reference loader whose last full run is older than its `max_age`, so it covers every bulk source, and a second start in the same hour finds them current. Ingest downloads stay on the volume, so the next run can ask the publisher whether a file changed. An ingest started by hand in step 10 downloads afresh, because the volume belongs to the hourly machine.

Fly's schedules run hourly, daily, weekly or monthly, at no fixed time ([`fly machine run --schedule`](https://docs.fly.io/flyctl/machine-run/)). One hourly machine that asks what is due needs nothing left running between starts.

### 11. Point the domain

The site is `openantiquity.org`. `www.openantiquity.org`, `openantiquity.com`, `openantiquity.co.uk` and their `www` names are answered by the application with a 308 to the same path on `openantiquity.org` (`FIELDCLUB_REDIRECT_HOSTS` in `fly.toml`, `backend/src/fieldclub/redirects.py`). Fly's proxy has no redirect setting of its own, so the application does it. `force_https` sends plain HTTP to HTTPS first, so every name needs a certificate: six, inside the ten free ones.

```
fly ips allocate-v4 --shared --app openantiquity      # if step 5 released them
fly ips allocate-v6 --app openantiquity
fly ips list --app openantiquity
for name in openantiquity.org www.openantiquity.org openantiquity.com www.openantiquity.com \
            openantiquity.co.uk www.openantiquity.co.uk; do
  fly certs add "$name" --app openantiquity
done
```

An apex name can't be a CNAME, so each domain's `@` gets an `A` record for the shared IPv4 address and an `AAAA` record for the IPv6 address, and each `www` a `CNAME` to `openantiquity.fly.dev.` ([custom domains](https://docs.fly.io/networking/custom-domain/)). The `AAAA` record is also one of the ways Fly checks that the domain is ours before it issues a certificate. `infra/dns.toml` holds these records commented out. Put the two addresses `fly ips list` printed into them, uncomment them, then:

```
uv run infra/dns.py plan
uv run infra/dns.py apply
fly certs check openantiquity.org --app openantiquity
```

`infra/dns.py` touches only what `dns.toml` lists, so Gandi's mail records stay as they are. Its token is `GANDI_DNS_SSL` in `.env`. The `CAA` records already allow Let's Encrypt, which Fly uses. A certificate is issued once its records resolve, which can take an hour.

### 12. The deploy workflow

In the repository's Settings, Environments, make an environment named `production` with deployment branches limited to `main`. Then make a deploy token for the web app alone and put it there, without it passing through the terminal:

```
fly tokens create deploy --app openantiquity --name github-deploy --expiry 2160h |
  gh secret set FLY_API_TOKEN --env production
```

A deploy token is limited to one app ([access tokens](https://docs.fly.io/security/tokens/)). The token above lasts 90 days; renew it the same way. `fly tokens list` and `fly tokens revoke <id>` take one away. GitHub never holds a token for the jobs app, so Defra's login is out of its reach.

## A deploy

1. Merge to `main`. CI runs both check suites, the docs lint, the scripts' tests and shellcheck, the Terraform checks while it stays, and an image build that is started and stopped as a Fly machine would be.
2. In GitHub, Actions, "Deploy", run the workflow on `main`. It runs `flyctl deploy --remote-only --image-label <commit>`, which builds the image, runs the schema command once and moves the three machines onto the new image one at a time (`strategy = "rolling"`).
3. Move the hourly machine to the same image, from the main checkout, with the command the run's summary prints:

   ```
   uv run infra/fly_jobs.py --commit <commit> schedule
   ```

   It updates the machine named `due` in place (`fly machine update --image`, [flags](https://docs.fly.io/flyctl/machine-update/)) without starting it. Until it is run, the hourly jobs run the image before, which still works against the schema, because the schema command only adds what is missing.

A deploy by hand is the same command as the workflow's, from the repository root: `fly deploy --image-label "$(git rev-parse HEAD)"`.

Fly sends the old machine `SIGTERM` (`kill_signal`) and kills it ten seconds later (`kill_timeout`). The server ends its event streams at once and closes whatever else it still holds after five seconds (`FIELDCLUB_SHUTDOWN_GRACE_S`), so it stops before it is killed, and the browser opens a new stream on another machine.

## Rolling back

Deploy the image before, which needs no build:

```
fly releases --app openantiquity --image
fly deploy --image registry.fly.io/openantiquity:<previous commit>
uv run infra/fly_jobs.py --commit <previous commit> schedule
```

A schema change can't be rolled back this way. The schema command only adds what is missing, so an older image runs against a newer schema as long as nothing it uses was removed.

Managed Postgres keeps backups. `fly mpg backup list` lists them and `fly mpg restore <cluster-id> --backup-id <id>`, or `--pitr-time <RFC 3339 time>`, restores one into a new cluster ([`fly mpg restore`](https://docs.fly.io/flyctl/mpg-restore/)). The original is left alone. Attach the new cluster to both apps and deploy. How long Fly keeps them wasn't found; check before relying on them.

## What to watch

- **The month's spend.** Fly has no billing alert and no spending cap (see [Spend](#spend)). Look at the dashboard's current month to date bill once a week.
- **The web app's machines.** `fly status --app openantiquity` and the dashboard's metrics: memory, CPU and how often machines are running. A machine that stays running with few requests is held by open event streams. Steady CPU at the shared baseline means Fly is throttling it (see [Sizing](#sizing)).
- **The database.** The cluster's page in the dashboard: CPU, memory, disk and connections. The Basic plan allows 112 connections.
- **The jobs.** `fly logs --app openantiquity-jobs`. Every job logs a one-line summary and exits non-zero when anything failed. Check the hourly machine's last runs after each deploy.
- **The tile cache's rule.** `fly ssh console --app openantiquity -C "python /app/jobs/cache_lifecycle.py --check"` exits 1 if the rule has gone.
- **Errors.** `fly logs --app openantiquity`, for lines at `ERROR`.

## Spend

Fly can't be asked what the month has cost. Its cost page says "We don't support billing alerts (yet)" and "there's no soft ceiling. If you go over, we'll bill you", and the only place it names for the month so far is the dashboard's "current month to date bill" ([cost management](https://docs.fly.io/about/cost-management/)). Its billing page describes no API or command for usage either ([billing](https://docs.fly.io/about/billing)). Prepaid credit is no cap: the billing page says usage "is subtracted from the credit balance each month" and says nothing of what happens when the credit runs out. So there is no scheduled spend check here, because there is nothing honest for one to read.

The guard is a manual check and limits that bound what the configuration can spend.

- **The check.** Once a week, read the current month to date bill in the dashboard's Billing section for the organisation. The alert on Google was £75 a month. At the prices below that is about twice the expected bill at light use, so a bill on course to pass £75 means something has changed.
- **Machines.** Fly's proxy starts and suspends machines but never creates one ([autostop and autostart](https://docs.fly.io/launch/autostop-autostart/)). The web app has three, so at most three run: $40.17 a month if all three ran all month, at US east prices. A fourth exists only if someone runs `fly scale count`.
- **Machine sizes.** `fly.toml` fixes the web machines at `shared-cpu-2x`, 2 GB, and `test_fly_config.py` fails if the memory changes. `fly_jobs.py` fixes each job's size, and every job but the hourly one is started by a person and removed when it ends.
- **What isn't bounded.** Data sent to visitors at $0.02 a GB, Tigris storage and requests, and the database's disk, which grows by itself. Those three are what the weekly check is for.

## Sizing

### The web service: three `shared-cpu-2x` machines with 2 GB, 20 to 30 requests each

Endpoints are synchronous and run on FastAPI's thread pool (Decision 0001), and terrain tiles are drawn on threads of their own (Decision 0016). A terrain tile is CPU work: about 75 ms of numpy per 512 px tile for the combined blend, and about 100 ms with encoding.

The image was measured on 2026-11-10 on the arm64 build with Docker limiting the CPUs, rendering 144 uncached zoom-15 tiles over Avebury from the local mirror:

| CPUs | Requests at once | Tiles a second | Median | 95th percentile |
|---|---|---|---|---|
| 1 | 1 | 4.9 | 193 ms | 279 ms |
| 1 | 4 | 7.7 | 502 ms | 603 ms |
| 1 | 16 | 5.8 | 2,715 ms | 3,209 ms |
| 2 | 1 | 5.3 | 181 ms | 265 ms |
| 2 | 4 | 15.5 | 268 ms | 303 ms |
| 2 | 16 | 11.5 | 1,369 ms | 1,610 ms |

One CPU renders about 8 new tiles a second at best, so a fresh screen of 12 to 20 tiles takes 2 to 3 seconds; two halve it. On Cloud Run a second vCPU was billed for as long as any request was open, and an event stream holds one open while the page is, so one vCPU was chosen there. A Fly machine is billed by the second while it runs, whatever its load, and at US east prices `shared-cpu-2x` with 2 GB is $13.39 a month against $9.70 for `shared-cpu-1x` with 1.5 GB, which is 1 GB at $6.70 and half a GB more at $6.00 a GB. Two CPUs cost about $3.70 more a month for a machine that runs all month.

Fly's shared CPUs are guaranteed 6.25% of a core each, may run at 100% while they have burst balance, and start with 5 seconds of it and keep up to 500 ([CPU performance](https://docs.fly.io/machines/cpu-performance/)). A screen of tiles is a burst of a few CPU-seconds, well inside that. Rendering many uncached areas for minutes on end would run the balance down and be throttled. If the metrics show that, move to `performance-1x`, $33.00 a month at US east prices.

2 GB holds the 320 MB in use at idle that the spike measured, a photo decode of up to about 400 MB (`services/media.py`) and renders at once. On Cloud Run 1.5 GiB was needed for a source tile fetched from Defra at the same time, about 1.1 GiB in all; the Fly service doesn't fetch. 2 GB is also the most a machine may have and still be suspended, with no swap ([suspend and resume](https://docs.fly.io/reference/suspend-resume/)), and the spike measured a suspended machine answering in 0.53 s against 20.8 s from stopped. A memory peak during a real upload hasn't been measured on Fly.

Concurrency counts requests (`type = "requests"`): past the soft limit of 20 the proxy prefers another machine and starts it if it is suspended, and it never sends one machine more than the hard limit of 30 ([configuration](https://docs.fly.io/reference/configuration)). Most requests wait rather than compute: cached tiles, JSON, and open event streams that each hold one. An event stream ends itself after 540 s (`FIELDCLUB_EVENTS_MAX_STREAM_S`); the spike held one open through the proxy for 600 s. A machine takes at most 26 streams (`FIELDCLUB_EVENTS_MAX_STREAMS`, the hard limit less four), so tiles and JSON always have four slots; a stream refused with `too_many_streams` makes the web client poll instead. Three machines of 30 are 90 requests at once, about 78 open tabs. Raise the count before that, minding the database connections below.

Each machine holds up to 8 database connections, so 24 at most, and the jobs up to 4 each. The Basic plan's `max_connections` is 112, and sixty from one machine were all accepted during the spike.

Fly's proxy suspends a machine after the app has been idle for several minutes and stops at most one machine per region on each pass ([autostop and autostart](https://docs.fly.io/launch/autostop-autostart/)). An open event stream kept the spike's machine running, so a machine runs for as long as anyone has the page open.

### The database: Managed Postgres Basic

The Basic plan is $38 a month plus $0.28 a GB ([pricing](https://docs.fly.io/about/pricing)). The development database holds 20,006 scheduled monuments in 137 MB, 6.8 KB a record, the heaviest kind. Most of the ten million records expected are points, so the estimate is 2 to 3 KB each, 20 to 30 GB in all, and up to 70 GB if every record were like a scheduled monument. The cluster starts at 10 GB and grows by itself. The Basic plan's memory wasn't found on the pages read; searches over ten million records will read their indexes from disk, which is fast enough for a few people at once. A larger plan is the first change if search slows.

### The jobs

| Job | Machine | Why |
|---|---|---|
| `sources` | `shared-cpu-1x`, 1 GB | Writes a handful of rows |
| `ingest <key>`, the hourly `due` | `shared-cpu-1x`, 2 GB | An ingest took 2 GiB on Cloud Run, and the refresh runs every due source in turn |
| `mirror <shares>` | `shared-cpu-1x`, 2 GB | Converting a tile peaked at 236 MiB; the work is waiting on the network |
| `national` | `performance-8x`, 16 GB, 20 GB disk | The Google job had 16 GiB of memory with its 8 GB work folder in it. On Fly the work folder is on disk; the build's own peak hasn't been measured, so the memory is kept |

### The elevation copy

The copy has 5,877 files, 353.6 GB, from one SFTP server that Defra offered freely, at about 8 MB/s per connection, so one connection would take about 12.3 hours and two about six. Defra's server dropped whole-file reads at 52 MiB, which the SFTP client handles by reading in 8 MiB windows. The copy is two machines of two shares each, rather than one machine:

- **It is polite by construction.** Each share holds one connection, and a machine runs its shares one after another, so two machines are two connections. A read that hears nothing for 60 seconds gives up, a failed attempt waits 2 seconds before the next, doubling each time up to a minute, and a refused login or a run of five failed tiles stops the share.
- **It resumes.** A tile already in the mirror is skipped, so a failed share, or the whole copy run again, fetches only what is missing.
- **Nothing to forget.** Each machine is removed when it exits.

The converted mirror is about half the source: SU16nw went from 48 MB to 24 MB. The bucket ends at about 177 GB.

## Copying the elevation from Google

Google's copy is finishing in `gs://$P-elevation/england/`, where `P` is the Google project id (`fieldclub-uk`). Copy it once to `openantiquity-elevation/england/` with [rclone](https://rclone.org/), from any machine with a good connection, after Google's copy has finished:

1. Make a temporary Tigris key in the dashboard (`fly storage dashboard openantiquity-elevation`) with Editor on `openantiquity-elevation` alone.
2. Write it into an untracked rclone configuration, `var/rclone.conf`, with an editor, so neither secret is typed on a command line:

   ```
   [google]
   type = google cloud storage
   env_auth = true
   bucket_policy_only = true

   [tigris]
   type = s3
   provider = Other
   endpoint = https://fly.storage.tigris.dev
   region = auto
   access_key_id = <the temporary key's id>
   secret_access_key = <its secret>
   ```

   `env_auth = true` uses the Google application default credentials the owner already has from `gcloud auth application-default login`.

3. Copy, leaving out the per-tile locks, then check:

   ```
   export P=fieldclub-uk
   RCLONE_CONFIG=var/rclone.conf rclone copy "google:$P-elevation/england" tigris:openantiquity-elevation/england \
     --exclude "mirror/locks/**" --checksum --transfers 8 --progress
   RCLONE_CONFIG=var/rclone.conf rclone check "google:$P-elevation/england" tigris:openantiquity-elevation/england \
     --exclude "mirror/locks/**" --one-way
   ```

4. Delete the temporary key in the dashboard, and `var/rclone.conf`.

The copy is about 177 GB, plus the national overview's 3.5 GB if Google built it. Google charges $0.12 a GB for data leaving its network, so about $21 to $22. Writing to Tigris is about 6,000 Class A requests, $0.03. The bytes pass through the machine running rclone. If Google's national overview was built, `national.json` and its COG come across with it and the service uses them; otherwise run step 9.

## Estimated monthly cost

Prices were read on 2026-11-11 from Fly's [pricing page](https://docs.fly.io/about/pricing), whose regional table didn't load, and from Tigris's [pricing page](https://www.tigrisdata.com/pricing/). Fly's machine prices are for its cheapest regions in the US east and "vary by region", so London's are not known and each machine figure is a floor. Fly lists Tigris on its own invoice at Tigris's list price.

Assumptions for light use, as on Google: 50 visits a day of ten minutes each, 300 tile requests a visit with half already cached, 150 KB a tile, each visit holding the event stream open for its ten minutes, one visit at a time. A machine then runs about 375 hours a month, counting a few idle minutes after each visit before Fly suspends it.

| Item | Price used | At rest | Light use |
|---|---|---|---|
| Managed Postgres Basic | $38 a month | $38.00 | $38.00 |
| Its storage, 30 to 70 GB once the records are in | $0.28 a GB-month | $8.40 to $19.60 | $8.40 to $19.60 |
| Web machines running, `shared-cpu-2x` 2 GB | $13.39 a month each, by the second | $0 | $6.97 |
| Web machines suspended, three root file systems of about 1 GB, an estimate from the image's size | $0.15 a GB-month | $0.45 | $0.45 |
| The hourly job machine, about 20 s an hour, and its stopped root file system | $12.70 a month at 2 GB; $0.15 a GB-month | $0.22 | $0.22 |
| Its volume, 10 GB | $0.15 a GB-month | $1.50 | $1.50 |
| Tigris storage, 177 GB of elevation and 6 GB of tiles and photos, 5 GB free | $0.02 a GB-month | $3.56 | $3.56 |
| Tigris writes, 225,000, 10,000 free | $0.005 a thousand | $0 | $1.08 |
| Tigris reads, about 2.5 million, 100,000 free | $0.0005 a thousand | $0 | $1.20 |
| Data out to visitors, 68 GB | $0.02 a GB | $0 | $1.36 |
| Shared IPv4, IPv6, six certificates | Free, the first ten certificates | $0 | $0 |
| Image builder and registry | Free today, which the page says may change | $0 | $0 |
| **Total** | | **about $52 to $63** | **about $63 to $74** |

At rest this is more than Google's estimate of $36 to $46, because Managed Postgres costs more than `db-g1-small`; Decision 0018 expected the two to cost about the same at rest. The saving is in traffic: at a thousand visits a day, the 675 GB a month the Google runbook assumed costs $13.50 here against $81 there, and there is no load balancer for the domain.

One-off costs: the national overview build on `performance-8x`, which the pricing page didn't list; at the listed $66 a month for `performance-2x`, four times that is about $0.37 an hour, so a build of a few hours costs a dollar or two. Copying the elevation from Google costs about $21 in Google's transfer fee.

What these figures leave out:

- London's machine prices.
- Data from the machines to Tigris, which Fly's pricing page says is billed separately, at a rate it didn't give.
- Managed Postgres backups, if they are charged.
- A real traffic pattern. The light-use row is a guess with its working shown.

## Google Cloud until the cut-over

The Google deployment in `terraform/` stays as it is, held back from the public (`service_public = false`), until the site on Fly has passed its checks (Decision 0018, point 10). Its full runbook is `git show 28488dd:infra/README.md`. Its Terraform, `bootstrap.sh` and `add-defra-secrets.sh` are kept unchanged until the project is taken down, and CI still checks the Terraform.

An image built from main can't run there any more: the application now speaks only S3, and `terraform/settings.tf` sets `FIELDCLUB_STORAGE_BACKEND=gcs` and `gs://` terrain folders, which the settings refuse. Google keeps running the image it has. Don't apply a new `image_tag` there.

### Taking the Google project down

Once the site on Fly answers on openantiquity.org, the elevation is in Tigris and checked, and the first ingests have run:

- [ ] `rclone check` (above) reports no missing files.
- [ ] Copy out anything else wanted. The Google database holds what ingests make again, and whatever the owner did while trying the held-back site.
- [ ] In `terraform/storage.tf`, remove the `prevent_destroy` line from the elevation bucket.
- [ ] From `infra/terraform`, with `terraform.tfvars` as it was applied: `terraform destroy`. It removes the service, the jobs, the schedules, the database, the buckets, the secrets, the service accounts, the federation and the budget.
- [ ] Delete the state bucket `gs://$P-tfstate`, then shut the project down: `gcloud projects delete "$P"`.
- [ ] In GitHub, remove the repository variables `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SERVICE_ACCOUNT` and `TFVARS`.
- [ ] Remove `pki.goog` from the `CAA` records in `dns.toml` and apply.
- [ ] Remove `terraform/`, `bootstrap.sh`, `add-defra-secrets.sh` and its test, and the Terraform step in `ci.yml`, in one commit, and update this file and `docs/ARCHITECTURE.md`.

## What can only be checked on the real platform

Each of these was written from documentation or inferred, and none was run:

- Every flyctl command and flag above, against `--help` of the flyctl in use. In particular: `fly mpg create`'s version prompt, `fly mpg databases extensions enable`, `fly storage create --app`, `fly secrets list --json` and `fly machine list --json` and the field names in their output, `fly machine run` taking the job's own flags after `--`, `fly machine update --schedule` and `--skip-start` on a scheduled machine, `fly releases --image`, and the release command's machine getting `[env]` and the secrets.
- That `fly storage create` makes a key with Editor on its own bucket and nothing more, and that a key given roles on three buckets reaches all three with one secret.
- That a machine in `openantiquity-jobs` can pull `registry.fly.io/openantiquity:<commit>`, an image pushed by another app in the same organisation. If it can't, push the image to the jobs app as well (`fly deploy --build-only --push --app openantiquity-jobs --image-label <commit>` with `--config fly.toml`) and pass `--image registry.fly.io/openantiquity-jobs:<commit>` to `fly_jobs.py`.
- That `--file-secret` writes the host key where the SFTP client reads it, readable by the image's user.
- That `fly ssh console -C` runs with the app's secrets in its environment, which `cache_lifecycle.py` needs, and that Tigris accepts boto3's lifecycle request with its checksum header.
- That `fly secrets import` keeps a value with `#`, `$`, quotes or inner spaces exactly as sent.
- That health checks don't keep a suspended machine awake, and that the database's `LISTEN` connection is found dead and replaced after a resume (the spike didn't test it).
- That Defra's server accepts connections from Fly's addresses, two at a time.
- Tigris multipart upload of the national COG, about 3.5 GB, which the spike didn't test.
- The certificates for six names, the shared IPv4 at the apex, and the 308 from each other name.
- Memory during a photo upload while tiles render, and real tile latency with the mirror in Tigris.
- London's prices, and what Fly does when prepaid credit runs out.
