"""Mention addresses: one canonical form for each, and the title, author and thumbnail behind it.

`canonical()` reduces an address to the form two people would agree is the
same thing. Every way of writing a YouTube link (watch, youtu.be, shorts,
live, embed, any of its hostnames, with a start time or tracking parameters)
becomes `https://www.youtube.com/watch?v=<id>` plus `start_seconds`. Vimeo
links become `https://vimeo.com/<id>`. A DOI in any form becomes its doi.org
address, in lower case because DOIs ignore case, without any query, fragment
or trailing slash. Anything else keeps its path and meaningful query, with a
lower-case host, no fragment, no tracking parameters, the query sorted and
unreserved characters no longer percent-encoded.

Two addresses that differ only in `http` or `https`, a leading `www.` or a
trailing slash are usually one page, but the canonical address keeps them,
because it is the one fetched and shown. `Address.match_key` drops them, and
a finding has at most one mention per match key.

`unfurl()` fetches what is known about an address, without keys:

| Kind | Route |
|------|-------|
| YouTube, Vimeo | The provider's oEmbed endpoint |
| DOI | doi.org content negotiation for CSL JSON |
| Anything else | The page's Open Graph tags, or its `<title>` |

Every fetch goes through `fieldclub.safe_fetch`, because the address came from
a member. Results, failures included, are cached in this process for a while,
so a preview followed by a save fetches once. A failure is never an error to
the caller: the mention is saved with the address alone.

Text taken from a page is someone else's and is shown publicly, so it is
stripped of control and format characters (bidi overrides, zero-width
characters, soft hyphens), its whitespace is collapsed and it is cut to
length. A thumbnail is kept only from YouTube's and Vimeo's image hosts, on
https. A page's own image is never kept: its site is whatever site the member
chose, so showing it would let a member see the address of everyone who
looks at the finding.

Fetches made for every caller together are capped by one budget for the
process, spent only when the cache can't answer. When it is used up the
address is left unfetched, as if the fetch had failed, and that isn't cached.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import httpx

from fieldclub import safe_fetch
from fieldclub.errors import RateLimitedError, ValidationFailedError
from fieldclub.ratelimit import enforce_key, get_limiter
from fieldclub.schemas.text import has_unstorable_character
from fieldclub.vocab import MentionKind

logger = logging.getLogger(__name__)

URL_MAX = 2000
TITLE_MAX = 300
AUTHOR_MAX = 200
# A start time beyond this is a typo, not a twelve-hour video.
MAX_START_SECONDS = 12 * 3600


class InvalidAddressError(ValidationFailedError):
    code = "invalid_address"
    message = "That isn't a web address or a DOI we can link to."


# --------------------------------------------------------------------------
# Canonical addresses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Address:
    # What was typed, trimmed, with a scheme added when it had none.
    url: str
    canonical_url: str
    # What the address looks like it is. A member may choose another kind.
    kind: MentionKind
    # `youtube`, `vimeo`, `doi`, a podcast service, or the site's host.
    provider: str
    start_seconds: int | None = None
    # The YouTube or Vimeo id, or the DOI.
    item_id: str | None = None

    @property
    def match_key(self) -> str:
        """What two addresses of the same thing share: the canonical address, less what rarely matters.

        For a page that is `http` or `https`, a leading `www.` and a trailing
        slash. The provider forms are exact already.
        """
        if self.provider in _EXACT_PROVIDERS:
            return self.canonical_url
        split = urlsplit(self.canonical_url)
        path = split.path.rstrip("/") or "/"
        return urlunsplit(("", _without_www(split.netloc), path, split.query, ""))


YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "gaming.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
        "youtu.be",
        "www.youtu.be",
    }
)
VIMEO_HOSTS = frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"})
DOI_HOSTS = frozenset({"doi.org", "dx.doi.org", "www.doi.org"})
_EXACT_PROVIDERS = frozenset({"youtube", "vimeo", "doi"})

_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
# The path forms that carry an id: /shorts/<id>, /live/<id>, /embed/<id>, /v/<id>, /e/<id>.
_YOUTUBE_PATH = re.compile(r"/(?:shorts|live|embed|v|e)/([A-Za-z0-9_-]{11})(?:[/?#]|$)")
_VIMEO_PATHS = (
    re.compile(r"/(\d+)(?:/([0-9a-f]{6,20}))?/?$"),
    re.compile(r"/video/(\d+)/?$"),
    re.compile(r"/(?:channels|showcase|album)/[^/]+/(?:video/)?(\d+)/?$"),
    re.compile(r"/groups/[^/]+/videos/(\d+)/?$"),
)
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DOI_PREFIX = re.compile(r"^(?:doi:\s*|https?://(?:dx\.|www\.)?doi\.org/)", re.IGNORECASE)
_DOI_URL_PREFIX = re.compile(r"^https?://", re.IGNORECASE)
_TIME_PART = re.compile(r"(\d+)([hms])")

# Characters a DOI keeps unescaped in its doi.org address. Angle and square
# brackets are escaped, as doi.org does, so the address is always a valid URL.
_DOI_SAFE = "/:;()._-"

# RFC 3986 unreserved characters: escaping one changes nothing, so it is undone.
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
# What may trail a YouTube id when a link is pasted at the end of a sentence.
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""

# Query parameters that only say where a click came from.
_TRACKING_PREFIXES = ("utm_", "mtm_", "pk_", "hsa_", "_hs")
_TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "yclid",
        "twclid",
        "ttclid",
        "li_fat_id",
        "igshid",
        "igsh",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "oly_anon_id",
        "oly_enc_id",
        "vero_id",
        "wickedid",
        "ref_src",
        "ref_url",
        "si",
        "feature",
        "pp",
        "ab_channel",
        "cmpid",
        "ocid",
        "at_medium",
        "at_campaign",
        "share",
    }
)

# Hosts whose links are usually one kind of thing. Anything else is an article.
_PODCAST_HOSTS = frozenset(
    {
        "podcasts.apple.com",
        "podcasts.google.com",
        "overcast.fm",
        "pca.st",
        "pocketcasts.com",
        "castbox.fm",
        "podbean.com",
        "player.fm",
        "anchor.fm",
        "podcasters.spotify.com",
        "creators.spotify.com",
    }
)
_SOCIAL_HOSTS = frozenset(
    {
        "twitter.com",
        "x.com",
        "bsky.app",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "threads.net",
        "reddit.com",
        "old.reddit.com",
        "linkedin.com",
        "mastodon.social",
    }
)


def parse_start(value: str | None) -> int | None:
    """Seconds from a start time written as `90`, `90s`, `1m30s`, `1h2m3s` or `1:30`."""
    if not value:
        return None
    value = value.strip().lower()
    seconds: int | None = None
    if value.isdigit():
        seconds = int(value)
    elif re.fullmatch(r"\d+(?::\d{1,2}){1,2}", value):
        seconds = 0
        for part in value.split(":"):
            seconds = seconds * 60 + int(part)
    elif re.fullmatch(r"(?:\d+[hms])+", value):
        units = {"h": 3600, "m": 60, "s": 1}
        seconds = sum(int(number) * units[unit] for number, unit in _TIME_PART.findall(value))
    if seconds is None or seconds <= 0 or seconds > MAX_START_SECONDS:
        return None
    return seconds


def _fragment_start(fragment: str) -> int | None:
    """A start time in a fragment such as `t=90` or `t=1m30s`."""
    for key, value in parse_qsl(fragment, keep_blank_values=True):
        if key in ("t", "start"):
            return parse_start(value)
    return None


def _without_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def has_format_character(text: str) -> bool:
    """Whether `text` holds an invisible format character, such as a bidi override or a soft hyphen."""
    return any(unicodedata.category(char) == "Cf" for char in text)


def _unescape_unreserved(text: str) -> str:
    """`%7Euser` as `~user`, and every other escape in upper case, so equal addresses are spelled alike."""

    def one(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else match.group(0).upper()

    return _PERCENT_ESCAPE.sub(one, text)


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


def doi_address(doi: str) -> Address:
    """The doi.org address of a DOI, such as `10.5284/1040209`."""
    doi = unquote(doi).strip().rstrip(".,;/")
    if not _DOI.fullmatch(doi) or has_unstorable_character(doi):
        raise InvalidAddressError("That DOI isn't in the form 10.1234/something.")
    doi = doi.lower()
    canonical = "https://doi.org/" + quote(doi, safe=_DOI_SAFE)
    return Address(canonical, canonical, MentionKind.PAPER, "doi", item_id=doi)


def _youtube(
    host: str, path: str, query: list[tuple[str, str]], fragment: str
) -> tuple[str, int | None] | None:
    params = dict(query)
    video_id: str | None = None
    if host in ("youtu.be", "www.youtu.be"):
        candidate = path.strip("/").split("/", 1)[0].rstrip(_TRAILING_PUNCTUATION)
        video_id = candidate if _YOUTUBE_ID.fullmatch(candidate) else None
    elif path.rstrip("/") == "/watch":
        candidate = params.get("v", "").rstrip(_TRAILING_PUNCTUATION)
        video_id = candidate if _YOUTUBE_ID.fullmatch(candidate) else None
    else:
        match = _YOUTUBE_PATH.match(path)
        video_id = match.group(1) if match else None
    if video_id is None:
        return None
    start = (
        parse_start(params.get("t"))
        or parse_start(params.get("start"))
        or parse_start(params.get("time_continue"))
        or _fragment_start(fragment)
    )
    return video_id, start


def _vimeo(path: str, query: list[tuple[str, str]], fragment: str) -> tuple[str, int | None] | None:
    for pattern in _VIMEO_PATHS:
        match = pattern.match(path)
        if match is None:
            continue
        video_id = match.group(1)
        unlisted = match.group(2) if pattern is _VIMEO_PATHS[0] else dict(query).get("h")
        if unlisted is not None and not re.fullmatch(r"[0-9a-f]{6,20}", unlisted):
            unlisted = None
        item = f"{video_id}/{unlisted}" if unlisted else video_id
        return item, _fragment_start(fragment)
    return None


def _kind_for(host: str, path: str) -> MentionKind:
    bare = _without_www(host)
    if bare == "open.spotify.com" and path.startswith(("/episode/", "/show/")):
        return MentionKind.PODCAST
    if bare in _PODCAST_HOSTS or bare.endswith((".podbean.com", ".libsyn.com", ".buzzsprout.com")):
        return MentionKind.PODCAST
    if bare in ("bbc.co.uk", "bbc.com") and path.startswith(("/iplayer", "/programmes")):
        return MentionKind.BROADCAST
    if bare in ("bbc.co.uk", "bbc.com") and path.startswith("/sounds"):
        return MentionKind.PODCAST
    if bare in _SOCIAL_HOSTS or (bare.startswith("m.") and bare[2:] in _SOCIAL_HOSTS):
        return MentionKind.SOCIAL
    return MentionKind.ARTICLE


def _wrapped_youtube_link(host: str, path: str, query: list[tuple[str, str]]) -> str | None:
    """The link inside a YouTube wrapper: `/attribution_link?u=/watch?v=...` or `/oembed?url=...`."""
    if host not in YOUTUBE_HOSTS:
        return None
    params = dict(query)
    if path.rstrip("/") == "/attribution_link" and params.get("u", "").startswith("/"):
        return "https://www.youtube.com" + params["u"]
    if path.rstrip("/") == "/oembed" and "url" in params:
        return params["url"]
    return None


def canonical(raw: str, *, _unwrapped: bool = False) -> Address:
    """The canonical form of an address someone typed, or `InvalidAddressError`."""
    text = raw.strip()
    if not text or len(text) > URL_MAX or has_unstorable_character(text) or has_format_character(text):
        raise InvalidAddressError()
    if _DOI_PREFIX.match(text) or _DOI.fullmatch(text):
        doi = _DOI_PREFIX.sub("", text)
        if _DOI_URL_PREFIX.match(text):
            # In a doi.org address a query or fragment is the address's, not the DOI's.
            doi = re.split(r"[?#]", doi, maxsplit=1)[0]
        return doi_address(doi)
    if any(char.isspace() for char in text):
        raise InvalidAddressError()
    if "://" not in text:
        if ":" in text.split("/", 1)[0] and not re.match(r"[^/:]+:\d+(/|$)", text):
            # `mailto:`, `javascript:` and the like.
            raise InvalidAddressError("Only web addresses can be mentions.")
        text = f"https://{text}"
    try:
        parsed = httpx.URL(text)
    except (httpx.InvalidURL, ValueError) as exc:
        raise InvalidAddressError() from exc
    if parsed.scheme not in ("http", "https"):
        raise InvalidAddressError("Only web addresses can be mentions.")
    if parsed.userinfo:
        raise InvalidAddressError("An address with a user name or password in it can't be a mention.")
    host = parsed.raw_host.decode("ascii").rstrip(".").lower()
    if not host or "." not in host:
        raise InvalidAddressError()
    split = urlsplit(str(parsed))
    path = split.path or "/"
    query = parse_qsl(split.query, keep_blank_values=True)
    fragment = split.fragment

    wrapped = None if _unwrapped else _wrapped_youtube_link(host, path, query)
    if wrapped is not None:
        try:
            inner = canonical(wrapped, _unwrapped=True)
        except InvalidAddressError:
            inner = None
        if inner is not None and inner.provider == "youtube":
            return Address(
                text, inner.canonical_url, inner.kind, inner.provider, inner.start_seconds, inner.item_id
            )
    if host in YOUTUBE_HOSTS:
        found = _youtube(host, path, query, fragment)
        if found is not None:
            video_id, start = found
            return Address(
                text,
                f"https://www.youtube.com/watch?v={video_id}",
                MentionKind.VIDEO,
                "youtube",
                start,
                video_id,
            )
    if host in VIMEO_HOSTS:
        found = _vimeo(path, query, fragment)
        if found is not None:
            item, start = found
            return Address(text, f"https://vimeo.com/{item}", MentionKind.VIDEO, "vimeo", start, item)
    if host in DOI_HOSTS and _DOI.fullmatch(unquote(path.lstrip("/"))):
        address = doi_address(path.lstrip("/"))
        return Address(text, address.canonical_url, address.kind, address.provider, item_id=address.item_id)

    kept = sorted((key, value) for key, value in query if not _is_tracking(key))
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    canonical_url = urlunsplit((parsed.scheme, netloc, _unescape_unreserved(path), urlencode(kept), ""))
    if len(canonical_url) > URL_MAX:
        raise InvalidAddressError()
    return Address(text, canonical_url, _kind_for(host, path), _without_www(host))


# --------------------------------------------------------------------------
# Fetching what an address is
# --------------------------------------------------------------------------


class FetchStatus(StrEnum):
    OK = "ok"
    # The address isn't one we fetch: a private network, an odd port.
    REFUSED = "refused"
    # It was tried and gave nothing usable.
    FAILED = "failed"


@dataclass(frozen=True)
class Metadata:
    title: str | None = None
    author_name: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class Unfurled:
    status: FetchStatus
    metadata: Metadata


NOTHING = Metadata()

# Provider image hosts that thumbnails may come from.
_VIDEO_IMAGE_HOSTS = re.compile(r"(?:i\d?\.ytimg\.com|i\.vimeocdn\.com)")

_JSON_TYPES = ("application/json", "text/json", "text/javascript")
_CSL_TYPES = ("application/vnd.citationstyles.csl+json", "application/json")
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_CSL_ACCEPT = "application/vnd.citationstyles.csl+json"

_JSON_LIMITS = safe_fetch.FetchLimits(max_bytes=256 * 1024)
# doi.org hands over to the registration agency, which may redirect again.
_DOI_LIMITS = safe_fetch.FetchLimits(max_bytes=512 * 1024, max_redirects=4)
_HTML_LIMITS = safe_fetch.FetchLimits(max_bytes=512 * 1024, truncate=True)


def clean_text(value: Any, limit: int) -> str | None:
    """Text from elsewhere, made safe to store and show: one line, no control characters, cut to length."""
    if not isinstance(value, str):
        return None
    # Format characters (bidi controls, zero-width characters, soft hyphens) go;
    # control characters and lone surrogates become spaces.
    text = "".join(
        "" if category == "Cf" else " " if category in ("Cc", "Cs") else char
        for char, category in ((char, unicodedata.category(char)) for char in value)
    )
    text = " ".join(text.split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _https_image(value: Any) -> httpx.URL | None:
    if not isinstance(value, str) or len(value) > URL_MAX or has_unstorable_character(value):
        return None
    try:
        url = httpx.URL(value.strip())
    except (httpx.InvalidURL, ValueError):
        return None
    if url.scheme != "https" or url.userinfo or url.port is not None or not url.host:
        return None
    return url


def video_thumbnail(value: Any) -> str | None:
    """A thumbnail address from a video provider, if it is on one of their image hosts."""
    url = _https_image(value)
    if url is None or not _VIDEO_IMAGE_HOSTS.fullmatch(url.host):
        return None
    return str(url)


def parse_date(value: Any) -> datetime | None:
    """An ISO 8601 date or time as UTC, or None when it isn't one or is implausible."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace(" ", "T", 1))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed.year < 1800 or parsed > datetime.now(UTC) + timedelta(days=2):
        return None
    return parsed


