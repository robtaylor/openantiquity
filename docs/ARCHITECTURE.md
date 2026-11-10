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
    main.py                 create_app(): routers auto-registered from fieldclub.api
    vocab.py                feature classes, periods, evidence kinds, tiers, checks
    layers.py               map layer catalogue served by /meta
    storage.py              Storage protocol, LocalStorage, GcsStorage
    ratelimit.py            in-memory token buckets as FastAPI dependencies
    gridref.py              OSGB and Irish grid conversion and parsing
    models/                 one file per domain, all imported by models/__init__.py
    schemas/                Pydantic request and response models, one file per domain
    api/                    one router module per domain, each exposes `router`
    services/               business logic with no FastAPI imports
    auth/                   sessions, the welcome step, magic links, OAuth
    terrain/                elevation sources, visualisations, tile rendering, cache
    ingest/                 connector base, registry, CLI, connectors/
    jobs/                   scheduled work (channel scan, source refresh)
  tests/                    mirrors src layout; conftest.py owns the database fixtures
frontend/
  src/
    api/                    typed client generated from the OpenAPI schema
    map/                    MapLibre setup, layer control, compare, terrain controls
    features/               findings, review, squares, records, investigations, account
    ui/                     shared components and design tokens
infra/
  docker-compose.yml        local PostGIS on port 54329
  Dockerfile                multi-stage build: frontend, then backend serving it
  terraform/                Cloud Run, Cloud SQL, buckets, secrets, scheduler
docs/
  DESIGN.md  ARCHITECTURE.md  DATA_SOURCES.md  adr/
