"""Adding the 5 km tiles a map or a profile asks for to the mirror in the background.

A tile missing from the mirror takes from 13 seconds to three minutes to
fetch from the bulk supply and convert. A request that waited for it would
hold one of the server's worker threads all that time, and a screenful of
such map tiles would hold all of them, so nothing else would be answered.
So a request never waits: `Prefetcher.request` starts adding what is
missing on a small pool of its own and says what is still missing, and the
caller answers `elevation_preparing` with a `Retry-After`.

- Each tile is added once however many requests want it: a tile already
  being added isn't queued again.
- The pool has as many threads as `FIELDCLUB_TERRAIN_FETCH_CONCURRENCY`, the
  limit the mirror already puts on downloads, so a queue of missing tiles
  costs threads only in this pool.
- A tile whose last background attempt failed is answered with that failure
  for `FAILURE_MEMORY_S`, so a map asking again learns it rather than hearing
  "being prepared" for ever. The mirror's own memory of failed tiles
  (`Mirror.refuse_if_failed`) is asked first, and is longer.

`fieldclub-terrain mirror` and `warm` don't use this: they fetch in the
foreground, as a command should.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for

from fieldclub.errors import AppError
from fieldclub.terrain.catalogue import normalise_name
from fieldclub.terrain.errors import ElevationUnavailableError
from fieldclub.terrain.mirror import Mirror

logger = logging.getLogger(__name__)

# How long a failed background attempt is told to whoever asks for the tile, before it is tried again.
FAILURE_MEMORY_S = 60.0


class Prefetcher:
    def __init__(
        self,
        mirror: Mirror,
        workers: int,
        *,
        failure_memory_s: float = FAILURE_MEMORY_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        assert workers >= 1, "at least one tile must be fetched at a time"
        self.mirror = mirror
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mirror-prefetch")
        self._failure_memory_s = failure_memory_s
        self._clock = clock
        self._guard = threading.Lock()
        self._pending: dict[str, Future[None]] = {}
        # Tiles whose last background attempt failed: when to try again, and the failure's code and message.
        self._failed: dict[str, tuple[float, str, str]] = {}

    def request(self, names: Sequence[str]) -> list[str]:
        """Start adding the tiles of `names` the mirror lacks, and return those still missing.

        Raises the error of a missing tile that couldn't be added lately,
        without starting anything for it.
        """
        missing = [normalise_name(name) for name in names if not self.mirror.has(name)]
        for name in missing:
            self._refuse_if_failed(name)
            # The mirror's longer memory, which other servers sharing a bucket write too.
            self.mirror.refuse_if_failed(name)
            with self._guard:
                if name not in self._pending:
                    self._pending[name] = self._pool.submit(self._add, name)
        return missing

    def _refuse_if_failed(self, name: str) -> None:
        """Raise the failure of this tile's last background attempt, while it is remembered."""
        with self._guard:
            failed = self._failed.get(name)
            if failed is None:
                return
            until, code, message = failed
            if self._clock() >= until:
                del self._failed[name]
                return
        # A new error each time, under the failure's own code: one raised again gathers tracebacks.
        raise ElevationUnavailableError(message, code=code)

    def pending(self) -> frozenset[str]:
        """The tiles being added now, or waiting their turn."""
        with self._guard:
            return frozenset(self._pending)

    def wait(self, timeout: float | None = None) -> None:
        """Wait for every tile being added now. For tests and for shutting down."""
        with self._guard:
            futures = list(self._pending.values())
        _, not_done = wait_for(futures, timeout=timeout)
        assert not not_done, f"{len(not_done)} tiles were still being added after {timeout} s"

    def close(self) -> None:
        """Start nothing more. A tile being converted finishes; queued ones are dropped."""
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _add(self, name: str) -> None:
        started = time.perf_counter()
        try:
            self.mirror.ensure(name)
        except AppError as exc:
            self._remember(name, exc)
            logger.warning("Couldn't add %s to the mirror in the background: %s", name, exc.message)
        except Exception:
            # A bug or an unexpected failure: say "unavailable" for a while rather than retrying at once.
            self._remember(name, ElevationUnavailableError())
            logger.exception("Adding %s to the mirror in the background failed", name)
        else:
            took = time.perf_counter() - started
            logger.info("Added %s to the mirror in the background in %.1f s", name, took)
        finally:
            with self._guard:
                self._pending.pop(name, None)

    def _remember(self, name: str, error: AppError) -> None:
        with self._guard:
            self._failed[name] = (self._clock() + self._failure_memory_s, error.code, error.message)
