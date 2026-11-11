"""Source refresh: each bulk source and reference loader runs when its data is older than its `max_age`."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.reference.base import Loader
from fieldclub.jobs.sources import DEFAULT_MAX_AGE, everything, refresh
from fieldclub.models import IngestRun, Place, Record, Source
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


class FakePlaces(Loader):
    """A loader of two places, which counts its runs and fails when told to."""

    source: ClassVar[SourceInfo] = dataclasses.replace(SOURCE, key="fake-places", category="map_label")
    model = Place
    runs: ClassVar[int] = 0
    broken: ClassVar[bool] = False

    def owned(self):
        return Place.source == self.source.key

    def fetch(self, *, bbox=None):
        type(self).runs += 1
        if type(self).broken:
            raise RuntimeError("upstream fell over")
        for n, lon in enumerate((-1.85, -1.84)):
            self.read += 1
            yield {
                "name": f"Place {n}",
                "kind": "village",
                "geom": Point(lon, 51.43),
                "rank": 700,
                "source": self.source.key,
            }


@pytest.fixture
def places() -> type[FakePlaces]:
    FakePlaces.runs = 0
    FakePlaces.broken = False
    return FakePlaces


def test_reference_loaders_are_refreshed_too(db: Session, places: type[FakePlaces]) -> None:
    assert refresh([places], now=NOW).ran == ["fake-places"]
    assert db.scalar(select(func.count()).select_from(Place)) == 2
    # Its full run counts like a connector's, so it isn't run again until it is due.
    assert refresh([places], now=NOW + timedelta(hours=1)).current == ["fake-places"]
    assert places.runs == 1


def test_a_loader_that_fails_stops_there_and_keeps_its_rows(db: Session, places: type[FakePlaces]) -> None:
    refresh([places], now=NOW)
    places.broken = True
    # Runs record the real time they finished, so look well past it.
    stats = refresh([places, connector("after-places")], now=datetime.now(UTC) + 2 * DEFAULT_MAX_AGE)
    assert (stats.failed, stats.ran) == (["fake-places"], ["after-places"])
    assert db.scalar(select(func.count()).select_from(Place)) == 2


def test_a_disabled_loader_is_skipped(db: Session, places: type[FakePlaces]) -> None:
    add_source(db, "fake-places", enabled=False)
    db.commit()
    assert refresh([places], now=NOW).skipped == ["fake-places"]
    assert places.runs == 0


def test_the_refresh_covers_every_connector_and_loader() -> None:
    keys = [cls.source.key for cls in everything()]
    assert {"os-open-names", "ons-countries-2025", "ons-counties-2025"} <= set(keys)
    assert "wikimedia-wikidata-heritage-items" in keys
    assert len(keys) == len(set(keys))


def test_wikidata_is_skipped_without_a_contact_even_when_enabled(db: Session, env) -> None:
    from fieldclub.ingest import registry

    env(CONTACT="", USER_AGENT="")
    wikidata = registry.get("wikimedia-wikidata-heritage-items")
    # Disabled by default (Decision 0011), so enable it as an operator would.
    add_source(db, wikidata.source.key, enabled=True)
    db.commit()
    assert refresh([wikidata], now=NOW).skipped == [wikidata.source.key]