```

## Conventions

- Database access goes through SQLAlchemy sessions from `get_db`. Write explicit `select()` statements. Don't rely on lazy-loaded relationships.
- Services take a `Session` and plain values, and return models or dataclasses. Routers translate between HTTP and services. Services never import FastAPI.
- Every error raised on purpose is a subclass of `AppError` with a stable `code`. The handler returns `{"error": {"code": ..., "message": ...}}`.
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
| `magic_links` | `email*`, `token_hash*` unique, `user_id`, `expires_at*`, `used_at` |
| `reputation_events` | `user_id*`, `delta*`, `reason*`, `finding_id` |

### Findings

| Table | Columns |
|-------|---------|
| `findings` | `public_id*` unique, `author_id*`, `title*`, `description`, `feature_class*`, `community_class`, `period*`, `location*` Point, `location_public*` Point, `outline` Geometry, `sensitivity*` (open, protected, restricted), `view_state*` jsonb, `nation`, `grid_ref`, `tier*`, `state*`, `state_reason`, `confidence*` smallint, `assessment*` jsonb, `observation_count*`, `evidence_count*`, `comment_count*`, `mention_count*`, `updated_at*`, `tier_changed_at`, `hidden_at` |
| `observations` | `finding_id*`, `user_id*`, `visible*` (yes, unsure, no), `feature_class`, `period`, `explanation` (modern, natural, artefact), `not_modern` bool, `not_natural` bool, `not_artefact` bool, `note`, `updated_at*`. Unique on finding and user |
| `evidence` | `finding_id*`, `user_id*`, `kind*`, `stance*` (supports, neutral, contradicts), `title`, `note`, `url`, `record_id`, `relation` (same_as, part_of, related), `media_id`, `occurred_on` date, `organisation`, `reference`, `outcome` (supports, inconclusive, contradicts), `data` jsonb, `verified_by`, `verified_at`, `deleted_at` |
| `evidence_votes` | `evidence_id*`, `user_id*`, `value*` (+1 or -1). Primary key on both |
| `comments` | `finding_id*`, `user_id*`, `body*`, `parent_id`, `edited_at`, `deleted_at` |
| `mentions` | `finding_id*`, `user_id`, `kind*` (video, article, podcast, paper, broadcast, social), `url*`, `canonical_url*`, `provider`, `title`, `author_name`, `thumbnail_url`, `published_at`, `start_seconds`, `note`, `auto_detected*`. Unique on finding and canonical URL |
| `follows` | `user_id*`, `finding_id*`. Primary key on both |
| `media` | `user_id*`, `storage_key*`, `content_type*`, `width`, `height`, `bytes*`, `sha256*`, `approved_at`, `approved_by` |

`view_state` records what the finder was looking at: `{layer, zoom, bearing, pitch, sun_azimuth, sun_altitude, exaggeration}`. Opening a finding restores it, so everyone starts from the same picture.

### Records

| Table | Columns |
|-------|---------|
| `sources` | `key*` text primary key, `name*`, `publisher*`, `licence*`, `licence_url`, `attribution*`, `reuse*` (open, share_alike, non_commercial, link_only), `homepage`, `coverage`, `category*`, `access*` (bulk, live, deeplink), `record_count`, `last_ingest_at`, `enabled*` |
| `records` | `source_key*`, `external_id*`, `name*`, `summary`, `category*`, `record_type`, `monument_types` text[], `periods` text[], `geom*` Geometry, `centroid*` Point, `precision_m`, `url`, `raw` jsonb, `source_updated_at`, `ingested_at*`, `search` tsvector generated. Unique on source and external id |
| `ingest_runs` | `source_key*`, `started_at*`, `finished_at`, `status*`, `stats` jsonb, `error` |
| `places` | `name*`, `kind*`, `district`, `county`, `nation`, `geom*` Point, `rank*`, `source*`. Gazetteer for the search box |
| `admin_areas` | `kind*` (nation, county), `code*`, `name*`, `geom*` MultiPolygon. Unique on kind and code. Used to work out which nation and county a point is in |

`sources.reuse` classes each source by what its licence allows, per Decision 0004. Field Club is non-commercial, so `non_commercial` sources are ingested. Exports carry the licence per record.

`sources.access` follows Decision 0007. A `bulk` source is stored in `records`. A `live` source is queried by the browser when someone looks at an area and is never stored on our servers. A `deeplink` source is only linked. A finding linked to a live or deep-link record stores the record's identifier and address in the evidence row and nothing else.

`records.category` is one of `designation`, `monument`, `find`, `event`, `document`, `community`, `map_label`. It drives map layers and filters. `precision_m` records how exact the position is. A Portable Antiquities find published to a 1 km square has `precision_m = 1000`.

### Collaboration around findings

| Table | Columns |
|-------|---------|
| `investigations` | `public_id*` unique, `owner_id*`, `title*`, `summary`, `notes` markdown, `area` Geometry, `visibility*` (public, unlisted, private), `updated_at*` |
| `investigation_members` | `investigation_id*`, `user_id*`, `role*` (owner, editor, viewer). Primary key on both |
| `investigation_items` | `investigation_id*`, `kind*` (finding, record, view, note, reference, profile), `finding_id`, `record_id`, `title`, `note`, `data` jsonb, `position*`, `added_by*` |
| `square_surveys` | `user_id*`, `square*` (1 km grid reference such as SU1069), `geom*` Polygon, `result*` (nothing, marked, skipped), `findings_count*`, `seconds`. Unique on user and square |
| `activity` | `kind*`, `actor_id`, `finding_id`, `investigation_id`, `data` jsonb, `location` Point |
| `notifications` | `user_id*`, `kind*`, `actor_id`, `finding_id`, `data` jsonb, `read_at` |
| `reports` | `reporter_id*`, `target_kind*`, `target_id*`, `reason*`, `note`, `status*` (open, upheld, dismissed), `resolved_by`, `resolved_at` |
| `watch_channels` | `provider*`, `channel_id*`, `title`, `last_checked_at`, `enabled*`. Channels scanned for links back to findings |

### Indexes that matter

- `GIST (location)`, `GIST ((location::geography))`, `GIST (location_public)` and `GIST ((location_public::geography))` on `findings`.
- `GIST (geom)`, `GIST ((centroid::geography))`, `GIN (search)` and a trigram `GIN (name gin_trgm_ops)` on `records`.
- Trigram `GIN (name gin_trgm_ops)` and `GIST (geom)` on `places`.
- `(finding_id)` on every child table of findings. `(user_id, read_at)` on `notifications`. `(created_at DESC)` on `activity`.

## Confidence engine

`services/confidence.py` exposes one pure function, `assess(inputs) -> Assessment`. It reads nothing from the database. `services/findings.py` gathers the inputs, calls it after every change to a finding's observations, evidence or votes, stores the result on the finding, and emits activity when the tier or state changes. The rules below are the specification. Thresholds live in one `Thresholds` dataclass so they can be tuned without touching logic.

### Weights

A person's weight is set by role: member 1.0, trusted 1.5, expert 3.0. Moderators and admins count as trusted. The finder's own opinion never counts towards visibility. Every contributor is a signed-in account, so there is no lower weight for anonymous input.

### Quantities

- `seen` is the summed weight of other people who answered "yes, I can see it". `unseen` is the same for "no". `observers` is the number of distinct people who answered yes.
- `seen_ratio = seen / (seen + unseen)` when the denominator is positive.
- Class support sums weight per feature class over the finder's class and every observation that names one. `unknown` is ignored. `class_agreement` is the top class's share. When agreement is at least 2/3 and total support is at least 2.0, the top class becomes `community_class`.
- An evidence item stands when its weighted vote total is not negative and it isn't deleted. It's independent when someone other than the finder added it, or someone other than its contributor endorsed it with weight of at least 1.0.
- Strands group evidence kinds: `lidar_view` is lidar, `aerial` is aerial, `historic_map` is historic map, `record_link` (relation related or part_of) is records, `document` is literature, `photo` and `field_visit` are ground, `geophysics` and `excavation` are survey, `her_record`, `designation` and `publication` are official. The desk strands are lidar, aerial, historic map, records and literature. A strand is supporting when it has at least one standing, independent item with stance `supports`.
- Each check (`not_modern`, `not_natural`, `not_artefact`) is cleared when the weight asserting it is at least 2.0 and more than twice the weight of observations giving the matching explanation.

### Tiers

| Tier | Label | Requires |
|------|-------|----------|
| `spotted` | Spotted | Nothing. Every finding starts here |
| `seen` | Seen by others | `seen >= 2.0`, `observers >= 2`, `seen_ratio >= 0.67` |
| `corroborated` | Corroborated | Seen, plus two supporting desk strands, plus `class_agreement >= 0.67` from at least two people |
| `probable` | Probable | Corroborated, plus all three checks cleared, plus a yes from a trusted or expert reviewer or `seen >= 7.0` |
| `ground_checked` | Checked on the ground | A standing ground or survey item with outcome `supports`, endorsed with weight 1.0 by someone else or added by a trusted or expert user. Doesn't require the earlier tiers |
| `confirmed` | On record | A standing official item verified by an expert or moderator. Doesn't require the earlier tiers |

### States

A finding's state is separate from its tier.

| State | When |
|-------|------|
| `open` | Default |
| `known` | A standing `record_link` with relation `same_as` whose contributor weight plus endorsements reaches 2.0. The finding matches an existing record |
| `disputed` | `seen >= 2.0` and `unseen >= 2.0` with ratio between 0.33 and 0.67, or contradicting strands at least equal supporting strands, or ground items disagree |
| `ruled_out` | `unseen >= 3.0` with ratio at most 0.33 (reason `not_visible`), or one explanation's weight is at least 3.0 and exceeds `seen` (reason is that explanation), or a standing ground item with outcome `contradicts` and none supporting (reason `ground_check`). Never applied at `ground_checked` or above |
| `withdrawn` | The finder withdrew it |

### Score and next steps

`confidence` is a 0 to 100 number for the meter. Each tier has a base: 10, 30, 50, 70, 85, 100. Progress towards the next tier adds a share of the gap in proportion to the requirements already met. A ruled-out finding scores 0.

`next_steps` lists the unmet requirements of the next tier as `{code, prompt, ...}`. Codes are `need_observers`, `need_strand`, `need_class_agreement`, `need_check`, `need_trusted_review`, `need_ground`, `need_official`. The same codes drive the help-wanted queue, so a finding's open steps are exactly the tasks offered to other people.

### Reputation

Points are written to `reputation_events`, so a person can see where each one came from. A finding reaching seen earns its finder 2, corroborated 5, probable 10, ground checked 20, confirmed 30. An observation that matches the outcome when a finding reaches corroborated or ruled out earns 1. An evidence item endorsed by two other people earns 1. A finding that turns out to match a known record earns 1. There are no penalties. A member is promoted to trusted at 50 points.

## API

All paths are under `/api/v1`. Bodies are JSON. The session is a `fieldclub_session` cookie, HttpOnly and SameSite=Lax. Every mutating request must carry the header `X-FieldClub-Client: web`, which a cross-site form can't send. Lists are paged with `limit` and an opaque `cursor`.

| Area | Endpoints |
|------|-----------|
| Meta | `GET /meta` returns vocabularies, tier definitions, the layer catalogue, every sign-in provider marked enabled or not, and source attributions |
| Auth | `GET /auth/me`, `PATCH /auth/me`, `DELETE /auth/me`, `POST /auth/welcome`, `POST /auth/logout`, `GET /auth/oauth/{provider}/start`, `GET` and `POST /auth/oauth/{provider}/callback`, `POST /auth/email/start`, `POST /auth/email/verify`, `GET /auth/handle-suggestion`, `POST /auth/dev-login` (development and test only) |
| Findings | `GET /findings` (filters: `bbox`, `tier`, `state`, `feature_class`, `author`, `q`, `sort`; `format=geojson` for the map), `POST /findings`, `GET /findings/{public_id}`, `PATCH /findings/{public_id}`, `POST /findings/{public_id}/withdraw` |
| Observations | `PUT /findings/{public_id}/observation`, `DELETE /findings/{public_id}/observation`, `GET /findings/{public_id}/observations` |
| Evidence | `POST /findings/{public_id}/evidence`, `DELETE /evidence/{id}`, `PUT /evidence/{id}/vote`, `POST /evidence/{id}/verify` |
| Discussion | `GET` and `POST /findings/{public_id}/comments`, `DELETE /comments/{id}`, `PUT` and `DELETE /findings/{public_id}/follow` |
| Mentions | `GET` and `POST /findings/{public_id}/mentions`, `DELETE /mentions/{id}`, `POST /mentions/preview`, `GET /mentions/recent` |
| Review | `GET /review/next` (blind cards: place and view only, with no title, class, tier or other answers until the reviewer has answered), `GET /review/tasks` (open next steps grouped by code) |
| Squares | `GET /squares/next`, `PUT /squares/{ref}`, `GET /squares/coverage?bbox=` |
| Records | `GET /records/search`, `GET /records/nearby`, `GET /records/{id}`, `GET /sources`, `GET /findings/{public_id}/suggested-records` |
| Context | `GET /context/nearby?lon=&lat=` (live lookups, cached), `GET /context/links?lon=&lat=` (deep links to external viewers) |
| Geo | `GET /geo/search?q=` (grid reference, coordinates, place, record or finding id), `GET /geo/point?lon=&lat=` (grid reference, nation, elevation) |
| Terrain | `POST /terrain/profile` (elevation along a line), `GET /terrain/coverage?bbox=` (the 5 km tiles that have 1 m elevation, as GeoJSON) |
| Investigations | `GET` and `POST /investigations`, `GET`, `PATCH` and `DELETE /investigations/{public_id}`, items and members sub-resources, `GET /investigations/{public_id}/export?format=` |
| Exports | `GET /findings/{public_id}/export?format=geojson|csv` |
| People | `GET /users/{handle}`, `GET /users/{handle}/findings`, `GET /users/{handle}/contributions` |
| Activity | `GET /activity`, `GET /events/stream` (server-sent events), `GET /notifications`, `POST /notifications/read` |
| Media | `POST /media`, `GET /media/{id}` |
| Moderation | `POST /reports`, `GET /mod/reports`, `POST /mod/reports/{id}/resolve`, `POST /mod/findings/{public_id}/hide`, `PUT /mod/users/{handle}/role`, `PUT /mod/findings/{public_id}/sensitivity` |

Tile endpoints sit outside `/api/v1` so a CDN can cache them by path:

| Path | Returns |
|------|---------|
| `/tiles/lidar/{style}/{z}/{x}/{y}.png` | A rendered terrain visualisation, 512 px |
| `/tiles/dem/{z}/{x}/{y}.png` | Elevation in Terrarium encoding, 512 px, for client-side shading and 3D |
| `/tiles/records/{z}/{x}/{y}.mvt` | Records as vector tiles. Aggregated counts at low zoom, features at high zoom |

### Accounts

Anyone can read everything public without signing in: the map, findings, records, investigations, activity. Every write needs a session. There are no guest accounts, so every stored contribution belongs to a real account.

People can still try the tool before joining. Marking a finding, answering a second look and scanning a square all work signed out, and the result is held in the browser as a draft. Drafts never reach the server. Pressing save opens the sign-in sheet, and after sign-in the frontend submits the drafts. Drafts live in `localStorage` because the provider redirect reloads the page.

Sign-in is by provider, with no passwords. Google, Apple, Microsoft and Facebook are the main ones, and OpenStreetMap is offered too because many contributors have an account there. Each provider is enabled only when its credentials are configured. An emailed one-time link is the fallback for people who use none of them. Providers run as a server-side authorisation-code flow with `state` and PKCE. The callback verifies the identity, finds or creates the user, sets the session cookie and redirects to the `next` path it was given, which must be a relative path on this site.

A first sign-in creates the user with a display name from the provider and a generated handle such as `QuietBarrow42`. A welcome sheet lets them change both. A second provider that asserts the same verified email is linked to the same user. An unverified email never links accounts.

Contributors must be 16 or over. The welcome sheet asks for an age band, 16 to 17 or 18 and over, and for acceptance of the contributor terms, and `POST /auth/welcome` stores both, once. Until then `age_band` and `terms_accepted_at` are empty, and every route that stores a contribution refuses with code `onboarding_required`. A bio is public free text, so it counts: `PATCH /auth/me` refuses a non-empty `bio` until the welcome step is done. Changing handle, display name or settings, and clearing a bio, stay open. An account in the 16 to 17 band shows only its handle, never a provider name or picture, and so does an account that hasn't chosen a band. The minimum age is the setting `FIELDCLUB_MIN_AGE`, 16 to 18. At 17 or 18 only the 18-and-over band is accepted, and accounts already in a lower band are refused with `below_minimum_age`. See Decision 0009.

There is no private messaging and no private channel between members. A private investigation has exactly one member. Adding a collaborator requires making it public or unlisted, and moderators can read unlisted investigations. An uploaded photo is shown to other people only after a moderator or trusted member approves it. The people who may approve photos see unapproved ones, so they can judge them, and nobody approves their own.

`POST /auth/dev-login` signs in as a named test user. It exists only when `FIELDCLUB_ENV` is `dev` or `test` and is how local development and end-to-end tests get a session.

`DELETE /auth/me` removes the email, identities and sessions and marks the user deleted. Their contributions stay, credited to "former member", because they were published under an open licence and other people's work builds on them.

### The meta document

`GET /meta` is the one place the frontend learns vocabularies and layers. Its shape:

```json
{
  "app": {"name": "Field Club", "version": "0.1.0", "contribution_licence": "CC BY 4.0"},
  "auth": {"providers": [{"id": "google", "label": "Google", "enabled": true}, {"id": "apple", "label": "Apple", "enabled": false}, {"id": "email", "label": "Email link", "enabled": true}]},
  "vocab": {
    "feature_classes": [{"id": "enclosure", "label": "Enclosure", "hint": "...", "fish_term": "ENCLOSURE"}],
    "periods": [{"id": "iron_age", "label": "Iron Age", "hint": "800 BC to AD 43"}],
    "evidence_kinds": [{"id": "aerial", "label": "Aerial photo", "strand": "aerial", "group": "desk", "hint": "..."}],
    "tiers": [{"id": "seen", "label": "Seen by others", "description": "...", "base_score": 30}],
    "states": [{"id": "known", "label": "Matches a known record", "description": "..."}],
    "checks": [{"id": "not_modern", "question": "Could it be modern?", "hint": "..."}],
    "explanations": [{"id": "modern", "label": "Modern feature", "hint": "..."}],
    "mention_kinds": [{"id": "video", "label": "Video"}],
    "record_categories": [{"id": "designation", "label": "Designations", "colour": "#d9544d"}]
  },
  "layers": {
    "views": [
      {
        "id": "composite", "title": "Composite", "description": "...",
        "group": "lidar", "type": "raster",
        "tiles": ["/tiles/lidar/composite/{z}/{x}/{y}.png"],
        "tile_size": 512, "minzoom": 7, "maxzoom": 16,
        "attribution": "...", "bounds": null, "default": true
      },
      {"id": "raking", "title": "Raking light", "group": "lidar", "type": "raking", "description": "...", "attribution": "..."}
    ],
    "dem": {
      "tiles": ["/tiles/dem/{z}/{x}/{y}.png"], "tile_size": 512, "encoding": "terrarium",
      "minzoom": 7, "maxzoom": 16, "attribution": "..."
    },
    "overlays": [
      {"id": "osm", "title": "OpenStreetMap", "type": "openmaptiles", "tilejson": "...", "glyphs": "...", "default_opacity": 0.8, "attribution": "..."},
      {"id": "records", "title": "Heritage records", "type": "records", "tiles": ["/tiles/records/{z}/{x}/{y}.mvt"]},
      {"id": "findings", "title": "Findings", "type": "findings"},
      {"id": "coverage", "title": "Scan coverage", "type": "coverage"}
    ],
    "initial_view": {"center": [-1.8542, 51.4286], "zoom": 14}
  },
  "sources": [{"key": "nhle-scheduled", "name": "...", "publisher": "...", "licence": "...", "attribution": "...", "homepage": "...", "category": "designation", "record_count": 0}],
  "notices": {"field_visit": {"england": ["..."], "scotland": ["..."], "wales": ["..."], "northern_ireland": ["..."]}, "field_visit_16_17": "...", "sensitivity": "..."}
}
```

A view layer of type `raster` is a tiled image. `group` is one of `lidar`, `imagery`, `historic`, `map`, `geology`. The single `raking` view is drawn in the browser as a hillshade of the `dem` source, with the sun position under the user's control. Any view can be the main layer or the comparison layer. Overlays stack above with their own opacity. The `osm` overlay is an OpenMapTiles-schema vector source that the frontend styles as thin lines and labels.

### Location sensitivity

See Decision 0005. A finding's `sensitivity` is `open`, `protected` or `restricted`. `location_public` holds the position anyone may see: the exact point for an open finding, and the centre of its 1 km grid square otherwise. It's written whenever the finding is saved through the ORM, so a change of level or location never goes through a bulk `UPDATE`. A database trigger refuses an open finding whose public position differs from its location, and a change from open to a higher level that leaves the public position exact. It can't check the square itself, because the grid is in Python.

| Viewer | open | protected | restricted |
|--------|------|-----------|------------|
| Signed out | exact | 1 km square | 1 km square |
| Member | exact | exact | 1 km square |
| Finder, trusted, expert, moderator | exact | exact | exact |

A generalised finding is returned with `obscured: true`, the square's reference, and no outline. The default level comes from the feature class: round barrow, long barrow, ritual monument and settlement earthworks default to `protected`, everything else to `open`. The finder, a trusted user or a moderator can raise a level. Only a moderator can lower one. A new finding starts at the higher of its class default and the level requested, and a request below the default is honoured only from a moderator (`starting_sensitivity`). Changing the feature class to one with a higher default raises the level to that default. It never lowers a level, and a change between classes with the same default leaves the level alone (`level_after_class_change`, applied when the finding is saved). Experts and admins count as trusted here, and admins as moderators.

One function in `services/sensitivity.py` decides what a viewer sees, and every route that returns a finding goes through it. Queries on behalf of signed-out visitors filter and sort on `location_public` only. Downloads use the generalised position for protected and restricted findings unless the person downloading is the finder or trusted.

Findings reach the map through `GET /findings?bbox=&format=geojson`, not through cacheable tiles, because the answer depends on the viewer. The `bbox` matches the position the viewer is allowed to see, so an obscured finding matches by the centre of its square. The frontend widens the box it asks for by 500 m on each side so that a square covering the view is returned even when its centre is off screen.

## Events

`services/activity.py` has `record(db, kind, actor, finding=None, investigation=None, data=None)`. It inserts an `activity` row, creates notifications for the finding's followers, and after commit sends a small payload through PostgreSQL `NOTIFY fieldclub_events`. One listener per process fans payloads out to connected event-stream clients. Because the bus is PostgreSQL, it works across Cloud Run instances.

Activity kinds: `finding_created`, `tier_changed`, `state_changed`, `observation_added`, `evidence_added`, `comment_added`, `mention_added`, `followup_logged`, `investigation_published`.

## Terrain service

The shape is fixed. The sources are filled in from `docs/DATA_SOURCES.md`.

`terrain/sources.py` defines `ElevationSource.read(bounds_3857, width, height) -> float32 array` with NaN for no data. There's one implementation per upstream service and a `Mosaic` that asks sources in priority order and fills gaps. `terrain/render.py` asks the mosaic for a tile's bounds plus a buffer, so neighbourhood filters have real data at tile edges, then crops. The buffered elevation array is cached once per tile, so switching style doesn't hit the upstream again. Rendered tiles are cached too. Both caches use `Storage`, which is local disk in development and a bucket in production.

`terrain/visualise.py` holds the pure numpy functions: hillshade, multi-directional hillshade, slope, local relief, sky-view factor, openness, and the blends. Each takes elevation and ground resolution in metres and returns an array with a fixed stretch, so adjacent tiles always match. Kernel sizes are given in metres and converted to pixels per zoom.

<!-- Terrain (b1/terrain) -->
Elevation is read only from the mirror (`terrain/mirror.py`): one COG per 5 km tile, LERC_ZSTD at 1 cm, 512-pixel blocks, overviews at 2, 4 and 8 m, in a local folder or under `gs://`. A tile that isn't mirrored is converted from Defra's source file on disk if it is there, or fetched from the SFTP bulk supply (`terrain/sftp.py`), once however many requests want it. `terrain/catalogue.py` lists the 5,877 tiles, so a tile that doesn't exist costs no network call. From zoom 13 up, map tiles read the 1 m mirror and fetch what is missing. Below 13 they read the national 10 m composite, or, until it is built, the overviews of tiles already mirrored, uncached. `fieldclub-terrain` mirrors tiles, warms the tile cache and reports on both. The styles, their parameters and versions are in `terrain/styles.py`.

## Ingest

A connector subclasses `ingest.base.Connector`, declares its `Source` row, and implements `fetch() -> Iterator[RecordIn]`. The runner batches upserts on `(source_key, external_id)`, removes rows that vanished upstream when a full run completes, and writes an `ingest_runs` row. `uv run fieldclub-ingest list|run <key> [--bbox] [--limit]` drives it. Runs are idempotent. Connectors hold no credentials. A source that needs a key reads it from settings and is skipped when the key is absent.

## Frontend

A single-page app. The map is always mounted. Panels and modes are routes layered over it: `/` explore, `/f/:id` a finding, `/r/:id` a record, `/review` second looks, `/scan` scan a square, `/i/:id` an investigation, `/u/:handle` a profile, `/about` and `/guide`. The API client and its types are generated from the backend's OpenAPI schema with `pnpm gen:api`, so the two sides can't drift. Vocabularies, tier definitions and the layer catalogue come from `/meta` at start-up. The frontend hard-codes none of them.
