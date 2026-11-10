"""Runs a connector and stores what it yields.

One run:

1. takes a lock on the source, so two runs of the same source can't overlap,
2. upserts the `sources` row, so licence and attribution exist before any data,
3. writes an `ingest_runs` row with status `running`,
4. validates each record and upserts in batches on `(source_key, external_id)`,
   committing after every batch,
5. on a full run that finished, deletes the source's rows the run did not see,
6. finishes the `ingest_runs` row and updates `sources.record_count`.

Runs are idempotent. A run that fails records the error and deletes nothing,
so the rows from earlier runs stay. Batches already committed stay too, which
is harmless because the next run upserts them again.

A full run is one with no `bbox` and no `limit`. Only a full run can tell that
a record has gone from the source.

Deleting is the one step that can't be undone. Evidence and investigation
items point at a record by id, the link is cleared when the record goes, and a
record that comes back gets a new id. So a full run that ended cleanly but
short, because upstream truncated its answer, must not be believed. A run that
yields nothing fails. A run that would remove more than
`FIELDCLUB_INGEST_MAX_SHRINK` of what is stored fails too, unless it was started
with `allow_shrink` (`--allow-shrink` on the command line).
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import shapely
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry
from sqlalchemy import (
    Engine,
    LargeBinary,
    Table,
    bindparam,
    delete,
    func,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from fieldclub.config import get_settings
from fieldclub.db import SessionLocal
from fieldclub.errors import ConflictError
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo, fill_attribution
from fieldclub.ingest.errors import IngestError
from fieldclub.models import IngestRun, Record, Source
from fieldclub.models.common import SRID
from fieldclub.services import record_tiles
from fieldclub.vocab import IngestStatus, Period, RecordCategory

logger = logging.getLogger(__name__)

MAX_EXTERNAL_ID_LENGTH = 500
MAX_ERROR_LENGTH = 4000

# First key of the two-part advisory lock. The second is a hash of the source key.
_LOCK_NAMESPACE = 5_867_002

# The shrink check is about shares, and a share of a handful of rows says
# little. A full run may always remove this many.
SHRINK_ALWAYS_ALLOWED = 10

# Columns a re-ingest overwrites. Everything except the identity of the row.
_UPDATED_COLUMNS = (
    "name",
    "summary",
    "category",
    "record_type",
    "monument_types",
    "periods",
    "geom",
    "centroid",
    "precision_m",
    "url",
    "raw",
    "source_updated_at",
    "ingested_at",
)


class InvalidRecordError(IngestError):
    """A connector yielded a record that breaks the rules for `records`."""

    code = "ingest_invalid_record"


class EmptyIngestError(IngestError):
    """A full run yielded nothing. Deleting every row on that evidence would be reckless."""

    code = "ingest_empty"


class ShrinkTooLargeError(IngestError):
    """A full run is missing so much of what is stored that upstream probably cut its answer short."""

    code = "ingest_shrink_too_large"


class ConnectorNotConfiguredError(IngestError):
    code = "ingest_not_configured"


class IngestBusyError(ConflictError):
    code = "ingest_busy"
    message = "Another ingest run for this source is in progress."


class IngestFailedError(IngestError):
    """Raised after a failed run has been recorded. `__cause__` is what went wrong."""

    code = "ingest_failed"

    def __init__(self, source_key: str, run_id: int, cause: BaseException) -> None:
        self.source_key = source_key
        self.run_id = run_id
        super().__init__(f"Ingest of {source_key} failed (run {run_id}): {type(cause).__name__}: {cause}")


@dataclass
class RunStats:
    full: bool
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0
    outside_bbox: int = 0
    repaired: int = 0
    deleted: int = 0
    seconds: float = 0.0


def check_bbox(bbox: BBox) -> BBox:
    """Validate a west, south, east, north box in degrees."""
    assert len(bbox) == 4, "a bbox has four numbers: west, south, east, north"
    west, south, east, north = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise IngestError("A bbox must be four finite numbers.")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise IngestError("A bbox is west,south,east,north in degrees, with west < east and south < north.")
    return west, south, east, north


# How to put each kind of multi-part geometry back together from its members.
_MULTIPART_TYPES: dict[str, Callable[[Any], BaseGeometry]] = {
    "MultiPoint": shapely.MultiPoint,
    "MultiLineString": shapely.MultiLineString,
    "MultiPolygon": shapely.MultiPolygon,
    "GeometryCollection": shapely.GeometryCollection,
}


def _without_empty_parts(geom: BaseGeometry) -> tuple[BaseGeometry, bool]:
    """A multi-part geometry or collection without its empty members, and whether any were removed.

    PostGIS takes the point for `centroid` from the highest-dimension member,
    so `GEOMETRYCOLLECTION(POINT(...), POLYGON EMPTY)` would be stored with an
    empty centroid and never be found by a distance query.
    """
    if not isinstance(geom, BaseMultipartGeometry):
        return geom, False
    kept: list[BaseGeometry] = []
    changed = False
    for part in geom.geoms:
        # A collection holding nothing but empty members is itself empty.
        if part.is_empty:
            changed = True
            continue
        part, part_changed = _without_empty_parts(part)
        changed = changed or part_changed
        kept.append(part)
    if not changed:
        return geom, False
    rebuild = _MULTIPART_TYPES.get(geom.geom_type)
    assert rebuild is not None, f"don't know how to rebuild a {geom.geom_type}"
    return rebuild(kept), True


def _clean_geometry(record_id: str, geom: Any, bounds: BBox) -> tuple[BaseGeometry, bool]:
    """Check a record's geometry. Returns it in 2D, and whether it had to be repaired."""
    if not isinstance(geom, BaseGeometry):
        raise InvalidRecordError(
            f"Record {record_id}: geom must be a shapely geometry, not {type(geom).__name__}."
        )
    if geom.is_empty:
        raise InvalidRecordError(f"Record {record_id}: the geometry is empty.")
    geom, dropped_empty_parts = _without_empty_parts(geom)
    assert not geom.is_empty, "a non-empty geometry has at least one non-empty part"
    geom = shapely.force_2d(geom)
    west, south, east, north = geom.bounds
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise InvalidRecordError(f"Record {record_id}: the geometry has coordinates that are not numbers.")
    if not (bounds[0] <= west and bounds[1] <= south and east <= bounds[2] and north <= bounds[3]):
        raise InvalidRecordError(
            f"Record {record_id}: the geometry spans {west:.4f},{south:.4f} to {east:.4f},{north:.4f}, "
            f"outside the expected area {bounds}. Is it in WGS84, longitude first?"
        )
    repaired = dropped_empty_parts
    if not geom.is_valid:
        # Repair can leave empty members behind, so trim again.
        geom, _ = _without_empty_parts(shapely.make_valid(geom))
        repaired = True
        if geom.is_empty or not geom.is_valid:
            raise InvalidRecordError(
                f"Record {record_id}: the geometry is invalid and could not be repaired."
            )
    return geom, repaired


