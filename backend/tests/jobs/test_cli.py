"""`fieldclub-jobs`: exit status and the one-line summary a scheduler sees."""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.jobs import cli, sources
from fieldclub.models import WatchChannel
from tests.mentions.support import data, ip_of

CHANNEL = "UCabcdefghijklmnopqrstuv"


@pytest.fixture(autouse=True)
def public_url(env: Callable[..., None]) -> None:
    env(PUBLIC_URL="https://fieldclub.example")


def serve_feed(status: int = 200) -> None:
    respx.get(host=ip_of("www.youtube.com"), path="/feeds/videos.xml").mock(
        return_value=httpx.Response(
            status, content=data("youtube-feed.xml"), headers={"content-type": "application/atom+xml"}
        )
    )


def test_add_channel_then_scan(
    db: Session, offline: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="fieldclub.jobs")
    assert cli.main(["add-channel", CHANNEL, "--title", "Barrow Walks"]) == 0
    assert db.scalar(select(WatchChannel.title)) == "Barrow Walks"
    serve_feed()
    assert cli.main(["scan-channels", "--delay", "0"]) == 0
    summaries = [r.getMessage() for r in caplog.records if r.getMessage().startswith("scan-channels:")]
    assert summaries == [
        "scan-channels: 1 channels (0 unchanged, 0 failed), 2 videos, 2 links to findings, 0 mentions added"
    ]


def test_a_failed_channel_makes_the_scan_exit_non_zero(db: Session, offline: respx.MockRouter) -> None:
    assert cli.main(["add-channel", CHANNEL]) == 0
    serve_feed(status=503)
    assert cli.main(["scan-channels", "--delay", "0"]) == 1


def test_a_bad_channel_id_is_refused(db: Session) -> None:
    assert cli.main(["add-channel", "@barrowwalks"]) == 1


def test_refresh_exit_status_follows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "refresh", lambda: sources.RefreshStats(ran=["a"]))
    assert cli.main(["refresh-sources"]) == 0
    monkeypatch.setattr(sources, "refresh", lambda: sources.RefreshStats(failed=["a"]))
    assert cli.main(["refresh-sources"]) == 1


def test_an_unexpected_error_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> sources.RefreshStats:
        raise RuntimeError("database gone")

    monkeypatch.setattr(sources, "refresh", boom)
    assert cli.main(["refresh-sources"]) == 1


@pytest.mark.parametrize(
    "argv", [["scan-channels", "--delay", "-1"], ["scan-channels", "--max-channels", "0"], []]
)
def test_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main(argv)
    assert exited.value.code == 2
