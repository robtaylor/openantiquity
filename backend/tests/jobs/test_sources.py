"""Source refresh: each bulk source runs when its data is older than its connector's `max_age`."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest.base import SourceInfo
from fieldclub.jobs.sources import DEFAULT_MAX_AGE, refresh
from fieldclub.models import IngestRun, Record, Source
from tests.helpers import add_source
from tests.ingest.fakes import SOURCE, FakeConnector, record

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


def connector(key: str, *, records: list | None = None, access: str = "bulk", **attrs: object) -> type:
    """A connector class the job builds as `cls(settings)`, with its records on the class."""
    info = dataclasses.replace(SOURCE, key=key, access=access)
    queue = [record("A"), record("B")] if records is None else records

    class Made(FakeConnector):
        source: ClassVar[SourceInfo] = info
        runs: ClassVar[int] = 0

        def __init__(self, settings: object = None) -> None:
            super().__init__(queue, configured=bool(attrs.get("configured", True)))

        def fetch(self, *, bbox=None, limit=None):
            type(self).runs += 1
            yield from super().fetch(bbox=bbox, limit=limit)

    if "max_age" in attrs:
        Made.max_age = attrs["max_age"]  # type: ignore[attr-defined]
    Made.__name__ = f"Connector_{key.replace('-', '_')}"
    return Made


def finished_run(
    db: Session, key: str, finished_at: datetime, *, full: bool = True, status: str = "completed"
) -> None:
    if db.get(Source, key) is None:
        add_source(db, key)
    db.add(
        IngestRun(
            source_key=key,
            started_at=finished_at,
            finished_at=finished_at,
            status=status,
            stats={"full": full},
        )
    )
    db.commit()


def test_a_source_never_run_is_run(db: Session) -> None:
    cls = connector("fresh-source")
    stats = refresh([cls], now=NOW)
    assert stats.ran == ["fresh-source"]
    assert cls.runs == 1
    assert db.scalar(select(IngestRun.status).where(IngestRun.source_key == "fresh-source")) == "completed"


def test_a_source_runs_only_once_its_data_is_older_than_max_age(db: Session) -> None:
    cls = connector("daily-source", max_age=timedelta(hours=20))
    finished_run(db, "daily-source", NOW - timedelta(hours=19))
    assert refresh([cls], now=NOW).current == ["daily-source"]
    assert cls.runs == 0
    assert refresh([cls], now=NOW + timedelta(hours=2)).ran == ["daily-source"]
    assert cls.runs == 1


def test_without_max_age_a_source_is_refreshed_weekly(db: Session) -> None:
    cls = connector("weekly-source")
    finished_run(db, "weekly-source", NOW - DEFAULT_MAX_AGE + timedelta(minutes=1))
    assert refresh([cls], now=NOW).current == ["weekly-source"]
    assert refresh([cls], now=NOW + timedelta(minutes=1)).ran == ["weekly-source"]


@pytest.mark.parametrize(("full", "status"), [(False, "completed"), (True, "failed")])
def test_only_a_completed_full_run_counts(db: Session, full: bool, status: str) -> None:
    cls = connector("partial-source", max_age=timedelta(days=1))
    finished_run(db, "partial-source", NOW - timedelta(hours=1), full=full, status=status)
    assert refresh([cls], now=NOW).ran == ["partial-source"]


def test_a_failure_stops_that_source_and_the_next_carries_on(db: Session) -> None:
    broken = connector("broken-source", records=[record("A"), RuntimeError("upstream fell over")])
    fine = connector("fine-source")
    stats = refresh([broken, fine], now=NOW)
    assert stats.failed == ["broken-source"]
    assert stats.ran == ["fine-source"]
    assert broken.runs == 1
    statuses = dict(db.execute(select(IngestRun.source_key, IngestRun.status)).all())
    assert statuses == {"broken-source": "failed", "fine-source": "completed"}
    assert db.scalar(select(Record.id).where(Record.source_key == "fine-source").limit(1)) is not None
    assert "1 failed (broken-source)" in stats.summary()


def test_disabled_live_and_unconfigured_sources_are_skipped(db: Session) -> None:
    disabled = connector("disabled-source")
    add_source(db, "disabled-source", enabled=False)
    db.commit()
    live = connector("live-source", access="live")
    unconfigured = connector("keyless-source", configured=False)
    stats = refresh([disabled, live, unconfigured], now=NOW)
    assert stats.ran == []
    assert stats.skipped == ["disabled-source", "keyless-source"]
    assert disabled.runs == live.runs == unconfigured.runs == 0


def test_a_bad_max_age_is_a_bug(db: Session) -> None:
    with pytest.raises(AssertionError):
        refresh([connector("odd-source", max_age=3600)], now=NOW)
