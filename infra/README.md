# Running OpenAntiquity on Fly.io

This is the runbook for the deployment on Fly.io: what the owner does once, what a deploy is afterwards, how to roll back, and what to watch. It also records the sizing and cost reasoning behind the defaults. Decision 0018 chose Fly.io, and the spike `docs/architecture/decisions/spikes/hosting-on-fly-io.md` measured what it rests on.

Everything lives in the Fly organisation `openantiquity`, in London (`lhr`). Every command that acts on an app names it with `--app`, so the directory a command runs in never chooses the app, with three exceptions: `fly deploy` reads the web app's name from `fly.toml`, `fly_jobs.py build` names the jobs app itself, and the `fly mpg` commands name the cluster. Commands run from the main checkout, at the repository root, because the secrets script reads the untracked `.env` and `var/` there. What has been done so far is recorded in `docs/plans/v1-england.md`, WS8.

Steps 1 to 11 were carried out on 2026-11-12. Step 12 hasn't been run. Each of their commands was written from Fly's and Tigris's documentation, cited beside it, or from the spike. Check each one with `--help` before running it, and correct this file where the platform differs.

## What is in this folder

| Path | What it is |
|---|---|
| `../fly.toml` | The web app `openantiquity`: the image, the release command, every non-secret setting, the HTTP service, its health check and machine size. At the repository root because `fly deploy` builds from the directory it runs in, and the image is built from the root |
| `Dockerfile` | One image for the service and every job, built from the repository root |
| `fly/jobs.toml` | The jobs app `openantiquity-jobs`: its non-secret settings and the hourly machine's volume. Read by `fly_jobs.py`. It is not a `fly.toml` and must never be given to `fly deploy` |
| `fly_jobs.py` | Builds the jobs app's image, starts each job as a machine in the jobs app, and keeps the hourly machine on the current image |
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
- **The jobs app `openantiquity-jobs`** runs an image built from the same commit and Dockerfile, pushed to its own repository by the owner, with other commands. Each job is a machine that runs once, exits and is removed. One machine named `due` is started by Fly every hour and runs `fieldclub-jobs due`, which deletes expired sessions and old sign-in links every time, and runs the channel scan every six hours and the source refresh at 03:00 UTC. A 10 GB volume on it keeps ingest downloads between runs. This app alone holds Defra's login: the web app must never have it (Decision 0018). Fly keeps secrets per app, so a second app is the only way to keep a secret from the service.
- **Managed Postgres** cluster `openantiquity`, PostgreSQL 17 with PostGIS, Basic plan, in London, attached to both apps. The application connects to its direct address, never the pooled one Fly attaches (`config.database_address`).
- **Three private Tigris buckets.** `openantiquity-elevation` holds the mirror under `england/mirror/` and the national overview under `england/national/`. On Google, permissions kept anything from deleting or replacing a mirror tile. Here the jobs key is Editor on the whole bucket, so only the code keeps the mirror safe: a tile is uploaded only if nothing has its name, the overview build prunes only its own `england-<build>.tif` files, and the settings refuse a mirror and overview folder that are the same or one inside the other. `openantiquity-cache` holds rendered tiles under `tiles/`, deleted 180 days after they were written. `openantiquity-photos` holds uploads, kept.
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
fly mpg create --name openantiquity --org openantiquity --region lhr --plan basic \
  --pg-major-version 17 --enable-postgis-support
