"""Drawing terrain tiles on threads of their own, so tiles can't starve the rest of the API.

FastAPI runs every plain `def` endpoint on one shared pool of worker threads
(anyio's, 40 by default). A map asks for a screenful of tiles at once, and
reading and drawing each takes a while, so if tiles ran there a few busy maps
would hold every thread and nothing else, `/meta`, findings or sign-in, would
be answered. The tile endpoints are `async` instead, and hand each tile to
`TileWorkers`:

- at most `workers` tiles are drawn at once, on this pool's own threads;
- at most `queue` more wait their turn, as coroutines on the event loop,
  which hold no thread;
- past that a tile is answered at once with 503 `tiles_busy` and a
  `Retry-After`, rather than waiting behind work its map may have panned
  away from.

So the shared pool is never taken by tiles, and tile work in hand is bounded.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from fieldclub.terrain.errors import TilesBusyError


class TileWorkers:
    def __init__(self, workers: int, queue: int) -> None:
        assert workers >= 1, "at least one tile must be drawn at a time"
        assert queue >= 0, "a queue can't be shorter than nothing"
        self.capacity = workers + queue
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tiles")
        self._guard = threading.Lock()
        self._in_hand = 0

    @property
    def in_hand(self) -> int:
        """Tiles being drawn or waiting their turn."""
        return self._in_hand

    async def run[T](self, draw: Callable[..., T], *args: object) -> T:
        """Draw a tile on this pool, or raise `TilesBusyError` when the pool and its queue are full."""
        with self._guard:
            if self._in_hand >= self.capacity:
                raise TilesBusyError()
            self._in_hand += 1
        try:
            return await asyncio.wrap_future(self._pool.submit(draw, *args))
        finally:
            with self._guard:
                self._in_hand -= 1

    def close(self) -> None:
        """Draw nothing more, and drop the tiles waiting their turn."""
        self._pool.shutdown(wait=False, cancel_futures=True)
