"""What a reference loader is, and the run that replaces its rows.

A loader declares its `SourceInfo`, the table it fills and which of that
table's rows are its own, and yields plain rows with a shapely geometry. The
run does the rest:

1. takes the source's lock, so two runs can't overlap,
2. upserts the `sources` row, so licence and attribution exist before any data,
3. writes an `ingest_runs` row with status `running`,
4. in one transaction, deletes the loader's rows (only those in the box, for a
   run with `bbox`) and inserts what `fetch()` yields, so a search never sees
   half a table,
5. finishes the `ingest_runs` row and sets `sources.record_count` to the
   number of rows the loader now owns.

A run that fails rolls back, so the rows from the last good run stay. A full
run that yields nothing fails, and so does one that would leave fewer than
`1 - FIELDCLUB_INGEST_MAX_SHRINK` of the rows it replaces, unless it was
started with `allow_shrink`. A loader takes no limit. It replaces what it
owns, so a run cut short at N rows would leave only N, and a quick trial
against a shared database would empty the table for everyone.
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
import shapely
from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement, Engine, delete, func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from fieldclub import http
from fieldclub.config import Settings, get_settings
from fieldclub.db import Base, SessionLocal
from fieldclub.ingest.base import BRITISH_ISLES, BBox, SourceInfo
from fieldclub.ingest.errors import IngestError
from fieldclub.ingest.runner import (
    SHRINK_ALWAYS_ALLOWED,
    EmptyIngestError,
    IngestFailedError,
    InvalidRecordError,
    ShrinkTooLargeError,
    check_bbox,
    source_lock,
    upsert_source,
)
from fieldclub.models import IngestRun, Source
from fieldclub.models.common import to_db_geometry
from fieldclub.services.geo import envelope
from fieldclub.vocab import IngestStatus

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 4000


class BBoxNotSupportedError(IngestError):
    code = "ingest_bbox_not_supported"


@dataclass
class LoadStats:
    full: bool
    # Rows the loader read upstream, and how many of them it kept.
    read: int = 0
    inserted: int = 0
    deleted: int = 0
    seconds: float = 0.0


class Loader(ABC):
    """Base class for a dataset that fills a lookup table instead of `records`."""

    source: ClassVar[SourceInfo]
    # The model whose table the loader fills.
    model: ClassVar[type[Base]]
    # Whether `fetch()` can be limited to a box. A loader that can't refuses `--bbox`.
    supports_bbox: ClassVar[bool] = True

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client
        # When the data was obtained upstream, which dates the attribution.
        self.obtained_at: datetime | None = None
        # How many upstream rows `fetch()` read, kept or not. Set by `fetch()`.
        self.read = 0

    @property
    def http(self) -> httpx.Client:
        return self._client or http.get_client()

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    def owned(self) -> ColumnElement[bool]:
        """Which rows of the table are this loader's, as a SQL condition."""

    @abstractmethod
    def fetch(self, *, bbox: BBox | None = None) -> Iterator[dict[str, Any]]:
        """Yield rows for `model`: column values, with `geom` as a shapely geometry in WGS84."""


def _check_geometry(source_key: str, row: dict[str, Any]) -> BaseGeometry:
    geom = row.get("geom")
    if not isinstance(geom, BaseGeometry) or geom.is_empty:
        raise InvalidRecordError(f"{source_key}: a row has no geometry: {row.get('name')!r}.")
    west, south, east, north = geom.bounds
    finite = all(math.isfinite(value) for value in (west, south, east, north))
    if not finite or not shapely.box(*BRITISH_ISLES).covers(shapely.box(west, south, east, north)):
        raise InvalidRecordError(
            f"{source_key}: {row.get('name')!r} lies outside Britain and Ireland, at {geom.bounds}."
        )
    if not geom.is_valid:
        raise InvalidRecordError(f"{source_key}: the geometry of {row.get('name')!r} is not valid.")
    return geom


