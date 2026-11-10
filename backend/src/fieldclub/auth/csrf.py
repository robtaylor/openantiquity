"""The `X-FieldClub-Client` header check that closes cross-site request forgery.

A cross-site form can't set a custom header, and a cross-site script can only
do so after a CORS preflight that this server never approves. Together with a
SameSite=Lax session cookie, requiring the header on every request that
changes data means such a request can only have come from our own pages.

The check is ASGI middleware, not a router dependency, so that it covers
everything the app serves: routes on any router, routes declared on the app
itself, plain Starlette routes and mounts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from fieldclub.config import CLIENT_HEADER, CLIENT_HEADER_VALUE
from fieldclub.errors import ClientHeaderRequiredError

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class ClientHeaderMiddleware:
    """Refuse any request that changes data unless it carries `X-FieldClub-Client: web`.

    `exempt` holds regular expressions for paths that must accept a POST from
    another site, and so have to defend themselves some other way. The one
    expected case is an OAuth callback that a provider posts back to (Apple's
    `form_post` response mode), which is protected by its `state` value. A
    path is exempt only when a pattern matches all of it.
    """

    def __init__(self, app: ASGIApp, exempt: Iterable[str] = ()) -> None:
        self.app = app
        self.exempt = tuple(re.compile(pattern) for pattern in exempt)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"].upper() in MUTATING_METHODS:
            sent = Headers(scope=scope).get(CLIENT_HEADER)
            if sent != CLIENT_HEADER_VALUE and not self._is_exempt(scope["path"]):
                # Outside the app's exception handlers, so answer directly.
                error = ClientHeaderRequiredError()
                response = JSONResponse(error.to_body(), status_code=error.status_code)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _is_exempt(self, path: str) -> bool:
        return any(pattern.fullmatch(path) for pattern in self.exempt)
