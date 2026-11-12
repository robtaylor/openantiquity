"""Response headers that limit what a page of ours may do, and the cap on request bodies.

Every response carries `SECURITY_HEADERS` and a `Content-Security-Policy`,
unless the route set its own: a photo (`api/media.py`) and the printable
investigation report send stricter ones of their own, which win.

The policy (`content_security_policy`) allows only what the app needs:

- scripts, styles, fonts and the app's own documents from this site alone,
  no inline script and no `eval`. The app shell's one inline `<style>` block
  is allowed by its hash, worked out from the built `index.html`
  (`inline_style_hashes`), so editing it can't break the page silently;
- MapLibre's workers from this site or from `blob:` addresses, and images
  from `data:` and `blob:` addresses, which it makes for tiles and markers;
- map tiles, the base map's style and fonts, and the live record sources,
  from the hosts the layer catalogue (`layers.py`) and the live-source
  catalogue (`data/live_sources.json`) name, which are exactly the hosts
  `/meta` and `/context/live-sources` send the browser to;
- video thumbnails from YouTube's and Vimeo's image hosts, the only
  third-party pictures a mention keeps (`services.unfurl`);
- no frames, no plugins, no `<base>`, forms posting only here, and no site
  may frame ours (`frame-ancestors 'none'`, with `X-Frame-Options: DENY`
  for older browsers).

Over https the answer also carries `Strict-Transport-Security`. The app can't
tell from a request whether the visitor used https, because the proxy in
front of it speaks plain http, so it goes by `FIELDCLUB_PUBLIC_URL`.

`BodyLimitMiddleware` refuses a request body over `BODY_MAX_BYTES` with 413
`request_too_large` before anything reads it, so nobody can make the process
decode megabytes of JSON before a sign-in check refuses them. A photo upload
has a limit of its own, checked by its route as it reads.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fieldclub import layers
from fieldclub.errors import AppError
from fieldclub.services import context, media

# The most a request body other than a photo may hold. The largest legitimate
# JSON body is an investigation's notes, 50,000 characters, which is at most
# 300 KB even with every character escaped.
BODY_MAX_BYTES = 1024 * 1024
# The photo upload reads its own body and refuses it past `media.MAX_UPLOAD_BYTES`.
_OWN_LIMIT_PATHS = frozenset({"/api/v1/media"})

# The only third-party image hosts a mention keeps a thumbnail from, as
# `services.unfurl` allows them: `i.ytimg.com` or `i0` to `i9`, and Vimeo's.
VIDEO_IMAGE_HOSTS = (
    "https://i.ytimg.com",
    *(f"https://i{n}.ytimg.com" for n in range(10)),
    "https://i.vimeocdn.com",
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
}
HSTS = "max-age=31536000; includeSubDomains"


class RequestTooLargeError(AppError):
    status_code = 413
    code = "request_too_large"
    message = "That request is too large."


def _origin(url: str) -> str | None:
    """`https://host[:port]` of an absolute https address, or None for a path on this site."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        assert not parts.scheme, f"a catalogue address that isn't https: {url!r}"
        return None
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname}{port}"


def _layer_addresses() -> Iterable[str]:
    for view in layers.VIEWS:
        yield from getattr(view, "tiles", None) or ()
    yield from layers.DEM.tiles
    for overlay in layers.OVERLAYS:
        yield from getattr(overlay, "tiles", None) or ()
        for name in ("tilejson", "glyphs"):
            value = getattr(overlay, name, None)
            if value:
                yield value


def map_hosts() -> list[str]:
    """Every host the browser fetches tiles, the base map's style or fonts from, in order."""
    return sorted({origin for address in _layer_addresses() if (origin := _origin(address))})


def live_source_hosts() -> list[str]:
    """Every host a live record source is queried at."""
    found = {_origin(source["endpoint"]) for source in context.shown_live_sources()}
    return sorted(origin for origin in found if origin)


_INLINE_STYLE = re.compile(r"<style(?:\s[^>]*)?>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?:\s[^>]*)?>", re.IGNORECASE)


def inline_style_hashes(index: Path | None) -> list[str]:
    """CSP hash sources for each inline `<style>` block in the built app shell.

    An inline script is refused outright: the policy has no way to allow one,
    and the app shell must not need one.
    """
    if index is None or not index.is_file():
        return []
    html = index.read_text(encoding="utf-8")
    assert not _INLINE_SCRIPT.search(html), f"{index} has an inline <script>, which the policy refuses"
    return [
        f"'sha256-{base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()}'"
        for block in _INLINE_STYLE.findall(html)
    ]


@cache
def content_security_policy(index: Path | None, https: bool) -> str:
    """The policy every page of the app is served under. See the module docstring."""
    tiles = map_hosts()
    live = live_source_hosts()
    directives = {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", *inline_style_hashes(index)],
        "img-src": ["'self'", "data:", "blob:", *tiles, *VIDEO_IMAGE_HOSTS],
        "connect-src": ["'self'", *tiles, *live],
        "font-src": ["'self'"],
        "worker-src": ["'self'", "blob:"],
        # Safari before 15.5 reads workers from child-src.
        "child-src": ["'self'", "blob:"],
        "frame-src": ["'none'"],
        "object-src": ["'none'"],
        "base-uri": ["'none'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
        "manifest-src": ["'self'"],
    }
    policy = "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())
    return f"{policy}; upgrade-insecure-requests" if https else policy


class SecurityHeadersMiddleware:
    """Add the security headers and the policy to every response that hasn't set its own."""

    def __init__(
        self, app: ASGIApp, *, policy: str, https: bool, exempt: frozenset[str] = frozenset()
    ) -> None:
        self.app = app
        self.policy = policy
        self.https = https
        # Paths sent without the policy: only the development docs pages.
        self.exempt = exempt

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with_policy = scope["path"] not in self.exempt

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if with_policy:
                    headers.setdefault("Content-Security-Policy", self.policy)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if self.https:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """Refuse a request body over `limit` bytes, whether it says its length or not.

    A body that states its length is refused unread when that is too much; the
    server holds the body to the length it states. A body sent without one
    (chunked) is read here, up to the limit, and handed on whole, because
    FastAPI turns an error raised while it reads a body into a plain 400.
    """

    def __init__(self, app: ASGIApp, *, limit: int = BODY_MAX_BYTES) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _OWN_LIMIT_PATHS:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None:
            if not declared.isdigit() or int(declared) > self.limit:
                await _refuse(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        if b"transfer-encoding" not in headers:
            # No body at all.
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away before it finished.
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await _refuse(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)


async def _refuse(scope: Scope, receive: Receive, send: Send) -> None:
    """413 `request_too_large`, sent from here: the app's error handler is inside this middleware."""
    error = RequestTooLargeError()
    response = JSONResponse(error.to_body(), status_code=error.status_code, headers={"Connection": "close"})
    await response(scope, receive, send)


assert media.MAX_UPLOAD_BYTES > BODY_MAX_BYTES, "a photo may be larger than any other request"
