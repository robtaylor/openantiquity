"""Helpers for the mention and job tests. Import as `from tests.mentions.support import ...`.

Every outbound request in these tests is answered by respx, and every host
name by `fake_resolver`, so nothing reaches the network or a real DNS server.
Each upstream answer the tests replay is a file in `tests/mentions/data` or
`tests/jobs/data`, in the shape the provider documents and returns.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from fieldclub.safe_fetch import FetchFailedError

API = "/api/v1"
MENTIONS_DATA = Path(__file__).parent / "data"
JOBS_DATA = Path(__file__).parent.parent / "jobs" / "data"

# Public addresses for the hosts the tests talk to. Requests go to these, with
# the name in the Host header.
DNS: dict[str, list[str]] = {
    "www.youtube.com": ["142.250.187.206"],
    "vimeo.com": ["162.159.128.61"],
    "doi.org": ["104.20.180.50"],
    "api.crossref.org": ["104.26.4.20"],
    "www.wiltshire-gazette.example": ["93.184.215.14"],
    "redirector.example": ["93.184.215.20"],
    "dual.example": ["93.184.215.21", "10.0.0.7"],
    "inside.example": ["192.168.1.10"],
    "metadata-alias.example": ["169.254.169.254"],
    "v6.example": ["2606:4700:4700::1111"],
    "v6-mapped.example": ["::ffff:127.0.0.1"],
    "nat64.example": ["64:ff9b::a9fe:a9fe"],
}

YOUTUBE_ID = "dQw4w9WgXcQ"
YOUTUBE_URL = f"https://www.youtube.com/watch?v={YOUTUBE_ID}"
ARTICLE_URL = "https://www.wiltshire-gazette.example/news/lost-enclosure"


def fake_resolver(host: str, port: int) -> list[str]:
    """The addresses in `DNS`. An unknown name fails as it would in DNS."""
    try:
        return list(DNS[host])
    except KeyError:
        raise FetchFailedError(f"{host} doesn't resolve.") from None


def ip_of(host: str) -> str:
    return DNS[host][0]


def data(name: str) -> bytes:
    """A recorded answer, from the mentions data or the jobs data."""
    path = MENTIONS_DATA / name
    return path.read_bytes() if path.exists() else (JOBS_DATA / name).read_bytes()


def serve(
    host: str,
    path: str,
    body: bytes,
    content_type: str,
    status: int = 200,
    *,
    headers: dict[str, str] | None = None,
) -> respx.Route:
    """Answer GETs to `path` on `host`'s address. Call inside `respx.mock`."""
    return respx.get(host=ip_of(host), path=path).mock(
        return_value=httpx.Response(
            status, content=body, headers={"content-type": content_type, **(headers or {})}
        )
    )


def serve_youtube_oembed() -> respx.Route:
    return serve("www.youtube.com", "/oembed", data("youtube-oembed.json"), "application/json")


def serve_article() -> respx.Route:
    return serve(
        "www.wiltshire-gazette.example",
        "/news/lost-enclosure",
        data("article.html"),
        "text/html; charset=utf-8",
    )
