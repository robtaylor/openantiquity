# Decision 0001 — Plain synchronous endpoints

**Status:** Proposed.

**TL;DR.** In the context of an API whose work is SQL, upstream HTTP and numpy rendering, facing async SQLAlchemy's failure modes across many parallel contributors, we chose plain synchronous endpoints on FastAPI's thread pool to keep the code simple and keep CPU work off the event loop, accepting that each in-flight request holds a thread.

## Context

Nothing was built when this was written. The backend foundation was in progress.

The API had three kinds of work to do: SQL, HTTP calls to upstream map and data services, and numpy rendering of terrain tiles. Many hands were going to write endpoints, including automated agents working in parallel against a shared contract.

Async SQLAlchemy had sharp edges for that kind of team. A lazy-loaded attribute raised `MissingGreenlet`. Every function on a call path had to be `async`. CPU-bound work such as tile rendering blocked the event loop unless it was pushed to a thread anyway.

## Decision

1. Endpoints are plain `def` functions. FastAPI runs them in its thread pool.
2. Database access uses synchronous SQLAlchemy 2 sessions on psycopg 3.
3. Outbound HTTP uses one shared synchronous `httpx.Client`.
4. The server-sent event stream is the only `async` endpoint. One listener per process on PostgreSQL `NOTIFY` feeds it.

## Alternatives considered

- **Async everywhere** (SQLAlchemy asyncio on asyncpg) was rejected because its failure modes are easy to hit and hard to review, and the tile path would still have needed a thread for numpy.
- **Async for the terrain path only** was rejected because two session styles would have doubled the fixtures and the review surface for a gain we hadn't measured.
- **A separate terrain service from the start** was rejected as premature. It's the first walk-back option below.

## Consequences

- The code is simpler to write and review, and tests use the ordinary `TestClient`.
- Rendering a tile doesn't stall other requests, because it never runs on the event loop.
- Each request holds a thread for its whole duration, including time spent waiting on an upstream service. One instance serves about forty requests at once. Cloud Run adds instances as load rises, so this bounds efficiency, not capacity.

## Walk-back options

- **If slow upstream elevation fetches starve the thread pool** and API latency suffers, run terrain tiles as their own Cloud Run service with its own pool. The tile routes are already mounted outside `/api/v1`, so the split needs no API change.
- **If one endpoint needs very high concurrency**, make that endpoint `async` with its own client. Don't convert the rest.

## Links

- Decision 0002 covers who may call the write endpoints.
