"""`fieldclub-jobs due`: one hourly run clears old sign-ins and runs the scan and the refresh when due."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest
import time_machine
from sqlalchemy.orm import Session

from fieldclub.auth import sessions
from fieldclub.jobs import channels, cli, due, sources
from fieldclub.models import UserSession, WatchChannel
from tests.helpers import MakeUser, count

CHANNEL = "UCabcdefghijklmnopqrstuv"
OTHER = "UCzyxwvutsrqponmlkjihgfe"
# Midday, well away from the refresh hour.
NOON = datetime(2026, 11, 12, 12, 7, tzinfo=UTC)


def watch(db: Session, channel_id: str = CHANNEL, **columns: object) -> None:
    db.add(WatchChannel(provider="youtube", channel_id=channel_id, **columns))
    db.commit()


def test_nothing_is_due_with_no_channels_outside_the_refresh_hour(db: Session) -> None:
    assert due.what_is_due(db, NOON) == due.Due(scan_channels=False, refresh_sources=False)


def test_a_channel_never_scanned_makes_the_scan_due(db: Session) -> None:
    watch(db)
    assert due.what_is_due(db, NOON).scan_channels


def test_the_scan_is_due_six_hours_after_the_last_one_give_or_take_the_hourly_start(db: Session) -> None:
    # Fly starts an hourly machine somewhere within each hour, so a scan that
    # ran at 06:50 must still be due at the run that starts at 12:07.
    watch(db, last_checked_at=NOON - timedelta(hours=5, minutes=17))
    assert due.what_is_due(db, NOON).scan_channels

    db.query(WatchChannel).update({"last_checked_at": NOON - timedelta(hours=4, minutes=59)})
    db.commit()
    assert not due.what_is_due(db, NOON).scan_channels


def test_the_scan_follows_the_most_recent_check_so_one_run_is_not_repeated_hourly(db: Session) -> None:
    # A scan takes the oldest channels first. Once it has run, the channels it
    # reached are recent, and the next scan waits its six hours.
    watch(db, CHANNEL, last_checked_at=NOON - timedelta(hours=9))
    watch(db, OTHER, last_checked_at=NOON - timedelta(hours=1))
    assert not due.what_is_due(db, NOON).scan_channels


def test_disabled_channels_are_not_a_reason_to_scan(db: Session) -> None:
    watch(db, enabled=False)
    assert not due.what_is_due(db, NOON).scan_channels


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(due.REFRESH_HOUR_UTC - 1, False), (due.REFRESH_HOUR_UTC, True), (due.REFRESH_HOUR_UTC + 1, False)],
)
def test_the_refresh_is_due_in_its_hour_only(db: Session, hour: int, expected: bool) -> None:
    now = datetime(2026, 11, 12, hour, 41, tzinfo=UTC)
    assert due.what_is_due(db, now).refresh_sources is expected


def test_the_refresh_hour_is_read_in_utc_whatever_the_zone_given(db: Session) -> None:
    one_ahead = timezone(timedelta(hours=1))
    now = datetime(2026, 11, 12, due.REFRESH_HOUR_UTC + 1, 5, tzinfo=one_ahead)
    assert due.what_is_due(db, now).refresh_sources


def test_a_time_without_a_zone_is_refused(db: Session) -> None:
    with pytest.raises(AssertionError):
        due.what_is_due(db, datetime(2026, 11, 12, 3, 0))  # noqa: DTZ001 - the point of the test


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Which jobs `due` started, with the jobs themselves replaced."""
    started: list[str] = []

    def scan(**_: object) -> channels.ScanStats:
        started.append("scan-channels")
        return channels.ScanStats()

    def refresh() -> sources.RefreshStats:
        started.append("refresh-sources")
        return sources.RefreshStats()

    monkeypatch.setattr(channels, "scan", scan)
    monkeypatch.setattr(sources, "refresh", refresh)
    return started


def at(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    monkeypatch.setattr(due, "utc_now", lambda: now)


def test_due_runs_only_what_is_due(
    db: Session, ran: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="fieldclub.jobs")
    at(monkeypatch, NOON)

    assert cli.main(["due"]) == 0

    assert ran == []
    assert "due: nothing" in caplog.text


def test_due_runs_the_scan_before_the_refresh(
    db: Session, ran: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="fieldclub.jobs")
    watch(db)
    at(monkeypatch, NOON.replace(hour=due.REFRESH_HOUR_UTC))

    assert cli.main(["due"]) == 0

    assert ran == ["scan-channels", "refresh-sources"]
    assert "due: scan-channels, refresh-sources" in caplog.text


def test_a_failed_scan_still_lets_the_refresh_run_and_the_run_exits_non_zero(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    refreshed: list[bool] = []
    monkeypatch.setattr(channels, "scan", lambda **_: channels.ScanStats(channels=1, failed=1))
    monkeypatch.setattr(sources, "refresh", lambda: refreshed.append(True) or sources.RefreshStats())
    watch(db)
    at(monkeypatch, NOON.replace(hour=due.REFRESH_HOUR_UTC))

    assert cli.main(["due"]) == 1
    assert refreshed == [True]


def test_a_failed_refresh_makes_the_run_exit_non_zero(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "refresh", lambda: sources.RefreshStats(failed=["a"]))
    at(monkeypatch, NOON.replace(hour=due.REFRESH_HOUR_UTC))

    assert cli.main(["due"]) == 1


def test_every_hourly_run_deletes_expired_sessions(
    db: Session, make_user: MakeUser, ran: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user()
    with time_machine.travel(datetime(2020, 1, 1, tzinfo=UTC), tick=False):
        sessions.create_session(db, user)
    live = sessions.create_session(db, user)
    db.commit()
    at(monkeypatch, NOON)

    assert cli.main(["due"]) == 0

    assert ran == []
    db.expire_all()
    assert count(db, UserSession) == 1
    assert sessions.resolve_session(db, live) is not None


def test_a_failed_purge_still_lets_the_rest_run_and_the_run_exits_non_zero(
    db: Session, ran: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object, **__: object) -> sessions.Purged:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(sessions, "purge", broken)
    watch(db)
    at(monkeypatch, NOON.replace(hour=due.REFRESH_HOUR_UTC))

    assert cli.main(["due"]) == 1
    assert ran == ["scan-channels", "refresh-sources"]
