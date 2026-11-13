"""A run keeps its lock's connection in use, and stops as soon as the lock has gone.

The lock lives on a connection of its own. On the hosted database a connection
that carries no statement for somewhere between half an hour and an hour is
closed, so a run that left it alone from its start to its last step failed
there once it took longer than that, having read every record.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import ClassVar

import pytest
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fieldclub.ingest import runner
from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.reference.base import Loader, run_loader
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Place
from tests.ingest.fakes import SOURCE, FakeConnector, record


def lock_holder(database: Engine) -> tuple[int, datetime]:
    """The backend holding this database's one source lock, and when it last ran a statement."""
    query = text(
        "SELECT a.pid, a.query_start FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE l.locktype = 'advisory' AND l.classid = :namespace "
        "AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    )
    with database.connect() as conn:
        rows = conn.execute(query, {"namespace": runner._LOCK_NAMESPACE}).all()
    assert len(rows) == 1, rows
    return rows[0].pid, rows[0].query_start


@pytest.fixture
def checked_at_every_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "LOCK_CHECK_EVERY_S", 0.0)


def test_the_lock_s_connection_is_used_while_records_flow(
    db: Session, database: Engine, checked_at_every_record: None
) -> None:
    used: list[datetime] = []

    class Watches(FakeConnector):
        def fetch(self, *, bbox=None, limit=None):
            for name in "ABC":
                yield record(name)
                used.append(lock_holder(database)[1])

    run_connector(Watches())

    assert used[0] < used[1] < used[2], "each record found the lock's connection used since the last"


def test_the_lock_s_connection_is_left_alone_between_checks(db: Session, database: Engine) -> None:
    assert runner.LOCK_CHECK_EVERY_S >= 30, "a check every record would be a round trip for each"
    used: list[datetime] = []

    class Watches(FakeConnector):
        def fetch(self, *, bbox=None, limit=None):
            for name in "ABC":
                yield record(name)
                used.append(lock_holder(database)[1])

    run_connector(Watches())

    assert used[0] == used[1] == used[2]


def test_a_check_asks_only_when_one_is_due_counting_from_the_last(db: Session, database: Engine) -> None:
    clock = [0.0]

    def used() -> datetime:
        return lock_holder(database)[1]

    with runner.source_lock(database, "a-source", clock=lambda: clock[0]) as still_held:
        taken = used()
        clock[0] = runner.LOCK_CHECK_EVERY_S - 1
        still_held(if_due=True)
        assert used() == taken, "not due yet"
        clock[0] = runner.LOCK_CHECK_EVERY_S
        still_held(if_due=True)
        first = used()
        assert first > taken, "due"
        clock[0] = 2 * runner.LOCK_CHECK_EVERY_S - 1
        still_held(if_due=True)
        assert used() == first, (
            "due again a whole interval after the last check, not after the lock was taken"
        )
        still_held()
        forced = used()
        assert forced > first, "a check before a step that can't be undone always asks"
        clock[0] = 3 * runner.LOCK_CHECK_EVERY_S - 2
        still_held(if_due=True)
        assert used() == forced, "and the interval starts again from it"


def test_a_run_stops_at_the_first_check_after_its_lock_has_gone(
    db: Session, database: Engine, checked_at_every_record: None
) -> None:
    asked_for: list[str] = []

    class LosesItsLock(FakeConnector):
        def fetch(self, *, bbox=None, limit=None):
            asked_for.append("A")
            yield record("A")
            with database.connect() as conn:
                assert conn.scalar(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": lock_holder(database)[0]}
                )
            for name in "BCDE":
                asked_for.append(name)
                yield record(name)

    with pytest.raises(IngestFailedError) as caught:
        run_connector(LosesItsLock())

    assert isinstance(caught.value.__cause__, runner.IngestLockLostError)
    assert asked_for == ["A", "B"], "the run went on reading a source it no longer held"


class WatchedPlaces(Loader):
    """A loader of three places that notes, after each, when the lock's connection was last used."""

    source: ClassVar[SourceInfo] = dataclasses.replace(SOURCE, key="watched-places", category="map_label")
    model = Place
    database: ClassVar[Engine]
    used: ClassVar[list[datetime]] = []
    lose_after_first: ClassVar[bool] = False

    def owned(self):
        return Place.source == self.source.key

    def fetch(self, *, bbox=None):
        lost = False
        for n, lon in enumerate((-1.85, -1.84, -1.83)):
            self.read += 1
            yield {
                "name": f"Place {n}",
                "kind": "village",
                "geom": Point(lon, 51.43),
                "rank": 700,
                "source": self.source.key,
            }
            if lost:
                continue
            pid, used = lock_holder(self.database)
            type(self).used.append(used)
            if n == 0 and self.lose_after_first:
                with self.database.connect() as conn:
                    assert conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
                lost = True


@pytest.fixture
def places(database: Engine) -> type[WatchedPlaces]:
    WatchedPlaces.database = database
    WatchedPlaces.used = []
    WatchedPlaces.lose_after_first = False
    return WatchedPlaces


def test_a_reference_loader_uses_the_lock_s_connection_too(
    db: Session, places: type[WatchedPlaces], checked_at_every_record: None
) -> None:
    run_loader(places())

    assert places.used[0] < places.used[1] < places.used[2]


def test_a_reference_loader_whose_lock_has_gone_replaces_nothing(
    db: Session, places: type[WatchedPlaces], checked_at_every_record: None
) -> None:
    run_loader(places())
    places.used = []
    places.lose_after_first = True

    with pytest.raises(IngestFailedError) as caught:
        run_loader(places())

    assert isinstance(caught.value.__cause__, runner.IngestLockLostError)
    assert len(places.used) == 1, "the loader went on reading a source it no longer held"
    assert db.scalar(select(func.count()).select_from(Place)) == 3, (
        "the rows of the run before are still there"
    )


def test_a_reference_loader_asks_once_more_before_it_replaces_anything(
    db: Session, places: type[WatchedPlaces]
) -> None:
    run_loader(places())
    before = set(db.scalars(select(Place.id)))
    places.lose_after_first = True
    loader = places()

    with pytest.raises(IngestFailedError) as caught:
        run_loader(loader)

    assert isinstance(caught.value.__cause__, runner.IngestLockLostError)
    assert loader.read == 3, "no check was due while the rows were read"
    assert set(db.scalars(select(Place.id))) == before, "the rows of the run before are still there"
