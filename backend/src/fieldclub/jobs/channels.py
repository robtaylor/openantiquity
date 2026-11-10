"""The channel scan: mentions added for links back to findings in watched channels' videos.

`watch_channels` lists the channels. For each enabled one, oldest checked
first, the scan reads the channel's public feed, which needs no key and
carries each recent video's description. Every link in a description to a
finding's page on this site (`<FIELDCLUB_PUBLIC_URL>/f/<public id>`) becomes
a mention of that video on that finding, with `auto_detected` set and no
member against it. The feed gives the title, channel, thumbnail and date, so
nothing else is fetched.

Being polite to the provider:

- One channel at a time, with a pause between channels, and at most
  `max_channels` channels per run.
- Conditional requests: the feed's `ETag` and `Last-Modified` are kept on the
  channel and sent back, so an unchanged feed costs a 304 and no parsing.
- At most `max_entries` videos per feed, and the feed read with a size cap,
  through `fieldclub.safe_fetch` like any other address.

A second run adds nothing: a finding has one mention per canonical address,
and the insert skips one that exists, removed ones included. A channel whose
feed is broken is recorded with its error and the scan carries on with the
next. Each channel's work is committed on its own.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from xml.sax import SAXException

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldclub import safe_fetch
from fieldclub.config import get_settings
from fieldclub.db import SessionLocal
from fieldclub.models import Finding, WatchChannel
from fieldclub.services import ids, mentions, unfurl

logger = logging.getLogger(__name__)


class ChannelProvider(StrEnum):
    YOUTUBE = "youtube"


YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml"
# A YouTube channel id: `UC` and 22 more characters.
YOUTUBE_CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
_FEED_TYPES = ("application/atom+xml", "application/xml", "text/xml", "application/rss+xml")
_ERROR_MAX = 500

# A web address in free text, up to the first character that can't be in one.
_LINK = re.compile(r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE)
_FINDING_PATH = re.compile(r"/f/([^/?#]+)/?")


class ChannelScanError(Exception):
    """A channel's feed couldn't be read or made sense of."""


@dataclass(frozen=True)
class ScanLimits:
    max_channels: int = 50
    # A YouTube feed lists a channel's fifteen newest videos.
    max_entries: int = 15
    # Between one channel and the next.
    delay_s: float = 2.0
    fetch: safe_fetch.FetchLimits = field(
        default_factory=lambda: safe_fetch.FetchLimits(max_bytes=1024 * 1024, max_redirects=2)
    )

    def __post_init__(self) -> None:
        assert self.max_channels >= 1, "max_channels must be at least 1"
        assert self.max_entries >= 1, "max_entries must be at least 1"
        assert self.delay_s >= 0, "delay_s must not be negative"


@dataclass
class ScanStats:
    channels: int = 0
    unchanged: int = 0
    failed: int = 0
    videos: int = 0
    links: int = 0
    added: int = 0

    def summary(self) -> str:
        return (
            f"scan-channels: {self.channels} channels ({self.unchanged} unchanged, {self.failed} failed), "
            f"{self.videos} videos, {self.links} links to findings, {self.added} mentions added"
        )


def feed_url(channel: WatchChannel) -> str:
    """The public feed of a channel."""
    if channel.provider != ChannelProvider.YOUTUBE.value:
        raise ChannelScanError(f"There is no feed for channels on {channel.provider!r}.")
    if not YOUTUBE_CHANNEL_ID.fullmatch(channel.channel_id):
        raise ChannelScanError(f"{channel.channel_id!r} isn't a YouTube channel id.")
    return str(httpx.URL(YOUTUBE_FEED, params={"channel_id": channel.channel_id}))


def _site_netloc(url: str) -> tuple[str, int | None]:
    parsed = httpx.URL(url)
    host = parsed.host.lower()
    return (host[4:] if host.startswith("www.") else host), parsed.port


def finding_ids_in(text: str, public_url: str) -> list[str]:
    """The public ids of findings linked from `text`, in order, each once.

    Only links to this site count: the host of `public_url`, with or without
    `www.`, over http or https.
    """
    site = _site_netloc(public_url)
    found: dict[str, None] = {}
    for match in _LINK.finditer(text):
        link = match.group(0).rstrip(".,;:!?")
        try:
            if _site_netloc(link) != site:
                continue
            path = httpx.URL(link).path
        except (httpx.InvalidURL, ValueError):
            continue
        path_match = _FINDING_PATH.fullmatch(path)
        public_id = ids.normalise(path_match.group(1)) if path_match else None
        if public_id is not None:
            found.setdefault(public_id)
    return list(found)


def _draft(entry: Any) -> mentions.Draft | None:
    """A mention of the video an entry describes, or None when it names no video we can link."""
    link = entry.get("link")
    video_id = entry.get("yt_videoid")
    if not isinstance(link, str) and isinstance(video_id, str):
        link = f"https://www.youtube.com/watch?v={video_id}"
    if not isinstance(link, str):
        return None
    try:
        address = unfurl.canonical(link)
    except unfurl.InvalidAddressError:
        return None
    if address.provider != "youtube":
        return None
    thumbnails = entry.get("media_thumbnail") or []
    thumbnail = thumbnails[0].get("url") if thumbnails and isinstance(thumbnails[0], dict) else None
    metadata = unfurl.Metadata(
        title=unfurl.clean_text(entry.get("title"), unfurl.TITLE_MAX),
        author_name=unfurl.clean_text(entry.get("author"), unfurl.AUTHOR_MAX),
        thumbnail_url=unfurl.video_thumbnail(thumbnail),
        published_at=unfurl.parse_date(entry.get("published")),
    )
    return mentions.Draft(
        address=address, kind=address.kind, metadata=metadata, start_seconds=address.start_seconds
    )


def _read_feed(
    channel: WatchChannel, limits: ScanLimits, resolver: safe_fetch.Resolver | None
) -> tuple[safe_fetch.Fetched, Any]:
    headers: dict[str, str] = {}
    if channel.etag:
        headers["If-None-Match"] = channel.etag
    if channel.last_modified:
        headers["If-Modified-Since"] = channel.last_modified
    try:
        fetched = safe_fetch.fetch(
            feed_url(channel),
            content_types=_FEED_TYPES,
            headers=headers,
            limits=limits.fetch,
            resolver=resolver,
        )
    except (safe_fetch.FetchFailedError, safe_fetch.FetchRefusedError) as exc:
        raise ChannelScanError(exc.message) from exc
    if fetched.not_modified:
        return fetched, None
    if fetched.truncated:
        raise ChannelScanError("The feed was larger than we read.")
    # Bytes, never a URL: feedparser would fetch a URL itself, without our guards.
    parsed = feedparser.parse(fetched.content)
    reason = parsed.get("bozo_exception")
    # feedparser reads on past broken XML, so a cut-off feed would pass as a short one.
    if not parsed.get("version") or isinstance(reason, SAXException):
        raise ChannelScanError(
            f"The feed couldn't be read: {type(reason).__name__ if reason else 'not a feed'}."
        )
    return fetched, parsed


def scan_channel(
    db: Session,
    channel: WatchChannel,
    stats: ScanStats,
    *,
    public_url: str,
    limits: ScanLimits,
    resolver: safe_fetch.Resolver | None = None,
) -> None:
    """Scan one channel and add what it links to. Raises `ChannelScanError`. The caller commits."""
    fetched, parsed = _read_feed(channel, limits, resolver)
    if parsed is None:
        stats.unchanged += 1
        return
    for entry in parsed.entries[: limits.max_entries]:
        stats.videos += 1
        description = entry.get("summary")
        if not isinstance(description, str):
            continue
        public_ids = finding_ids_in(description, public_url)
        if not public_ids:
            continue
        draft = _draft(entry)
        if draft is None:
            continue
        for public_id in public_ids:
            stats.links += 1
            finding = db.scalar(select(Finding).where(Finding.public_id == public_id))
            if finding is not None and mentions.add_detected(db, finding, draft) is not None:
                stats.added += 1
                logger.info(
                    "Channel %s links finding %s from %s",
                    channel.channel_id,
                    public_id,
                    draft.address.canonical_url,
                )
    channel.etag = fetched.headers.get("etag")
    channel.last_modified = fetched.headers.get("last-modified")


def scan(
    *,
    limits: ScanLimits | None = None,
    session_factory: sessionmaker[Session] | None = None,
    resolver: safe_fetch.Resolver | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ScanStats:
    """Scan the enabled channels, oldest checked first, one at a time."""
    limits = limits or ScanLimits()
    factory = session_factory or SessionLocal
    public_url = get_settings().public_url
    stats = ScanStats()
    with factory() as db:
        channel_ids = db.scalars(
            select(WatchChannel.id)
            .where(WatchChannel.enabled.is_(True))
            .order_by(WatchChannel.last_checked_at.asc().nulls_first(), WatchChannel.id)
            .limit(limits.max_channels)
        ).all()
    for position, channel_id in enumerate(channel_ids):
        if position:
            sleep(limits.delay_s)
        stats.channels += 1
        with factory() as db:
            channel = db.get(WatchChannel, channel_id)
            assert channel is not None, "a channel listed a moment ago has gone"
            try:
                scan_channel(db, channel, stats, public_url=public_url, limits=limits, resolver=resolver)
                channel.last_error = None
            except ChannelScanError as exc:
                db.rollback()
                stats.failed += 1
                channel = db.get(WatchChannel, channel_id)
                assert channel is not None, "a channel listed a moment ago has gone"
                channel.last_error = str(exc)[:_ERROR_MAX]
                logger.warning("Channel %s %s: %s", channel.provider, channel.channel_id, exc)
            channel.last_checked_at = datetime.now(UTC)
            db.commit()
    return stats


def add_channel(
    db: Session, channel_id: str, *, title: str | None = None, enabled: bool = True
) -> WatchChannel:
    """Watch a YouTube channel, or change one already watched. The caller commits."""
    if not YOUTUBE_CHANNEL_ID.fullmatch(channel_id):
        raise ChannelScanError(f"{channel_id!r} isn't a YouTube channel id, which starts with UC.")
    channel = db.scalar(
        select(WatchChannel).where(
            WatchChannel.provider == ChannelProvider.YOUTUBE.value, WatchChannel.channel_id == channel_id
        )
    )
    if channel is None:
        channel = WatchChannel(provider=ChannelProvider.YOUTUBE.value, channel_id=channel_id)
        db.add(channel)
    channel.enabled = enabled
    if title is not None:
        channel.title = title
    db.flush()
    return channel
