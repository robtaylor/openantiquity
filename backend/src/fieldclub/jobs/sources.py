"""Source refresh: the scheduled form of `fieldclub-ingest run`.

Each registered connector for a `bulk` source, and each reference loader
(`ingest/reference/`: the gazetteer and the boundaries), is run, one at a
time, when its last successful full run finished longer ago than its
`max_age` (a class attribute, such as 20 hours for a daily export) or there
has been none. One that declares no `max_age` is refreshed once a week has
passed, so every eighth night where the refresh runs nightly. A source
is skipped when its `sources` row has been disabled, or when no row exists
yet and its connector declares it disabled, as the Wikidata cross-walk does
(Decision 0011).

A failed run is recorded as usual. That source stops there, is left until
the next refresh, and the others carry on. A source that lacks a setting it
needs, such as the contact address Wikidata asks for, or that another
process is already ingesting, is skipped.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from fieldclub.config import get_settings
from fieldclub.db import SessionLocal
from fieldclub.ingest import reference, registry, runner
from fieldclub.ingest.base import Connector
from fieldclub.ingest.reference.base import Loader, run_loader
from fieldclub.models import IngestRun, Source
from fieldclub.vocab import IngestStatus, SourceAccess

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE = timedelta(days=7)

# What the refresh runs: a connector, which fills `records`, or a reference loader.
Refreshable = type[Connector] | type[Loader]


def everything() -> list[Refreshable]:
    """Every registered connector and loader, connectors first, each in key order."""
    return [*registry.all_connectors(), *reference.all_loaders()]


def max_age(connector: Refreshable) -> timedelta:
    """How old a source's data may get before it is fetched again."""
    age = getattr(connector, "max_age", DEFAULT_MAX_AGE)
    assert isinstance(age, timedelta), f"{connector.__name__}.max_age must be a timedelta"
    assert age > timedelta(0), f"{connector.__name__}.max_age must be positive"
    return age


@dataclass
class RefreshStats:
    ran: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    current: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"refresh-sources: {len(self.ran)} refreshed, {len(self.failed)} failed"
            + (f" ({', '.join(self.failed)})" if self.failed else "")
            + f", {len(self.current)} current, {len(self.skipped)} skipped"
        )


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


def _run(cls: Refreshable, factory: sessionmaker[Session]) -> None:
    """One full run of a connector or loader. Raises as `fieldclub-ingest run` does."""
    settings = get_settings()
    if issubclass(cls, Loader):
        loader = cls(settings)
        if not loader.is_configured():
            raise runner.ConnectorNotConfiguredError(f"{cls.source.key} is not configured, so it was skipped")
        run_loader(loader, session_factory=factory)
        return
    runner.run_connector(cls(settings), session_factory=factory)


def refresh(
    connectors: Sequence[Refreshable] | None = None,
    *,
    now: datetime | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> RefreshStats:
    """Run every bulk source that is due, connectors and loaders, one after another."""
    connectors = everything() if connectors is None else connectors
    factory = session_factory or SessionLocal
    stats = RefreshStats()
    for cls in connectors:
        key = cls.source.key
        if cls.source.access != SourceAccess.BULK.value:
            continue
        with factory() as db:
            enabled = is_enabled(db, cls)
            due = enabled and is_due(db, cls, now or datetime.now(UTC))
        if not enabled:
            stats.skipped.append(key)
            continue
        if not due:
            stats.current.append(key)
            continue
        try:
            _run(cls, factory)
        except (runner.ConnectorNotConfiguredError, runner.IngestBusyError) as exc:
            logger.info("%s: %s", key, exc.message)
            stats.skipped.append(key)
            continue
        except runner.IngestFailedError as exc:
            # The runner has recorded the failure. Leave this source until next time.
            logger.error("%s", exc.message)
            stats.failed.append(key)
            continue
        stats.ran.append(key)
    return stats