def _replace(db: Session, loader: Loader, stats: LoadStats, bbox: BBox | None, batch_size: int) -> None:
    model = loader.model
    geom_column = model.__table__.c.geom
    scope = loader.owned()
    if bbox is not None:
        scope = scope & func.ST_Intersects(geom_column, envelope(bbox))
    deleted = db.execute(delete(model).where(scope))
    stats.deleted = int(deleted.rowcount)  # pyright: ignore[reportAttributeAccessIssue]
    area = shapely.box(*bbox) if bbox is not None else None
    batch: list[dict[str, Any]] = []
    for row in loader.fetch(bbox=bbox):
        geom = _check_geometry(loader.source.key, row)
        if area is not None and not area.intersects(geom):
            continue
        batch.append(row | {"geom": to_db_geometry(geom)})
        if len(batch) >= batch_size:
            db.execute(insert(model), batch)
            stats.inserted += len(batch)
            batch = []
    if batch:
        db.execute(insert(model), batch)
        stats.inserted += len(batch)
    stats.read = loader.read


def _check_full_run(loader: Loader, stats: LoadStats, allow_shrink: bool) -> None:
    """Refuse a full run that gave nothing, or far fewer rows than it would replace."""
    key = loader.source.key
    if stats.inserted == 0:
        raise EmptyIngestError(f"{key} gave no rows. Nothing was replaced, in case the source broke.")
    if allow_shrink:
        return
    lost = stats.deleted - stats.inserted
    allowed = max(SHRINK_ALWAYS_ALLOWED, int(stats.deleted * get_settings().ingest_max_shrink))
    if lost > allowed:
        raise ShrinkTooLargeError(
            f"{key} gave {stats.inserted} rows to replace {stats.deleted}. Nothing was replaced, in case "
            "the source cut its answer short. If it really is smaller, run again with --allow-shrink."
        )


def _finish(
    db: Session, run_id: int, loader: Loader, stats: LoadStats, status: IngestStatus, error: str | None
) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(status=status.value, finished_at=now, stats=asdict(stats), error=error)
    )
    count = db.scalar(select(func.count()).select_from(loader.model).where(loader.owned()))
    values: dict[str, Any] = {"record_count": count}
    if status is IngestStatus.COMPLETED:
        values["last_ingest_at"] = now
    db.execute(update(Source).where(Source.key == loader.source.key).values(**values))
    db.commit()


def run_loader(
    loader: Loader,
    *,
    bbox: BBox | None = None,
    allow_shrink: bool = False,
    batch_size: int | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> IngestRun:
    """Replace the loader's rows with what its source has now, and return the `ingest_runs` row."""
    info = loader.source
    if bbox is not None:
        if not loader.supports_bbox:
            raise BBoxNotSupportedError(f"{info.key} is loaded whole, so it takes no --bbox.")
        bbox = check_bbox(bbox)
    batch_size = batch_size or get_settings().ingest_batch_size
    stats = LoadStats(full=bbox is None)
    clock = time.monotonic()
    factory = session_factory or SessionLocal

    with factory() as db:
        bind = db.get_bind()
        engine = bind if isinstance(bind, Engine) else bind.engine
        with source_lock(engine, info.key):
            upsert_source(db, info)
            db.execute(
                update(IngestRun)
                .where(IngestRun.source_key == info.key, IngestRun.status == IngestStatus.RUNNING.value)
                .values(status=IngestStatus.FAILED.value, error="Interrupted before it finished.")
            )
            run = IngestRun(
                source_key=info.key, started_at=datetime.now(UTC), status=IngestStatus.RUNNING.value
            )
            db.add(run)
            db.commit()
            run_id = run.id
            logger.info("%s: run %d started (%s)", info.key, run_id, "full" if stats.full else "partial")
            try:
                _replace(db, loader, stats, bbox, batch_size)
                if stats.full:
                    _check_full_run(loader, stats, allow_shrink)
                db.commit()
            except BaseException as exc:
                db.rollback()
                stats.seconds = round(time.monotonic() - clock, 3)
                stats.inserted = stats.deleted = 0
                error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
                _finish(db, run_id, loader, stats, IngestStatus.FAILED, error)
                logger.error("%s: run %d failed: %s", info.key, run_id, error)
                if isinstance(exc, Exception):
                    raise IngestFailedError(info.key, run_id, exc) from exc
                raise
            stats.seconds = round(time.monotonic() - clock, 3)
            if loader.obtained_at is not None:
                upsert_source(db, info, loader.obtained_at)
            _finish(db, run_id, loader, stats, IngestStatus.COMPLETED, None)
            logger.info("%s: run %d completed: %s", info.key, run_id, asdict(stats))
            db.refresh(run)
            return run
