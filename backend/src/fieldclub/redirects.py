"""The site's other names answer with a redirect to its one address.

`FIELDCLUB_REDIRECT_HOSTS` lists names such as `www.openantiquity.org` and
`openantiquity.com`. A request whose `Host` is one of them is answered 308,
with `Location` the same path and query on `FIELDCLUB_PUBLIC_URL`. 308 keeps the
method, so a form posted to an old name is posted again to the site. Every
other name is served as it is, which keeps the platform's own address and its
health checks working.

Sessions, sign-in redirects and emailed links are all built from the one
address, so a visitor who arrives by another name leaves it at once.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


class CanonicalHostMiddleware:
    def __init__(self, app: ASGIApp, *, hosts: Iterable[str], target: str) -> None:
        self.app = app
        self.hosts = frozenset(host.lower() for host in hosts)
        self.target = target.rstrip("/")
        assert self.hosts, "a redirect needs at least one name"
        assert self.target.startswith(("http://", "https://")), "the target is a full address"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._host(scope) not in self.hosts:
            await self.app(scope, receive, send)
            return
        # raw_path keeps the request's own percent-encoding. It is always
        # appended to the target, so it can never name another host.
        path = (scope.get("raw_path") or scope["path"].encode()).decode("latin-1")
        query = scope.get("query_string", b"").decode("latin-1")
        location = self.target + path + (f"?{query}" if query else "")
        await Response(status_code=308, headers={"Location": location})(scope, receive, send)

    @staticmethod
    def _host(scope: Scope) -> str:
        # Without its port. An IPv6 address is cut short, but it is never a listed name anyway.
        return Headers(scope=scope).get("host", "").split(":", 1)[0].lower()