def prepare_row(
    record: RecordIn, info: SourceInfo, bounds: BBox, ingested_at: datetime
) -> tuple[dict[str, Any], bool]:
    """Validate one record and shape it for the upsert. Returns the row and whether geometry was repaired."""
    external_id = record.external_id.strip() if isinstance(record.external_id, str) else ""
    if not external_id or len(external_id) > MAX_EXTERNAL_ID_LENGTH:
        raise InvalidRecordError(
            f"A record from {info.key} has an unusable external_id: {record.external_id!r}."
        )
    name = record.name.strip() if isinstance(record.name, str) else ""
    if not name:
        raise InvalidRecordError(f"Record {external_id}: a record needs a name.")
    try:
        category = RecordCategory(record.category or info.category)
    except ValueError:
        raise InvalidRecordError(
            f"Record {external_id}: {record.category or info.category!r} is not a record category."
        ) from None
    periods = list(record.periods or ())
    unknown = [period for period in periods if period not in Period]
    if unknown:
        raise InvalidRecordError(
            f"Record {external_id}: unknown periods {unknown}. Map them to vocab.Period."
        )
    monument_types = list(record.monument_types or ())
    if any(not isinstance(term, str) or not term.strip() for term in monument_types):
        raise InvalidRecordError(f"Record {external_id}: monument types must be non-empty strings.")
    if record.precision_m is not None and not (math.isfinite(record.precision_m) and record.precision_m > 0):
        raise InvalidRecordError(f"Record {external_id}: precision_m must be a positive number of metres.")
    if record.source_updated_at is not None and record.source_updated_at.tzinfo is None:
        raise InvalidRecordError(f"Record {external_id}: source_updated_at must carry a time zone.")
    if record.raw is not None:
        if not isinstance(record.raw, dict):
            raise InvalidRecordError(f"Record {external_id}: raw must be a JSON object.")
        try:
            json.dumps(record.raw, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InvalidRecordError(f"Record {external_id}: raw is not valid JSON ({exc}).") from None
    geom, repaired = _clean_geometry(external_id, record.geom, bounds)

    row = {
        "source_key": info.key,
        "external_id": external_id,
        "name": name,
        "summary": record.summary or None,
        "category": category.value,
        "record_type": record.record_type or None,
        "monument_types": [term.strip() for term in monument_types] or None,
        "periods": [Period(period).value for period in periods] or None,
        "geom_wkb": shapely.to_wkb(shapely.set_srid(geom, SRID), include_srid=True),
        "precision_m": record.precision_m,
        "url": record.url or None,
        "raw": record.raw,
        "source_updated_at": record.source_updated_at,
        "ingested_at": ingested_at,
    }
    return row, repaired


def _records_table() -> Table:
    table = Record.__table__
    assert isinstance(table, Table)
    return table


@cache
def _upsert_statement() -> Any:
    """The batch upsert. Built once: it is the same for every batch of every run."""
    table = _records_table()
    geom = func.ST_GeomFromEWKB(bindparam("geom_wkb", type_=LargeBinary))
    # ST_PointOnSurface always lands on the geometry. A centroid can fall
    # outside a crescent-shaped or ring-shaped one.
    statement = pg_insert(table).values(geom=geom, centroid=func.ST_PointOnSurface(geom))
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.source_key, table.c.external_id],
        set_={column: statement.excluded[column] for column in _UPDATED_COLUMNS},
    )
    # xmax is zero on a row this statement inserted, and set on one it updated.
    return statement.returning(literal_column("(xmax = 0)").label("inserted"))


