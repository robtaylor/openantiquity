"""The one outbound HTTP client.

Everything that talks to an upstream service uses `get_client()`, so every
request carries a timeout and a `User-Agent` that names the project. Being
polite beyond that (caching, delays, caps on loops) is up to the caller.
"""

from __future__ import annotations

import ssl
import threading

import httpx

from fieldclub.config import get_settings

_client: httpx.Client | None = None
_lock = threading.Lock()


def build_client(*, verify: ssl.SSLContext | None = None) -> httpx.Client:
    """A new client with the project defaults. Prefer `get_client()`.

    `verify` replaces the default certificate check, for the rare server that
    sends an incomplete chain and needs its issuer's intermediate added.
    """
    settings = get_settings()
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_s, connect=min(10.0, settings.http_timeout_s)),
        headers={"User-Agent": settings.outbound_user_agent},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        verify=verify if verify is not None else True,
    )


def get_client() -> httpx.Client:
    """The shared client. It is thread-safe and lives for the whole process."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = build_client()
    return _client


def close_client() -> None:
    """Close the shared client. The next `get_client()` builds a fresh one."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None
