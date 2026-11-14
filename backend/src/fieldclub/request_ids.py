"""Each request's id, so a failure seen in a browser can be found in the server's log.

The server makes the id itself and never takes one from the client, which
could otherwise write whatever it liked into the log. `RequestIdMiddleware`
sends it back in `X-Request-ID` on every response, an error's included, and
holds it in a context variable while the request is handled. An error body
repeats it (`errors.AppError.to_body`), and `RequestIdFilter` adds it to each
log line written meanwhile: on the event loop, in the thread pool, and on the
tile threads, which run in a copy of the request's context
(`terrain/workers.py`).

This module is imported by `errors`, which services import, so it keeps
Starlette's imports inside the middleware, as `errors` does.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-ID"
# Where the id is kept in the request's scope, for the last-resort error
# handler, which Starlette runs after the middleware has returned.
SCOPE_KEY = "fieldclub.request_id"
# What a log line written outside any request shows in the id's place.
NO_REQUEST = "-"
# The log format the server writes, with the id beside the level.
LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

_current: ContextVar[str | None] = ContextVar("fieldclub_request_id", default=None)


def new_id() -> str:
    """Sixteen hex digits: short enough to read out, and with 64 random bits no two requests share one."""
    return secrets.token_hex(8)


def current() -> str | None:
    """The id of the request being handled, or None outside one."""
    return _current.get()


def from_scope(scope: Scope) -> str | None:
    """The id the middleware gave this request, or None if it never passed through it."""
    value = scope.get(SCOPE_KEY)
    return value if isinstance(value, str) else None


@contextmanager
def bound(request_id: str | None) -> Iterator[None]:
    """Treat what runs inside as part of the request with this id."""
    token = _current.set(request_id)
    try:
        yield
    finally:
        _current.reset(token)


class RequestIdMiddleware:
    """Give every HTTP request an id, send it in `X-Request-ID`, and hold it while the request is handled.

    It must be the outermost middleware the app adds, so that every other
    middleware's own answer carries the id and is logged with it.
    """

    def __init__(self, app: ASGIApp) -> None:
        from starlette.datastructures import MutableHeaders

        self.app = app
        self._headers = MutableHeaders

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        MutableHeaders = self._headers  # noqa: N806 - the class, kept from __init__

        request_id = new_id()
        scope[SCOPE_KEY] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        token = _current.set(request_id)
        await self.app(scope, receive, send_with_id)
        # Only once the request has been answered. An exception goes on to
        # Starlette's last-resort handler and to uvicorn, which write the 500,
        # its access line and the traceback after this has returned, so the
        # id is left bound for them. Each request under uvicorn runs in a task
        # of its own, so nothing else sees it.
        _current.reset(token)


class RequestIdFilter(logging.Filter):
    """Put the current request's id on each record as `request_id`, or `NO_REQUEST` outside one.

    It goes on the handler, not on a logger, so that lines from every
    logger, uvicorn's included, pass through it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current() or NO_REQUEST
        return True
