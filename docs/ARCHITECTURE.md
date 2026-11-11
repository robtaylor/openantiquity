# Architecture

This is the build contract. `docs/DESIGN.md` says what the product does and why. This file says how the code is laid out, what the tables are, and what the API looks like. If code and this file disagree, fix one of them in the same change.

The product is called "Field Club". The Python package, database and cookie prefix are all `fieldclub`.

## Stack

| Part | Choice |
|------|--------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (sync) on psycopg 3, GeoAlchemy2, Pydantic 2 |
| Database | PostgreSQL 17 with PostGIS 3.5, `pg_trgm`, `citext` |
| Terrain | numpy, scipy, rasterio. Tiles are rendered on demand and cached |
| Frontend | TypeScript (strict), React 19, Vite, MapLibre GL JS 6, TanStack Query, Zustand |
| Tests | pytest against a real PostGIS, Vitest, Playwright for end-to-end |
| Deploy | One container on Cloud Run, Cloud SQL, Cloud Storage. Terraform in `infra/terraform` |

Endpoints are plain `def` functions. FastAPI runs them in its thread pool, which suits a workload of SQL, upstream HTTP and numpy. Only the event stream is `async`. See Decision 0001 in `docs/architecture/decisions/`.

## Layout

```
backend/
  pyproject.toml            uv project, ruff and pyright config, pytest config
  src/fieldclub/
    config.py               Settings (pydantic-settings, env prefix FIELDCLUB_)
    db.py                   engine, SessionLocal, get_db dependency, Base
    errors.py               AppError hierarchy and the JSON error handler
    main.py                 create_app(): routers auto-registered from fieldclub.api, the middleware
    vocab.py                feature classes, periods, evidence kinds, tiers, checks
    layers.py               map layer catalogue served by /meta
    storage.py              Storage protocol, LocalStorage, GcsStorage
    ratelimit.py            in-memory token buckets as FastAPI dependencies
    safe_fetch.py           fetching an address someone else chose, guarded against request forgery
    gridref.py              OSGB and Irish grid conversion and parsing
    data/                   live-source and deep-link catalogues, generated from docs/sources/worklists
    models/                 one file per domain, all imported by models/__init__.py
    schemas/                Pydantic request and response models, one file per domain
    api/                    one router module per domain, each exposes `router`
    services/               business logic with no FastAPI imports
    auth/                   sessions, the welcome step, magic links, OAuth
    terrain/                elevation sources, visualisations, tile rendering, cache
    ingest/                 connector base, registry, runner, CLI, adapters/, connectors/, reference/ (gazetteer and boundary loaders)
    jobs/                   scheduled work (channel scan, source refresh)
  tests/                    mirrors src layout; conftest.py owns the database fixtures, test_routes.py lists every route
frontend/
  src/
    api/                    typed client generated from the OpenAPI schema
    map/                    MapLibre setup, layer control, compare, terrain controls
    features/               findings, review, squares, records, investigations, account
    ui/                     shared components and design tokens
infra/
  README.md                 the deployment runbook, with sizing and cost
  docker-compose.yml        local PostGIS on port 54329
  Dockerfile                multi-stage build: frontend, then backend serving it; one image for the service and every job
  bootstrap.sh              makes a project's Terraform state bucket
  jobs/                     deployment glue run inside the image, such as the sharded elevation copy
  terraform/                Cloud Run, Cloud SQL, buckets, secrets, scheduler
.github/workflows/          ci.yml on pushes to main and pull requests; deploy.yml by hand builds, pushes and plans
docs/
  DESIGN.md  ARCHITECTURE.md  UI.md  prose-style.md
  architecture/             area docs, and decision records in decisions/
  sources/                  the source catalogue and its work-lists
  plans/  handoffs/
```

## Conventions

- Database access goes through SQLAlchemy sessions from `get_db`. Write explicit `select()` statements. Don't rely on lazy-loaded relationships.
- Services take a `Session` and plain values, and return models or dataclasses. Routers translate between HTTP and services. Services never import FastAPI.
- Every error raised on purpose is a subclass of `AppError` with a stable `code`. The handler returns `{"error": {"code": ..., "message": ...}}`. An error raised by one module is defined there. An error raised by more than one module lives in `errors.py`, or in its package's own errors module (`terrain/errors.py`, `ingest/errors.py`, `auth/failures.py`), and the module it first lived in imports it back so old imports keep working. A router defines none.
- A response model takes an `Out` suffix only when it would otherwise share a name with a type the code already uses: a model, a service or vocabulary type, another schema, or a library type such as shapely's `Point`. So `RecordOut` and `SourceOut` beside the `Record` and `Source` models, but `LiveSource`, `Location` and `GeoPoint`. A renamed model renames the generated client's type, so `pnpm gen:api` follows it.
- Enumerations are `StrEnum` classes in `vocab.py`, stored as `TEXT`. No native PostgreSQL enums.
- Primary keys are `BIGINT` identity columns. Public URLs use `findings.public_id`, `investigations.public_id` and `users.handle`, never raw ids.
- All geometry is stored in EPSG:4326. Distance queries cast to `geography`. The functional indexes below make those casts indexable.
- Timestamps are `timestamptz` and always UTC.
- Until the first release there's no migration history. `fieldclub.db.create_schema()` builds everything from the models plus `models/extras.sql`. Alembic starts at the first deploy.
- Logging uses the `logging` module. No `print` outside the CLIs.
- Outbound HTTP uses the shared `httpx.Client` from `fieldclub.http`, which sets a timeout and a `User-Agent` naming the project.
- Assert assumptions. A wrong assumption about an upstream payload should fail loudly in ingest, not write bad rows.

## Data model

Columns marked with `*` are required. Every table has `id BIGINT` and `created_at` unless stated.

### People

| Table | Columns |
|-------|---------|
| `users` | `handle*` citext unique, `display_name*`, `email` citext unique, `email_verified_at`, `avatar_url`, `age_band` (16_17, 18_plus), `terms_accepted_at`, `role*` (member, trusted, expert, moderator, admin), `reputation*` float, `bio`, `settings` jsonb, `last_seen_at`, `banned_at`, `deleted_at` |
| `auth_identities` | `user_id*`, `provider*`, `subject*`, `email`, unique on provider and subject |
| `sessions` | `user_id*`, `token_hash*` unique, `expires_at*`, `last_used_at`, `user_agent`, `ip_hash` |
| `magic_links` | `email*`, `token_hash*` unique, `user_id`, `expires_at*`, `used_at`, `browser_hash` |
| `reputation_events` | `user_id*`, `delta*`, `reason*`, `finding_id`. Unique on user, finding and reason, so an award is never paid twice |

### Findings

