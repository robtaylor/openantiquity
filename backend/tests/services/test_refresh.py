"""How the source refresh is going: whether last night's finished, and where each source it covers stands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from fieldclub.jobs.sources import refresh
from fieldclub.models import RefreshRun
from fieldclub.services.refresh import (
    OVERDUE_AFTER,
    REFRESH_HOUR_UTC,
    REFRESH_OVER_AFTER,
    RUN_LIMIT,
    everything,
    expected_at,
    report,
    source_states,
    standing,
)
from fieldclub.vocab import RefreshState
from tests.helpers import add_source
from tests.jobs.support import NOW, connector, finished_run

# The start of the refresh hour on the day of NOW, which is midday, and when that night's refresh is over.
LAST_NIGHT = NOW.replace(hour=REFRESH_HOUR_UTC)
OVER = LAST_NIGHT + REFRESH_OVER_AFTER


def states(db: Session, *classes: type, now: datetime = NOW) -> dict[str, RefreshState]:
    return {state.source_key: state.state for state in source_states(db, classes, now=now)}


def refresh_run(db: Session, started_at: datetime, finished_at: datetime | None) -> None:
    db.add(RefreshRun(started_at=started_at, finished_at=finished_at))
    db.commit()


# The refresh itself


def test_the_night_that_counts_is_the_last_one_that_is_over() -> None:
    assert LAST_NIGHT < OVER < NOW, "midday is after the night's refresh is over"
    assert expected_at(NOW) == LAST_NIGHT
    assert expected_at(OVER) == LAST_NIGHT
    # While a night's refresh may still be going, the one before is the one to ask after.
    assert expected_at(OVER - timedelta(seconds=1)) == LAST_NIGHT - timedelta(days=1)
    assert expected_at(LAST_NIGHT + timedelta(minutes=41)) == LAST_NIGHT - timedelta(days=1)


def test_the_night_is_reckoned_in_utc_whatever_the_zone_given() -> None:
    ahead = NOW.astimezone(timezone(timedelta(hours=9)))
    assert expected_at(ahead) == LAST_NIGHT


def test_a_refresh_that_finished_last_night_is_current(db: Session) -> None:
    started = LAST_NIGHT + timedelta(minutes=41)
    refresh_run(db, started, started + timedelta(hours=2))
    stood = standing(db, NOW)
    assert stood.state == RefreshState.CURRENT
    assert (stood.expected_at, stood.started_at, stood.finished_at) == (
        LAST_NIGHT,
        started,
        started + timedelta(hours=2),
    )


def test_a_night_with_no_refresh_is_overdue_the_morning_after(db: Session) -> None:
    """The machine wasn't started: the night before's refresh is the last there is."""
    before = LAST_NIGHT - timedelta(days=1) + timedelta(minutes=41)
    refresh_run(db, before, before + timedelta(hours=2))
    stood = standing(db, NOW)
    assert stood.state == RefreshState.OVERDUE
    assert (stood.started_at, stood.finished_at) == (before, before + timedelta(hours=2))


def test_a_refresh_stopped_part_way_is_overdue(db: Session) -> None:
    started = LAST_NIGHT + timedelta(minutes=41)
    refresh_run(db, started, None)
    stood = standing(db, NOW)
    assert stood.state == RefreshState.OVERDUE
    assert (stood.started_at, stood.finished_at) == (started, None)


def test_with_no_refresh_ever_written_down_it_is_overdue(db: Session) -> None:
    stood = standing(db, NOW)
    assert (stood.state, stood.started_at, stood.finished_at) == (RefreshState.OVERDUE, None, None)


def test_a_refresh_still_going_does_not_make_last_nights_overdue(db: Session) -> None:
    """Asked at four in the morning, the answer is about the night before, whose refresh finished."""
    before = LAST_NIGHT - timedelta(days=1) + timedelta(minutes=41)
    refresh_run(db, before, before + timedelta(hours=2))
    refresh_run(db, LAST_NIGHT + timedelta(minutes=41), None)
    stood = standing(db, LAST_NIGHT + timedelta(hours=1))
    assert stood.state == RefreshState.CURRENT
    assert stood.finished_at is None, "the last refresh to start is the one still going"


def test_a_refresh_run_by_hand_after_a_missed_night_makes_it_current(db: Session) -> None:
    refresh_run(db, NOW - timedelta(minutes=5), NOW - timedelta(minutes=4))
    assert standing(db, NOW).state == RefreshState.CURRENT


def test_the_job_writes_what_the_report_reads(db: Session) -> None:
    refresh([connector("fine-source")])
    assert report(db, [connector("fine-source")]).refresh.state == RefreshState.CURRENT


# Each source


def test_a_source_refreshed_within_its_max_age_is_current(db: Session) -> None:
    cls = connector("daily-source", max_age=timedelta(hours=20))
    finished_run(db, "daily-source", NOW - timedelta(hours=19))
    [state] = source_states(db, [cls], now=NOW)
    assert (state.source_key, state.state) == ("daily-source", RefreshState.CURRENT)
    assert state.last_success_at == state.last_run_at == NOW - timedelta(hours=19)
    assert state.error is None


def test_a_source_whose_last_run_failed_is_failed_and_names_the_kind_of_error(db: Session) -> None:
    cls = connector("big-source")
    finished_run(db, "big-source", NOW - timedelta(days=8))
    finished_run(
        db,
        "big-source",
        NOW - timedelta(hours=6),
        status="failed",
        error="DiskFullError: The disk filled while big.gpkg was downloaded to /data/var/ingest/big-source.",
    )
    [state] = source_states(db, [cls], now=NOW)
    assert state.state == RefreshState.FAILED
    # The kind and no more: the message can name a path or an address.
    assert state.error == "DiskFullError"
    assert state.last_success_at == NOW - timedelta(days=8)
    assert state.last_run_at == NOW - timedelta(hours=6)


def test_the_kind_of_error_is_read_from_what_the_runner_writes(db: Session) -> None:
    broken = connector("broken-source", records=[RuntimeError("upstream fell over at /data/var")])
    assert refresh([broken], now=NOW).failed == ["broken-source"]
    [state] = source_states(db, [broken], now=datetime.now(UTC))
    assert (state.state, state.error) == (RefreshState.FAILED, "RuntimeError")


def test_a_failure_that_names_no_kind_of_error_gives_none(db: Session) -> None:
    cls = connector("stopped-source")
    finished_run(
        db, "stopped-source", NOW, status="failed", full=None, error="Interrupted before it finished."
    )
    [state] = source_states(db, [cls], now=NOW)
    assert (state.state, state.error) == (RefreshState.FAILED, None)


def test_a_source_that_failed_and_then_completed_is_current(db: Session) -> None:
    cls = connector("mended-source")
    finished_run(db, "mended-source", NOW - timedelta(days=1), status="failed", error="OSError: [Errno 28]")
    finished_run(db, "mended-source", NOW - timedelta(hours=6))
    [state] = source_states(db, [cls], now=NOW)
    assert (state.state, state.error) == (RefreshState.CURRENT, None)


def test_a_run_still_going_within_its_limit_is_not_a_failure(db: Session) -> None:
    cls = connector("slow-source")
    finished_run(db, "slow-source", NOW - timedelta(days=2))
    finished_run(db, "slow-source", NOW - RUN_LIMIT, status="running", full=None)
    [state] = source_states(db, [cls], now=NOW)
    assert state.state == RefreshState.CURRENT
    assert state.last_run_at == NOW - RUN_LIMIT, "a run with no end is dated by its start"


def test_a_run_still_going_long_past_its_limit_was_lost_and_is_failed(db: Session) -> None:
    """As `timeout` leaves a run it stops: `running`, until the source's next run marks it."""
    cls = connector("killed-source")
    finished_run(db, "killed-source", NOW - timedelta(days=2))
    finished_run(db, "killed-source", NOW - RUN_LIMIT - timedelta(minutes=16), status="running", full=None)
    [state] = source_states(db, [cls], now=NOW)
    assert (state.state, state.error) == (RefreshState.FAILED, None)


