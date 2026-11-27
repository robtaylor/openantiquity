"""What the tests of the source refresh share: a time, connectors made to order, and runs already made."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy.orm import Session

from fieldclub.ingest.base import SourceInfo
from fieldclub.models import IngestRun, Source
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
    db: Session,
    key: str,
    finished_at: datetime,
    *,
    full: bool | None = True,
    status: str = "completed",
    error: str | None = None,
) -> None:
    """A run of `key` that ended at `finished_at`. `full=None` gives it no `stats`, as a run still going."""
    if db.get(Source, key) is None:
        add_source(db, key)
    db.add(
        IngestRun(
            source_key=key,
            started_at=finished_at,
            finished_at=None if status == "running" else finished_at,
            status=status,
            stats=None if full is None else {"full": full},
            error=error,
        )
    )
    db.commit()
