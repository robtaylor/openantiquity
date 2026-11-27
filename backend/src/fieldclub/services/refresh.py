"""The source refresh: what it covers, when a source is due, and where it stands.

`jobs.sources.refresh` runs each bulk source and reference loader whose last
completed full run finished longer ago than its `max_age`, once a night, in
the hour `REFRESH_HOUR_UTC` (`jobs.due`). The rules it follows are here, so
that the job and whoever asks how it went read the same ones.

`report` says how it went, for someone watching from outside
(`GET /sources/refresh-state`):

- The refresh itself is `current` when one that started at or after the last
  night that should be over by now has finished, and `overdue` otherwise: it
  wasn't started, or was stopped part way. `jobs.sources.refresh` writes a
  `refresh_runs` row as it starts and again as it ends.
- A source is `failed` when its last run failed, or has been running for
  longer than a run is allowed. It is `overdue` when no run failed and its
  last completed full run is older than its `max_age` and `OVERDUE_AFTER`,
  which is what a source the refresh keeps passing over looks like. It is
  `not_loaded` when it has never had a completed full run.

A run limited by area or count, as one made by hand can be, is neither a
refresh nor a failure of one, and is left out of both.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from fieldclub.ingest import reference, registry
from fieldclub.ingest.base import Connector
from fieldclub.ingest.reference.base import Loader
from fieldclub.ingest.runner import error_kind
from fieldclub.models import IngestRun, RefreshRun, Source
from fieldclub.vocab import IngestStatus, RefreshState, SourceAccess

DEFAULT_MAX_AGE = timedelta(days=7)
# 03:00 to 03:59 UTC: 03:00 in winter and 04:00 in summer in London, when the site is quietest.
REFRESH_HOUR_UTC = 3
# How long a refresh, or one source's run, may take: the limit the hourly machine's command and a run by
# hand are given (`scheduled` and `ingest` in infra/fly_jobs.py, which a test holds to this).
RUN_LIMIT = timedelta(hours=6)
# How long after its limit a run is given to be stopped and written down before it is counted as lost.
_SLACK = timedelta(minutes=15)
# How long after the start of its hour a night's refresh is over, however it went.
REFRESH_OVER_AFTER = timedelta(hours=1) + RUN_LIMIT + _SLACK
# How long past its `max_age` a source's data may be before it is overdue. A source that comes due just
# after one night's refresh waits a day for the next, which may take its whole limit.
OVERDUE_AFTER = timedelta(days=1) + RUN_LIMIT + timedelta(hours=6)

# What the refresh runs: a connector, which fills `records`, or a reference loader.
Refreshable = type[Connector] | type[Loader]


def everything() -> list[Refreshable]:
    """Every registered connector and loader, connectors first, each in key order."""
    return [*registry.all_connectors(), *reference.all_loaders()]


def bulk(connectors: Sequence[Refreshable]) -> list[Refreshable]:
    """The ones whose data is kept here, and so can be refreshed (Decision 0007)."""
    return [cls for cls in connectors if cls.source.access == SourceAccess.BULK.value]


def max_age(connector: Refreshable) -> timedelta:
    """How old a source's data may get before it is fetched again."""
    age = getattr(connector, "max_age", DEFAULT_MAX_AGE)
    assert isinstance(age, timedelta), f"{connector.__name__}.max_age must be a timedelta"
    assert age > timedelta(0), f"{connector.__name__}.max_age must be positive"
    return age


def _in_full() -> ColumnElement[bool]:
    """A run of the whole source. A row with no `stats`, from before a run said so at its start, counts."""
    return IngestRun.stats["full"].as_boolean().isnot(False)


def last_success(db: Session, source_key: str) -> datetime | None:
    """When the source's last completed full run finished. A run limited by area or count doesn't count."""
    return db.scalar(
        select(func.max(IngestRun.finished_at)).where(
            IngestRun.source_key == source_key,
            IngestRun.status == IngestStatus.COMPLETED.value,
            IngestRun.stats["full"].as_boolean().is_(True),
        )
    )


def is_enabled(db: Session, connector: Refreshable) -> bool:
    stored = db.scalar(select(Source.enabled).where(Source.key == connector.source.key))
    return connector.source.enabled if stored is None else stored