def _json(fetched: safe_fetch.Fetched) -> dict[str, Any]:
    try:
        data = json.loads(fetched.content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise safe_fetch.FetchFailedError("The answer wasn't JSON.") from exc
    if not isinstance(data, dict):
        raise safe_fetch.FetchFailedError("The answer wasn't a JSON object.")
    return data


def _oembed(endpoint: str, address: Address, resolver: safe_fetch.Resolver | None) -> Metadata:
    fetched = safe_fetch.fetch(
        str(httpx.URL(endpoint, params={"url": address.canonical_url, "format": "json"})),
        content_types=_JSON_TYPES,
        accept="application/json",
        limits=_JSON_LIMITS,
        resolver=resolver,
    )
    data = _json(fetched)
    return Metadata(
        title=clean_text(data.get("title"), TITLE_MAX),
        author_name=clean_text(data.get("author_name"), AUTHOR_MAX),
        thumbnail_url=video_thumbnail(data.get("thumbnail_url")),
        published_at=parse_date(data.get("upload_date")),
    )


def _csl_authors(authors: Any) -> str | None:
    if not isinstance(authors, list):
        return None
    names: list[str] = []
    for person in authors:
        if not isinstance(person, dict):
            continue
        name = person.get("literal") or " ".join(
            part for part in (person.get("given"), person.get("family")) if isinstance(part, str)
        )
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    if not names:
        return None
    shown = ", ".join(names[:3])
    return clean_text(shown + (" and others" if len(names) > 3 else ""), AUTHOR_MAX)


def _csl_date(issued: Any) -> datetime | None:
    parts = issued.get("date-parts") if isinstance(issued, dict) else None
    if not (isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]):
        return None
    numbers = [int(part) for part in parts[0][:3] if isinstance(part, int | str) and str(part).isdigit()]
    if not numbers:
        return None
    year, month, day = [*numbers, 1, 1][:3]
    try:
        return parse_date(datetime(year, month, day, tzinfo=UTC).isoformat())
    except ValueError:
        return None


