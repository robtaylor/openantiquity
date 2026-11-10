"""The channel scan: links back to findings in watched channels' videos become mentions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.jobs import channels
from fieldclub.jobs.channels import ScanLimits, finding_ids_in, scan
from fieldclub.models import Finding, Mention, Notification, User, WatchChannel
from fieldclub.services import findings
from fieldclub.vocab import ActivityKind
from tests.helpers import MakeFinding, MakeUser, count
from tests.mentions.support import data, ip_of

PUBLIC_URL = "https://fieldclub.example"
CHANNEL = "UCabcdefghijklmnopqrstuv"
OTHER = "UCzyxwvutsrqponmlkjihgfe"
BROKEN = "UCbrokenbrokenbrokenbrok"
FEED = data("youtube-feed.xml")
ETAG = '"feed-v1"'


@pytest.fixture(autouse=True)
def public_url(env: Callable[..., None]) -> None:
    env(PUBLIC_URL=PUBLIC_URL)


@pytest.fixture
def linked(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> tuple[User, Finding, Finding]:
    finder = make_user(handle="Finder")
    enclosure = make_finding(finder, public_id="7K3QXM", title="Enclosure")
    barrow = make_finding(finder, public_id="ABC12Z", title="Barrow", feature_class="round_barrow")
    # A finder follows their findings, as `findings.create_finding` arranges.
    for finding in (enclosure, barrow):
        findings.follow(db, finder, finding)
    db.commit()
    return finder, enclosure, barrow


def watch(db: Session, *channel_ids: str, **columns: object) -> list[WatchChannel]:
    made = [WatchChannel(provider="youtube", channel_id=cid, **columns) for cid in channel_ids]
    db.add_all(made)
    db.commit()
    return made


class Feeds:
    """The feed endpoint: answers per channel id, honouring If-None-Match like YouTube does."""

    def __init__(self, bodies: dict[str, httpx.Response]) -> None:
        self.bodies = bodies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        channel_id = request.url.params["channel_id"]
        response = self.bodies[channel_id]
        if response.headers.get("etag") and request.headers.get("if-none-match") == response.headers["etag"]:
            return httpx.Response(304, headers={"etag": response.headers["etag"]})
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)


def feed(body: bytes = FEED, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=body,
        headers={"content-type": "application/atom+xml; charset=UTF-8", **(headers or {})},
    )


def serve_feeds(**bodies: httpx.Response) -> Feeds:
    feeds = Feeds(bodies)
    respx.get(host=ip_of("www.youtube.com"), path="/feeds/videos.xml").mock(side_effect=feeds)
    return feeds


NO_DELAY = ScanLimits(delay_s=0)


def test_links_in_descriptions_become_mentions(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    _finder, enclosure, barrow = linked
    watch(db, CHANNEL)
    feeds = serve_feeds(**{CHANNEL: feed(headers={"etag": ETAG})})
    stats = scan(limits=NO_DELAY)
    assert (stats.channels, stats.failed, stats.videos, stats.links, stats.added) == (1, 0, 2, 2, 2)

    found = db.scalars(select(Mention).order_by(Mention.id)).all()
    assert [m.finding_id for m in found] == [enclosure.id, barrow.id]
    for mention in found:
        assert mention.auto_detected is True
        assert mention.user_id is None
        assert mention.kind == "video"
        assert mention.provider == "youtube"
        assert mention.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert mention.title == "A new enclosure & a barrow"
        assert mention.author_name == "Barrow Walks"
        assert mention.thumbnail_url == "https://i2.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
        assert mention.published_at == datetime(2026, 11, 1, 18, 0, 6, tzinfo=UTC)
    db.refresh(enclosure)
    assert enclosure.mention_count == 1

    request = feeds.requests[0]
    assert request.headers["host"] == "www.youtube.com"
    assert request.url.params["channel_id"] == CHANNEL
    channel = db.scalars(select(WatchChannel)).one()
    assert channel.etag == ETAG
    assert channel.last_checked_at is not None
    assert channel.last_error is None


def test_the_finder_is_told_with_no_actor(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    finder, _, _ = linked
    watch(db, CHANNEL)
    serve_feeds(**{CHANNEL: feed()})
    scan(limits=NO_DELAY)
    told = db.scalars(select(Notification)).all()
    assert [(n.user_id, n.kind, n.actor_id) for n in told] == [
        (finder.id, ActivityKind.MENTION_ADDED.value, None)
    ] * 2


def test_a_second_run_adds_nothing_with_a_conditional_request(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    watch(db, CHANNEL)
    feeds = serve_feeds(**{CHANNEL: feed(headers={"etag": ETAG})})
    scan(limits=NO_DELAY)
    notified = count(db, Notification)
    stats = scan(limits=NO_DELAY)
    assert feeds.requests[1].headers["if-none-match"] == ETAG
    assert (stats.unchanged, stats.added) == (1, 0)
    assert count(db, Mention) == 2
    assert count(db, Notification) == notified


def test_a_second_run_adds_nothing_when_the_feed_comes_again(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    watch(db, CHANNEL)
    serve_feeds(**{CHANNEL: feed()})
    scan(limits=NO_DELAY)
    notified = count(db, Notification)
    stats = scan(limits=NO_DELAY)
    assert (stats.links, stats.added) == (2, 0)
    assert count(db, Mention) == 2
    assert count(db, Notification) == notified


@pytest.mark.parametrize(
    "broken",
    [
        feed(b"<html><body>Sorry</body></html>", headers={"content-type": "text/html"}),
        feed(b"<feed><entry>", status=200),
        feed(b"", status=500),
        feed(b"Not Found", status=404),
    ],
    ids=["html", "truncated", "server-error", "not-found"],
)
def test_a_broken_channel_doesnt_stop_the_others(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter, broken: httpx.Response
) -> None:
    watch(db, BROKEN, CHANNEL)
    serve_feeds(**{BROKEN: broken, CHANNEL: feed()})
    stats = scan(limits=NO_DELAY)
    assert (stats.channels, stats.failed, stats.added) == (2, 1, 2)
    by_id = {c.channel_id: c for c in db.scalars(select(WatchChannel))}
    assert by_id[BROKEN].last_error
    assert by_id[BROKEN].last_checked_at is not None
    assert by_id[CHANNEL].last_error is None


def test_a_channel_that_doesnt_answer_is_a_failure(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    watch(db, CHANNEL)
    respx.get(host=ip_of("www.youtube.com")).mock(side_effect=httpx.ConnectError("down"))
    assert scan(limits=NO_DELAY).failed == 1
    assert count(db, Mention) == 0


def test_it_waits_between_channels_and_reads_a_capped_number(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    third = "UCthirdthirdthirdthirdth"
    watch(db, CHANNEL, OTHER)
    watch(db, third, last_checked_at=datetime(2026, 1, 1, tzinfo=UTC))
    feeds = serve_feeds(**{CHANNEL: feed(), OTHER: feed(), third: feed()})
    waits: list[float] = []
    stats = scan(limits=ScanLimits(max_channels=2, delay_s=1.5), sleep=waits.append)
    assert stats.channels == 2
    assert waits == [1.5]
    # Never-checked channels come first.
    assert [r.url.params["channel_id"] for r in feeds.requests] == [CHANNEL, OTHER]


def test_entries_per_feed_are_capped(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    watch(db, CHANNEL)
    serve_feeds(**{CHANNEL: feed()})
    assert scan(limits=ScanLimits(delay_s=0, max_entries=1)).videos == 1


def test_disabled_channels_are_left_alone(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    watch(db, CHANNEL, enabled=False)
    assert scan(limits=NO_DELAY).channels == 0
    assert offline.calls.call_count == 0


def test_hidden_withdrawn_and_removed_get_nothing(
    db: Session, linked: tuple[User, Finding, Finding], offline: respx.MockRouter
) -> None:
    _, enclosure, barrow = linked
    enclosure.hidden_at = datetime(2026, 11, 1, tzinfo=UTC)
    barrow.state = "withdrawn"
    db.commit()
    watch(db, CHANNEL)
    serve_feeds(**{CHANNEL: feed()})
    assert scan(limits=NO_DELAY).added == 0

    enclosure.hidden_at = None
    barrow.state = "open"
    removed = Mention(
        finding_id=enclosure.id,
        kind="video",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        auto_detected=True,
        deleted_at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    db.add(removed)
    db.commit()
    assert scan(limits=NO_DELAY).added == 1
    assert db.scalars(select(Mention.finding_id).where(Mention.deleted_at.is_(None))).all() == [barrow.id]


def test_a_channel_on_another_provider_fails_cleanly(db: Session, offline: respx.MockRouter) -> None:
    db.add(WatchChannel(provider="vimeo", channel_id="fieldfilms"))
    db.commit()
    assert scan(limits=NO_DELAY).failed == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See https://fieldclub.example/f/7K3QXM.", ["7K3QXM"]),
        ("http://www.fieldclub.example/f/7k3qxm/ and https://FIELDCLUB.example/f/7K3QXM", ["7K3QXM"]),
        ("(https://fieldclub.example/f/abc12z?ref=yt)", ["ABC12Z"]),
        ("https://fieldclub.example/f/7K3-QXM#map", ["7K3QXM"]),
        ("https://fieldclub.example/f/ABC12Z https://fieldclub.example/f/7K3QXM", ["ABC12Z", "7K3QXM"]),
        ("https://elsewhere.example/f/7K3QXM", []),
        ("https://fieldclub.example.evil.example/f/7K3QXM", []),
        ("https://fieldclub.example:8443/f/7K3QXM", []),
        ("https://fieldclub.example/f/TOOLONGID", []),
        ("https://fieldclub.example/r/7K3QXM", []),
        ("https://fieldclub.example/f/7K3QXM/evidence", []),
        ("fieldclub.example/f/7K3QXM", []),
        ("", []),
    ],
)
def test_finding_links(text: str, expected: list[str]) -> None:
    assert finding_ids_in(text, PUBLIC_URL) == expected


def test_add_channel_is_idempotent(db: Session) -> None:
    first = channels.add_channel(db, CHANNEL, title="Barrow Walks")
    again = channels.add_channel(db, CHANNEL, enabled=False)
    db.commit()
    assert first.id == again.id
    assert (again.title, again.enabled) == ("Barrow Walks", False)
    with pytest.raises(channels.ChannelScanError):
        channels.add_channel(db, "not-a-channel")