def _upsert_batch(db: Session, rows: list[dict[str, Any]], stats: RunStats) -> None:
    if not rows:
        return
    inserted = sum(1 for row in db.execute(_upsert_statement(), rows) if row.inserted)
    db.commit()
    stats.inserted += inserted
    stats.updated += len(rows) - inserted
    stats.seen += len(rows)


def upsert_source(db: Session, info: SourceInfo, obtained: datetime | None = None) -> None:
    """Create or refresh the `sources` row. `enabled` is left alone once the row exists.

    The attribution's `[year]` and `[date]` are filled from `obtained`, or from now.
    """
    values = {
        "name": info.name,
        "publisher": info.publisher,
        "licence": info.licence,
        "licence_url": info.licence_url,
        "attribution": fill_attribution(info.attribution, (obtained or datetime.now(UTC)).date()),
        "homepage": info.homepage,
        "coverage": info.coverage,
        "category": str(info.category),
        "access": str(info.access),
        "reuse": str(info.reuse),
    }
    statement = pg_insert(Source).values(key=info.key, enabled=info.enabled, **values)
    db.execute(statement.on_conflict_do_update(index_elements=[Source.key], set_=values))


@contextmanager
def _source_lock(engine: Engine, source_key: str) -> Iterator[None]:
    """Hold an advisory lock for the source on a connection of its own.

    A session gives its connection back to the pool at every commit, so the
    lock can't live on the session's connection.
    """
    params = {"namespace": _LOCK_NAMESPACE, "key": source_key}
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not conn.scalar(text("SELECT pg_try_advisory_lock(:namespace, hashtext(:key))"), params):
            raise IngestBusyError(f"Another ingest run for {source_key} is in progress.")
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:namespace, hashtext(:key))"), params)


def _start_time(db: Session, source_key: str) -> datetime:
    """A start time later than any `ingested_at` the source already has.

    Rows touched by a run carry its start time, and a full run deletes the
    rows that don't. That only works if no older row can share the value.
    """
    now = datetime.now(UTC)
    latest = db.scalar(select(func.max(Record.ingested_at)).where(Record.source_key == source_key))
    if latest is not None and latest >= now:
        now = latest + timedelta(microseconds=1)
    return now


def _ingest(
    db: Session,
    connector: Connector,
    started_at: datetime,
    stats: RunStats,
    bbox: BBox | None,
    limit: int | None,
    batch_size: int,
) -> None:
    info = connector.source
    area = shapely.box(*bbox) if bbox is not None else None
    seen_ids: set[str] = set()
    batch: list[dict[str, Any]] = []
    for record in connector.fetch(bbox=bbox, limit=limit):
        if not isinstance(record, RecordIn):
            raise InvalidRecordError(f"{type(connector).__name__}.fetch() yielded a {type(record).__name__}.")
        row, repaired = prepare_row(record, info, connector.bounds, started_at)
        if area is not None and not area.intersects(shapely.from_wkb(row["geom_wkb"])):
            stats.outside_bbox += 1
            continue
        if row["external_id"] in seen_ids:
            # Paged APIs repeat a record when the data shifts between pages.
            stats.duplicates += 1
            continue
        seen_ids.add(row["external_id"])
        stats.repaired += int(repaired)
        batch.append(row)
        if len(batch) >= batch_size:
            _upsert_batch(db, batch, stats)
            batch = []
            if stats.seen % (batch_size * 20) == 0:
                logger.info("%s: %d records so far", info.key, stats.seen)
        if limit is not None and len(seen_ids) >= limit:
            break
    _upsert_batch(db, batch, stats)