def _first_text(value: Any) -> Any:
    """CSL gives some fields as a list of strings."""
    return value[0] if isinstance(value, list) and value else value


def _doi(address: Address, resolver: safe_fetch.Resolver | None) -> Metadata:
    fetched = safe_fetch.fetch(
        address.canonical_url,
        content_types=_CSL_TYPES,
        accept=_CSL_ACCEPT,
        limits=_DOI_LIMITS,
        resolver=resolver,
    )
    data = _json(fetched)
    return Metadata(
        title=clean_text(_first_text(data.get("title")), TITLE_MAX),
        author_name=_csl_authors(data.get("author"))
        or clean_text(_first_text(data.get("container-title")) or data.get("publisher"), AUTHOR_MAX),
        published_at=_csl_date(data.get("issued")) or _csl_date(data.get("published")),
    )


class _HeadParser(HTMLParser):
    """Collects `<title>` and `<meta>` from a page's head, and stops at its body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        if tag == "body":
            self.done = True
        elif tag == "title" and self.title is None:
            self._in_title = True
        elif tag == "meta":
            values = {key.lower(): value for key, value in attrs if value is not None}
            name = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            content = values.get("content")
            if name and content is not None and name not in self.meta:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = "".join(self._title_parts)
        elif tag == "head":
            self.done = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def page_metadata(html: str, page_url: str) -> Metadata:
    """What a page's Open Graph tags, or failing them its title, say about it. Never its image."""
    parser = _HeadParser()
    try:
        # Fed in pieces, so parsing ends soon after the head does.
        for start in range(0, len(html), 8192):
            parser.feed(html[start : start + 8192])
            if parser.done:
                break
    except (AssertionError, ValueError):
        logger.debug("Couldn't parse the head of %s", page_url)
    meta = parser.meta
    author = meta.get("author") or meta.get("article:author")
    if author is not None and author.strip().startswith(("http://", "https://")):
        author = None
    return Metadata(
        title=clean_text(meta.get("og:title") or meta.get("twitter:title") or parser.title, TITLE_MAX),
        author_name=clean_text(author or meta.get("og:site_name"), AUTHOR_MAX),
        published_at=parse_date(
            meta.get("article:published_time") or meta.get("datepublished") or meta.get("date")
        ),
    )