@pytest.mark.parametrize(("status", "expected"), [("completed", "failed"), ("failed", "current")])
def test_a_run_limited_by_area_or_count_neither_hides_a_failure_nor_is_one(
    db: Session, status: str, expected: str
) -> None:
    cls = connector("tried-by-hand")
    whole = "failed" if status == "completed" else "completed"
    finished_run(db, "tried-by-hand", NOW - timedelta(hours=8), status=whole, error=None)
    finished_run(db, "tried-by-hand", NOW - timedelta(hours=1), full=False, status=status)
    [state] = source_states(db, [cls], now=NOW)
    assert state.state == expected
    assert state.last_run_at == NOW - timedelta(hours=8), "the run of the whole source is the one that counts"


def test_a_run_by_hand_that_is_still_going_does_not_hide_a_failure(db: Session) -> None:
    cls = connector("tried-by-hand")
    finished_run(db, "tried-by-hand", NOW - timedelta(days=1))
    finished_run(db, "tried-by-hand", NOW - timedelta(hours=6), status="failed", error="DiskFullError: full")
    finished_run(db, "tried-by-hand", NOW - timedelta(minutes=10), status="running", full=False)
    [state] = source_states(db, [cls], now=NOW)
    assert (state.state, state.error) == (RefreshState.FAILED, "DiskFullError")