def _finish(
    db: Session, run_id: int, source_key: str, stats: RunStats, status: IngestStatus, error: str | None
) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(status=status.value, finished_at=now, stats=asdict(stats), error=error)
    )
    count = db.scalar(select(func.count()).select_from(Record).where(Record.source_key == source_key))
    values: dict[str, Any] = {"record_count": count}
    if status is IngestStatus.COMPLETED:
        values["last_ingest_at"] = now
    db.execute(update(Source).where(Source.key == source_key).values(**values))
    # Low-zoom record tiles read stored counts. A failed run may have committed batches, so always.
    record_tiles.refresh_counts(db, source_key)
    db.commit()


def _check_shrink(db: Session, source_key: str, started_at: datetime, stats: RunStats) -> None:
    """Refuse to delete when a full run is missing too much of what is stored."""
    stale = db.scalar(
        select(func.count())
        .select_from(Record)
        .where(Record.source_key == source_key, Record.ingested_at != started_at)
    )
    assert stale is not None, "count(*) always returns a row"
    # Every row that was there before the run was either seen again or is stale.
    stored_before = stats.updated + stale
    allowed = max(SHRINK_ALWAYS_ALLOWED, int(stored_before * get_settings().ingest_max_shrink))
    if stale > allowed:
        raise ShrinkTooLargeError(
            f"{source_key} returned {stats.seen} records, and {stale} of the {stored_before} already "
            f"stored are missing from them. Nothing was deleted, in case the source cut its answer "
            f"short. If they really have gone, run again with --allow-shrink."
        )


def run_connector(
    connector: Connector,
    *,
    bbox: BBox | None = None,
    limit: int | None = None,
    batch_size: int | None = None,
    allow_shrink: bool = False,
    session_factory: sessionmaker[Session] | None = None,
) -> IngestRun:
    """Run one connector to completion and return its `ingest_runs` row.

    `allow_shrink` lets a full run delete however many stored records it did
    not see. Without it the run fails when too many are missing.

    Raises `IngestFailedError` after recording a failed run, `IngestBusyError`
    when the source is already being ingested, and
    `ConnectorNotConfiguredError` when the connector lacks a setting it needs.
    """
    info = connector.source
    if not connector.is_configured():
        raise ConnectorNotConfiguredError(f"{info.key} is not configured, so it was skipped.")
    if bbox is not None:
        bbox = check_bbox(bbox)
    assert limit is None or limit >= 1, "limit must be at least 1"
    batch_size = batch_size or get_settings().ingest_batch_size
    assert batch_size >= 1, "batch_size must be at least 1"
    factory = session_factory or SessionLocal
    stats = RunStats(full=bbox is None and limit is None)
    clock = time.monotonic()

    with factory() as db:
        bind = db.get_bind()
        engine = bind if isinstance(bind, Engine) else bind.engine
        with _source_lock(engine, info.key):
            upsert_source(db, info)
            # We hold the lock, so a run still marked as running was killed.
            db.execute(
                update(IngestRun)
                .where(IngestRun.source_key == info.key, IngestRun.status == IngestStatus.RUNNING.value)
                .values(status=IngestStatus.FAILED.value, error="Interrupted before it finished.")
            )
            started_at = _start_time(db, info.key)
            run = IngestRun(source_key=info.key, started_at=started_at, status=IngestStatus.RUNNING.value)
            db.add(run)
            db.commit()
            run_id = run.id
            logger.info("%s: run %d started (%s)", info.key, run_id, "full" if stats.full else "partial")

            try:
                _ingest(db, connector, started_at, stats, bbox, limit, batch_size)
                if stats.full:
                    if stats.seen == 0:
                        raise EmptyIngestError(
                            f"{info.key} returned no records. Nothing was deleted, in case the source broke."
                        )
                    if not allow_shrink:
                        _check_shrink(db, info.key, started_at, stats)
                    deleted = db.execute(
                        delete(Record).where(Record.source_key == info.key, Record.ingested_at != started_at)
                    )
                    stats.deleted = int(deleted.rowcount)  # pyright: ignore[reportAttributeAccessIssue]
            except BaseException as exc:
                db.rollback()
                stats.seconds = round(time.monotonic() - clock, 3)
                error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
                _finish(db, run_id, info.key, stats, IngestStatus.FAILED, error)
                logger.error("%s: run %d failed: %s", info.key, run_id, error)
                if isinstance(exc, Exception):
                    raise IngestFailedError(info.key, run_id, exc) from exc
                raise

            stats.seconds = round(time.monotonic() - clock, 3)
            if connector.obtained_at is not None:
                # The attribution's date is when the data was obtained, which fetch() has now said.
                upsert_source(db, info, connector.obtained_at)
            _finish(db, run_id, info.key, stats, IngestStatus.COMPLETED, None)
            logger.info("%s: run %d completed: %s", info.key, run_id, asdict(stats))
            db.refresh(run)
            return run
