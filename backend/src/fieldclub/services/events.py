"""The live event stream: one LISTEN per process, fanned out to every connected client.

`services.activity.record` sends a small JSON payload on the PostgreSQL
channel `fieldclub_events` when its transaction commits. Each process runs one
`EventHub`. The hub holds a single connection that LISTENs on the channel,
and hands each event to the clients of `GET /events/stream`.

How it is served (Decision 0001 makes every other endpoint synchronous):

- The stream is the one `async` endpoint. Each client is an async generator
  waiting on its own `asyncio.Queue`, so a connected client costs a queue
  and a coroutine on the event loop, not a worker thread or a database
  connection. The hub's connection is a psycopg `AsyncConnection`, also on
  the loop.
- Before an event is announced the hub asks the database, once per event
  and not once per client, whether a signed-out visitor's feed lists it
  (`feed.public_event`) and which 1 km square it is in. That short query
  runs in a worker thread with a session of its own. An event on a hidden or
  withdrawn finding, a non-public investigation, or by a banned account is
  never announced.
- Each client's queue is bounded. A client that falls that far behind is
  dropped: its queue is emptied, it gets a final `dropped` signal, and the
  hub sends it nothing more. Nothing is ever buffered for it without limit.
  It keeps its place under both caps until its response has ended
  (`unsubscribe`), because a client that stopped reading may still hold its
  connection open.
- The listener reconnects after any failure, waiting a little longer after
  each one in a row. Events sent while it was away are lost, so after a
  reconnect every client gets a `resync` signal and should refetch what it
  shows. Every `idle_check_s`, whatever arrives, and as soon as a client
  subscribes, the hub runs `SELECT 1` and gives up on the connection if no
  answer comes within `check_timeout_s`. Making a connection and its `LISTEN`
  have the same limit, so a reconnect can't hang on a peer that accepts the
  connection and never answers. TCP keepalives (`db.KEEPALIVES`)
  watch it in between. So a connection that died silently, as one may while
  Fly has the machine suspended, is noticed promptly and replaced. An event
  that can't be checked is skipped, never announced unchecked. Should the
  listener stop all the same, the next client to subscribe starts it again.
- `stop()` ends every client with a `closed` signal, so their responses
  finish and the server can shut down without waiting for them.

What a client receives (`Announcement`) is the payload as `activity` sent it:
the activity id, its kind, and the public ids of the finding, investigation
and actor. No position and nothing about an answer: a second look's events
have no actor (Decision 0008). Clients refetch through the API, which applies
the viewer's rights. A filter by box matches the centre of the finding's 1 km
square, which anyone may see, and the square never leaves the server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, LiteralString

import psycopg
from psycopg.conninfo import make_conninfo

from fieldclub.db import KEEPALIVES, SessionLocal, get_engine
from fieldclub.errors import AppError
from fieldclub.models.common import point_lon_lat
from fieldclub.schemas.common import BBox, is_bbox
from fieldclub.services import feed
from fieldclub.services.activity import EVENT_CHANNEL

logger = logging.getLogger(__name__)

# How long to wait before reconnecting after each failure in a row.
RETRY_DELAYS_S: tuple[float, ...] = (0.25, 1.0, 2.0, 5.0, 10.0)
IDLE_CHECK_S = 15.0
# How long `SELECT 1`, the `LISTEN` and making the connection may each take
# before the connection is given up for dead.
CHECK_TIMEOUT_S = 10.0
# The longest the listener waits for notifications before it looks whether a
# check is due, so a client's request for one is answered within this.
_SLICE_S = 1.0

LISTEN: LiteralString = f"LISTEN {EVENT_CHANNEL}"

_PAYLOAD_KEYS = frozenset({"id", "kind", "finding", "investigation", "actor"})


class TooManyStreamsError(AppError):
    status_code = 429
    code = "too_many_streams"
    message = "Too many live connections are open from here. Close one and try again."


class Signal(StrEnum):
    """What the hub tells a client besides events. Each is sent as an SSE event of that name."""

    # The listener reconnected and events may have been missed: refetch.
    RESYNC = "resync"
    # This client fell too far behind and has been let go. The stream ends.
    DROPPED = "dropped"
    # The server is shutting down. The stream ends.
    CLOSED = "closed"


ENDING_SIGNALS = frozenset({Signal.DROPPED, Signal.CLOSED})


@dataclass(frozen=True)
class Announcement:
    """One event as a client receives it: ids and a kind, nothing more."""

    id: int
    kind: str
    finding: str | None
    investigation: str | None
    actor: str | None

    @classmethod
    def parse(cls, payload: str) -> Announcement:
        """Read a payload from `activity.event_payload`. Raises `ValueError` for anything else."""
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != _PAYLOAD_KEYS:
            raise ValueError(
                f"unexpected event payload keys: {sorted(data) if isinstance(data, dict) else data!r}"
            )
        if not isinstance(data["id"], int) or not isinstance(data["kind"], str):
            raise ValueError("an event payload needs a whole-number id and a kind")
        for key in ("finding", "investigation", "actor"):
            if data[key] is not None and not isinstance(data[key], str):
                raise ValueError(f"an event payload's {key} must be a string or null")
        return cls(**data)


@dataclass(frozen=True)
class StreamFilter:
    """Which events a client wants: those in a box, those on one finding, or all of them."""

    bbox: BBox | None = None
    # A finding's public id, as normalised by `services.ids`.
    finding: str | None = None

    def __post_init__(self) -> None:
        assert self.bbox is None or is_bbox(self.bbox), "bbox runs west to east and south to north"

    def matches(self, event: Announcement, square: tuple[float, float] | None) -> bool:
        if self.finding is not None and event.finding != self.finding:
            return False
        if self.bbox is not None:
            if square is None:
                return False
            west, south, east, north = self.bbox
            lon, lat = square
            return west <= lon <= east and south <= lat <= north
        return True


@dataclass(frozen=True)
class Listed:
    """What the hub learns about an event the public feed lists. Never sent to a client."""

    # The centre of the finding's 1 km square, or None for an event with no finding or off the grids.
    square: tuple[float, float] | None


# Given an activity id: Listed if a signed-out visitor's feed lists it, None if not.
Lookup = Callable[[int], Awaitable[Listed | None]]


class Subscription:
    """One connected client: its filter, its address and its bounded queue."""

    def __init__(self, stream_filter: StreamFilter, address: str, queue_size: int) -> None:
        assert queue_size >= 1, "a queue holds at least one item"
        self.filter = stream_filter
        self.address = address
        self.queue: asyncio.Queue[Announcement | Signal] = asyncio.Queue(maxsize=queue_size)
        self.ended = False

    def offer(self, item: Announcement | Signal) -> bool:
        """Queue an item without waiting. False when the queue is full.

        A client that has ended takes nothing more, and that isn't a failure.
        """
        if self.ended:
            return True
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            return False
        return True

    def end(self, signal: Signal) -> None:
        """Throw away what is queued and leave only `signal`, so the client stops at once."""
        assert signal in ENDING_SIGNALS, f"{signal} doesn't end a stream"
        if self.ended:
            return
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(signal)
        self.ended = True

    async def next(self, timeout: float) -> Announcement | Signal | None:
        """The next item, or None if nothing came within `timeout` seconds."""
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except TimeoutError:
            return None


class EventHub:
    """The one listener in a process, and the clients it serves. Use it from one event loop."""

    def __init__(
        self,
        conninfo: str,
        lookup: Lookup,
        *,
        queue_size: int,
        max_per_address: int,
        max_streams: int,
        idle_check_s: float = IDLE_CHECK_S,
        check_timeout_s: float = CHECK_TIMEOUT_S,
        retry_delays_s: Sequence[float] = RETRY_DELAYS_S,
    ) -> None:
        assert max_per_address >= 1, "the cap per address must allow one stream"
        assert max_streams >= 1, "the cap per process must allow one stream"
        assert retry_delays_s, "give at least one retry delay"
        assert idle_check_s > 0, "checks need a positive interval"
        assert check_timeout_s > 0, "a check needs a positive timeout"
        self.conninfo = conninfo
        self.lookup = lookup
        self.queue_size = queue_size
        self.max_per_address = max_per_address
        self.max_streams = max_streams
        self.idle_check_s = idle_check_s
        self.check_timeout_s = check_timeout_s
        # libpq takes whole seconds, and treats anything below 2 as 2.
        self.connect_timeout_s = max(2, math.ceil(check_timeout_s))
        self.retry_delays_s = tuple(retry_delays_s)
        self.loop = asyncio.get_running_loop()
        self.connected = asyncio.Event()
        # The listening connection's server process, for diagnostics and tests.
        self.backend_pid: int | None = None
        # Clients that are sent events.
        self._subscriptions: set[Subscription] = set()
        # Clients that hold a place under the caps: those above, and those
        # dropped whose responses haven't ended yet.
        self._held: set[Subscription] = set()
        self._per_address: dict[str, int] = {}
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        # Set when the listener stopped unexpectedly, so its successor sends `resync`.
        self._lost = False
        # Set when a client arrives, so the listener checks its connection at
        # once: the first visitor to a machine just resumed may otherwise wait
        # for the next timed check to learn that its events can't come.
        self._check_soon = False

    # Clients ---------------------------------------------------------------

    def subscribe(self, stream_filter: StreamFilter, address: str) -> Subscription:
        """Add a client, or raise `TooManyStreamsError`. Starts the listener if it isn't running."""
        assert not self._stopped, "the hub has been stopped"
        if len(self._held) >= self.max_streams or self._per_address.get(address, 0) >= self.max_per_address:
            raise TooManyStreamsError()
        subscription = Subscription(stream_filter, address, self.queue_size)
        self._subscriptions.add(subscription)
        self._held.add(subscription)
        self._per_address[address] = self._per_address.get(address, 0) + 1
        self._check_soon = True
        self.start()
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Forget a client and free its place, once its response has ended. Harmless if it is already gone."""
        if subscription not in self._held:
            return
        self._held.discard(subscription)
        self._subscriptions.discard(subscription)
        remaining = self._per_address[subscription.address] - 1
        if remaining:
            self._per_address[subscription.address] = remaining
        else:
            del self._per_address[subscription.address]

    @property
    def subscriptions(self) -> frozenset[Subscription]:
        """The clients that are sent events."""
        return frozenset(self._subscriptions)

    @property
    def held(self) -> int:
        """How many places under the per-process cap are taken."""
        return len(self._held)

    def _drop(self, subscription: Subscription) -> None:
        """Stop sending to a client. Its place stays taken until `unsubscribe`."""
        logger.info("Dropping an event-stream client that fell %d events behind", self.queue_size)
        subscription.end(Signal.DROPPED)
        self._subscriptions.discard(subscription)

    def _broadcast(self, signal: Signal) -> None:
        for subscription in list(self._subscriptions):
            if not subscription.offer(signal):
                self._drop(subscription)

    async def deliver(self, payload: str) -> None:
        """Hand one payload from the channel to every client whose filter matches it."""
        if not self._subscriptions:
            return
        try:
            event = Announcement.parse(payload)
        except ValueError:
            logger.exception("Ignoring an event payload that isn't one activity.record sends")
            return
        try:
            listed = await self.lookup(event.id)
            if listed is None:
                return
            for subscription in list(self._subscriptions):
                if subscription.filter.matches(event, listed.square) and not subscription.offer(event):
                    self._drop(subscription)
        except Exception:
            # Whatever went wrong, the listener carries on. Announcing the
            # event unchecked could tell people about something hidden.
            logger.exception("Couldn't check event %s, so it isn't announced", event.id)

    # The listener ----------------------------------------------------------

    def start(self) -> None:
        """Start listening, unless already listening. Call from the hub's event loop."""
        assert asyncio.get_running_loop() is self.loop, "a hub belongs to the loop that made it"
        if self._task is None and not self._stopped:
            self._task = self.loop.create_task(self._listen(), name="fieldclub-event-listener")
            self._task.add_done_callback(self._listener_ended)

    def _listener_ended(self, task: asyncio.Task[None]) -> None:
        """Forget a listener that has ended, so the next `subscribe` starts another."""
        if self._task is task:
            self._task = None
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._lost = True
            self.connected.clear()
            self.backend_pid = None
            logger.error("The event listener stopped", exc_info=error)

    async def stop(self) -> None:
        """Stop listening and end every client's stream with `closed`. Idempotent, and never raises."""
        self._stopped = True
        for subscription in list(self._held):
            subscription.end(Signal.CLOSED)
            self.unsubscribe(subscription)
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            # `wait` doesn't raise what the task raised: `_listener_ended` logs it.
            await asyncio.wait([task])
        self.connected.clear()
        self.backend_pid = None

    async def _timed(self, conn: psycopg.AsyncConnection[Any], query: LiteralString) -> None:
        """Run `query`, and raise `TimeoutError` when no answer comes within `check_timeout_s`."""
        probe = asyncio.ensure_future(conn.execute(query))
        try:
            done, _ = await asyncio.wait([probe], timeout=self.check_timeout_s)
        finally:
            if not probe.done():
                # Cancelling the query would have psycopg spend ten seconds
                # asking the server to cancel one it never received. Close the
                # connection under it instead, so the cancel is immediate.
                conn.pgconn.finish()
                probe.cancel()
                await asyncio.wait([probe])
                if not probe.cancelled():
                    probe.exception()
        if not done:
            raise TimeoutError(f"The database didn't answer {query!r} within {self.check_timeout_s:.1f} s")
        probe.result()

    async def _listen(self) -> None:
        failures = 0
        while True:
            try:
                address = make_conninfo(self.conninfo, **KEEPALIVES, connect_timeout=self.connect_timeout_s)
                async with await psycopg.AsyncConnection.connect(address, autocommit=True) as conn:
                    # Timed like the checks: a reconnect can reach a peer
                    # that accepts the connection and then never answers.
                    await self._timed(conn, LISTEN)
                    self.backend_pid = conn.info.backend_pid
                    if failures or self._lost:
                        logger.info("The event listener is back after %d failed attempts", failures)
                        self._broadcast(Signal.RESYNC)
                    failures, self._lost, self._check_soon = 0, False, False
                    self.connected.set()
                    checked = self.loop.time()
                    while True:
                        async for notice in conn.notifies(timeout=min(self.idle_check_s, _SLICE_S)):
                            await self.deliver(notice.payload)
                        if self._check_soon or self.loop.time() - checked >= self.idle_check_s:
                            # Make sure the connection is still there, without waiting for traffic.
                            self._check_soon = False
                            await self._timed(conn, "SELECT 1")
                            checked = self.loop.time()
            except Exception as exc:
                # A lost connection, or anything else: either way, start again.
                self.connected.clear()
                self.backend_pid = None
                delay = self.retry_delays_s[min(failures, len(self.retry_delays_s) - 1)]
                failures += 1
                # A check that got no answer is a TimeoutError, which is an OSError.
                expected = isinstance(exc, (psycopg.Error, OSError))
                logger.warning(
                    "The event listener failed (%s). Retrying in %.2f s",
                    exc,
                    delay,
                    exc_info=None if expected else exc,
                )
                await asyncio.sleep(delay)


