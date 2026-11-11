"""The ingest runner, driven by a fake connector against the real database."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
import shapely
import time_machine
from geoalchemy2.shape import to_shape
from shapely.geometry import GeometryCollection, LineString, MultiPoint, MultiPolygon, Point, Polygon, box
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from fieldclub.ingest import runner
from fieldclub.ingest.base import RecordIn
from fieldclub.ingest.runner import (
    ConnectorNotConfiguredError,
    EmptyIngestError,
    IngestBusyError,
    IngestFailedError,
    InvalidRecordError,
    ShrinkTooLargeError,
    run_connector,
)
from fieldclub.models import Evidence, IngestRun, InvestigationItem, Record, Source
from tests.ingest.fakes import SOURCE, FakeConnector, record

KEY = SOURCE.key


def names(db: Session) -> dict[str, str]:
    db.expire_all()
    rows = db.execute(select(Record.external_id, Record.name).order_by(Record.external_id))
    return {row[0]: row[1] for row in rows}


def runs(db: Session) -> list[IngestRun]:
    db.expire_all()
    return list(db.scalars(select(IngestRun).order_by(IngestRun.id)))


def source(db: Session) -> Source:
    db.expire_all()
    found = db.get(Source, KEY)
    assert found is not None
    return found


# --------------------------------------------------------------------------
# Insert, re-run, update, delete
# --------------------------------------------------------------------------


def test_first_run_inserts_records_and_the_source_row(db: Session) -> None:
    run = run_connector(FakeConnector([record("A"), record("B"), record("C")]))

    assert names(db) == {"A": "Barrow A", "B": "Barrow B", "C": "Barrow C"}
    assert run.status == "completed"
    assert run.error is None
    assert run.finished_at is not None
    assert run.finished_at >= run.started_at
    assert run.stats is not None
    assert {
        key: run.stats[key] for key in ("full", "seen", "inserted", "updated", "deleted", "duplicates")
    } == {
        "full": True,
        "seen": 3,
        "inserted": 3,
        "updated": 0,
        "deleted": 0,
        "duplicates": 0,
    }

    row = source(db)
    assert (row.name, row.publisher, row.licence, row.attribution) == (
        "Fake monuments",
        "The test suite",
        "Open Government Licence v3.0",
        "Contains made-up data",
    )
    assert (row.category, row.access, row.coverage, row.enabled) == ("monument", "bulk", "Wiltshire", True)
    assert row.reuse == "open"
    assert row.record_count == 3
    assert row.last_ingest_at is not None


def test_every_column_is_stored(db: Session) -> None:
    updated = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)
    outline = box(-1.86, 51.42, -1.85, 51.43)
    run_connector(
        FakeConnector(
            [
                record(
                    "  1005678  ",
                    "  Windmill Hill  ",
                    geom=outline,
                    category="designation",
                    summary="A causewayed enclosure.",
                    record_type="Scheduled Monument",
                    monument_types=["CAUSEWAYED ENCLOSURE", " ROUND BARROW "],
                    periods=["neolithic", "bronze_age"],
                    precision_m=10.0,
                    url="https://example.org/1005678",
                    raw={"ListEntry": 1005678, "nested": {"a": [1, 2]}},
                    source_updated_at=updated,
                )
            ]
        )
    )
    stored = db.scalars(select(Record)).one()
    assert (stored.source_key, stored.external_id, stored.name) == (KEY, "1005678", "Windmill Hill")
    assert (stored.category, stored.record_type) == ("designation", "Scheduled Monument")
    assert stored.summary == "A causewayed enclosure."
    assert stored.monument_types == ["CAUSEWAYED ENCLOSURE", "ROUND BARROW"]
    assert stored.periods == ["neolithic", "bronze_age"]
    assert stored.precision_m == 10.0
    assert stored.url == "https://example.org/1005678"
    assert stored.raw == {"ListEntry": 1005678, "nested": {"a": [1, 2]}}
    assert stored.source_updated_at == updated
    assert to_shape(stored.geom).equals(outline)
    assert db.scalar(select(func.ST_SRID(Record.geom))) == 4326
    assert db.scalar(select(func.ST_SRID(Record.centroid))) == 4326
    hits = db.scalar(
        select(func.count())
        .select_from(Record)
        .where(Record.search.op("@@")(func.websearch_to_tsquery("english", "causewayed")))
    )
    assert hits == 1


def test_category_defaults_to_the_sources_and_empty_lists_become_null(db: Session) -> None:
    run_connector(FakeConnector([record("A", summary="", url="")]))
    stored = db.scalars(select(Record)).one()
    assert stored.category == "monument"
    assert db.scalar(select(Record.raw.is_(None))) is True, "no payload is SQL NULL, not JSON null"
    assert (stored.monument_types, stored.periods, stored.summary, stored.url, stored.raw) == (
        None,
        None,
        None,
        None,
        None,
    )


def test_centroid_always_lies_on_the_geometry(db: Session) -> None:
    # The centroid of a C-shaped enclosure falls in the gap. ST_PointOnSurface doesn't.
    horseshoe = Polygon(
        [
            (-1.860, 51.420),
            (-1.850, 51.420),
            (-1.850, 51.422),
            (-1.858, 51.422),
            (-1.858, 51.428),
            (-1.850, 51.428),
            (-1.850, 51.430),
            (-1.860, 51.430),
        ]
    )
    assert not horseshoe.contains(horseshoe.centroid)
    line = LineString([(-1.86, 51.42), (-1.85, 51.43), (-1.84, 51.42)])
    run_connector(FakeConnector([record("poly", geom=horseshoe), record("line", geom=line), record("pt")]))

    rows = {row.external_id: row for row in db.scalars(select(Record))}
    assert horseshoe.contains(to_shape(rows["poly"].centroid))
    assert line.distance(to_shape(rows["line"].centroid)) < 1e-9
    assert to_shape(rows["pt"].centroid).equals(Point(-1.85, 51.43))
    on_surface = db.scalars(select(func.ST_Intersects(Record.geom, Record.centroid))).all()
    assert on_surface == [True, True, True]


def test_rerunning_unchanged_data_changes_nothing(db: Session) -> None:
    connector = FakeConnector([record("A"), record("B")])
    run_connector(connector)
    before = {row.external_id: (row.id, row.name, row.created_at) for row in db.scalars(select(Record))}

    second = run_connector(connector)
    after = {row.external_id: (row.id, row.name, row.created_at) for row in db.scalars(select(Record))}
    assert after == before, "a re-run keeps the same rows, ids included"
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 2, 0)
    assert source(db).record_count == 2
    assert [run.status for run in runs(db)] == ["completed", "completed"]


def test_changed_records_are_updated_in_place(db: Session) -> None:
    run_connector(FakeConnector([record("A", "Unnamed mound"), record("B")]))
    original = db.scalars(select(Record).where(Record.external_id == "A")).one()
    original_id, first_ingest = original.id, original.ingested_at

    run_connector(
        FakeConnector(
            [
                record("A", "Adam's Grave", lon=-1.84, lat=51.37, periods=["neolithic"], raw={"v": 2}),
                record("B"),
            ]
        )
    )
    db.expire_all()
    updated = db.scalars(select(Record).where(Record.external_id == "A")).one()
    assert updated.id == original_id
    assert (updated.name, updated.periods, updated.raw) == ("Adam's Grave", ["neolithic"], {"v": 2})
    assert to_shape(updated.geom).equals(Point(-1.84, 51.37))
    assert to_shape(updated.centroid).equals(Point(-1.84, 51.37)), "the centroid follows the geometry"
    assert updated.ingested_at > first_ingest
    grave = func.websearch_to_tsquery("english", "grave")
    assert db.scalar(select(Record.external_id).where(Record.search.op("@@")(grave))) == "A"


def test_a_full_run_deletes_what_the_source_no_longer_has(db: Session) -> None:
    run_connector(FakeConnector([record("A"), record("B"), record("C")]))
    run = run_connector(FakeConnector([record("A"), record("C"), record("D")]))

    assert set(names(db)) == {"A", "C", "D"}
    assert run.stats is not None
    assert (run.stats["inserted"], run.stats["updated"], run.stats["deleted"]) == (1, 2, 1)
    assert source(db).record_count == 3


def test_stale_deletion_leaves_other_sources_alone(db: Session) -> None:
    class OtherConnector(FakeConnector):
        source = SOURCE.__class__(**{**SOURCE.__dict__, "key": "fake-other", "name": "Other"})

    run_connector(OtherConnector([record("A"), record("Z")]))
    run_connector(FakeConnector([record("A"), record("B")]))
    run_connector(FakeConnector([record("B")]))

    rows = db.execute(
        select(Record.source_key, Record.external_id).order_by(Record.source_key, Record.external_id)
    )
    assert [tuple(row) for row in rows] == [(KEY, "B"), ("fake-other", "A"), ("fake-other", "Z")]


def test_stale_deletion_works_even_when_the_clock_stands_still(db: Session) -> None:
    with time_machine.travel(datetime(2026, 11, 10, 12, 0, tzinfo=UTC), tick=False):
        run_connector(FakeConnector([record("A"), record("B")]))
        run_connector(FakeConnector([record("B")]))
    assert set(names(db)) == {"B"}


def test_stale_deletion_works_when_the_clock_goes_backwards(db: Session) -> None:
    with time_machine.travel(datetime(2026, 11, 10, 12, 0, tzinfo=UTC), tick=False):
        run_connector(FakeConnector([record("A"), record("B")]))
    with time_machine.travel(datetime(2026, 11, 9, 12, 0, tzinfo=UTC), tick=False):
        run_connector(FakeConnector([record("B")]))
    assert set(names(db)) == {"B"}


def test_deleting_a_stale_record_keeps_evidence_that_cited_it(db: Session, make_finding) -> None:
    run_connector(FakeConnector([record("A"), record("B")]))
    cited = db.scalars(select(Record).where(Record.external_id == "A")).one()
    finding = make_finding()
    evidence = Evidence(
        finding_id=finding.id, user_id=finding.author_id, kind="record_link", record_id=cited.id
    )
    db.add(evidence)
    db.commit()

    run_connector(FakeConnector([record("B")]))
    db.refresh(evidence)
    assert evidence.record_id is None
    assert set(names(db)) == {"B"}


# --------------------------------------------------------------------------
# Failure
# --------------------------------------------------------------------------


def test_a_failed_run_keeps_old_rows_and_records_the_error(db: Session) -> None:
    run_connector(FakeConnector([record("A", "Old A"), record("B", "Old B"), record("C", "Old C")]))
    first = source(db)
    first_ingest_at = first.last_ingest_at

    broken = FakeConnector([record("A", "New A"), RuntimeError("upstream returned HTML")])
    with pytest.raises(IngestFailedError) as caught:
        run_connector(broken)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert caught.value.source_key == KEY

    assert names(db) == {"A": "Old A", "B": "Old B", "C": "Old C"}, "nothing deleted, nothing half-written"
    completed, failed = runs(db)
    assert completed.status == "completed"
    assert failed.id == caught.value.run_id
    assert failed.status == "failed"
    assert failed.error == "RuntimeError: upstream returned HTML"
    assert failed.finished_at is not None
    assert failed.stats is not None
    assert failed.stats["deleted"] == 0
    assert source(db).record_count == 3
    assert source(db).last_ingest_at == first_ingest_at, "a failed run is not the last good ingest"


def test_a_failure_after_committed_batches_still_deletes_nothing(db: Session) -> None:
    run_connector(FakeConnector([record("A", "Old A"), record("B", "Old B"), record("C", "Old C")]))
    broken = FakeConnector([record("A", "New A"), record("D", "New D"), RuntimeError("connection reset")])
    with pytest.raises(IngestFailedError):
        run_connector(broken, batch_size=2)

    # The first batch had been committed. That is fine: the rows are valid and
    # the next run will upsert them again. What matters is that B and C survive.
    assert names(db) == {"A": "New A", "B": "Old B", "C": "Old C", "D": "New D"}
    failed = runs(db)[-1]
    assert failed.status == "failed"
    assert failed.stats is not None
    assert (failed.stats["seen"], failed.stats["deleted"]) == (2, 0)
    assert source(db).record_count == 4


def test_a_run_after_a_failure_puts_things_right(db: Session) -> None:
    run_connector(FakeConnector([record("A"), record("B")]))
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector([record("C"), RuntimeError("boom")]), batch_size=1)
    run_connector(FakeConnector([record("A"), record("B")]))
    assert set(names(db)) == {"A", "B"}
    assert [run.status for run in runs(db)] == ["completed", "failed", "completed"]


def test_a_failure_on_the_very_first_run_still_leaves_a_source_and_a_run_row(db: Session) -> None:
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector([ValueError("bad payload")]))
    assert source(db).record_count == 0
    assert source(db).last_ingest_at is None
    (failed,) = runs(db)
    assert (failed.status, failed.error) == ("failed", "ValueError: bad payload")


def test_a_full_run_that_yields_nothing_fails_and_deletes_nothing(db: Session) -> None:
    run_connector(FakeConnector([record("A"), record("B")]))
    with pytest.raises(IngestFailedError) as caught:
        run_connector(FakeConnector([]))
    assert isinstance(caught.value.__cause__, EmptyIngestError)
    assert set(names(db)) == {"A", "B"}
    assert runs(db)[-1].status == "failed"


# --------------------------------------------------------------------------
# A short answer from upstream
# --------------------------------------------------------------------------


def many(count: int, start: int = 0) -> list[RecordIn]:
    return [record(f"R{index:03d}", lon=-1.9 + index * 0.0001) for index in range(start, start + count)]


def record_ids(db: Session) -> dict[str, int]:
    db.expire_all()
    return {row[0]: row[1] for row in db.execute(select(Record.external_id, Record.id))}


def test_a_truncated_full_run_fails_and_deletes_nothing(db: Session, make_finding) -> None:
    run_connector(FakeConnector(many(200)))
    cited = db.scalars(select(Record).where(Record.external_id == "R150")).one()
    finding = make_finding()
    evidence = Evidence(
        finding_id=finding.id,
        user_id=finding.author_id,
        kind="record_link",
        record_id=cited.id,
        relation="same_as",
    )
    db.add(evidence)
    db.commit()
    ids_before = record_ids(db)

    # Upstream answers cleanly, but with one record where there were 200.
    with pytest.raises(IngestFailedError) as caught:
        run_connector(FakeConnector(many(1)))
    cause = caught.value.__cause__
    assert isinstance(cause, ShrinkTooLargeError)
    assert cause.code == "ingest_shrink_too_large"
    assert "199 of the 200" in cause.message
    assert "--allow-shrink" in cause.message

    failed = runs(db)[-1]
    assert failed.status == "failed"
    assert failed.stats is not None
    assert (failed.stats["seen"], failed.stats["deleted"]) == (1, 0)
    assert source(db).record_count == 200
    db.refresh(evidence)
    assert evidence.record_id == cited.id, "the link from someone's evidence survives"

    # The next healthy run finds every record where it was, with the id it had.
    run_connector(FakeConnector(many(200)))
    assert record_ids(db) == ids_before
    db.refresh(evidence)
    assert evidence.record_id == cited.id


def test_investigation_items_keep_their_record_through_a_truncated_run(db: Session, make_user) -> None:
    from fieldclub.models import Investigation

    run_connector(FakeConnector(many(60)))
    cited = db.scalars(select(Record).where(Record.external_id == "R040")).one()
    owner = make_user()
    investigation = Investigation(public_id="INV001", owner_id=owner.id, title="Parish survey")
    db.add(investigation)
    db.flush()
    item = InvestigationItem(
        investigation_id=investigation.id, kind="record", record_id=cited.id, position=0, added_by=owner.id
    )
    db.add(item)
    db.commit()

    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector(many(5)))
    db.refresh(item)
    assert item.record_id == cited.id


def test_a_real_loss_can_be_allowed(db: Session) -> None:
    run_connector(FakeConnector(many(200)))
    run = run_connector(FakeConnector(many(1)), allow_shrink=True)
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["deleted"] == 199
    assert set(names(db)) == {"R000"}


def test_ordinary_churn_is_not_mistaken_for_truncation(db: Session) -> None:
    run_connector(FakeConnector(many(200)))
    # A quarter of the records gone, and some new ones: allowed without a flag.
    run = run_connector(FakeConnector(many(150) + many(40, start=500)))
    assert run.status == "completed"
    assert run.stats is not None
    assert (run.stats["deleted"], run.stats["inserted"], run.stats["updated"]) == (50, 40, 150)
    # One more than a quarter is refused.
    with pytest.raises(IngestFailedError) as caught:
        run_connector(FakeConnector(many(142)))
    assert isinstance(caught.value.__cause__, ShrinkTooLargeError)
    assert len(names(db)) == 190


def test_a_small_source_may_lose_a_few_records_whatever_the_share(db: Session) -> None:
    run_connector(FakeConnector(many(12)))
    run = run_connector(FakeConnector(many(2)))
    assert run.stats is not None
    assert run.stats["deleted"] == runner.SHRINK_ALWAYS_ALLOWED == 10
    run_connector(FakeConnector(many(12)))
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector(many(1)))


def test_the_share_that_may_go_is_a_setting(db: Session, env: Callable[..., None]) -> None:
    run_connector(FakeConnector(many(100)))
    env(INGEST_MAX_SHRINK="0.6")
    run = run_connector(FakeConnector(many(40)))
    assert run.stats is not None
    assert run.stats["deleted"] == 60


def test_a_partial_run_is_never_a_shrink(db: Session) -> None:
    run_connector(FakeConnector(many(200)))
    run = run_connector(FakeConnector(many(1)), limit=1)
    assert run.status == "completed"
    assert len(names(db)) == 200


def test_long_errors_are_truncated(db: Session) -> None:
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector([RuntimeError("x" * 20_000)]))
    error = runs(db)[-1].error
    assert error is not None
    assert len(error) == runner.MAX_ERROR_LENGTH


def test_a_run_left_running_by_a_killed_process_is_marked_failed(db: Session) -> None:
    run_connector(FakeConnector([record("A")]))
    db.add(IngestRun(source_key=KEY, started_at=datetime.now(UTC) - timedelta(hours=3), status="running"))
    db.commit()
    run_connector(FakeConnector([record("A")]))
    assert [(run.status, run.error) for run in runs(db)] == [
        ("completed", None),
        ("failed", "Interrupted before it finished."),
        ("completed", None),
    ]


def test_two_runs_of_one_source_cannot_overlap(db: Session, database: Engine) -> None:
    class Reentrant(FakeConnector):
        def fetch(self, *, bbox=None, limit=None):
            yield record("A")
            with pytest.raises(IngestBusyError) as caught:
                run_connector(FakeConnector([record("Z")]))
            assert caught.value.status_code == 409
            yield record("B")

    run_connector(Reentrant())
    assert set(names(db)) == {"A", "B"}
    # The lock is released afterwards, whether the run worked or not.
    with pytest.raises(IngestFailedError):
        run_connector(FakeConnector([RuntimeError("boom")]))
    run_connector(FakeConnector([record("A"), record("B")]))
    assert held_source_locks(database) == 0


def held_source_locks(engine: Engine) -> int:
    """Source locks held in this session's own database.

    pg_locks covers the whole server. Counting every advisory lock would make
    this test fail whenever another pytest session, or anything else, held one.
    """
    query = text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
        "AND classid = :namespace"
    )
    with engine.connect() as conn:
        held = conn.scalar(query, {"namespace": runner._LOCK_NAMESPACE})
    assert held is not None
    return held


def test_locks_held_elsewhere_on_the_server_are_none_of_our_business(db: Session, database: Engine) -> None:
    elsewhere = database.url.set(database="postgres")
    other = create_engine(elsewhere, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with other.connect() as conn, database.connect() as mine:
            # The same key as a source lock, taken in another database, and a
            # lock of another kind taken in ours.
            conn.execute(
                text("SELECT pg_advisory_lock(:namespace, hashtext(:key))"),
                {"namespace": runner._LOCK_NAMESPACE, "key": KEY},
            )
            mine.execute(text("SELECT pg_advisory_lock(424242)"))
            assert held_source_locks(database) == 0
            run_connector(FakeConnector([record("A")]))
            assert held_source_locks(database) == 0
    finally:
        other.dispose()
    assert set(names(db)) == {"A"}


def test_an_unconfigured_connector_is_skipped_before_anything_is_written(db: Session) -> None:
    with pytest.raises(ConnectorNotConfiguredError):
        run_connector(FakeConnector([record("A")], configured=False))
    assert db.get(Source, KEY) is None
    assert runs(db) == []


# --------------------------------------------------------------------------
# Partial runs
# --------------------------------------------------------------------------


def test_limit_stops_early_and_never_deletes(db: Session) -> None:
    run_connector(FakeConnector([record("A"), record("B"), record("C")]))
    connector = FakeConnector([record("D"), record("E"), record("F")])
    run = run_connector(connector, limit=2)

    assert set(names(db)) == {"A", "B", "C", "D", "E"}
    assert connector.calls == [{"bbox": None, "limit": 2}]
    assert run.stats is not None
    assert (run.stats["full"], run.stats["seen"], run.stats["deleted"]) == (False, 2, 0)
    assert source(db).record_count == 5


def test_bbox_keeps_only_records_inside_and_never_deletes(db: Session) -> None:
    run_connector(FakeConnector([record("old", lon=-3.0, lat=54.0)]))
    wiltshire = (-2.0, 51.0, -1.5, 51.6)
    connector = FakeConnector(
        [
            record("in", lon=-1.85, lat=51.43),
            record("out", lon=-0.12, lat=51.5),
            record("straddles", geom=box(-1.6, 51.5, -1.4, 51.7)),
        ]
    )
    run = run_connector(connector, bbox=wiltshire)

    assert set(names(db)) == {"old", "in", "straddles"}
    assert connector.calls == [{"bbox": wiltshire, "limit": None}]
    assert run.stats is not None
    assert (run.stats["full"], run.stats["seen"], run.stats["outside_bbox"]) == (False, 2, 1)


def test_an_empty_partial_run_is_not_an_error(db: Session) -> None:
    run = run_connector(FakeConnector([]), limit=10)
    assert run.status == "completed"


@pytest.mark.parametrize(
    "bbox", [(1.0, 51.0, -1.0, 52.0), (-2.0, 52.0, -1.0, 51.0), (-200.0, 51.0, -1.0, 52.0)]
)
def test_nonsense_bboxes_are_refused(db: Session, bbox: tuple[float, float, float, float]) -> None:
    with pytest.raises(runner.IngestError):
        run_connector(FakeConnector([record("A")]), bbox=bbox)
    assert runs(db) == []


# --------------------------------------------------------------------------
# Batching and duplicates
# --------------------------------------------------------------------------


@pytest.mark.parametrize("batch_size", [1, 2, 7, 500])
def test_batching_does_not_change_the_result(db: Session, batch_size: int) -> None:
    records = [record(f"R{index:03d}", lon=-1.9 + index * 0.001) for index in range(25)]
    run = run_connector(FakeConnector(records), batch_size=batch_size)
    assert run.stats is not None
    assert (run.stats["seen"], run.stats["inserted"]) == (25, 25)
    assert len(names(db)) == 25

    run = run_connector(FakeConnector(records[:20]), batch_size=batch_size)
    assert run.stats is not None
    assert (run.stats["updated"], run.stats["deleted"]) == (20, 5)
    assert len(names(db)) == 20


def test_repeated_ids_in_one_run_are_stored_once(db: Session) -> None:
    run = run_connector(
        FakeConnector(
            [record("A", "First"), record("B"), record("A", "Repeat"), record(" A ", "Padded repeat")]
        ),
        batch_size=2,
    )
    assert names(db) == {"A": "First", "B": "Barrow B"}
    assert run.stats is not None
    assert (run.stats["seen"], run.stats["duplicates"]) == (2, 2)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def bad(**fields) -> RecordIn:
    return record(fields.pop("external_id", "X"), **fields)


@pytest.mark.parametrize(
    ("bad_record", "message"),
    [
        (bad(external_id="  "), "unusable external_id"),
        (bad(external_id="x" * 501), "unusable external_id"),
        (RecordIn(external_id=123, name="N", geom=Point(-1.8, 51.4)), "unusable external_id"),  # type: ignore[arg-type]
        (bad(name="   "), "needs a name"),
        (bad(category="rumour"), "not a record category"),
        (bad(periods=["neolithic", "Late Bronze Age"]), "unknown periods"),
        (bad(monument_types=["BARROW", ""]), "monument types"),
        (bad(precision_m=0), "precision_m"),
        (bad(precision_m=float("nan")), "precision_m"),
        (bad(source_updated_at=datetime(2024, 1, 1)), "time zone"),  # noqa: DTZ001 - a naive time is the point
        (bad(raw=["not", "an", "object"]), "raw must be a JSON object"),
        (bad(raw={"when": datetime(2024, 1, 1, tzinfo=UTC)}), "raw is not valid JSON"),
        (bad(raw={"value": float("nan")}), "raw is not valid JSON"),
        (bad(geom="POINT (-1.8 51.4)"), "must be a shapely geometry"),
        (bad(geom=Point()), "geometry is empty"),
        (bad(geom=Point(float("nan"), 51.4)), "outside the expected area|not numbers"),
        (bad(geom=Point(410250, 169960)), "outside the expected area"),
        (bad(geom=Point(51.4286, -1.8542)), "outside the expected area"),
        (bad(geom=Point(2.35, 48.86)), "outside the expected area"),
    ],
)
def test_bad_records_stop_the_run(db: Session, bad_record: RecordIn, message: str) -> None:
    run_connector(FakeConnector([record("A")]))
    with pytest.raises(IngestFailedError) as caught:
        run_connector(FakeConnector([record("A", "Changed"), bad_record]))
    assert isinstance(caught.value.__cause__, InvalidRecordError)
    assert caught.value.__cause__.code == "ingest_invalid_record"
    with pytest.raises(InvalidRecordError, match=message):
        raise caught.value.__cause__
    assert names(db) == {"A": "Barrow A"}, "a bad record stops the run before anything is written"


def test_fetch_must_yield_record_in(db: Session) -> None:
    with pytest.raises(IngestFailedError, match="yielded a dict"):
        run_connector(FakeConnector([{"external_id": "A"}]))  # type: ignore[list-item]


def test_self_intersecting_polygons_are_repaired(db: Session) -> None:
    bowtie = Polygon([(-1.86, 51.42), (-1.85, 51.43), (-1.85, 51.42), (-1.86, 51.43)])
    assert not bowtie.is_valid
    run = run_connector(FakeConnector([record("bowtie", geom=bowtie), record("fine")]))
    assert run.stats is not None
    assert run.stats["repaired"] == 1
    stored = db.scalars(select(Record).where(Record.external_id == "bowtie")).one()
    shape = to_shape(stored.geom)
    assert shape.is_valid
    assert isinstance(shape, MultiPolygon)
    assert shape.area == pytest.approx(shapely.make_valid(bowtie).area)
    assert db.scalar(select(func.ST_IsValid(Record.geom)).where(Record.external_id == "bowtie")) is True


def test_empty_members_of_a_collection_are_dropped(db: Session) -> None:
    # PostGIS takes the centroid from the highest-dimension member. Left in,
    # the empty polygon would give the record an empty centroid.
    mixed = GeometryCollection([Point(-1.85, 51.43), Polygon()])
    nested = GeometryCollection(
        [GeometryCollection([Polygon(), LineString()]), box(-1.86, 51.42, -1.85, 51.43)]
    )
    run = run_connector(
        FakeConnector([record("mixed", geom=mixed), record("nested", geom=nested), record("fine")])
    )
    assert run.stats is not None
    assert run.stats["repaired"] == 2

    rows = {row.external_id: row for row in db.scalars(select(Record))}
    assert to_shape(rows["mixed"].geom).equals(GeometryCollection([Point(-1.85, 51.43)]))
    assert to_shape(rows["mixed"].centroid).equals(Point(-1.85, 51.43))
    assert to_shape(rows["nested"].geom).equals(box(-1.86, 51.42, -1.85, 51.43))
    assert db.scalar(select(func.count()).select_from(Record).where(func.ST_IsEmpty(Record.centroid))) == 0
    here = func.ST_SetSRID(func.ST_MakePoint(-1.85, 51.43), 4326)
    found = db.scalars(select(Record.external_id).where(func.ST_DWithin(Record.centroid, here, 0.001))).all()
    assert "mixed" in found, "a distance query finds it"


@pytest.mark.parametrize(
    ("wkt", "cleaned"),
    [
        ("MULTIPOLYGON (EMPTY, ((-1.86 51.42, -1.85 51.42, -1.85 51.43, -1.86 51.42)))", "MultiPolygon"),
        ("MULTIPOINT (EMPTY, (-1.85 51.43))", "MultiPoint"),
        ("MULTILINESTRING (EMPTY, (-1.86 51.42, -1.85 51.43))", "MultiLineString"),
    ],
)
def test_empty_members_of_a_parsed_multipart_geometry_are_dropped(
    db: Session, wkt: str, cleaned: str
) -> None:
    # shapely won't build these from parts, but it will parse them, and
    # parsing is how a connector gets its geometry.
    run = run_connector(FakeConnector([record("multi", geom=shapely.from_wkt(wkt))]))
    assert run.stats is not None
    assert run.stats["repaired"] == 1
    stored = to_shape(db.scalars(select(Record)).one().geom)
    assert stored.geom_type == cleaned
    assert len(stored.geoms) == 1  # pyright: ignore[reportAttributeAccessIssue]
    assert db.scalar(select(func.ST_IsEmpty(Record.centroid))) is False


def test_a_geometry_of_nothing_but_empty_members_is_refused(db: Session) -> None:
    with pytest.raises(IngestFailedError) as caught:
        run_connector(FakeConnector([record("hollow", geom=GeometryCollection([Polygon(), Point()]))]))
    assert isinstance(caught.value.__cause__, InvalidRecordError)
    assert "geometry is empty" in str(caught.value.__cause__)


def test_whole_multipart_geometry_is_left_as_it_was(db: Session) -> None:
    points = MultiPoint([(-1.85, 51.43), (-1.84, 51.42)])
    run = run_connector(FakeConnector([record("points", geom=points)]))
    assert run.stats is not None
    assert run.stats["repaired"] == 0
    assert to_shape(db.scalars(select(Record)).one().geom).equals(points)


def test_three_dimensional_geometry_is_flattened(db: Session) -> None:
    run_connector(FakeConnector([record("3d", geom=Point(-1.85, 51.43, 152.0))]))
    stored = db.scalars(select(Record)).one()
    assert not to_shape(stored.geom).has_z
    assert db.scalar(select(func.ST_NDims(Record.geom))) == 2


def test_a_connector_may_widen_its_bounds(db: Session) -> None:
    class Worldwide(FakeConnector):
        bounds = (-180.0, -90.0, 180.0, 90.0)

    run_connector(Worldwide([record("paris", geom=Point(2.35, 48.86))]))
    assert set(names(db)) == {"paris"}


# --------------------------------------------------------------------------
# The source row
# --------------------------------------------------------------------------


def test_source_details_are_refreshed_but_enabled_is_left_alone(db: Session) -> None:
    run_connector(FakeConnector([record("A")]))
    row = source(db)
    row.enabled = False
    row.attribution = "Stale attribution"
    db.commit()

    run_connector(FakeConnector([record("A")]))
    row = source(db)
    assert row.attribution == "Contains made-up data"
    assert row.enabled is False, "someone switched the source off, and a re-run must not switch it back on"


def test_the_attribution_year_and_date_are_filled_in_when_stored(db: Session) -> None:
    class Dated(FakeConnector):
        source = dataclasses.replace(SOURCE, attribution="\u00a9 Someone [year], obtained [date]")

    with time_machine.travel(datetime(2027, 1, 2, 9, tzinfo=UTC), tick=False):
        run_connector(Dated([record("A")]))
    assert source(db).attribution == "\u00a9 Someone 2027, obtained 2 January 2027"

    # A connector that says when its data was obtained dates it from then instead.
    class Cached(Dated):
        def fetch(self, *, bbox=None, limit=None):
            self.obtained_at = datetime(2026, 12, 31, 23, tzinfo=UTC)
            yield from super().fetch(bbox=bbox, limit=limit)

    with time_machine.travel(datetime(2027, 1, 2, 9, tzinfo=UTC), tick=False):
        run_connector(Cached([record("A")]))
    db.expire_all()
    assert source(db).attribution == "\u00a9 Someone 2026, obtained 31 December 2026"


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("Legal &amp; General House", "Legal & General House"),
        # Encoded twice over, as some sources send it.
        ("Wilkin &amp;amp; Sons", "Wilkin & Sons"),
        ("St Monica&#39;s Road", "St Monica's Road"),
        ("Swartland Road&lt; Dounby", "Swartland Road< Dounby"),
        ("Caf&eacute; &#x26; bar", "Café & bar"),
        ("Fish & chips; no entity here", "Fish & chips; no entity here"),
    ],
)
def test_html_entities_in_text_are_decoded_once_where_records_are_stored(given: str, stored: str) -> None:
    started = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    row, _ = runner.prepare_row(
        record("A", given, summary=given, record_type=given, monument_types=[given]),
        SOURCE,
        (-11.5, 49.0, 2.5, 61.5),
        started,
    )
    assert (row["name"], row["summary"], row["record_type"], row["monument_types"]) == (
        stored,
        stored,
        stored,
        [stored],
    )


def test_prepare_row_is_pure_and_shapes_the_upsert() -> None:
    started = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    row, repaired = runner.prepare_row(
        record(" A ", periods=["roman"]), SOURCE, (-11.5, 49.0, 2.5, 61.5), started
    )
    assert repaired is False
    assert (row["source_key"], row["external_id"], row["category"], row["periods"]) == (
        KEY,
        "A",
        "monument",
        ["roman"],
    )
    assert row["ingested_at"] == started
    geom = shapely.from_wkb(row["geom_wkb"])
    assert shapely.get_srid(geom) == 4326
    assert geom.equals(Point(-1.85, 51.43))
