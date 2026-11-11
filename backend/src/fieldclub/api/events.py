"""`GET /events/stream`: live events as server-sent events.

The one `async` endpoint (Decision 0001). See `services.events` for how one
listener per process serves every client without a thread or a database
connection each. This module asks for no database session on purpose: a
dependency's session would stay open for as long as the stream does.

On the wire:

- `event: activity` with `id:` the activity id and `data:` a `StreamEvent`
  (public ids and a kind, nothing more). Refetch through the API to show it.
- `event: resync`: events may have been missed. Refetch what is on screen.
- `event: dropped` or `event: closed`: the stream ends. The browser's
  `EventSource` reconnects by itself after `retry` milliseconds.
- A 429 before the stream starts (`too_many_streams` or `rate_limited`) is
  final for an `EventSource`, which doesn't retry it. The client reopens
  after a delay, or polls.
- A comment line (`: ping`) every `FIELDCLUB_EVENTS_HEARTBEAT_S` seconds, so
  proxies keep the connection open.

A stream ends after `FIELDCLUB_EVENTS_MAX_STREAM_S` seconds, so clients
spread themselves over instances as they come and go.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from fieldclub.api.deps import BBoxQuery
from fieldclub.auth.deps import client_ip
from fieldclub.config import get_settings
from fieldclub.ratelimit import address_key, enforce_key, get_limiter
from fieldclub.schemas.activity import StreamEvent
from fieldclub.schemas.common import parse_bbox
from fieldclub.services import events, findings, ids
from fieldclub.services.events import ENDING_SIGNALS, Signal, StreamFilter, Subscription, TooManyStreamsError
from fieldclub.vocab import ActivityKind

router = APIRouter(tags=["events"])

# How long a browser waits before reconnecting, in milliseconds.
RETRY_MS = 3000

# Opening a stream, per address. EventSource reconnects by itself, so this is
# generous, but it stops a loop of reconnections from hammering the hub.
_opens = get_limiter("event_stream_opens", 240, per_seconds=3600)


async def stream_filter(
    # Matched against the centre of each finding's 1 km square, never its spot.
    bbox: BBoxQuery = None,
    finding: Annotated[
        str | None, Query(max_length=ids.LENGTH + 8, description="A finding's public id")
    ] = None,
) -> StreamFilter:
    public_id = findings.normalise_public_id(finding) if finding is not None else None
    return StreamFilter(bbox=parse_bbox(bbox), finding=public_id)


async def subscription(
    request: Request, wanted: Annotated[StreamFilter, Depends(stream_filter)]
) -> AsyncIterator[Subscription]:
    """A place in this process's hub for the length of the stream, or a 429."""
    ip = client_ip(request)
    address = address_key(ip) if ip else "unknown"
    enforce_key(_opens, f"ip:{address}")
    settings = get_settings()
    hub = events.get_hub(
        queue_size=settings.events_queue_size,
        max_per_address=settings.events_max_per_address,
        max_streams=settings.events_max_streams,
    )
    subscribed = hub.subscribe(wanted, address)
    try:
        yield subscribed
    finally:
        hub.unsubscribe(subscribed)


@router.get(
    "/events/stream",
    response_class=EventSourceResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"},
        429: {"description": f"`{TooManyStreamsError.code}` or `rate_limited`"},
    },
)
async def stream(
    subscribed: Annotated[Subscription, Depends(subscription)],
) -> AsyncIterator[StreamEvent]:
    """Live events, optionally only those in a box or on one finding.

    Each carries ids and a kind and nothing else: fetch what it is about
    through the API, which shows what you may see.
    """
    settings = get_settings()
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + settings.events_max_stream_s
    yield ServerSentEvent(comment="connected", retry=RETRY_MS)  # pyright: ignore[reportReturnType]
    while (left := ends_at - loop.time()) > 0:
        item = await subscribed.next(min(settings.events_heartbeat_s, left))
        if item is None:
            yield ServerSentEvent(comment="ping")  # pyright: ignore[reportReturnType]
        elif isinstance(item, Signal):
            # A browser ignores an event with no data, so each signal carries an empty object.
            yield ServerSentEvent(event=item.value, raw_data="{}")  # pyright: ignore[reportReturnType]
            if item in ENDING_SIGNALS:
                return
        else:
            data = StreamEvent(
                id=item.id,
                kind=ActivityKind(item.kind),
                finding=item.finding,
                investigation=item.investigation,
                actor=item.actor,
            )
            yield ServerSentEvent(event="activity", id=str(item.id), data=data)  # pyright: ignore[reportReturnType]