def is_due(db: Session, connector: Refreshable, now: datetime) -> bool:
    age = max_age(connector)
    finished = last_success(db, connector.source.key)
    return finished is None or now - finished >= age


@dataclass(frozen=True)
class RefreshStanding:
    """Where the refresh itself stands: whether the last night that is over by now had one that finished."""

    state: RefreshState
    # The start of the hour that night's refresh was due to start in.
    expected_at: datetime
    # When the last refresh of any night started and finished. One stopped part way never finished.
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class SourceRefresh:
    """Where one source stands with the refresh."""

    source_key: str
    state: RefreshState
    last_success_at: datetime | None
    last_run_at: datetime | None
    # The kind of error the last run failed with, and never its message, which can name a path or an address.
    error: str | None


@dataclass(frozen=True)
class RefreshReport:
    refresh: RefreshStanding
    sources: list[SourceRefresh]


def expected_at(now: datetime) -> datetime:
    """The start of the refresh hour of the last night that is over by `now`."""
    assert now.tzinfo is not None, "the time must carry its zone"
    night = now.astimezone(UTC).replace(hour=REFRESH_HOUR_UTC, minute=0, second=0, microsecond=0)
    while night + REFRESH_OVER_AFTER > now:
        night -= timedelta(days=1)
    return night


def standing(db: Session, now: datetime) -> RefreshStanding:
    """Whether a refresh has finished since the last night that should have had one."""
    expected = expected_at(now)
    finished = db.scalar(
        select(func.count())
        .select_from(RefreshRun)
        .where(RefreshRun.started_at >= expected, RefreshRun.finished_at.is_not(None))
    )
    last = db.scalars(
        select(RefreshRun).order_by(RefreshRun.started_at.desc(), RefreshRun.id.desc()).limit(1)
    ).first()
    return RefreshStanding(
        state=RefreshState.CURRENT if finished else RefreshState.OVERDUE,
        expected_at=expected,
        started_at=None if last is None else last.started_at,
        finished_at=None if last is None else last.finished_at,
    )


def _failed(run: IngestRun, now: datetime) -> bool:
    """Whether a run failed, or was lost: still `running` when no run is allowed to be."""
    lost = run.status == IngestStatus.RUNNING.value and now - run.started_at > RUN_LIMIT + _SLACK
    return lost or run.status == IngestStatus.FAILED.value


def source_states(
    db: Session, connectors: Sequence[Refreshable] | None = None, *, now: datetime
) -> list[SourceRefresh]:
    """Where each source the refresh covers stands, in the order the refresh runs them."""
    covered = bulk(everything() if connectors is None else connectors)
    keys = [cls.source.key for cls in covered]
    # Each source's last run of the whole source: the newest row, since a run is written as it starts.
    newest = (
        select(func.max(IngestRun.id))
        .where(IngestRun.source_key.in_(keys), _in_full())
        .group_by(IngestRun.source_key)
    )
    last_runs = {run.source_key: run for run in db.scalars(select(IngestRun).where(IngestRun.id.in_(newest)))}
    states = []
    for cls in covered:
        key = cls.source.key
        if not is_enabled(db, cls):
            continue
        last = last_runs.get(key)
        failure = last if last is not None and _failed(last, now) else None
        success = last_success(db, key)
        if failure is not None:
            state = RefreshState.FAILED
        elif success is None:
            state = RefreshState.NOT_LOADED
        elif now - success >= max_age(cls) + OVERDUE_AFTER:
            state = RefreshState.OVERDUE
        else:
            state = RefreshState.CURRENT
        states.append(
            SourceRefresh(
                source_key=key,
                state=state,
                last_success_at=success,
                last_run_at=None if last is None else last.finished_at or last.started_at,
                error=None if failure is None else error_kind(failure.error),
            )
        )
    return states


def report(
    db: Session, connectors: Sequence[Refreshable] | None = None, *, now: datetime | None = None
) -> RefreshReport:
    """How the refresh is going: the refresh itself, then each source it covers."""
    now = now or datetime.now(UTC)
    return RefreshReport(refresh=standing(db, now), sources=source_states(db, connectors, now=now))