```

Every flag is in `fly mpg create --help` of flyctl 0.5.7. The cluster starts with 10 GB and grows by itself.

PostGIS has to be enabled through Fly, because the app's login can't create it (the spike, Q3 step 1). `--enable-postgis-support` makes it available on the cluster but doesn't install it in the database. On 2026-11-12 the extension list showed it absent until the `enable` command below was run, which installed PostGIS 3.6.4.

```
fly mpg list --org openantiquity               # note the cluster's id
fly mpg databases extensions list <cluster-id> --database fly-db
fly mpg databases extensions enable postgis --cluster <cluster-id> --database fly-db
fly mpg attach <cluster-id> --app openantiquity
fly mpg attach <cluster-id> --app openantiquity-jobs
```

Each attach sets the secret `DATABASE_URL` on its app, with the pooled address, and restarts the app, which has no machines yet. It prints the secret it adds, so clear the terminal and its scrollback afterwards. The cluster starts with one login, `fly-user`, whose role is `schema_admin`, and both apps connect as it. The application turns it into the direct one, and reads `DATABASE_URL` only on a Fly machine. The schema command creates `pg_trgm` and `citext` itself.

### 3. The buckets and their keys

`fly storage create`, run with an app, makes a bucket and a key and sets five secrets on that app: `BUCKET_NAME`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` ([Fly's Tigris page](https://docs.fly.io/tigris)). It also prints the key's id and secret, which flyctl can't show again. Nothing here needs the printed secret, because the app already holds it, so clear the terminal and its scrollback after each one. Fly's page doesn't say what a second create does to an app that already has the secrets, so each app gets one:

```
fly storage create -a openantiquity-jobs -n openantiquity-elevation
fly storage create -a openantiquity -n openantiquity-cache
```

Both were run on 2026-11-12, so the two buckets exist and each app holds its key: don't run either again. The command asks whether Tigris's terms are accepted, and `--yes` answers it.

Make the third bucket, `openantiquity-photos`, private, in Tigris's dashboard (`fly storage dashboard openantiquity-cache`, then Buckets), with no key of its own. Then give the web app's key its two other buckets: find it under Access Keys and give it Editor on `openantiquity-cache` and `openantiquity-photos` and ReadOnly on `openantiquity-elevation`. With Tigris's own CLI the same is

```
tigris access-keys assign <tid_ key id> --bucket openantiquity-cache,openantiquity-photos,openantiquity-elevation \
  --role Editor,Editor,ReadOnly
```

([`tigris access-keys assign`](https://www.tigrisdata.com/docs/cli/access-keys/assign/)). Tigris's page doesn't say whether this adds to a key's roles or replaces them, so name all three. Then, in the same dashboard:

- check that the jobs app's key is Editor on `openantiquity-elevation` and has no other bucket;
- check that neither key is Admin, which bypasses the per-bucket roles ([Tigris access control](https://www.tigrisdata.com/docs/partner-integrations/access-control/)).

The application ignores `BUCKET_NAME`: the buckets are named in `fly.toml` and `fly/jobs.toml`. Making a bucket accepts Tigris's terms of service for the organisation, which the spike already did. A key made by hand in the dashboard instead reaches an app through `bash infra/fly-secrets.sh <web|jobs> --from <file>`, which takes `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from an untracked file.

### 4. Secrets

```
bash infra/fly-secrets.sh web --session-key
bash infra/fly-secrets.sh jobs --defra
```

Only the web app gets a session key. The jobs sign nobody in, and the settings ask for the key only when the service starts, so the jobs app is never given one. `--defra` reads `DEFRA_SFTP_HOST`, `DEFRA_SFTP_USER` and `DEFRA_SFTP_PASSWORD` from `.env` and the pinned host key from `var/defra_known_hosts`, and is refused for the web app. The host key is stored base64-encoded as `DEFRA_KNOWN_HOSTS_B64`, and `fly_jobs.py` has Fly write it as a file into each copy machine (`fly machine run --file-secret`, [flags](https://docs.fly.io/flyctl/machine-run/)).

The sign-in providers' secrets and the mail password go in an untracked file, one `NAME=VALUE` a line, such as `var/web-secrets.env`, and are set from it once they exist:

```
bash infra/fly-secrets.sh web --from var/web-secrets.env
```

It reads only `FIELDCLUB_GOOGLE_CLIENT_SECRET`, `FIELDCLUB_MICROSOFT_CLIENT_SECRET`, `FIELDCLUB_FACEBOOK_APP_SECRET`, `FIELDCLUB_OSM_CLIENT_SECRET`, `FIELDCLUB_APPLE_PRIVATE_KEY`, `FIELDCLUB_SMTP_PASSWORD`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from it, and ignores every other line. Add the provider's client id to `fly.toml` at the same time, then deploy. A provider is offered only when both are there. The application reads the id from its environment, so it can be a secret as well: OpenStreetMap's and Google's are, as `FIELDCLUB_OSM_CLIENT_ID` and `FIELDCLUB_GOOGLE_CLIENT_ID`, because the owner keeps each in `.env` beside its secret. `var/handoff/tools/env_to_fly_secrets.py` hands named values from `.env` to an app's secrets under other names, without showing them.

The script sends each secret alone with `fly secrets set NAME=- --stage`, which reads the value from standard input. Checked on Fly on 2026-11-12 with flyctl 0.5.7: quotes, `$`, `#`, `=` and line breaks inside a value arrive unchanged, and white space at either end is trimmed. So the script refuses a value that starts or ends with a space or a line break, and Apple's private key, a PEM file over several lines, goes in the file inside single quotes with the closing quote straight after its last line. `fly secrets import` is not used, because it strips a pair of quotes from around a value. `--stage` means a secret takes effect at the next deploy of the web app, and on each jobs machine started afterwards. A secret already set is left alone; `--replace` sends it again.

Register each sign-in provider with the redirect address `https://openantiquity.org/api/v1/auth/oauth/<provider>/callback`, where `<provider>` is `google`, `microsoft`, `apple`, `facebook` or `osm`.

### 5. The first deploy

From the repository root:

```
fly deploy --no-public-ips --flycast --image-label "$(git rev-parse HEAD)"
fly scale count 3 --region lhr --app openantiquity
```

`fly deploy` reads `fly.toml`, builds the image on Fly's builder (`--remote-only` is the default), pushes it as `registry.fly.io/openantiquity:<commit>`, runs the release command `fieldclub-release` on a machine of its own and then starts the service ([`fly deploy`](https://docs.fly.io/flyctl/deploy/), [`[deploy]`](https://docs.fly.io/reference/configuration)). The schema command creates the extensions, the tables and the extras, and is safe to run again. Until the first release there is no migration history (`docs/ARCHITECTURE.md`, Conventions), so a change to an existing table needs the database rebuilt or Alembic, which starts at the first public release.

The release command checks the elevation mirror before it creates the schema (`fieldclub-terrain check`, Decision 0027): every tile of the catalogue is in the bucket, and GDAL reads one on a thread of its own, as a map tile is drawn. It needs the web app's key to read the elevation bucket, so finish step 3 first. A fresh setup has no mirror at this step: for its first deploy add `FIELDCLUB_TERRAIN_CHECK_ALLOW_MISSING = "5877"` to `[env]` in `fly.toml`, and take it out once step 8 has filled the mirror.

The first deploy makes two machines (`--ha` is on by default) and `fly scale count` makes the third. One deploy during the spike failed after the image was pushed, with an internal error from Fly's API, and worked when run again. On 2026-11-12 one `fly machine run` was refused with a 408 from the same API, left nothing behind and worked when run again.

The site stays private until step 11, which waits on the security review (`docs/plans/v1-england.md`, WS9). `--no-public-ips` allocates no public address, and `--flycast` gives the app a private one, `openantiquity.flycast`, which goes through Fly's proxy and so wakes a suspended machine ([Flycast](https://docs.fly.io/networking/flycast/)). The deploy workflow passes `--no-public-ips` too, so no deploy opens the site by itself. Check it answers, through a WireGuard tunnel to the Flycast address, with the `curl` in a second terminal:

```
fly proxy 8443:443 openantiquity.flycast --app openantiquity
curl --fail --resolve openantiquity.fly.dev:8443:127.0.0.1 https://openantiquity.fly.dev:8443/healthz
```

Plain HTTP on port 80 is answered 301 to https, because of `force_https`, so the check goes to port 443 under the app's `fly.dev` name, whose certificate Fly's proxy already holds. `fly checks list --app openantiquity` shows what each machine's own health check last answered.

The same tunnel wakes a suspended machine before `fly ssh console`, which needs one running.

### 6. The tile cache's expiry rule

Tiles in `openantiquity-cache` are deleted 180 days after they were written, the rule the Google bucket had. A tile's key carries its style and data version, so a tile not rewritten for half a year is almost certainly one nobody asks for. Tigris takes an expiry by prefix through the S3 lifecycle interface, up to ten rules a bucket ([object lifecycle rules](https://www.tigrisdata.com/docs/buckets/object-lifecycle-rules/)). The script runs on a web machine, which holds the cache bucket's key:

```
fly ssh console --app openantiquity -C "python /app/jobs/cache_lifecycle.py"
```

It replaces the bucket's whole lifecycle configuration, so it is safe to run again, and prints the rule read back. `--check` only reads it. A suspended machine needs waking first, through the tunnel in step 5.

### 7. The jobs app's image and the elevation's sources rows

```
uv run infra/fly_jobs.py build
uv run infra/fly_jobs.py sources
```

`build` builds the commit at `HEAD` with `fly.toml`'s Dockerfile and pushes it to the jobs app's own repository as `registry.fly.io/openantiquity-jobs:<commit>` (`fly deploy --build-only --push --app openantiquity-jobs --image-label <commit>`). It refuses a checkout with uncommitted changes, or one that isn't the commit named, because the image is labelled with it. The deploy token GitHub holds belongs to the web app, so it can push the web app's images but not these, and can't choose the code that runs beside Defra's login.

The LIDAR `sources` rows must exist before any elevation is stored or shown. The copy and the overview build leave them to this job (`--skip-sources`). It is safe to run again.

`fly_jobs.py` runs the jobs app's image of the commit at `HEAD`. `--commit <sha>` names another and `--image <reference>` gives a whole one. `--dry-run` prints the fly command without running it. Each one-off job is `fly machine run` with `--rm` and `--restart no`: it runs once, exits and is removed, and is never restarted, so a failed one is seen in `fly logs --app openantiquity-jobs` and run again by hand. Each runs under `timeout`, with the Cloud Run job's limit where there was one: 15 minutes for `sources`, 6 hours for an ingest, the overview build and the hourly machine, 5 hours a share for the copy, and an hour for anything else. A job that hangs is stopped and its machine removed.

### 8. England's elevation in the bucket

The converted elevation in Google's bucket was copied across on 2026-11-12 (Decision 0018, point 8): 5,877 tiles, 126.4 GB, each checked against Google's by size and MD5. Defra's server wasn't asked for the country a second time. How it was done is in [Copying the elevation from Google](#copying-the-elevation-from-google). The Fly copy below is for a tile that goes missing, or for a fresh start if the bucket is lost.

```
uv run infra/fly_jobs.py mirror 1 3
uv run infra/fly_jobs.py mirror 2 4
```

The 5,877 tiles are split into four shares of about 88 GB each, by size. Each command starts one machine that runs its two shares one after the other, each with one SFTP connection, so the two machines hold two connections to Defra's server at once, as the Google job did. A share that stops, because the supply refused the login, showed another host key or failed five tiles in a row, stops its machine, and the machine's last log lines name the share. Run a failed share again by naming it, for example `uv run infra/fly_jobs.py mirror 3`. A tile already in the mirror is skipped, so a rerun fetches only what is still missing. The spike held two connections to Defra's server at once from a Fly machine in London, but no share of the copy has run there: start with one machine and watch its log before starting the second.

The web app adds nothing to the mirror, because it holds neither Defra's login nor a key that writes the elevation bucket (`FIELDCLUB_TERRAIN_API_FETCH=false` in `fly.toml`). A map tile that needs a tile not yet mirrored is answered 503 `elevation_unavailable` for a minute at a time, logged as a warning, until a copy adds it.

Progress is what `fieldclub-terrain info` reports:

```
uv run infra/fly_jobs.py run fieldclub-terrain info
fly logs --app openantiquity-jobs
```

### 9. Build the national overview

```
uv run infra/fly_jobs.py national
```

It runs `fieldclub-terrain national build --skip-sources` on a `performance-8x` machine, the size Fly lists with 16 GB, with a 20 GB root file system (`--rootfs-size`). The build mosaics the 8 m copies inside the mirrored tiles into one cloud-optimised file under `england/national/`, uploads it and points `england/national/national.json` at it (Decision 0012). The service reads `national.json`, so nothing needs deploying afterwards. Its work folder, about 8 GB for all of England, is on the machine's disk here, where on Cloud Run it was in memory. Run it again whenever tiles have been added. It exits 0 when the overview is current and 1 on an error. On 2026-11-12 it built all of England from the 5,877 tiles in 13 minutes, a file of 3.08 GB.

### 10. The first ingests and the hourly machine

```
uv run infra/fly_jobs.py run fieldclub-ingest list
uv run infra/fly_jobs.py ingest he-nhle-scheduled-monuments
```

Then make the volume and the hourly machine. A second `fly volumes create` would make a second volume with the same name, billed as well, so look first and create it only if `jobs_var` isn't listed:

```
fly volumes list --app openantiquity-jobs
fly volumes create jobs_var --app openantiquity-jobs --region lhr --size 10 --yes
uv run infra/fly_jobs.py schedule
```

Fly gives a new volume's mount point to the image's user, so the jobs can write `/data` without being root. 10 GB is a guess: nothing measured the bulk sources' downloads together, and nothing prunes `var/ingest/` on the volume, as Google's 90-day rule on `ingest/` did. Watch its use with `fly volumes list` and extend it with `fly volumes extend` if it fills.

`schedule` makes a machine named `due` with `--schedule hourly`, the volume mounted at `/data` and `FIELDCLUB_VAR_DIR=/data/var`, running `fieldclub-jobs due`. Fly starts it once an hour at a time of its own choosing in the hour. `fieldclub-jobs due` first deletes expired sessions, and sign-in links spent or expired over a day ago, as the privacy notice says happens. It then decides from the database and the clock what is due (`backend/src/fieldclub/jobs/due.py`): the channel scan when some channel is watched and none has been checked for five hours, which keeps scans about six hours apart, and the source refresh when the hour is 03 UTC. The refresh runs every enabled bulk connector and reference loader whose last full run is older than its `max_age`, so it covers every bulk source, and a second start in the same hour finds them current. Ingest downloads stay on the volume, so the next run can ask the publisher whether a file changed. An ingest started by hand in step 10 downloads afresh, because the volume belongs to the hourly machine.

Fly's schedules run hourly, daily, weekly or monthly, at no fixed time ([`fly machine run --schedule`](https://docs.fly.io/flyctl/machine-run/)). One hourly machine that asks what is due needs nothing left running between starts.

### 11. Opening the site: point the domain

Done on 2026-11-12, at the owner's word. The app's addresses are the shared IPv4 address 66.241.124.216 and the IPv6 address 2a09:8280:1::1fe:8e38:0, and the six certificates were issued within three minutes of the records changing. The site is `openantiquity.org`. `www.openantiquity.org`, `openantiquity.com`, `openantiquity.co.uk` and their `www` names are answered by the application with a 308 to the same path on `openantiquity.org` (`FIELDCLUB_REDIRECT_HOSTS` in `fly.toml`, `backend/src/fieldclub/redirects.py`). Fly's proxy has no redirect setting of its own, so the application does it. `force_https` sends plain HTTP to HTTPS first, so every name needs a certificate: six, inside the ten free ones.

```
fly ips allocate-v4 --shared --app openantiquity
fly ips allocate-v6 --app openantiquity
fly ips list --app openantiquity
for name in openantiquity.org www.openantiquity.org openantiquity.com www.openantiquity.com \
            openantiquity.co.uk www.openantiquity.co.uk; do
  fly certs add "$name" --app openantiquity
done
```

An apex name can't be a CNAME, so each domain's `@` gets an `A` record for the shared IPv4 address and an `AAAA` record for the IPv6 address, and each `www` a `CNAME` to `openantiquity.fly.dev.` ([custom domains](https://docs.fly.io/networking/custom-domain/)). The `AAAA` record is also one of the ways Fly checks that the domain is ours before it issues a certificate. `infra/dns.toml` holds these records, with the two addresses `fly ips list` printed. To change them:

```
uv run infra/dns.py plan
uv run infra/dns.py apply
fly certs check openantiquity.org --app openantiquity
```

`infra/dns.py` touches only what `dns.toml` lists, so Gandi's mail records stay as they are. Its token is `GANDI_DNS_SSL` in `.env`. The `CAA` records already allow Let's Encrypt, which Fly uses. A certificate is issued once its records resolve, which can take an hour. The records Gandi made at registration had a time to live of three hours, so some resolvers kept sending visitors to Gandi's parking page that long after the change.

Every answer over https carries `Strict-Transport-Security` with `includeSubDomains`, the redirects from the other names included, so a browser that has visited `openantiquity.com` or `openantiquity.co.uk` will use https for every name under them for a year. Never put anything that serves plain http, such as a mail provider's link-tracking name, under any of the three domains.

### 12. The deploy workflow

In the repository's Settings, Environments, make an environment named `production` with deployment branches limited to `main`. Then make a deploy token for the web app alone and put it there, without it passing through the terminal:

```
fly tokens create deploy --app openantiquity --name github-deploy --expiry 2160h |
  gh secret set FLY_API_TOKEN --env production
```

A deploy token is limited to one app ([access tokens](https://docs.fly.io/security/tokens/)). The token above lasts 90 days; renew it the same way. `fly tokens list` and `fly tokens revoke <id>` take one away. GitHub never holds a token for the jobs app, and the jobs app runs only images the owner built (step 7), so neither Defra's login nor the code that runs beside it is in GitHub's reach.

## A deploy

1. Merge to `main`. CI runs both check suites, the docs lint, the scripts' tests and shellcheck, the Terraform checks while it stays, and an image build that is started and stopped as a Fly machine would be.
2. In GitHub, Actions, "Deploy", run the workflow on `main`. It runs `flyctl deploy --remote-only --no-public-ips --image-label <commit>`, which builds the image, runs the release command once and moves the three machines onto the new image one at a time (`strategy = "rolling"`). The release command checks the elevation mirror, then creates what the schema lacks.
3. Build the jobs app's image of the same commit and move the hourly machine to it, from a clean checkout of that commit, with the commands the run's summary prints:

   ```
   uv run infra/fly_jobs.py --commit <commit> build
   uv run infra/fly_jobs.py --commit <commit> schedule
   ```

   `schedule` updates the machine named `due` in place (`fly machine update --image`, [flags](https://docs.fly.io/flyctl/machine-update/)) and then starts it once, which runs whatever is due and stops. The start is there because on 2026-11-12 the machine wasn't started by its schedule after an update until it had been started by hand. If the schedule starts `due` between the two steps, the start fails after a good update: run `schedule` again once it has stopped. It refuses while `due` is running, because updating a started machine stops it; run it again once `fly machine list --app openantiquity-jobs` shows it stopped. The update keeps the machine's command and time limit; to change those, destroy `due` and run `schedule` again. Until it is run, the hourly jobs run the image before, which still works against the schema, because the schema command only adds what is missing.

If the mirror check fails, the deploy stops before anything is replaced, and the release machine's log says which tiles are missing or why one couldn't be read (`fly logs --app openantiquity`). Add missing tiles with `uv run infra/fly_jobs.py mirror 1 2 3 4`, which fetches only what the bucket lacks, and deploy again. To deploy knowing tiles are missing, set `FIELDCLUB_TERRAIN_CHECK_ALLOW_MISSING` in `fly.toml` to their number. To deploy with no check at all, as when Tigris can't be listed, set `release_command` back to `python -m fieldclub.db` for that deploy.

A deploy leaves the three machines stopped, not suspended, and the first request afterwards waits for one to start from cold: 32 seconds on 2026-11-12, of which Fly's start is about 20. Ask for `/healthz` once after a deploy. A machine started that way is suspended when it next idles, and then answers in under a second.

A deploy by hand is the same command as the workflow's, from the repository root: `fly deploy --no-public-ips --image-label "$(git rev-parse HEAD)"`.

The schema command waits at most five seconds for a lock on any table (`SCHEMA_LOCK_TIMEOUT_MS` in `backend/src/fieldclub/db.py`). If something holds a table longer, the release fails, the schema is as it was and the machines keep their image: deploy again.

While the machines are swapped, one still on the image before serves requests against the new schema. It reads past an activity kind or a next step the new image added (Decision 0033), but what it writes doesn't fill columns the new image added. Deploy a release that adds columns when nobody is marking or answering.

The release that first brings lines and shapes has one more step. Once `fly status --app openantiquity` shows every machine on the new image, and the jobs app's image of the same commit is built, run the backfill:

```
uv run infra/fly_jobs.py run python -m fieldclub.services.shapes backfill
```

It fills the simplified copies, the kind and the length of every outline saved before paths existed, and the ground second looks were given on for every finding answered before that was kept. It logs how many of each it filled, and is safe to run again. Run it after the swap and not before, so that nothing an earlier machine wrote meanwhile is missed.

Fly sends the old machine `SIGTERM` (`kill_signal`) and kills it ten seconds later (`kill_timeout`). The server ends its event streams at once and closes whatever else it still holds after five seconds (`FIELDCLUB_SHUTDOWN_GRACE_S`), so it stops before it is killed, and the browser opens a new stream on another machine.

## Rolling back

Deploy the image before, which needs no build:

```
fly releases --app openantiquity --image
fly deploy --no-public-ips --image registry.fly.io/openantiquity:<previous commit>
uv run infra/fly_jobs.py --commit <previous commit> schedule
```

The jobs app's image of that commit is still in its repository if `build` ran for it; otherwise check the commit out and run `build` first. The image has to hold the release command that `fly.toml` names. Images built before `fieldclub-release` was added on 2026-11-12, `85ad12a` among them, don't: deploy one of those from a checkout of its own commit. A schema change can't be rolled back this way. The schema command only adds what is missing, so an older image runs against a newer schema as long as nothing it uses was removed. The older image also meets the rows the newer one stored. An image built on or after 13 November 2026 passes over an activity kind or a next step it has no name for (Decision 0033). An image older than that answers 500 wherever it meets one, so don't go back past that date once a later version has added either. An image built on or after 13 November 2026 from a commit that holds Decision 0035 also reads a feature class it has no name for as "Not sure". An image built before it answers 500 wherever it meets one, so don't go back past it once a later version has added a class.

Managed Postgres keeps backups. `fly mpg backup list` lists them and `fly mpg restore <cluster-id> --backup-id <id>`, or `--pitr-time <RFC 3339 time>`, restores one into a new cluster ([`fly mpg restore`](https://docs.fly.io/flyctl/mpg-restore/)). The original is left alone. Attach the new cluster to both apps and deploy. The spike's cluster took one every hour without being asked: a full backup a day, a differential every six hours and incrementals between. How long Fly keeps them wasn't found, and no restore has been tried; check both before relying on them.

## What to watch

- **The month's spend.** Fly has no billing alert and no spending cap (see [Spend](#spend)). Look at the dashboard's current month to date bill once a week.
- **The web app's machines.** `fly status --app openantiquity` and the dashboard's metrics: memory, CPU and how often machines are running. A machine that stays running with few requests is held by open event streams. Steady CPU at the shared baseline means Fly is throttling it (see [Sizing](#sizing)).
- **The database.** The cluster's page in the dashboard: CPU, memory, disk and connections. The Basic plan allows 112 connections.
- **The jobs.** `fly logs --app openantiquity-jobs`. Every job logs a one-line summary and exits non-zero when anything failed. Check the hourly machine's last runs after each deploy.
- **The mirror.** `/api/v1/meta` gives `catalogue_tiles` and `mirrored_tiles`, which should be equal. A web machine logs `The mirror lacks` at `ERROR`, with the number and the names, when they aren't.
- **The tile cache's rule.** `fly ssh console --app openantiquity -C "python /app/jobs/cache_lifecycle.py --check"` exits 1 if the rule has gone.
- **Errors.** `fly logs --app openantiquity`, for lines at `ERROR`.

## Spend

Decision 0018, point 9, says the deployment supplies its own check of the month's spend. It doesn't yet: what is here is a weekly look and limits, which the owner has to accept in a decision that supersedes point 9, or replace with a check.

Fly can't be asked what the month has cost, as far as its documentation says. Its cost page says "We don't support billing alerts (yet)" and "there's no soft ceiling. If you go over, we'll bill you", and the only place it names for the month so far is the dashboard's "current month to date bill" ([cost management](https://docs.fly.io/about/cost-management/)). Its billing page describes no API or command for usage either ([billing](https://docs.fly.io/about/billing)). Whether Fly's GraphQL API exposes the current invoice wasn't looked into. Prepaid credit is no cap: the billing page says usage "is subtracted from the credit balance each month" and says nothing of what happens when the credit runs out.

- **The check.** Once a week, read the current month to date bill in the dashboard's Billing section for the organisation. The alert on Google was £75 a month, about $95 to $100, which is 1.3 to 1.6 times the expected bill at light use below, so a bill on course to pass £75 means something has changed.
- **Machines.** Fly's proxy starts and suspends machines but never creates one ([autostop and autostart](https://docs.fly.io/launch/autostop-autostart/)). The web app has three, so at most three run: $40.17 a month if all three ran all month, at US east prices. A fourth exists only if someone runs `fly scale count`.
- **Machine sizes.** `fly.toml` fixes the web machines at `shared-cpu-2x`, 2 GB, and `test_fly_config.py` fails if the memory changes. `fly_jobs.py` fixes each job's size.
- **How long a job runs.** Every job but the hourly one is started by a person, and every job, the hourly one included, runs under `timeout` (step 7). The dearest, the overview build on `performance-8x`, at about $0.37 an hour, stops after 6 hours, about $2.20.
- **What isn't bounded.** Data sent to visitors at $0.02 a GB, Tigris storage and requests, and the database's disk, which grows by itself. Those three are what the weekly check is for. A multipart upload of the overview that fails part way leaves its parts in the bucket, billed as storage until they are removed, and Tigris's lifecycle rules list no way to expire them.

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

Concurrency counts requests (`type = "requests"`): past the soft limit of 20 the proxy prefers another machine and starts it if it is suspended, and it never sends one machine more than the hard limit of 30 ([configuration](https://docs.fly.io/reference/configuration)). Most requests wait rather than compute: cached tiles, JSON, and open event streams that each hold one. An event stream ends itself after 540 s (`FIELDCLUB_EVENTS_MAX_STREAM_S`); the spike held one open through the proxy for 600 s. A machine takes at most 26 streams (`FIELDCLUB_EVENTS_MAX_STREAMS`, the hard limit less four), so tiles and JSON always have four slots, and at most 6 from one address (`FIELDCLUB_EVENTS_MAX_PER_ADDRESS`, a quarter of 26 rounded down, the most the application allows); a stream refused with `too_many_streams` makes the web client poll instead. Every tile being drawn or waiting holds a slot as well. The four tile workers and a queue of 16 (`FIELDCLUB_TERRAIN_RENDER_QUEUE`) make 20, the soft limit, so one screen of tiles fits, and a larger burst is answered `tiles_busy` before it takes the ten slots above the soft limit. Three machines of 30 are 90 requests at once, about 78 open tabs. Raise the count before that, minding the database connections below.

Each machine holds up to 8 database connections, so 24 at most, and the jobs up to 4 each. The Basic plan's `max_connections` is 112, and sixty from one machine were all accepted during the spike.

Fly's proxy suspends a machine after the app has been idle for several minutes and stops at most one machine per region on each pass ([autostop and autostart](https://docs.fly.io/launch/autostop-autostart/)). An open event stream kept the spike's machine running, so a machine runs for as long as anyone has the page open.

### The database: Managed Postgres Basic

The Basic plan is $38 a month plus $0.28 a GB ([pricing](https://docs.fly.io/about/pricing)). The development database holds 20,006 scheduled monuments in 137 MB, 6.8 KB a record, the heaviest kind. Most of the ten million records expected are points, so the estimate is 2 to 3 KB each, 20 to 30 GB in all, and up to 70 GB if every record were like a scheduled monument. The cluster starts at 10 GB and grows by itself. The Basic plan has 2 shared vCPUs and 1 GB of memory ([Managed Postgres](https://docs.fly.io/mpg/create-and-connect/)), so searches over ten million records will read most of their indexes from disk, which is fast enough for a few people at once. A larger plan is the first change if search slows.

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

The converted mirror is a little over a third of the source: 126.4 GB for 353.6 GB of source files. SU16nw went from 48 MB to 24 MB.

## Copying the elevation from Google

Done on 2026-11-12. Google's copy, `gs://fieldclub-uk-elevation/england/mirror/`, held 5,877 `.tif` files and nothing else: no locks and no national overview. [rclone](https://rclone.org/) copied them to `openantiquity-elevation/england/mirror/` from a machine in the jobs app, so the bytes went from Google to Fly's London region to Tigris and never through a laptop. The copy took 12.5 minutes at about 160 MiB a second on a `performance-2x` machine. `rclone check` then found 5,877 matching files and no differences, by size and MD5, and each bucket holds 126,358,266,985 bytes.

To repeat it while the Google project exists:

1. Do it before step 4 gives the jobs app Defra's login, or in an app of its own. The machine runs rclone's published image, not ours, and a machine sees every secret of the app it runs in.
2. Make a Google service account that can only read the bucket, with `roles/storage.objectViewer` on it, and an HMAC key for that account. Google's bucket answers the S3 interface to an HMAC key, so rclone needs no Google login. Hand the key's two halves to the jobs app as the secrets `RCLONE_CONFIG_GOOGLE_ACCESS_KEY_ID` and `RCLONE_CONFIG_GOOGLE_SECRET_ACCESS_KEY`, each on standard input with `fly secrets set NAME=- --stage`, so neither is typed or shown.
3. Copy, as a machine that exits and is removed. rclone takes its settings from the environment, and its Tigris key is the one the app already holds:

   ```
   fly machine run rclone/rclone@sha256:5a25abdcf2f2f093a03e1e6a13caddeb5fae3cd07ae6c699768e6f1917a5d3ce \
     --app openantiquity-jobs --region lhr --rm --restart no --vm-size performance-2x \
     -e RCLONE_CONFIG_GOOGLE_TYPE=s3 -e RCLONE_CONFIG_GOOGLE_PROVIDER=GCS \
     -e RCLONE_CONFIG_GOOGLE_ENDPOINT=https://storage.googleapis.com \
     -e RCLONE_CONFIG_TIGRIS_TYPE=s3 -e RCLONE_CONFIG_TIGRIS_PROVIDER=Other -e RCLONE_CONFIG_TIGRIS_ENV_AUTH=true \
     -e RCLONE_CONFIG_TIGRIS_ENDPOINT=https://fly.storage.tigris.dev -e RCLONE_CONFIG_TIGRIS_REGION=auto \
     -- copy google:fieldclub-uk-elevation/england tigris:openantiquity-elevation/england \
     --exclude "mirror/locks/**" --checksum --transfers 16 --checkers 16 --s3-no-check-bucket \
     --stats 60s --stats-one-line --stats-log-level NOTICE
   ```

   The image is rclone 1.75.2, published on 2026-10-09 and named by its digest. `fly logs --app openantiquity-jobs` shows a line of progress a minute.
4. Check, with the same command but `check` in place of `copy`, and after the two folders only `--exclude "mirror/locks/**" --checkers 16`. Its last log lines give the number of matching files and of differences.
5. Unset the two secrets, delete the HMAC key and the service account, and take the account off the bucket's permissions.

All five were done on 2026-11-12, and nothing of the temporary key is left on either side.

Google charges $0.12 a GB for data leaving its network, so the 126.4 GB cost about $15. Writing to Tigris was about 6,000 Class A requests, $0.03. Google's bucket holds no national overview, so step 9 builds it on Fly.

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
| Tigris storage, 126 GB of elevation and 6 GB of tiles and photos, 5 GB free | $0.02 a GB-month | $2.54 | $2.54 |
| Tigris writes, 225,000, 10,000 free | $0.005 a thousand | $0 | $1.08 |
| Tigris reads, about 2.5 million, 100,000 free | $0.0005 a thousand | $0 | $1.20 |
| Data out to visitors, 68 GB | $0.02 a GB | $0 | $1.36 |
| Shared IPv4, IPv6, six certificates | Free, the first ten certificates | $0 | $0 |
| Image builder and registry | Free today, which the page says may change | $0 | $0 |
| **Total** | | **about $51 to $62** | **about $62 to $73** |

At rest this is more than Google's estimate of $36 to $46, because Managed Postgres costs more than `db-g1-small`; Decision 0018 expected the two to cost about the same at rest. The saving is in traffic: at a thousand visits a day, the 675 GB a month the Google runbook assumed costs $13.50 here against $81 there, and there is no load balancer for the domain.

One-off costs: the national overview build on `performance-8x`, which the pricing page didn't list; at the listed $66 a month for `performance-2x`, four times that is about $0.37 an hour, so the 13 minutes the build took cost about $0.08. Copying the elevation from Google cost about $15 in Google's transfer fee.

What these figures leave out:

- London's machine prices.
- Data from the machines to Tigris, which Fly's pricing page says is billed separately, at a rate it didn't give. The copy on 2026-11-12 sent 126 GB that way, so November's invoice will show the rate.
- Whether the database's storage is billed once or for each node's copy. Fly's Managed Postgres page says storage is billed on usage and replicated across the cluster's nodes. The spike's cluster, made with the default 10 GB, reported 2.3 GB used, 20 GB allocated and one replica.
- Managed Postgres backups, if they are charged.
- A real traffic pattern. The light-use row is a guess with its working shown.

## Google Cloud until the cut-over

The Google deployment in `terraform/` stays as it is, held back from the public (`service_public = false`), until the site on Fly has passed its checks (Decision 0018, point 10). Its full runbook is `git show 28488dd:infra/README.md`. Its Terraform, `bootstrap.sh` and `add-defra-secrets.sh` are kept unchanged until the project is taken down, and CI still checks the Terraform.

An image built from main can't run there any more: the application now speaks only S3, and `terraform/settings.tf` sets `FIELDCLUB_STORAGE_BACKEND=gcs` and `gs://` terrain folders, which the settings refuse. Google keeps running the image it has. Don't apply a new `image_tag` there.

### Taking the Google project down

Once the site on Fly answers on openantiquity.org, the elevation is in Tigris and checked, and the first ingests have run:

- [x] `rclone check` reports no missing files. Done on 2026-11-12: 5,877 matching files and no differences.
- [ ] Copy out anything else wanted. The Google database holds what ingests make again, and whatever the owner did while trying the held-back site.
- [ ] In `terraform/storage.tf`, remove the `prevent_destroy` line from the elevation bucket.
- [ ] From `infra/terraform`, with `terraform.tfvars` as it was applied: `terraform destroy`. It removes the service, the jobs, the schedules, the database, the buckets, the secrets, the service accounts, the federation and the budget.
- [ ] Delete the state bucket `gs://$P-tfstate`, then shut the project down: `gcloud projects delete "$P"`.
- [ ] In GitHub, remove the repository variables `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SERVICE_ACCOUNT` and `TFVARS`.
- [ ] Remove `pki.goog` from the `CAA` records in `dns.toml` and apply.
- [ ] Remove `terraform/`, `bootstrap.sh`, `add-defra-secrets.sh` and its test, and the Terraform step in `ci.yml`, in one commit, and update this file and `docs/ARCHITECTURE.md`.

## What can only be checked on the real platform

Each of these was written from documentation or inferred, and none was run:

- Checked against flyctl 0.5.7 and the spike's app on 2026-11-12, so no longer open: the flags of `fly deploy`, `fly machine run`, `fly machine update`, `fly mpg create`, `fly mpg attach`, `fly mpg databases extensions enable` and `fly storage create`; the field names `name` in `fly secrets list --json` and `id`, `name` and `state` in `fly machine list --json`; how `fly secrets set NAME=-` treats a value; that `fly ssh console -C` runs with the app's secrets in its environment; and that Defra's server accepts two connections at once from a Fly machine in London, reading at 17 to 22 MiB a second each.
- Checked on the jobs app on 2026-11-12, during the copy from Google, so no longer open: `fly machine run` passes the flags after `--` to the command; a machine started with `--rm` and `--restart no` is removed when its command exits; a secret set with `--stage` is in the environment of the next machine started; and the key `fly storage create` made for the jobs app lists, writes and reads `openantiquity-elevation`.
- Checked on 2026-11-12 while steps 2 to 7 were carried out, so no longer open: the release command's machine gets `[env]` and the secrets, and connects to the database's direct address; `fly deploy --build-only --push --app openantiquity-jobs --image-label <commit>` pushes to `registry.fly.io/openantiquity-jobs:<commit>` and starts nothing; a job under `timeout` and `tini` exits and its machine is removed when the job ends by itself; the jobs start without a session key; Tigris accepts boto3's lifecycle request and gives the rule back; and Tigris takes the national overview, 3.08 GB, as a multipart upload.
- Found on the web app on 2026-11-12 and fixed: no terrain tile drew, though the mirror's listing was whole. GDAL had the Tigris endpoint only on the thread that set it, and tiles are drawn on others. The release command now reads a tile that way before every deploy.
- Checked on 2026-11-12 with the fix deployed: the release command's mirror check passes and stops nothing when the mirror is whole; terrain tiles draw from the mirror in Tigris, a tile over a fresh area in about 4 seconds, a cached one in 0.4, and an overview tile in about 4; health checks don't keep idle machines awake; the hourly machine is made with its volume, runs `fieldclub-jobs due` and stops; and `fly deploy` without `--flycast` keeps the private address, though it prints that the app has none.
- Checked on 2026-11-12 when the domains were pointed: the six certificates, the shared IPv4 address at each apex, and the 308 from each of the five other names to the same path on `openantiquity.org`.
- Checked on 2026-11-12 after step 11: a later `fly deploy --no-public-ips` leaves the public addresses alone, though it still prints that the app has none; OpenStreetMap sign-in starts and OpenStreetMap accepts the application and its redirect address; and each Tigris key reaches only what step 3 gives it, tried from a machine of each app.
- Checked on 2026-11-12 at the second deploy of the day: `uv run infra/fly_jobs.py schedule` moves the hourly machine to a new image in place, with `fly machine update`, and keeps its volume and its command. That update left the machine stopped, and its settings still said hourly, but it then missed the runs of 22:41 and 23:41. It ran on the hour again, at 00:41 on 2026-11-13, once it had been started by hand at 00:14, so `schedule` now starts it after updating it. Also checked that day: Google sign-in starts, and Google accepts the application and its redirect address.
- Found on the jobs app on 2026-11-13, at the first nightly refresh, and fixed: the two sources whose runs take over an hour, 87 and 62 minutes, read every record and then failed at their last step, because the connection holding each run's lock had been closed. It had carried no statement since the lock was taken. A test on a jobs machine the same morning held two connections to the database's direct address for 78 minutes, both with the TCP settings of `db.KEEPALIVES`: the one asked `SELECT 1` every minute answered throughout, and the one left alone was closed. The lock's connection of a run of 30 minutes survived, so the limit is between 30 and 62 minutes without a statement. PostgreSQL's own `idle_session_timeout` is 0 on the cluster, and what closes the connection wasn't found. A run now uses its lock's connection once a minute while records flow (`runner.LOCK_CHECK_EVERY_S`), and stops at the next record once the lock has gone. Not covered: a source that goes that long without giving a record, whose run then stops at its next one with `IngestLockLostError`. The web app holds no connection that long unused: the pool replaces a connection after 30 minutes and tries each before use, and the event listener asks `SELECT 1` while it waits.
- Still to run for the first time: `fly releases --image`.
- That the web app's deploy token can't push to the jobs app's repository.
- That `timeout` from the image's coreutils stops a job that runs past its limit, and the machine then exits and is removed. `tini` warns on every start that it isn't process 1, because Fly's own init is.
- That the key `fly storage create` makes reaches no bucket but its own, and that a key given roles on three buckets reaches all three with one secret.
- That `--file-secret` writes the host key where the SFTP client reads it, readable by the image's user.
- That the database's `LISTEN` connection is found dead and replaced after a resume (the spike didn't test it).
- Whether Tigris answers 409 to overlapping conditional writes and `NoSuchBucket` for a misnamed bucket, as AWS does. The code takes any 412 or 409, and a 404 only with the code `NoSuchKey`, as a refusal.
- The flyctl the workflow pins, 0.5.8, was published on 2026-11-11 and its `setup-flyctl` commit was read through a summariser; check both against GitHub and prefer a release at least two weeks old.
- Memory during a photo upload while tiles render, and tile latency under a real screen of tiles at once.
- London's prices, and what Fly does when prepaid credit runs out.