| Table | Columns |
|-------|---------|
| `findings` | `public_id*` unique, `author_id*`, `title*`, `description`, `feature_class*`, `community_class`, `period*`, `location*` Point, `location_public*` Point, `outline` Geometry, `sensitivity*` (open, protected, restricted), `view_state*` jsonb, `nation`, `grid_ref`, `tier*`, `state*`, `state_reason`, `confidence*` smallint, `assessment*` jsonb, `observation_count*`, `evidence_count*`, `comment_count*`, `mention_count*`, `updated_at*`, `tier_changed_at`, `hidden_at`, `open_steps*` text[] (the next steps' codes, for the help-wanted queue), `answers_to_next` (second looks that would move it up, for the review queue), `client_ref` (the browser's name for the draft it was saved from, never shown; unique per author where set) |
| `observations` | `finding_id*`, `user_id*`, `visible*` (yes, unsure, no), `feature_class`, `period`, `explanation` (modern, natural, artefact), `not_modern` bool, `not_natural` bool, `not_artefact` bool, `note`, `updated_at*`, `withdrawn_at` (taken back: it stops counting, and the row stays so it can't be replaced), `revealed_at` (when the person was shown the answers; empty while the answer waits for its detail). Unique on finding and user |
| `evidence` | `finding_id*`, `user_id*`, `kind*`, `stance*` (supports, neutral, contradicts), `title`, `note`, `url`, `record_id`, `relation` (same_as, part_of, related), `media_id`, `occurred_on` date, `organisation`, `reference`, `outcome` (supports, inconclusive, contradicts), `data` jsonb, `verified_by`, `verified_at`, `deleted_at`, `hidden_at` |
| `evidence_votes` | `evidence_id*`, `user_id*`, `value*` (+1 or -1). Primary key on both |
| `comments` | `finding_id*`, `user_id*`, `body*`, `parent_id`, `edited_at`, `deleted_at`, `hidden_at` |
| `mentions` | `finding_id*`, `user_id`, `kind*` (video, article, podcast, paper, broadcast, social), `url*`, `canonical_url*`, `provider`, `title`, `author_name`, `thumbnail_url`, `published_at`, `start_seconds`, `note`, `auto_detected*`, `match_key*`, `deleted_at`, `hidden_at`. Unique on finding and match key among live mentions and hidden ones, removed or not |
| `follows` | `user_id*`, `finding_id*`. Primary key on both |
| `media` | `user_id*`, `storage_key*` unique, `content_type*`, `width`, `height`, `bytes*`, `sha256*`, `approved_at`, `approved_by`, `rejected_at`, `rejected_by`, `hidden_at`. Never both approved and rejected |

`view_state` records what the finder was looking at: `{layer, zoom, bearing, pitch, sun_azimuth, sun_altitude, exaggeration}`. Opening a finding restores it, so everyone starts from the same picture.

### Records

| Table | Columns |
|-------|---------|
| `sources` | `key*` text primary key, `name*`, `publisher*`, `licence*`, `licence_url`, `attribution*`, `reuse*` (open, share_alike, non_commercial, link_only), `homepage`, `coverage`, `category*`, `access*` (bulk, live, deeplink), `record_count`, `last_ingest_at`, `enabled*` |
| `records` | `source_key*`, `external_id*`, `name*`, `summary`, `category*`, `record_type`, `monument_types` text[], `periods` text[], `geom*` Geometry, `centroid*` Point, `precision_m`, `url`, `raw` jsonb, `source_updated_at`, `ingested_at*`, `search` tsvector generated. Unique on source and external id |
| `ingest_runs` | `source_key*`, `started_at*`, `finished_at`, `status*`, `stats` jsonb, `error` |
| `record_cell_counts` | `level*`, `cx*`, `cy*`, `category*`, `source_key*`, `count*`. Primary key on the first five, no `id`. Records per Web Mercator cell for the low-zoom record tiles, rebuilt per source after every ingest run |
| `places` | `name*`, `kind*`, `district`, `county`, `nation`, `geom*` Point, `rank*`, `source*`. Gazetteer for the search box |
| `admin_areas` | `kind*` (nation, county), `code*`, `name*`, `geom*` MultiPolygon. Unique on kind and code. Used to work out which nation and county a point is in |

`sources.reuse` classes each source by what its licence allows, per Decision 0004. Field Club is non-commercial, so `non_commercial` sources are ingested. Exports carry the licence per record.

`sources.access` follows Decision 0007. A `bulk` source is stored in `records`. A `live` source is queried by the browser when someone looks at an area and is never stored on our servers. A `deeplink` source is only linked. A finding linked to a live or deep-link record stores the record's identifier and address in the evidence row and nothing else. Evidence linking a stored record keeps its identifier (`reference`), address (`url`) and source key as well as `record_id`, so when a full ingest removes the record and `record_id` is emptied, the evidence stays a working reference.

`records.category` is one of `designation`, `monument`, `find`, `event`, `document`, `community`, `map_label`. It drives map layers and filters. `precision_m` records how exact the position is. A Portable Antiquities find published to a 1 km square has `precision_m = 1000`. The `map_label` records are the antiquities lettered on the Ordnance Survey six-inch maps of about 1900, from the GB1900 gazetteer, under its share-alike licence.

### Collaboration around findings

| Table | Columns |
|-------|---------|
| `investigations` | `public_id*` unique, `owner_id*`, `title*`, `summary`, `notes` markdown, `area` Geometry, `visibility*` (public, unlisted, private), `updated_at*`, `hidden_at` |
| `investigation_members` | `investigation_id*`, `user_id*`, `role*` (owner, editor, viewer), `accepted_at` (null while an invitation waits; never null for the owner). Primary key on both |
| `investigation_items` | `investigation_id*`, `kind*` (finding, record, view, note, reference, profile), `finding_id`, `record_id`, `title`, `note`, `data` jsonb, `position*`, `added_by*`. Unique on investigation and position, checked at commit |
| `square_surveys` | `user_id*`, `square*` (1 km grid reference such as SU1069), `geom*` Polygon, `result*` (nothing, marked, skipped), `findings_count*`, `seconds`. Unique on user and square |
| `activity` | `kind*`, `actor_id`, `finding_id`, `investigation_id`, `data` jsonb, `location` Point |
| `notifications` | `user_id*`, `kind*`, `actor_id`, `finding_id`, `investigation_id` (an invitation's), `data` jsonb, `read_at` |
| `reports` | `reporter_id*`, `target_kind*` (finding, comment, evidence, mention, photo, user, investigation), `target_id*` (the target's own `id`), `reason*`, `note`, `status*` (open, upheld, dismissed), `resolved_by`, `resolved_at`. One open report per reporter and target |
| `moderation_actions` | `actor_id*`, `action*` (hide, unhide, resolve_report, change_role, ban, unban, change_sensitivity, approve_photo, reject_photo), `target_kind*`, `target_id*`, `reason`, `data` jsonb. One row per action, never changed |
| `watch_channels` | `provider*`, `channel_id*`, `title`, `last_checked_at`, `enabled*`, `etag`, `last_modified`, `last_error`. Channels scanned for links back to findings |

<!-- Investigations and squares (track b2/investigations). -->
Anyone with an investigation's id can read a public or unlisted one; a private one is found only by its owner, and everyone else gets `investigation_not_found`. The owner and editors change the title, summary, notes, area and items. Only the owner changes visibility, members and deletes it, and any other member can leave. The owner invites a contributor by handle; someone who hasn't finished the welcome step can't be invited. An invited person has no role, and the investigation isn't in their `mine` list, until they accept with `POST .../invitation`. They decline by leaving, which needs only a session. Inviting someone sends them an `investigation_invitation` notification naming only the owner and the investigation's public id, never its title or any other free text (Decision 0009), and nothing reaches the feed or the event stream. It leaves their list once they decline or the owner takes it back. Only public investigations are in the public list. `scope=invited` lists a person's waiting invitations, and `scope=unlisted` lists every unlisted investigation for moderators only, so collaborators never share a notebook moderators can't find (Decision 0009, rule 5). Anyone who can read an investigation can report it, and a moderator can hide it: a hidden investigation is found only by its members and moderators, carries `hidden: true` for them, and leaves the public list, the invitations list and feeds. Making one public records `investigation_published`, and making it unlisted or private deletes that row. Every change takes the investigation's row lock first, so membership and visibility can't race, and `investigation_items` has a deferred unique constraint on `(investigation_id, position)`. An item pointing at a withdrawn finding or a record no longer in the index is returned with `unavailable` set to `withdrawn` or `gone` and nothing of the target. So is one pointing at a hidden finding, with `hidden`, for anyone but the finder and moderators. Exports follow the download rule of Decision 0005 and leave such items out; the report is one HTML page with no scripts, served with a sandboxing `Content-Security-Policy`. When an account is deleted its private investigations are deleted with it, each shared one it owns passes to its longest-standing editor, and one with no editor stays readable with nobody able to manage it. Its memberships and invitations elsewhere go.

A square survey counts towards coverage unless its result is `skipped`. `GET /squares/next` ranks the squares a person hasn't done near the point by how many people have had them, skips included, then by distance, and picks at random among the best eight, so people asking at once are spread out. A square has 1 m elevation to scan when the 5 km tile of `terrain/catalogue.py` that holds it is listed and its centre is inside England's boundary in `admin_areas`. The catalogue lists partial tiles at the coast and the borders, so the tile alone would hand out squares at sea or in Wales and Scotland. Nothing reads the rasters, so a coastal square whose centre is offshore is lost and one whose centre is just inland may be mostly sea. Until `admin_areas` holds England, the tile alone decides and a warning is logged. Coverage counts each result as it was given: a square stays marked after the finding marked there is hidden, withdrawn or deleted, because a survey keeps only a count of findings. It shows no more than that somebody marked something in a public 1 km square.

### Indexes that matter

- `GIST (location)`, `GIST ((location::geography))`, `GIST (location_public)` and `GIST ((location_public::geography))` on `findings`. Also `GIN (open_steps)` for the help-wanted lists and `(created_at, id)` for the newest-first list.
- `GIST (geom)`, `GIST ((centroid::geography))`, `GIN (search)` and a trigram `GIN (name gin_trgm_ops)` on `records`. Also `GIST (centroid)` for the record tiles and `(lower(name) text_pattern_ops)` for names that start with the search text.
- Trigram `GIN (name gin_trgm_ops)` and `GIST (geom)` on `places`.
- `(finding_id)` on every child table of findings. `(user_id, read_at)` and `(user_id, id DESC)` on `notifications`: the unread count uses the first, and a page of someone's notifications the second. `(created_at DESC)`, `(kind, id DESC)` and `GIST (location)` on `activity`: the feed's `kind` filter uses the second, and its box filter the third.

## Confidence engine

`services/confidence.py` exposes one pure function, `assess(inputs) -> Assessment`. It reads nothing from the database. `services/findings.py` gathers the inputs, calls it after every change to a finding's observations, evidence or votes, stores the result on the finding, and emits activity when the tier or state changes. The rules below are the specification. Thresholds live in one `Thresholds` dataclass so they can be tuned without touching logic.

### Weights

A person's weight is set by role: member 1.0, trusted 1.5, expert 3.0. Moderators and admins count as trusted. The finder's own opinion never counts towards visibility. Every contributor is a signed-in account, so there is no lower weight for anonymous input.

### Quantities

- `seen` is the summed weight of other people who answered "yes, I can see it". `unseen` is the same for "no". `observers` is the number of distinct people who answered yes.
- `seen_ratio = seen / (seen + unseen)` when the denominator is positive.
- Class support sums weight per feature class over the finder's class and every observation that counts towards `seen` and names one. `unknown` is ignored. `class_agreement` is the top class's share. When agreement is at least 2/3 and total support is at least 2.0, the top class becomes `community_class`.
- An evidence item stands when its weighted vote total is not negative and it isn't deleted. A finding's page gives each item that total with the number of people who endorsed and disputed it, counted the same way. It's independent when someone other than the finder added it, or someone other than its contributor endorsed it with weight of at least 1.0.
- Strands group evidence kinds: `lidar_view` is lidar, `aerial` is aerial, `historic_map` is historic map, `record_link` (relation related or part_of) is records, `document` is literature, `photo` and `field_visit` are ground, `geophysics` and `excavation` are survey, `her_record`, `designation` and `publication` are official. The desk strands are lidar, aerial, historic map, records and literature. A strand is supporting when it has at least one standing, independent item with stance `supports`. Ground and survey items count towards the disputed and ruled-out rules below only when they are standing and independent too.
- Each check (`not_modern`, `not_natural`, `not_artefact`) is cleared when the weight of observations that count towards `seen` and assert it is at least 2.0 and more than twice the weight of observations giving the matching explanation.

### Tiers

| Tier | Label | Requires |
|------|-------|----------|
| `spotted` | Spotted | Nothing. Every finding starts here |
| `seen` | Seen by others | `seen >= 2.0`, `observers >= 2`, `seen_ratio >= 2/3` |
| `corroborated` | Corroborated | Seen, plus two supporting desk strands, plus `class_agreement >= 2/3` from at least two people |
| `probable` | Probable | Corroborated, plus all three checks cleared, plus a yes from a trusted or expert reviewer or `seen >= 7.0` |
| `ground_checked` | Checked on the ground | A standing ground or survey item with outcome `supports`, endorsed with weight 1.0 by someone else or added by a trusted or expert user. Doesn't require the earlier tiers |
| `confirmed` | On record | A standing official item verified by an expert or moderator who is neither the finder nor the item's contributor. Doesn't require the earlier tiers |

### States

A finding's state is separate from its tier.

| State | When |
|-------|------|
| `open` | Default |
| `known` | A standing `record_link` with relation `same_as` whose contributor weight plus endorsements reaches 2.0. The finding matches an existing record |
| `disputed` | `seen >= 2.0` and `unseen >= 2.0` with ratio strictly between 0.33 and 2/3, or contradicting strands at least equal supporting strands, or ground items disagree |
| `ruled_out` | `unseen >= 3.0` with ratio at most 0.33 (reason `not_visible`), or one explanation's weight is at least 3.0 and exceeds `seen` (reason is that explanation), or a standing ground item with outcome `contradicts` and none supporting (reason `ground_check`). Never applied at `ground_checked` or above |
| `withdrawn` | The finder withdrew it |

### Score and next steps

`confidence` is a 0 to 100 number for the meter. Each tier has a base: 10, 30, 50, 70, 85, 100. Progress towards the next tier adds a share of the gap in proportion to the requirements already met. A ruled-out finding scores 0.

`next_steps` lists the unmet requirements of the next tier as `{code, prompt, ...}`. Codes are `need_observers`, `need_strand`, `need_class_agreement`, `need_check`, `need_trusted_review`, `need_ground`, `need_official`. The same codes drive the help-wanted queue, so a finding's open steps are exactly the tasks offered to other people.

### Finer rules

The module docstring of `services/confidence.py` gives the reasoning for each of these.

- The finder's own observation is ignored for everything. Their class counts once, through the finding's feature class.
- Only a "yes" with no explanation counts as seeing it: towards `seen`, as an observer or a reviewer, for class support and for the checks. A "yes" that gives an explanation counts only as that explanation's weight, as every answer's explanation does.
- Votes by an item's own contributor and by the finder are ignored. Independence is required of contradicting evidence as well as supporting evidence.
- A field item points the way its `outcome` says, and `inconclusive` is neutral. Without an outcome, and for every other kind, its `stance` decides. Only independent field items count towards "ground items disagree" and the ruling-out on the ground. A finder's own field item needs someone else's endorsement to reach Checked on the ground, even when the finder is trusted.
- A verifier is an expert, moderator or admin who is neither the finder nor the item's contributor, on an official item that stands and supports.
- Every two-thirds figure is exactly 2/3. The disputed band is open at both ends, so a ratio of 2/3 is Seen. Contradicting strands make a finding disputed only when there is at least one.
- State precedence is withdrawn, ruled out, disputed, known, open. A ruled-out rule that holds at Checked on the ground or above makes the finding disputed, with that rule's reason. When several ruled-out rules hold, the reason is `ground_check`, then the heaviest explanation, then `not_visible`.
- A withdrawn finding keeps its tier, scores that tier's base and has no next steps. A ruled-out one scores 0 and has none either. The score is rounded down.

### Reputation

Points are written to `reputation_events`, so a person can see where each one came from. A finding reaching seen earns its finder 2, corroborated 5, probable 10, ground checked 20, confirmed 30. An observation that matches the outcome when a finding reaches corroborated or ruled out earns 1. An evidence item endorsed by two other people earns 1. A finding that turns out to match a known record earns 1. There are no penalties. A finding earns the points of every tier whose rule it newly meets, not only the one it lands on, and each award is paid once however often a finding drops and climbs back. A ruled-out or withdrawn finding earns nothing while it stays so. An answer matches corroborated when it counts as seeing it, and ruled out when it says "no" or gives an explanation. The two endorsers are people other than the contributor and the finder. A member who reaches 50 points becomes eligible for trusted, and a moderator makes the promotion. It isn't automatic: trusted users see restricted positions (Decision 0005), and three colluding accounts can take a finding to Checked on the ground, worth 27 points to its finder.

## API

All paths are under `/api/v1`. Bodies are JSON. The session is a `fieldclub_session` cookie, HttpOnly and SameSite=Lax. Every mutating request must carry the header `X-FieldClub-Client: web`, which a cross-site form can't send. The one exemption is the exact path `POST /auth/oauth/apple/callback` (see Accounts).

Rules every route follows, whichever area it belongs to:

- Every write is rate-limited. One that stores a contribution needs a signed-in account that has finished the welcome step, or answers `onboarding_required`. Every route has a response model, so the generated client covers it.
- Lists are paged with `limit` and an opaque `cursor`. Each list keeps its own cursor: a key for a list whose order is fixed, an offset for one whose order moves as people answer. No offset goes past 2,000. A cursor that is wrong in any way is 400 `invalid_cursor`, and a `limit` above the list's maximum is 422 `validation_error`.
- A `bbox` is `west,south,east,north` in degrees, four finite numbers with west < east and south < north. Anything else is 400 `invalid_bbox`, and `fieldclub-ingest --bbox` takes the same boxes.
- A filter with several values is a repeated parameter, `category=a&category=b`, and an unknown value is 422 `validation_error`. The record tile address is the exception: its `category` is comma-separated, because a tile address is a template.
- A response that sets no cache policy of its own is sent `private, no-cache` with `Vary: Cookie`, because most answers depend on who is asking. Only answers that are the same for everyone are publicly cacheable: tiles, the coverage layers, the context catalogue, and for five minutes (`deps.shared`) `/meta`, `GET /sources`, record search, nearby records and a record's page. `tests/test_routes.py` marks each with `public` and fails when a route's policy and its row disagree.

| Area | Endpoints |
|------|-----------|
| Meta | `GET /meta` returns vocabularies, tier definitions, what meets each next step, the layer catalogue, every sign-in provider marked enabled or not, whether the development sign-in is on, the age bands and contributor terms of the welcome step, source attributions, notices, and the zoom from which terrain is drawn from the 1 m data with whether the national overview is built |
| Auth | `GET /auth/me` (401 signed out), `GET /auth/session` (the person or null, never an error), `PATCH /auth/me` (`avatar_url: null` removes the provider's picture), `DELETE /auth/me`, `POST /auth/welcome`, `POST /auth/logout`, `GET /auth/oauth/{provider}/start`, `GET` and `POST /auth/oauth/{provider}/callback`, `POST /auth/email/start`, `POST /auth/email/verify`, `GET /auth/handle-suggestion`, `POST /auth/dev-login` and `GET /auth/dev-outbox?to=` (development and test only) |
| Findings | `GET /findings` (filters: `bbox`, `tier`, `state`, `feature_class`, `author`, `q`, `sort`; `format=geojson` for the map), `POST /findings` (an optional `client_ref`: sent again by the same person, it answers 200 with the finding already made), `GET /findings/{public_id}`, `PATCH /findings/{public_id}`, `POST /findings/{public_id}/withdraw`, `PUT /findings/{public_id}/sensitivity` (finder, trusted or moderator raises; a moderator lowers only through `PUT /mod/findings/{public_id}/sensitivity`) |
| Observations | `PUT /findings/{public_id}/observation` (`detail_follows` for an answer in two steps), `POST /findings/{public_id}/observation/reveal` (the detail, or none, and the reveal), `DELETE /findings/{public_id}/observation`, `GET /findings/{public_id}/observations` |
| Evidence | `POST /findings/{public_id}/evidence`, `DELETE /evidence/{id}`, `PUT /evidence/{id}/vote`, `POST /evidence/{id}/verify` |
| Discussion | `GET` and `POST /findings/{public_id}/comments`, `DELETE /comments/{id}`, `PUT` and `DELETE /findings/{public_id}/follow` |
| Mentions | `GET` and `POST /findings/{public_id}/mentions`, `DELETE /mentions/{id}`, `POST /mentions/preview`, `GET /mentions/recent` |
| Review | `GET /review/next` (blind cards: place and view only, with no title, class, tier or other answers until the reviewer has answered), `GET /review/tasks` (open next steps grouped by code) |
| Squares | `GET /squares/next?lon=&lat=&exclude=` (a 1 km square with 1 m elevation that few people have had, never one you have done nor one named by a repeated `exclude`), `PUT /squares/{ref}` (your result, one per person and square, a second replacing the first), `GET /squares/coverage?bbox=` (scans per square as GeoJSON, at most 2,500 km² per box) |
| Records | `GET /records/search`, `GET /records/nearby`, `GET /records/{id}`, `GET /records/{id}/findings` (the findings linked to it that the viewer sees exactly), `GET /sources`, `GET /findings/{public_id}/suggested-records` |
| Context | `GET /context/live-sources` (the sources the browser queries itself, with endpoint, query pattern, the answer's format, its id and name fields, the parameter that caps it and its largest value, the lowest zoom to ask from, the research's licence and attribution notes, and how a visitor sees it credited: `shown`, false while the research hasn't settled the credit, `credit`, `licence_label`, `homepage`, and `credit_field` and `licence_field` where the terms ask for a credit taken from each record), `GET /context/links?lon=&lat=` (deep links to external viewers, each with a `title` to show and what it `shows`, filled in for that point and the nation it is in; until the nations are loaded, a point on the Irish Grid gets only the viewers that cover the wider world) |
| Geo | `GET /geo/search?q=` (grid reference, coordinates, place, record or finding id), `GET /geo/point?lon=&lat=` (grid reference, nation, county, elevation, the boundary sources to credit, and the nearest settlement within 10 km with its distance) |
| Terrain | `POST /terrain/profile` (elevation along a line, and the resolution read), `GET /terrain/coverage?bbox=` (the 5 km tiles that have 1 m elevation, with the years they were flown, as GeoJSON with an ETag) |
| Investigations | `GET /investigations` (`scope=public`, `mine`, `invited`, or `unlisted` for moderators; `bbox` matching the area), `POST /investigations`, `GET`, `PATCH` and `DELETE /investigations/{public_id}`, `GET` and `POST /investigations/{public_id}/items`, `PATCH` and `DELETE /investigations/{public_id}/items/{id}`, `POST /investigations/{public_id}/items/{id}/move`, `GET /investigations/{public_id}/members`, `PUT` (invite) and `DELETE /investigations/{public_id}/members/{handle}`, `POST /investigations/{public_id}/invitation` (accept), `GET /investigations/{public_id}/export?format=geojson|csv|html` |
| Exports | `GET /findings/{public_id}/export?format=geojson|csv`, `GET /findings/export` (the list's filters, a filtered set) |
| People | `GET /users/{handle}`, `GET /users/{handle}/findings`, `GET /users/{handle}/contributions` (`kind=evidence|comment|mention`, or `second_look` on its own, which lists something only for the person themselves), `GET /users/{handle}/points` (the person's own itemised points only) |
| Activity | `GET /activity` (filters: `bbox`, `kind`, `finding`, `investigation`, `person`), `GET /events/stream` (server-sent events; `bbox` or `finding`), `GET /notifications` (with `unread_count`), `POST /notifications/read` (`{ids}` or `{all, up_to}`; a session is enough, since it stores nothing) |
| Media | `POST /media` (the image as the request body), `GET /media/{id}`, `GET /mod/media` (the approval queue), `POST /mod/media/{id}/approve`, `POST /mod/media/{id}/reject` |
| Moderation | `POST /reports`, `GET /mod/reports`, `POST /mod/reports/{id}/resolve`, `POST /mod/{findings,comments,evidence,mentions,media,investigations}/{id}/hide` and `/unhide`, `PUT /mod/findings/{public_id}/sensitivity`, `GET /mod/users/eligible`, `PUT /mod/users/{handle}/role`, `POST /mod/users/{handle}/ban` and `/unban`, `GET /mod/actions` |

A finding's page carries `actions`: whether this viewer may answer, add evidence, comment, edit, withdraw, raise the level, lower it (through the moderation route) and verify an official item, each as `{allowed, reason}`, and each evidence item its own `vote` and `verify`. `services/actions.py` works each one out by running the check functions its route runs, so `reason` is the code the route would refuse with, or `already_answered`, `highest_level` or `lowest_level` when there is nothing to do. `tests/findings/test_actions.py` holds every flag to its route for every kind of viewer, level and state.

A finding is looked up the same way everywhere (`services.findings.get_finding`): a hidden one is found only by its finder and moderators, and anything else gets 404 `finding_not_found`. Lists leave hidden findings out, and withdrawn ones too unless `state=withdrawn` is asked for. The search box always leaves both out. Suggested records are served for any finding the viewer can open, withdrawn ones included. A record's linked findings leave out withdrawn ones, hidden ones for all but their finder and moderators, and every finding the viewer doesn't see exactly, because naming the record would place the finding as closely as the record is placed: its own page leaves the link out for them (`redacted`).

Tile endpoints sit outside `/api/v1` so a CDN can cache them by path:

| Path | Returns |
|------|---------|
| `/tiles/lidar/{style}/{z}/{x}/{y}.png?v=` | A rendered terrain visualisation, 512 px |
| `/tiles/dem/{z}/{x}/{y}.png?v=` | Elevation in Terrarium encoding, 512 px, for client-side shading and 3D |
| `/tiles/records/{z}/{x}/{y}.mvt?v=` | Records as vector tiles. Aggregated counts below zoom 12, features from 12 up, each with its `precision_m` where the source gives one |

`GET /healthz` sits outside `/api/v1` and the schema, for the platform's probes, and answers `{"status": "ok", "version": ...}`.

Every tile carries an ETag and answers `If-None-Match` with 304, through one helper, `api.deps.not_modified`, which the coverage layer uses too. A tile off the map is 404 `tile_not_found`. A terrain tile at a zoom outside the range it is served at is 404 `zoom_out_of_range`, while a record tile answers `tile_not_found` for any zoom outside 0 to 22. The addresses in `/meta` carry `?v=`, a token of everything that could change the tile: for terrain, the style version, the elevation format and the data editions, the national overview's build among them; for records, the tiles' format (`record_tiles.TILE_FORMAT`), the last ingest run to finish in any status, every run still going and the enabled sources. A failed run counts because the runner commits batch by batch. A tile asked for with the current token is sent as immutable, so an ingest or a new edition reaches every browser at once. A record tile is never immutable while an ingest run is going, because each batch changes it.

### Accounts

Anyone can read everything public without signing in: the map, findings, records, investigations, activity. Every write needs a session. There are no guest accounts, so every stored contribution belongs to a real account.

People can still try the tool before joining. Marking a finding, answering a second look and scanning a square all work signed out, and the result is held in the browser as a draft. Drafts never reach the server. Pressing save opens the sign-in sheet, and after sign-in the frontend submits the drafts. Drafts live in `localStorage` because the provider redirect reloads the page.

Sign-in is by provider, with no passwords. Google, Apple, Microsoft and Facebook are the main ones, and OpenStreetMap is offered too because many contributors have an account there. Each provider is enabled only when its credentials are configured. An emailed one-time link is the fallback for people who use none of them. Providers run as a server-side authorisation-code flow with `state` and PKCE. The callback verifies the identity, finds or creates the user, sets the session cookie and redirects to the `next` path it was given, which must be a relative path on this site.

The state, OpenID Connect nonce and PKCE verifier of one provider sign-in travel in `fieldclub_oauth`, an HMAC-signed, HttpOnly cookie that lasts ten minutes, is scoped to that provider's callback path and is cleared by the callback. A cookie rather than a server-side row binds the flow to the browser that started it, which stops a callback address being replayed into someone else's browser, and costs no write per click. Google, Microsoft, Apple and OpenStreetMap go through one OpenID Connect client that caches each provider's discovery document and key set, fetches the key set again when a token names an unknown key (at most once a minute), and accepts only RS256 and ES256 signatures. Facebook is plain OAuth 2 with a profile call. Apple returns with a cross-site POST that can't carry the client header, so `POST /auth/oauth/apple/callback` is the one path exempt from it, and its flow cookie is SameSite=None. A sign-in that fails at the start or the callback redirects to the `next` path with `?signin_error=` and a short code: `state_mismatch`, `invalid_token`, `provider_error`, `cancelled`, `banned`, `account_deleted`, `provider_unavailable` (a provider that isn't offered), `email_unavailable` or `signin_failed` (anything unexpected). Every sign-in issues a new session and ends any session the browser presented. Apple's cross-site POST doesn't carry the SameSite=Lax session cookie, so the flow cookie also holds the hash of the session presented at the start, and the callback ends that one too. Only Google's and Apple's verified addresses count as verified, and Microsoft's only with the domain-owner flag (`xms_edov`), because a Microsoft directory can set any address. OpenStreetMap is asked for no address, and Facebook never says one is verified, so neither links accounts. An address goes on an account only when it is verified and nobody else holds it. Addresses are CITEXT, and Postgres `lower()` folds a few non-ASCII capitals to ASCII letters (`İ` to `i`), so an address the database matches counts as the same only when the two differ in nothing but ASCII case. Otherwise a link answers `email_unavailable` and a provider identity gets an account of its own, without the address.

The `next` path must start with exactly one slash and contain no backslash, no control or invisible character and no `.` or `..` segment, in any percent-decoded form. The frontend uses a `next` it receives (from `?next=` on the link page, or the target of a `signin_error` redirect) only through same-origin router navigation, never by assigning it to `location`.

`POST /auth/email/start` stores a SHA-256 of a fresh token and emails the link for any well-formed address, without looking the address up, so the answer never says whether an account has it. Asking again spends the address's earlier unspent links, so only the newest works. Five links an hour per mailbox, counting `ann+tag@` as `ann@`, and ten per caller. The token is in the link's fragment, so it stays out of server logs. `POST /auth/email/verify` spends it with one conditional update: a link works once, within fifteen minutes, and an unknown, spent or expired link all fail with `link_invalid`. `start` sets `fieldclub_email_link`, an HttpOnly cookie scoped to the verify path that lasts as long as the link, holding a random value whose hash is stored on the link. Verify signs in at once only when that cookie comes back. In any other browser it answers 409 `confirmation_required` with `details.email` masked (`a***@example.org`), spends nothing, and signs in when posted again with `confirm: true`. The link page must show the masked address and ask "Sign in as …?", and never confirm on the person's behalf: otherwise someone could send their own link to a victim and sign the victim in to the sender's account. A link that can't be sent answers 502 `mail_not_sent`. `FIELDCLUB_MAIL_BACKEND` chooses `log` (development and tests only) or `smtp`.

A first sign-in creates the user with a display name from the provider and a generated handle such as `QuietBarrow42`. A welcome sheet lets them change both. A second provider that asserts the same verified email is linked to the same user. An unverified email never links accounts.

Contributors must be 16 or over. The welcome sheet asks for an age band, 16 to 17 or 18 and over, and for acceptance of the contributor terms, and `POST /auth/welcome` stores both, once. Until then `age_band` and `terms_accepted_at` are empty, and every route that stores a contribution refuses with code `onboarding_required`. A bio is public free text, so it counts: `PATCH /auth/me` refuses a non-empty `bio` until the welcome step is done. Changing handle, display name or settings, and clearing a bio, stay open. An account in the 16 to 17 band shows only its handle, never a provider name or picture, and so does an account that hasn't chosen a band. The minimum age is the setting `FIELDCLUB_MIN_AGE`, 16 to 18. At 17 or 18 only the 18-and-over band is accepted, and accounts already in a lower band are refused with `below_minimum_age`. See Decision 0009.

There is no private messaging and no private channel between members. A private investigation has exactly one member. Adding a collaborator requires making it public or unlisted, and moderators can read and list unlisted investigations. Nobody becomes a collaborator without accepting an invitation. An uploaded photo is shown to other people only after a moderator or trusted member approves it. The people who may approve photos see unapproved ones, so they can judge them, and nobody approves their own.

`POST /auth/dev-login` signs in as a named test user, through the same path as every other sign-in, so it ends the session the browser presented. `GET /auth/dev-outbox?to=` lists, newest first, the emails the log mailer sent to that address, with each sign-in link apart. Both exist only when `FIELDCLUB_ENV` is `dev` or `test` and `FIELDCLUB_DEV_LOGIN` is on, and `/meta` says so as `auth.dev_login`. They are how local development and end-to-end tests get a session.

`GET /auth/me` and `GET /auth/session` give the person's own `id`, which never changes, so the browser can tell whose drafts are whose. `PublicUser` never carries it, but it isn't secret: the moderation routes name a reported or acted-on person by it as `target.id`. `POST /findings` with a `client_ref` takes a transaction-level advisory lock on the person and the reference before looking for the finding it made, so two copies of one draft sent at once make one finding.

`DELETE /auth/me` removes the email, identities, sessions, follows, notifications and the file of every photo the person uploaded, and marks the user deleted. A photo's row goes with its file, except for a refused or hidden photo, whose row stays so that the same image stays refused to everyone, and which nobody can download any more. The files are deleted only after the deletion commits, so a failure leaves orphaned files rather than rows without one. Their contributions stay, credited to "former member", because they were published under an open licence and other people's work builds on them: findings, answers, evidence, votes, comments, mentions, square surveys and investigation items. So do reports they made or that are about them, and the moderation log. `tests/auth/test_account_deletion.py` says which of the two each user column is, and fails for a new one.

### The meta document

`GET /meta` is the one place the frontend learns vocabularies and layers. Its shape:

```json
{
  "app": {"name": "Field Club", "version": "0.1.0", "contribution_licence": "CC BY 4.0"},
  "auth": {
    "providers": [{"id": "google", "label": "Google", "enabled": true}, {"id": "apple", "label": "Apple", "enabled": false}, {"id": "email", "label": "Email link", "enabled": true}],
    "dev_login": false, "age_bands": ["16_17", "18_plus"], "terms": {"summary": "...", "url": "/about#terms"}
  },
  "vocab": {
    "feature_classes": [{"id": "enclosure", "label": "Enclosure", "hint": "...", "fish_term": "ENCLOSURE", "sensitivity": "open"}],
    "periods": [{"id": "iron_age", "label": "Iron Age", "hint": "800 BC to AD 43"}],
    "evidence_kinds": [{"id": "aerial", "label": "Aerial photo", "strand": "aerial", "group": "desk", "hint": "..."}],
    "tiers": [{"id": "seen", "label": "Seen by others", "description": "...", "base_score": 30}],
    "states": [{"id": "known", "label": "Matches a known record", "description": "..."}],
    "checks": [{"id": "not_modern", "question": "Could it be modern?", "hint": "..."}],
    "explanations": [{"id": "modern", "label": "Modern feature", "hint": "..."}],
    "mention_kinds": [{"id": "video", "label": "Video"}],
    "record_categories": [{"id": "designation", "label": "Designations", "colour": "#d9544d"}],
    "report_reasons": [{"id": "spam", "label": "Spam", "hint": "...", "due_hours": null}],
    "next_steps": [{"id": "need_strand", "met_by": "evidence", "evidence_kinds": ["lidar_view", "aerial", "historic_map", "record_link", "document"], "record_relations": ["part_of", "related"], "outcome": null, "stance": "supports", "needs_verification": false}]
  },
  "layers": {
    "views": [
      {
        "id": "composite", "title": "Composite", "description": "...",
        "group": "lidar", "type": "raster",
        "tiles": ["/tiles/lidar/composite/{z}/{x}/{y}.png?v=3f2a9c01b7de"],
        "tile_size": 512, "minzoom": 7, "maxzoom": 16,
        "attribution": "...", "licence": "Open Government Licence v3.0", "licence_url": "...", "reuse": "open",
        "bounds": null, "default": true
      },
      {"id": "raking", "title": "Raking light", "group": "lidar", "type": "raking", "description": "...", "attribution": "...", "licence": "...", "licence_url": "...", "reuse": "open"}
    ],
    "dem": {
      "tiles": ["/tiles/dem/{z}/{x}/{y}.png?v=8c41d07e5a26"], "tile_size": 512, "encoding": "terrarium",
      "minzoom": 7, "maxzoom": 16, "attribution": "...", "licence": "...", "licence_url": "...", "reuse": "open"
    },
    "overlays": [
      {"id": "osm", "title": "OpenStreetMap", "type": "openmaptiles", "tilejson": "...", "glyphs": "...", "default_opacity": 0.8, "attribution": "...", "licence": "Open Database License 1.0", "licence_url": "...", "reuse": "share_alike"},
      {"id": "records", "title": "Heritage records", "type": "records", "tiles": ["/tiles/records/{z}/{x}/{y}.mvt?v=5be0c2d19a47"]},
      {"id": "findings", "title": "Findings", "type": "findings"},
      {"id": "coverage", "title": "Scan coverage", "type": "coverage"}
    ],
    "initial_view": {"center": [-1.8542, 51.4286], "zoom": 14}
  },
  "sources": [{"key": "nhle-scheduled", "name": "...", "publisher": "...", "licence": "...", "licence_url": "...", "attribution": "...", "reuse": "open", "homepage": "...", "coverage": "...", "category": "designation", "access": "bulk", "record_count": 0, "last_ingest_at": null}],
  "notices": {"field_visit": {"england": ["..."], "scotland": ["..."], "wales": ["..."], "northern_ireland": ["..."]}, "field_visit_16_17": "...", "sensitivity": "...", "find_reporting": {"england": {"scheme": "Portable Antiquities Scheme", "url": "https://finds.org.uk/", "text": "..."}, "scotland": {...}, "wales": {...}, "northern_ireland": {...}}},
  "terrain": {"fine_minzoom": 13, "catalogue_tiles": 5877, "overview": {"built": true, "built_at": "2026-11-10T09:00:00Z", "tiles": 412}}
}
```

`sources` is the same list, in the same order and shape, as `GET /sources`: every enabled source by name. `vocab.next_steps` is `confidence.STEP_RULES`: whether a second look or evidence meets each step, and for evidence the kinds that count and what the item must say. `terrain.overview.built` is null when the overview's manifest can't be read. `auth.terms` comes from `FIELDCLUB_TERMS_SUMMARY` and `FIELDCLUB_TERMS_URL`, which production refuses to start without, and `auth.age_bands` from `FIELDCLUB_MIN_AGE`. A feature class's `sensitivity` is the level a new finding of it starts at. `notices.find_reporting` is Decision 0005, item 9: the Portable Antiquities Scheme in England and Wales, Treasure Trove in Scotland, and in Northern Ireland the Ulster Museum, the police or the Department for Communities, for which no address is given. Every layer someone else publishes carries its attribution, licence and reuse class, as a source does (Decision 0004). Records carry their source's terms per feature, and findings are under the contribution licence.

A view layer of type `raster` is a tiled image. `group` is one of `lidar`, `imagery`, `historic`, `map`, `geology`. The single `raking` view is drawn in the browser as a hillshade of the `dem` source, with the sun position under the user's control. Any view can be the main layer or the comparison layer. Overlays stack above with their own opacity. The `osm` overlay is an OpenMapTiles-schema vector source that the frontend styles as thin lines and labels.

### Location sensitivity

See Decision 0005. A finding's `sensitivity` is `open`, `protected` or `restricted`. `location_public` holds the position anyone may see: the exact point for an open finding, and the centre of its 1 km grid square otherwise. It's written whenever the finding is saved through the ORM, so a change of level or location never goes through a bulk `UPDATE`. A database trigger refuses an open finding whose public position differs from its location, and a change from open to a higher level that leaves the public position exact. It can't check the square itself, because the grid is in Python.

| Viewer | open | protected | restricted |
|--------|------|-----------|------------|
| Signed out | exact | 1 km square | 1 km square |
| Member | exact | exact | 1 km square |
| Finder, trusted, expert, moderator | exact | exact | exact |

A generalised finding is returned with `obscured: true`, the square's reference, and no outline. The default level comes from the feature class: round barrow, long barrow, ritual monument and settlement earthworks default to `protected`, everything else to `open`. The finder, a trusted user or a moderator can raise a level. Only a moderator can lower one, through `PUT /mod/findings/{public_id}/sensitivity` with a reason for the log, and the plain route answers a moderator's lower level with `lower_through_moderation`. A new finding starts at the higher of its class default and the level requested, and a request below the default is honoured only from a moderator (`starting_sensitivity`). Changing the feature class to one with a higher default raises the level to that default. It never lowers a level, and a change between classes with the same default leaves the level alone (`level_after_class_change`, applied when the finding is saved). Experts and admins count as trusted here, and admins as moderators.

One function in `services/sensitivity.py` decides what a viewer sees, and every route that returns a finding goes through it. Queries on behalf of signed-out visitors filter and sort on `location_public` only. Downloads use the generalised position for protected and restricted findings unless the person downloading is the finder or trusted (`sensitivity.downloads_exact`, beside the other viewer rules). Suggested records and the search box start from the position the viewer may see, so for someone who sees only the square, distances, order and the set returned are the same wherever in the square the finding lies. `tests/test_routes.py` lists every route the app serves and names the test, in `tests/findings/test_leaks.py` or beside the route's own tests, that tries each one carrying a position as every viewer against every level, and fails when a route has no row.

Findings reach the map through `GET /findings?bbox=&format=geojson`, not through cacheable tiles, because the answer depends on the viewer. The `bbox` matches the position the viewer is allowed to see, so an obscured finding matches by the centre of its square. The frontend widens the box it asks for by 500 m on each side so that a square covering the view is returned even when its centre is off screen.

### Second looks

Decision 0008 makes second looks blind. These rules keep each answer independent after it's given:

- An answer is final. Answering reveals the finding and everyone's answers, so `PUT /findings/{public_id}/observation` refuses a different answer with `answer_final`, and only the note can change. `DELETE` marks the answer withdrawn, which stops it counting. The same answer given again restores it, and a different one is refused.
- An answer can come in two steps, so the detail is asked for after it (`docs/UI.md`). `PUT .../observation` with `detail_follows: true` carries `visible` alone. The answer is stored and counts at once, and the reply is `{revealed: false, observation}`. `POST .../observation/reveal` then adds the class, period, explanation, checks and note, or nothing, once, and its reply is the reveal (`revealed: true`). The detail counts exactly as detail sent with the answer. Asked again, it gives the same reveal while the detail matches and `answer_final` otherwise. A `PUT` of the whole answer on one still waiting adds its detail the same way. `observations.revealed_at` records the reveal. Until it is set the reviewer is someone who hasn't seen the answers on every route, and a finding's page gives them `my_observation` with `revealed: false`, so they can finish from there. A request that carries the answer and its detail without `detail_follows` reveals at once, as before. The reveal's tier and state are those before and after its own request, so a move the answer made in the first step isn't shown as one.
- Answers, evidence and votes come only from someone who sees the finding's exact position. Anyone else gets `location_hidden`. Comments stay open to every contributor.
- `observation_added`, and a tier or state change that an answer or its withdrawal causes, are recorded with no actor, so followers can't tell how anyone answered.
- A viewer who may not see the answers gets the next steps that second looks meet without `people`, `weight_needed` or a number in the prompt.
- "May see answers" means being the finder or having an answer that has been revealed, even if it was taken back later (`findings.answers_visible`).
- A finding page names the people who answered only to those who may see answers (Decision 0010). Everyone else gets no credit for an answer, neither a name nor a count.
- Suggested records weigh a record's fit with the community class only for those who may see answers, so neither `type_fit` nor the order gives the class away.
- A profile counts and lists the findings a person took a second look at only to that person. Everyone else gets `counts.second_looks` as null and an empty `kind=second_look` list, because someone polling a profile would see when an answer arrived, and the unnamed tier change at that moment would show which way it went (the reasoning of Decision 0010).

Known limits, accepted for now. A review card carries the finding's `public_id`, because the answer is sent to it, so a reviewer who opens the finding's page first sees the claim there, as Decision 0008 allows. The tier, the score (`confidence` and `assessment.score`) and the order of the review queue (`answers_to_next`) all follow from other people's answers and reach people who haven't answered. None carries a name, but someone who watches a page can tell that an unnamed answer moved the score up or down (Decision 0010). The feed, notifications and the event stream announce each `observation_added` as it happens, with no actor, so they too say that someone answered and when, not who. The review queue and the help-wanted lists page by an offset held in the cursor, because their order changes as people answer, so a card can move between pages or appear twice.

### Moderation

Any contributor can report a finding, comment, piece of evidence, mention, photo, person or investigation, with a reason from `vocab.REPORT_REASONS` (served in `/meta` as `report_reasons`) and a note only moderators read. A report names its target as the API does: a finding or an investigation by public id, a person by handle, anything else by id. Something the reporter can't see is `target_not_found`, a second open report on the same target is `already_reported`, and a report on a target within 24 hours of the same person's report on it being dismissed is `recently_dismissed`. Moderators see the queue oldest first, without the reports they made or that are about them or their work. A report for an intimate image or an untrue statement about a person carries `due_at`, 48 hours after it was made, because the law gives that long. Resolving a report, upheld or dismissed, resolves every open report on its target. Nobody resolves a report they made or one about them or their work. A reporter is told nothing more, and nothing a moderator writes reaches any one member (Decision 0009).

Everything under `/mod`, the queues, the eligible list and the log included, needs the welcome step finished (`onboarding_required`), because that step is where a person accepts the terms. `tests/test_routes.py` marks such a read with `welcome`. A moderator hides and unhides findings, comments, evidence, mentions, photos and investigations, except their own (`own_content`), and removes someone else's comment, evidence or mention only by hiding it: `DELETE /comments/{id}`, `DELETE /evidence/{id}` and `DELETE /mentions/{id}` are for its author alone (`mention_forbidden`). A moderator raising the level of someone else's finding through `PUT /findings/{public_id}/sensitivity` is logged as `change_sensitivity` with no reason. It takes effect on the next request. A hidden finding is seen only by its finder and moderators. A hidden comment reads as removed, with no author and no body, to everyone but its author and moderators, and leaves `comment_count`. Hidden evidence stops counting at once, the finding is reassessed, and it leaves finding pages, credits and exports for everyone. A hidden mention leaves `mention_count` for everyone, and the finding's list, the recent feed, profiles, the feed and notifications for everyone but its adder and moderators, who see it marked `hidden`. While it stays hidden it holds its address on the finding, even once its adder removes it, so neither a member nor the channel scan can add it again (`mention_hidden`, 409). A hidden photo is served only to its uploader and moderators. Every read route says in `tests/test_routes.py` how it leaves hidden things out, naming the walk in `tests/moderation/test_hidden_everywhere.py` that reads it as every kind of viewer after each kind of thing is hidden, or why it holds nothing a moderator can hide.

A moderator makes a member trusted, from fifty points (`not_eligible` below that), puts a trusted member back, and marks or unmarks an archaeologist as expert. Only an admin makes or unmakes a moderator, admins are made outside the API, and nobody changes their own role. `GET /mod/users/eligible` lists members with fifty points who aren't trusted, with the findings their points came from, the other people on each, and those people counted across all of them. Second looks stay blind (Decision 0008): the people who answered a finding, and points earned by answering it, are tied to it only for a moderator who found or answered it. Otherwise answer points are added up in one source with no finding and the reason `second_looks`. A ban ends every session the person has, and while it lasts their second looks, votes, evidence and verifications stop counting, their evidence leaves pages and exports, and evidence they verified no longer names them. Their square surveys stop counting in coverage and in choosing the next square. Every finding they touched is reassessed with no actor, and again when the ban is lifted. Their findings, comments, mentions and investigations stay, and their profile answers `user_not_found`. Their events and notifications leave every list, because the feed drops a banned actor's rows. An event stream they hold open carries only what the public feed lists until it ends. An invitation waiting for them can't be accepted while they are signed out, and stays. A moderator bans anyone below moderator, and only an admin bans a moderator. Every one of these actions, and every photo approved or refused, writes a `moderation_actions` row, which `GET /mod/actions` lists newest first.

### Photos

`POST /media` takes the image as the request body, at most 15 MB, refused unread when `Content-Length` says more. Pillow must read it as a JPEG, PNG or WebP still image of at most 50 million pixels, fully decoded, and a picture over 4096 by 4096 pixels needs at least one byte of file for every 200 pixels (`image_too_many_pixels`). A multi-picture JPEG is read as its first picture. A JPEG is decoded at a half, a quarter or an eighth of its size where that leaves at least 3072 pixels across, and one upload is decoded at a time in the process: one that waits more than 30 seconds is `uploads_busy` (503). The pixels are copied into a new image, turned the way the EXIF orientation says, scaled to at most 4096 pixels across and saved as a JPEG, or a PNG when it has transparency, so no EXIF, GPS, XMP, ICC profile or text survives. The file is stored under a random 128-bit key that no response contains. An upload matching a refused or hidden photo byte for byte is `media_blocked`. `GET /media/{id}` serves the photo as `image/jpeg` or `image/png` with `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` and an inline disposition. It is always sent `private, no-cache`, varying by cookie, approved or not. Before approval it goes only to its uploader, moderators and trusted members. After it, a photo attached to a finding goes only to people who see that finding's exact position, and never when the evidence or finding is hidden or the uploader banned. Anything refused is the same 404, `media_not_found`, as an id never used. Refusing a photo deletes its file. An approved photo is hidden, not refused.

## Events

`services/activity.py` has `record(db, kind, actor, finding=None, investigation=None, data=None)`. It inserts an `activity` row, creates notifications for the finding's followers, and after commit sends a small payload through PostgreSQL `NOTIFY fieldclub_events`. One listener per process fans payloads out to connected event-stream clients. Because the bus is PostgreSQL, it works across Cloud Run instances.

An event caused by a second look has no actor (see Second looks above).

Nobody is notified of their own action. A second look's events have no actor, so `record` takes the answerer as `quiet_for` and leaves them out of the notifications instead. `activity.location` is the centre of the finding's 1 km square for every finding, and `activity.relocate` moves it when the finding moves.

`GET /activity` and `GET /notifications` list an event only while what it is about can still be seen: not on a finding that is hidden from the viewer or withdrawn, not on an investigation that isn't public or is hidden from the viewer, not by a banned account, and not about a comment, evidence or mention (`data.comment_id`, `evidence_id`, `mention_id`) that has been deleted or is hidden from the viewer. An invitation's notification is listed while the person is still invited or a member. A deleted actor is shown as no one. Both are newest first by id. The feed's `bbox` matches `activity.location`, so a shrinking box can find no more than the square, which everyone may see, and each item's finding carries its position as the viewer may see it.

The event stream is the one `async` endpoint, served on the event loop (`services/events.py`). Each process runs one hub: a psycopg `AsyncConnection` holds the `LISTEN`, and each client is an async generator waiting on its own bounded queue, so a client costs a coroutine and holds no worker thread and no database connection. Before announcing an event the hub checks, once per event and in a worker thread, that a signed-out visitor's feed lists it, and reads its square for clients filtering by box. The square never leaves the server: a client receives `{id, kind, finding, investigation, actor}` and refetches through the API. A client that falls `FIELDCLUB_EVENTS_QUEUE_SIZE` events behind is dropped with a `dropped` event, and keeps its place under the caps until its response ends, because a client that stopped reading may still hold the connection. The listener reconnects after any failure and sends `resync`, because events sent meanwhile are lost. An event the hub can't check is skipped, never announced unchecked. Streams send a `: ping` comment every `FIELDCLUB_EVENTS_HEARTBEAT_S` and end after `FIELDCLUB_EVENTS_MAX_STREAM_S`. One address may hold `FIELDCLUB_EVENTS_MAX_PER_ADDRESS` streams, and a process `FIELDCLUB_EVENTS_MAX_STREAMS`, beyond which the answer is 429 `too_many_streams`. A browser's `EventSource` doesn't retry after a 429, so the frontend reopens the stream after a delay, or polls, when it finds the stream closed. `fieldclub-api` ends every stream with `closed` before uvicorn waits for open responses, so shutdown doesn't wait for them.

A person sees their own second looks on their profile as `second_look`, without a date and in the findings' order (see Second looks for why nobody else does). The reputation others see leaves out the points answers earned (`observation_corroborated`, `observation_ruled_out`), and the itemised points are the person's alone. Profiles of deleted and banned accounts answer `user_not_found`. A handle-only account (16 to 17, or no band yet) shows no bio either.

Activity kinds: `finding_created`, `tier_changed`, `state_changed`, `observation_added`, `evidence_added`, `comment_added`, `mention_added`, `followup_logged`, `investigation_published`. `investigation_invitation` is a notification only, written by `activity.notify_invitation`, never an `activity` row.

The payload carries ids only, and `activity.location` is the centre of the finding's 1 km square, never an exact position.

## Mentions

`services/unfurl.py` reduces every address to one canonical form: each way of writing a YouTube link becomes `https://www.youtube.com/watch?v=<id>` with the start time in `start_seconds`, Vimeo links become `https://vimeo.com/<id>`, a DOI in any form becomes its lower-case doi.org address without query, fragment or trailing slash, and anything else loses its fragment and tracking parameters, has its query sorted and its unreserved characters unescaped. A finding's mentions are compared by `match_key`, the canonical address less `http` or `https`, a leading `www.` and a trailing slash. An address holding a format character (a bidi override, a zero-width character) is refused, and page text loses them. It fetches the title, author, thumbnail and date without keys: oEmbed for YouTube and Vimeo, doi.org content negotiation for CSL JSON, and Open Graph tags or `<title>` for a page. Results are cached in the process for an hour, failures for five minutes. A fetch that fails or is refused leaves the mention with its address alone. Thumbnails are kept only on https and only from YouTube's and Vimeo's image hosts: a page's own image is never kept, because the member chose its site and it would learn who looked at the finding. Fetches the cache can't answer spend one budget for the process (600 an hour); when it is used up the address is left unfetched and that isn't cached.

Every such fetch goes through `safe_fetch.fetch`: http and https only, ports 80 and 443, no credentials, the host resolved once and refused if any address is private, loopback, link-local, shared, reserved, multicast or a cloud metadata address (IPv4 in odd notations or inside IPv6 included), the connection made to the checked address with the name as `Host` and TLS server name, redirects followed by hand with the same checks (three by default), the content type checked, the body capped after decompression, and a deadline on the whole fetch that bounds every socket operation, headers included. The name lookup is given up on after five seconds. These fetches use a client of their own with eight connections, so they never take the shared client's. `POST /mentions/preview` and `POST /findings/{id}/mentions` are rate-limited per contributor after the contributor check, and end the request's transaction before fetching, so no database connection waits on a stranger's server.

Adding a mention bumps `mention_count` and records `mention_added`, which tells the finding's followers (the finder and everyone who helped) except whoever added it. A mention never touches the confidence engine. `GET /mentions/recent` lists mentions on findings the viewer may list, newest first, each with its finding's position from `location_out`. Withdrawn findings and removed mentions are left out, and hidden ones for everyone but their adder and moderators. Only the person who added a mention removes it, and that blocks nothing, so anyone may add that address again. A moderator hides one instead, the scan's included, through `/mod/mentions/{id}/hide` (see Moderation).

`fieldclub-jobs scan-channels` reads each enabled channel's public feed, one at a time with a pause between them and conditional requests, and adds an `auto_detected` mention with no member for every link in a video description to `<FIELDCLUB_PUBLIC_URL>/f/<public id>`. `fieldclub-jobs refresh-sources` runs each enabled bulk source's connector, and each reference loader, one at a time, when its last completed full run is older than its `max_age` (a week when it declares none). A source that lacks a setting it needs, such as the contact address Wikidata asks for, is skipped, and one that fails stops there until the next refresh. It never allows a shrink, so a full run that would remove more than `FIELDCLUB_INGEST_MAX_SHRINK` of a source fails and is counted as failed. Both exit non-zero when anything failed, after carrying on with the rest.

## Terrain service

The shape is fixed. The sources are filled in from the catalogue in `docs/sources/`, `lidar.md` and `lidar-england-bulk-supply.md` among them.

`terrain/sources.py` defines `ElevationSource.read(bounds_3857, width, height) -> float32 array` with NaN for no data, and `cacheable_for(...)`, whether that read can change under its edition. `terrain/render.py` asks the source for a tile's bounds plus a buffer, so neighbourhood filters have real data at tile edges, then crops. The buffered elevation array is cached once per tile, so switching style doesn't hit the upstream again. Rendered tiles are cached too. Both caches use `Storage`, which is local disk in development and a bucket in production. Each kind of data is a namespace (`tiles`, `media`) under `FIELDCLUB_GCS_BUCKET`, unless `FIELDCLUB_GCS_NAMESPACE_BUCKETS` gives it a bucket of its own, as production does for uploaded photos.

`terrain/visualise.py` holds the pure numpy functions: hillshade, multi-directional hillshade, slope, local relief, sky-view factor, openness, and the blends. Each takes elevation and ground resolution in metres and returns an array with a fixed stretch, so adjacent tiles always match. Kernel sizes are given in metres and converted to pixels per zoom.

Elevation is read only from the mirror (`terrain/mirror.py`): one COG per 5 km tile, LERC_ZSTD at 1 cm, 512-pixel blocks, overviews at 2, 4 and 8 m, in a local folder or under `gs://`. A tile that isn't mirrored is converted from Defra's source file on disk if it is there, or fetched from the SFTP bulk supply (`terrain/sftp.py`), once however many requests want it. In a bucket that holds across servers too, through a lock object per tile that is created only if absent, rewritten by its holder while it works, and taken over once it hasn't been rewritten for `FIELDCLUB_TERRAIN_LOCK_STALE_S` (`terrain/blobs.py`). A tile whose every copy was unreadable isn't fetched again for six hours, recorded under `failed/` in the mirror. A read that hears nothing for 60 s gives up, and a failed attempt waits before the next, twice as long each time. A refused login or a wrong host key isn't retried: fetches pause for 15 minutes, and a `fieldclub-terrain mirror` run stops, as it does after five failed tiles in a row. The mirror only adds files and never replaces one. `terrain/catalogue.py` lists the 5,877 tiles, so a tile that doesn't exist costs no network call. From zoom 13 up, map tiles read the 1 m mirror and fetch what is missing. Below 13 they read the national overview (`terrain/national.py`, `terrain/overview.py`, Decision 0012): one COG at 8 m built from the mirror's own 8 m copies, named in `national.json` and rebuilt with `fieldclub-terrain national build`. A low-zoom tile is cacheable when the build holds every 5 km tile it touches, and otherwise draws the mirror's tiles uncached. Beyond the reach of its data a Terrarium tile takes the overview's height, then sea level, which is wrong over the 351 km² North York Moors gap in the 2022 composite: the DEM draws a pit there until the post-2022 tiles fill it. The coverage layer's capture years come from Defra's survey index, packaged as `terrain/data/england-dtm-2022-years.tsv` by `fieldclub-terrain years build`. The LIDAR sources have `sources` rows (`terrain/attribution.py`), which `fieldclub-terrain sources` and every command that stores elevation write. `fieldclub-terrain` mirrors tiles, builds the overview, warms the tile cache and reports on all three. The terrain folders default to places under `FIELDCLUB_VAR_DIR`, which storage and ingest use too. A relative `FIELDCLUB_VAR_DIR` is resolved against the repository root, so all three find the same folder from any working directory. The styles, their parameters and versions are in `terrain/styles.py`. Terrain tile URLs carry `?v=`, a token of the style version, the elevation format and the data editions, the overview's build among them: a tile asked for with the token of the build it was drawn from is sent as immutable, one from a source that is still filling as `no-cache`, and `tests/terrain/test_versions.py` fails when pixels change without a version.

## Ingest

A connector subclasses `ingest.base.Connector`, declares its `Source` row, and implements `fetch() -> Iterator[RecordIn]`. The runner upserts the `sources` row first, batches upserts on `(source_key, external_id)`, removes rows that vanished upstream when a full run completes, writes an `ingest_runs` row and rebuilds the source's `record_cell_counts`. A full run has no `bbox` and no `limit`. A run that yields nothing fails, and so does a full run that would remove more than `FIELDCLUB_INGEST_MAX_SHRINK` of what is stored, unless it is run with `--allow-shrink`. `uv run fieldclub-ingest list|run <key> [--bbox] [--limit] [--allow-shrink]` drives it. Runs are idempotent. Connectors hold no credentials. A source that needs a key reads it from settings and is skipped when the key is absent. Shared readers in `ingest/adapters/` do the fetching: ArcGIS, WFS, SPARQL, files and downloads, and `rest` for paged JSON, which checks the distinct items it reads against the count the service reports and can keep each page for a day. `ingest.base.in_britain_and_ireland` is the coarse test that leaves out the Continent, which the runner's own box for the isles still holds. A source that only cross-walks identifiers, such as Wikidata, declares `enabled=False`, so its records stay out of the map, tiles and search (Decision 0011). `ingest/connectors/README.md` is the guide to writing a connector.

The National Heritage List layers share `ingest/connectors/he_nhle_hub.py`: the Open Data Hub export address, the licence, the currency statement and the list-entry link. Where a layer comes as points and as polygons of the same entries, only one is enabled, so no designation is found twice. The listed buildings keep their points, which cover every entry, and the notices and certificates keep their polygons. The other layer of each pair is registered disabled: its records are stored when it is run and hidden from search, lists and tiles.

A record is a thing, not a feature. Where a source publishes several features for one thing, its connector joins them: York's HER gives a point, lines and outlines under one `MonUID`, and `york-her-monuments` stores one record per `MonUID` with every part as one geometry, which is why it holds about 5,200 records for 9,662 features. The undesignated parklands do the same: parts of one name and HER within 2 km of each other are one record, a MultiPolygon, and parts further apart, or marked distinct in a comment, stay separate parks. A York monument that is a point plus an outline is a GeometryCollection in the record API, but its vector-tile geometry keeps only the highest-dimension parts, so tiles show its outline and not its point. When a source has no identifier of its own, the connector hashes the fields that name the thing and raises if two features give the same hash. A source whose own coordinates are wrong is placed from the better field: the lost villages are placed from their grid references, and the layer's geometry is used only when the reference does not parse. `ArcGISLayer` pages by offset where it can. A layer that is a view of several shapes needs `by_object_id=True`, because its offsets count rows the layer hides.

Some sources are not records. Natural England's CRoW access land (42,054 polygons), the National Historic Landscape Characterisation 250 m grid (2.1 million cells) and the Forestry Commission's woodland opportunity map (552,503 cells) say where one may walk or what kind of landscape lies under a cell. They hold no sites to find. They belong in the map layer catalogue, not in `records`, where they would fill search, nearby results and suggestions with polygons that are not sites. They have no connector.

A reference loader in `ingest/reference/` fills `places` or `admin_areas` instead of `records`. It declares its `Source` row like a connector, and each run replaces its rows in one transaction and writes an `ingest_runs` row. `fieldclub-ingest run <key>` runs loaders too: `--bbox` replaces only the rows in the box, and `--limit` is refused, because a run that kept N rows would delete the rest. `os-open-names` fills `places` with Great Britain's populated places, landforms, water, woods and the airports, harbours and stations people navigate by, about 270,000 names, and leaves out postcodes, roads and buildings. A place's `rank` is its kind in the hundreds (a city 9, a town 8, a village 7, down to a wood 2) plus up to 99 for the size of its bounding box. The search box orders names that start with the query by rank, and the rest by similarity first, under the same time limit as record search. It then ranks places and records together: a name that is the whole query first, then names that start with it (places before records), then the rest by similarity. Each place carries its source, so its attribution goes with it. `ons-countries-2025` and `ons-counties-2025` fill `admin_areas` with the four nations and ONS's counties and unitary authorities, simplified to 20 m as one coverage so neighbours share their borders, and each reaching 2 km out to sea from a coarse copy of its coast, except where it is that close to another area. A point at sea in no nation takes the nearest nation within 10 km for a new finding, and the viewers of every nation that near for context links. A finding's page gives a viewer who sees only its 1 km square the square's nation, which is none when the square meets two (`sensitivity.visible_nation`).

Eight more Historic England layers are connectors beside the scheduled monuments one, read from ArcGIS FeatureServers, except the detailed mapping, which is the Hub's 4.7 GB GeoPackage export because its FeatureServer pages time out near object id 400,000: the three Aerial Investigation and Mapping layers (detailed mapping, monument extents, project areas), Heritage at Risk 2026, Research Spatial Reports, Turning the Plough 2, the removed designations and the Greater London priority areas. They take the Hub's address, its export address and the Open Government Licence address from `he_nhle_hub.py`. A layer with no identifier of its own gets a key from `FeatureKeys` (`adapters/common.py`): a hash of the fields that name the feature and its geometry in the source's own British National Grid coordinates, to a tenth of a metre, so a change of PROJ or datum grid doesn't renumber it. The detailed mapping skips an exact repeat and tells two interpretations of one outline apart by a hash of their attributes. The project areas are survey coverage rather than finds, so `nearby()` and the record suggestions leave out records of a type in `vocab.COVERAGE_RECORD_TYPES`. HER boundaries is not a connector, because the records table has no category for it.

## Frontend

A single-page app. The map is always mounted. Panels and modes are routes layered over it: `/` explore, `/f/:id` a finding, `/r/:id` a record, `/review` second looks, `/scan` scan a square, `/i/:id` an investigation, `/u/:handle` a profile, `/account` the signed-in person's own details, `/signin/email` where an emailed link lands, `/about` and `/guide`. The API client and its types are generated from the backend's OpenAPI schema with `pnpm gen:api`, so the two sides can't drift. Vocabularies, tier definitions and the layer catalogue come from `/meta` at start-up. The frontend hard-codes none of them.

<!-- Accounts and drafts (f0/account). -->
`features/account/session.ts` is the only place that knows who is signed in. `useSession()` answers from `GET /auth/me` with `status` (loading, signed-out, signed-in, or unknown when the server couldn't be asked), `me`, `role`, `needsWelcome`, and `ready` for someone signed in and through the welcome step. A 401 from any request signs the whole interface out, and a 403 `onboarding_required` from any request asks for the session again and opens the welcome sheet (`onUnauthorised` and `onForbidden` in `api/client.ts`). Whenever the person changes, every query whose answer depends on the viewer is dropped and asked again. A sign-in or sign-out in another tab is picked up through a `localStorage` signal that holds no personal data.

A feature gates a save with `useRequireAccount()` from `features/account/requireAccount.ts`. The function it returns resolves at once with the person when they are ready. Otherwise it opens the sign-in sheet, or the welcome sheet, over the current view, and resolves when they are ready or rejects with `AccountRequiredError` if they close it. When the session isn't known and the server can't be asked, it says so and rejects with `SessionUnknownError`, a kind of `AccountRequiredError`, rather than treating the person as signed out. A provider sign-in is a full-page round trip, so work that has to survive it is a draft. The sign-in sheet's provider buttons are links to `/auth/oauth/{provider}/start?next=`, with `next` set to the current path and map position. `features/account/next.ts` checks every `next` by the rules in "Accounts", and the app follows one only through the router. The emailed link's token is taken out of the address before the app renders (`features/account/emailLink.ts`), held in memory only, and sent nowhere but `POST /auth/email/verify`. A `signin_error` in the address opens the sign-in sheet with a message for its code and is then removed.

`features/drafts/store.ts` keeps signed-out work in `localStorage` under `fieldclub.drafts` as `{version: 2, epoch, drafts: [...]}`. A draft is `{id, kind, data, owner, createdAt, updatedAt, state}`, where `kind` is one of `DRAFT_KINDS` (finding, observation, square) and `data` is the owning feature's JSON, at most `MAX_DRAFT_CHARS` long. A feature defines its kind once with `defineDraftKind<T>({kind, label, parse, save, describe})` from `features/drafts/savers.ts`, which registers the saver and returns `put(data: T, id?)` and `read(draft)` bound to that kind; `useKindDrafts(kind)` reads its drafts in a component with typed data, and `DraftBadge` goes beside anything drawn from one. `put` throws `DraftTooLargeError` for data too big to keep and `DraftBusyError` while the draft is being saved. A browser can be shared, so `owner` records who made each draft: the account (`accountIdentity(me)`, which still uses the account's creation time and should move to `Me.id`), or the signed-out epoch. When someone signs in, the drafts made signed out in the current epoch become theirs and a new epoch starts. Once the person is ready, every waiting draft of theirs with a saver is saved exactly once: one run at a time in a page, a Web Lock across tabs, and a claim on each draft in storage. A saved draft is removed, unless it was changed while it was being sent. A failed one stays with its reason. Drafts that aren't the signed-in person's are never saved unasked: the drafts bar asks whether to save them as theirs or discard them. Signing out with drafts in the browser asks whether to keep them, and deleting the account discards them unless told not to. An unreadable store is copied aside under `fieldclub.drafts.unreadable.<time>`, an older version is migrated, and a newer build's store is left alone. When the browser won't store everything, what it refuses stays in memory and the rest, removals above all, is still stored. Fixture mode registers one stand-in kind, `fixture_probe`, for the end-to-end tests. Nothing else registers a saver yet.

`pnpm e2e` runs the end-to-end tests in fixture mode. `pnpm e2e:full` runs `frontend/e2e-full/` against the real backend. It creates a database called `fieldclub_e2e_<pid>` on the development PostGIS server, starts the backend in the test environment with the development sign-in on (port `FIELDCLUB_E2E_API_PORT`, default 6198), starts Vite proxying to it (port `FIELDCLUB_E2E_PORT`, default 5198), and drops the database at the end. Outside tile services and terrain tiles are stubbed. The sign-in sheet offers the development sign-in only when `/meta` says `auth.dev_login: true`, which the backend now sends, though these tests still add it to the `/meta` answer themselves. The backend's output goes to a log file, where `e2e-full/support/inbox.ts` reads the emailed sign-in links its log mailer writes. `GET /auth/dev-outbox` gives the same links without the log, for the tests to move to, so the emailed link is tested end to end in the browser that asked for it and in another. Add a spec for any flow fixture mode can't prove.
