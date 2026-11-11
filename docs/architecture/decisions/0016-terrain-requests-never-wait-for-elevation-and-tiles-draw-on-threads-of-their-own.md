# Decision 0016 — Terrain requests never wait for elevation and tiles draw on threads of their own

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Terrain service"](../../ARCHITECTURE.md#terrain-service).

**TL;DR.** In the context of map tiles drawn from a mirror that fills on first use, facing downloads of 13 seconds to three minutes that held every worker thread and left the rest of the API unanswered, we chose to fetch missing elevation in the background and answer the request at once with `elevation_preparing`, and to draw terrain tiles in `async` endpoints on a bounded pool of their own, to keep the API answering whatever the map asks for, accepting that a first visit to an area shows "being prepared" instead of terrain until the fetch ends.

## Context

When this was written, a map tile from zoom 13 up that needed a 5 km tile missing from the mirror fetched it from Defra's bulk supply inside the request. The fetch and conversion took from 13 seconds to three minutes. The tile endpoints were plain `def` functions on FastAPI's one thread pool, 40 threads by default (Decision 0001). The people building the interface found that one screenful of tiles over an area not yet mirrored took every thread, and then `/meta`, findings and sign-in went unanswered until the downloads ended. The height profile fetched the same way. The point read never fetched.

The mirror already fetched each tile once however many requests wanted it, limited downloads to `FIELDCLUB_TERRAIN_FETCH_CONCURRENCY`, and remembered tiles that couldn't be added.

## Decision

1. No request the API serves waits for a tile to be added to the mirror. A map tile or a profile that needs one starts adding it on a pool of `FIELDCLUB_TERRAIN_FETCH_CONCURRENCY` threads of its own, each tile once, and is answered 503 `elevation_preparing` at once, with the missing tiles in `details.tiles`, a `Retry-After` and `no-cache`.
2. A tile whose background attempt failed answers that failure for a minute, so the map learns it rather than hearing "being prepared" for ever.
3. The point read still never fetches, and now says whether its height came from the 1 m data, from the overview while the 1 m tile is being prepared, or from nowhere.
4. The coverage layer says for each 5 km tile whether it is in the mirror yet, so the map can show where an area is being prepared.
5. The terrain tile endpoints are `async` and draw each tile on `FIELDCLUB_TERRAIN_RENDER_WORKERS` threads of their own, with at most `FIELDCLUB_TERRAIN_RENDER_QUEUE` more waiting as coroutines. Past that a tile is answered 503 `tiles_busy` with a `Retry-After`. The shared thread pool never runs a terrain tile.
6. The commands (`fieldclub-terrain mirror`, `warm`) still fetch in the foreground.

## Alternatives considered

- **A bound on concurrent renders alone, inside the plain `def` endpoints**, was rejected because a request waiting for a slot would still hold a thread of the shared pool, so enough waiting tiles would starve everything else in the same way.
- **A larger shared thread pool** was rejected because it only moves the point at which a busy map starves the API, and costs memory per thread.
- **Drawing a preparing tile from the national overview at 8 m, uncached,** was rejected for now because the map couldn't tell coarse terrain from the real thing, and a finder could mark what the 1 m data doesn't show. The frontend can draw the overview's zoom-12 tile beneath a preparing area instead.
- **A separate terrain service**, Decision 0001's walk-back, was rejected as more than the problem needed: the tile endpoints touch no database session, so making them `async` doesn't bring the two session styles Decision 0001 avoided.

## Consequences

- The API keeps answering while the mirror fills, whatever the maps ask for. A test fills the tile workers and their queue with stuck tiles and gets `/meta` answered at once.
- The first view of an area not yet mirrored shows nothing at zoom 13 and above until the fetch ends. The frontend has to retry after `Retry-After` and say the area is being prepared.
- Background fetches belong to the process. A server that stops mid-fetch leaves the tile to the next request that wants it, which starts it again, as a killed request did before.
- On several servers, each fetches what its own maps ask for, under the mirror's lock per tile, so a tile is still fetched once.
- Tiles past the queue are turned away rather than served late, which a map panning quickly would have abandoned anyway.

## Walk-back options

- **If people find the empty first view worse than a coarse one**, draw a preparing tile from the overview, uncached and marked as such, instead of answering 503.
- **If the tile workers are the bottleneck**, raise `FIELDCLUB_TERRAIN_RENDER_WORKERS` towards the cores the server has, or move the tiles to a service of their own.

## Links

- Decision 0001 — plain synchronous endpoints, to which the terrain tiles are now an exception.
- Decision 0006 — terrain tiles rendered from raw elevation, fetched on first use.
- Decision 0012 — the national overview the point read falls back to.
