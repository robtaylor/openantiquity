# Decision 0027 — The web app never fetches elevation, and a deploy checks the mirror first

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Terrain service"](../../ARCHITECTURE.md#terrain-service).

**TL;DR.** In the context of a web app on Fly that holds no supply login, facing squares that answer "unavailable" when an elevation tile is missing, where Decision 0016 has them answer "being prepared", we chose to keep the web app from fetching, hold the whole mirror from the start, and have each deploy check the mirror before it replaces anything, to keep Defra's login out of the public service without letting a gap arrive unseen, accepting that a tile lost between deploys stays blank until someone runs the mirror job.

## Context

When this was written the web app on Fly ran with `FIELDCLUB_TERRAIN_API_FETCH=false`. A map tile that needed an elevation tile the mirror lacked was answered 503 `elevation_unavailable` for a minute at a time. Nothing checked the mirror at a deploy.

Decision 0016, point 1, has a request for a missing tile start fetching it and answer `elevation_preparing`. Decision 0018, point 7, gave Defra's supply login only to the app that copies elevation, and gave no reason. The Google deployment had a switch for the same thing, `service_fetches_elevation`, and it was applied as false.

What was found on 2026-11-12:

- The fetcher knew only the 5,877 tiles of the 2022 composite, a list packaged with the code (`terrain/catalogue.py`). All 5,877 were in the Tigris bucket that day, copied from Google's and checked against it. A fetch on demand could therefore only replace a tile that had gone from the bucket.
- No code deleted a mirrored tile. The mirror deleted only its failure markers and the overview build only its own build files. A tile could go missing three ways: a person or a tool deletes it; Tigris loses it or suspends the bucket; or a deploy changes what the code expects, with a larger catalogue, another mirror folder or a new format.
- The first terrain tiles asked of the web app on Fly were all answered 500, though the mirror's listing was whole. GDAL was given the Tigris endpoint through rasterio's `set_gdal_config`, which in rasterio 1.5.2 reaches only the calling thread. Tiles are drawn on threads of their own, and there GDAL asked amazonaws.com for the bucket. No test had seen it, because none reads a bucket.

The owner asked for the data to be moved once, which was done, then for a pre-flight check, and asked whether the app could make it at start-up.

## Decision

1. The web app on Fly holds no supply login and adds nothing to the mirror. The login was issued to the owner under a Defra ticket. A public service has no use for it once the mirror is whole, and the web app's key only reads the elevation bucket, so a fault in the public service can't alter the mirror.
2. On Fly a missing tile is answered `elevation_unavailable`. "Being prepared" stays where the API fetches, which is development.
3. Each deploy runs `fieldclub-release` before any machine is replaced. It first runs `fieldclub-terrain check`, which compares the catalogue with the mirror's listing and reads one tile through GDAL on a thread of its own. The deploy stops when more tiles are missing than `FIELDCLUB_TERRAIN_CHECK_ALLOW_MISSING`, which is 0, or when the tile can't be read. The schema is created only after the check passes.
4. The check only looks. A missing tile is added by the mirror job, by a person.
5. A server that can't add tiles lists the mirror when it starts, and logs an error whenever the tiles it lacks change. It never refuses to start over them.

## Alternatives considered

- **Give the web app Defra's login, so it fetches on demand** — rejected for the reasons in point 1. It would have restored "being prepared" exactly.
- **Have the hourly machine fetch what the web app found missing** — rejected because it needs the web app to tell the jobs app what it missed, and buys only the repair of a lost tile.
- **Fetch whatever is missing at each deploy** — rejected because against an empty bucket it would ask Defra for the country again, and because GitHub's deploy token reaches only the web app, so it couldn't run with the deploy.
- **Refuse to start when a tile is missing** — rejected because any restart with one tile missing would then take the whole site down for a blank square.
- **Check the listing alone** — rejected after the fault above: the listing was whole while no tile could be drawn.

## Consequences

- A deploy can't bring in a larger catalogue, another mirror folder or a GDAL fault without someone seeing it first.
- A tile lost between deploys stays blank until the mirror job is run. The log says so within a minute, and `/api/v1/meta` gives both counts.
- A deploy needs the bucket to answer. While Tigris can't be listed nothing deploys, unless `release_command` in `fly.toml` is set back to the schema command for that deploy.
- The first deploy of a fresh setup comes before the mirror is filled, so it has to allow every tile to be missing.
- An image built before `fieldclub-release` existed can't be deployed with a `fly.toml` that names it. Rolling back that far means deploying from that commit's checkout.

## Walk-back options

- **If tiles go missing between deploys often enough to matter** — have the hourly machine run `fieldclub-terrain mirror --all` once a day. It lists the mirror first and connects to Defra only when something is missing.
- **If "unavailable" confuses people** — draw a missing tile from the national overview, marked as such, which Decision 0016 already names as its own walk-back.

## Links

- Decision 0016 — the "being prepared" answer, which this narrows to where the API fetches.
- Decision 0018 — point 7, the rule this gives the reason for.
- Decision 0006 — the mirror and the bulk supply.
- Decision 0012 — the national overview.