# --------------------------------------------------------------------------
# The process's hub
# --------------------------------------------------------------------------


def conninfo() -> str:
    """The configured database as a libpq connection string."""
    url = get_engine().url.set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def _public_square(activity_id: int) -> Listed | None:
    with SessionLocal() as db:
        row = feed.public_event(db, activity_id)
        if row is None:
            return None
        return Listed(point_lon_lat(row.location, f"activity {row.id}") if row.location is not None else None)


async def lookup_public(activity_id: int) -> Listed | None:
    """Whether a signed-out visitor's feed lists the event, and its square. Runs in a worker thread."""
    return await asyncio.to_thread(_public_square, activity_id)


_hub: EventHub | None = None


def get_hub(**options: Any) -> EventHub:
    """This process's hub, made on first use with `options` for `EventHub`.

    A hub belongs to one event loop. A test that runs several loops gets a
    fresh hub on each.
    """
    global _hub
    loop = asyncio.get_running_loop()
    if _hub is None or _hub.loop is not loop or _hub.loop.is_closed():
        _hub = EventHub(conninfo(), lookup_public, **options)
    return _hub


async def stop_hub() -> None:
    """Stop this process's hub, if it is running on this loop. For shutdown."""
    global _hub
    hub, _hub = _hub, None
    if hub is not None and hub.loop is asyncio.get_running_loop():
        await hub.stop()