def test_a_source_is_overdue_once_its_data_is_older_than_its_max_age_and_the_wait(db: Session) -> None:
    """No run failed: the refresh passed the source over, or didn't run."""
    cls = connector("daily-source", max_age=timedelta(hours=20))
    finished_run(db, "daily-source", NOW - timedelta(hours=20) - OVERDUE_AFTER + timedelta(minutes=1))
    assert states(db, cls) == {"daily-source": RefreshState.CURRENT}
    assert states(db, cls, now=NOW + timedelta(minutes=1)) == {"daily-source": RefreshState.OVERDUE}


def test_a_source_with_no_completed_full_run_is_not_loaded(db: Session) -> None:
    never = connector("never-run")
    partial = connector("partial-only")
    finished_run(db, "partial-only", NOW - timedelta(hours=1), full=False)
    assert states(db, never, partial) == {
        "never-run": RefreshState.NOT_LOADED,
        "partial-only": RefreshState.NOT_LOADED,
    }
    for state in source_states(db, [never, partial], now=NOW):
        assert (state.last_success_at, state.last_run_at) == (None, None)


def test_a_source_never_loaded_whose_last_run_failed_is_failed(db: Session) -> None:
    cls = connector("new-source")
    finished_run(
        db, "new-source", NOW - timedelta(hours=1), status="failed", error="UpstreamFormatError: no Notes"
    )
    [state] = source_states(db, [cls], now=NOW)
    assert (state.state, state.error, state.last_success_at) == (
        RefreshState.FAILED,
        "UpstreamFormatError",
        None,
    )


def test_the_sources_with_a_state_are_the_ones_the_refresh_looks_at(db: Session) -> None:
    disabled = connector("disabled-source")
    add_source(db, "disabled-source", enabled=False)
    db.commit()
    live = connector("live-source", access="live")
    second, first = connector("b-source"), connector("a-source")
    finished_run(db, "a-source", NOW)
    classes = [disabled, live, second, first]
    stats = refresh(classes, now=NOW)
    looked_at = [key for key in ("b-source", "a-source") if key in stats.ran + stats.current + stats.failed]
    assert list(states(db, *classes, now=datetime.now(UTC))) == looked_at == ["b-source", "a-source"]


def test_every_registered_bulk_source_that_is_enabled_has_a_state(db: Session) -> None:
    covered = [cls.source.key for cls in everything() if cls.source.access == "bulk" and cls.source.enabled]
    assert covered
    assert [state.source_key for state in source_states(db, now=NOW)] == covered
