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

What is covered and when a source is due are `services.refresh`'s rules,
which also reports how the refresh went. For that report each refresh writes
a `refresh_runs` row as it starts and again as it ends, so one that was never
started, or was stopped part way, can be told from one that found nothing to
do.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from fieldclub.config import get_settings
from fieldclub.db import SessionLocal
from fieldclub.ingest import runner
from fieldclub.ingest.reference.base import Loader, run_loader
from fieldclub.models import RefreshRun
from fieldclub.services.refresh import Refreshable, bulk, everything, is_due, is_enabled

logger = logging.getLogger(__name__)


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
    with factory() as db:
        this = RefreshRun(started_at=datetime.now(UTC))
        db.add(this)
        db.commit()
        refresh_id = this.id
    for cls in bulk(connectors):
        key = cls.source.key
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
    # Written only here: a refresh that was stopped, or that raised, is left without an end.
    with factory() as db:
        db.execute(
            update(RefreshRun)
            .where(RefreshRun.id == refresh_id)
            .values(finished_at=datetime.now(UTC), stats=asdict(stats))
        )
        db.commit()
    return stats