def _page(address: Address, resolver: safe_fetch.Resolver | None) -> Metadata:
    fetched = safe_fetch.fetch(
        address.canonical_url,
        content_types=_HTML_TYPES,
        accept="text/html,application/xhtml+xml",
        limits=_HTML_LIMITS,
        resolver=resolver,
    )
    return page_metadata(fetched.text(), fetched.url)


def _fetch(address: Address, resolver: safe_fetch.Resolver | None) -> Metadata:
    if address.provider == "youtube":
        return _oembed("https://www.youtube.com/oembed", address, resolver)
    if address.provider == "vimeo":
        return _oembed("https://vimeo.com/api/oembed.json", address, resolver)
    if address.provider == "doi":
        return _doi(address, resolver)
    return _page(address, resolver)


# How long a result is kept, by outcome. A failure is kept briefly, so a
# broken site isn't asked again on every click but a passing fault clears.
_TTL_S = {FetchStatus.OK: 3600.0, FetchStatus.REFUSED: 3600.0, FetchStatus.FAILED: 300.0}
_CACHE_SIZE = 512

# Fetches this process makes for everyone together, whoever asks.
_all_fetches = get_limiter("mention-fetches-all", 600, per_seconds=3600)
_cache: OrderedDict[str, tuple[float, Unfurled]] = OrderedDict()
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def unfurl(address: Address, *, resolver: safe_fetch.Resolver | None = None) -> Unfurled:
    """The title, author, thumbnail and date behind an address, from the cache or fetched now."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(address.canonical_url)
        if hit is not None and hit[0] > now:
            _cache.move_to_end(address.canonical_url)
            return hit[1]
    try:
        enforce_key(_all_fetches, "all")
    except RateLimitedError:
        logger.warning("The fetch budget is used up, so %s isn't fetched", address.canonical_url)
        return Unfurled(FetchStatus.FAILED, NOTHING)
    try:
        result = Unfurled(FetchStatus.OK, _fetch(address, resolver))
    except safe_fetch.FetchRefusedError as exc:
        logger.info("Not fetching %s: %s", address.canonical_url, exc.message)
        result = Unfurled(FetchStatus.REFUSED, NOTHING)
    except safe_fetch.FetchFailedError as exc:
        logger.info("Fetching %s failed: %s", address.canonical_url, exc.message)
        result = Unfurled(FetchStatus.FAILED, NOTHING)
    with _cache_lock:
        _cache[address.canonical_url] = (now + _TTL_S[result.status], result)
        _cache.move_to_end(address.canonical_url)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return result
