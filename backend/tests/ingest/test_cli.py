"""`fieldclub-ingest list` and `fieldclub-ingest run`."""

from __future__ import annotations

import dataclasses
import subprocess
from collections.abc import Iterator
from typing import ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import cli, registry
from fieldclub.models import IngestRun, Record
from tests.ingest.fakes import SOURCE, FakeConnector, record


class CliConnector(FakeConnector):
    """Built by the CLI as `cls(settings)`, so its records live on the class."""

    queue: ClassVar[list] = []
    ready: ClassVar[bool] = True
    last_call: ClassVar[dict] = {}

    def __init__(self, settings=None) -> None:
        super().__init__(type(self).queue, configured=type(self).ready)

    def fetch(self, *, bbox=None, limit=None):
        type(self).last_call = {"bbox": bbox, "limit": limit}
        yield from super().fetch(bbox=bbox, limit=limit)


@pytest.fixture
def registered() -> Iterator[type[CliConnector]]:
    saved = dict(registry._registry)
    CliConnector.queue = [record("A"), record("B"), record("C", lon=-3.0, lat=54.0)]
    CliConnector.ready = True
    CliConnector.last_call = {}
    registry.register(CliConnector)
    yield CliConnector
    registry._registry.clear()
    registry._registry.update(saved)


def test_list_with_no_connectors(capsys: pytest.CaptureFixture[str]) -> None:
    # Discover first, so the real connectors can't register after the clear.
    registry.discover()
    saved = dict(registry._registry)
    registry._registry.clear()
    try:
        assert cli.main(["list"]) == 0
    finally:
        registry._registry.update(saved)
    assert capsys.readouterr().out.strip() == "No connectors are registered yet."


def test_list_shows_each_connector(
    registered: type[CliConnector], capsys: pytest.CaptureFixture[str]
) -> None:
    @registry.register
    class NeedsKey(CliConnector):
        source = dataclasses.replace(SOURCE, key="aaa-needs-key", name="Needs a key", access="live")

        def is_configured(self) -> bool:
            return False

    assert cli.main(["list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["KEY", "CATEGORY", "ACCESS", "READY", "NAME"]
    assert lines[1].split() == ["aaa-needs-key", "monument", "live", "no", "Needs", "a", "key"]
    assert lines[2].split() == ["fake-monuments", "monument", "bulk", "yes", "Fake", "monuments"]


def test_run_ingests_and_reports(
    db: Session, registered: type[CliConnector], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "fake-monuments"]) == 0
    assert (
        capsys.readouterr()
        .out.strip()
        .startswith("fake-monuments: 3 records (3 new, 0 updated, 0 removed) in ")
    )
    assert set(db.scalars(select(Record.external_id))) == {"A", "B", "C"}
    assert registered.last_call == {"bbox": None, "limit": None}


def test_run_passes_bbox_and_limit(db: Session, registered: type[CliConnector]) -> None:
    assert cli.main(["run", "fake-monuments", "--bbox", "-2,51,-1.5,51.6", "--limit", "1"]) == 0
    assert registered.last_call == {"bbox": (-2.0, 51.0, -1.5, 51.6), "limit": 1}
    assert set(db.scalars(select(Record.external_id))) == {"A"}
    stats = db.scalars(select(IngestRun.stats)).one()
    assert stats is not None
    assert stats["full"] is False


def test_a_run_that_would_empty_most_of_a_source_needs_allow_shrink(
    db: Session, registered: type[CliConnector], capsys: pytest.CaptureFixture[str]
) -> None:
    registered.queue = [record(f"R{index:02d}") for index in range(40)]
    assert cli.main(["run", "fake-monuments"]) == 0
    capsys.readouterr()

    registered.queue = [record("R00")]
    assert cli.main(["run", "fake-monuments"]) == 1
    refused = capsys.readouterr().err
    assert "39 of the 40" in refused
    assert "--allow-shrink" in refused
    assert len(db.scalars(select(Record.external_id)).all()) == 40

    assert cli.main(["run", "fake-monuments", "--allow-shrink"]) == 0
    assert "(0 new, 1 updated, 39 removed)" in capsys.readouterr().out
    assert db.scalars(select(Record.external_id)).all() == ["R00"]


def test_run_of_an_unknown_key_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "no-such-source"]) == 1
    assert "No connector called 'no-such-source'" in capsys.readouterr().err


def test_run_reports_failure_with_a_non_zero_exit(
    db: Session, registered: type[CliConnector], capsys: pytest.CaptureFixture[str]
) -> None:
    registered.queue = [record("A"), RuntimeError("upstream is down")]
    assert cli.main(["run", "fake-monuments"]) == 1
    assert "upstream is down" in capsys.readouterr().err
    assert db.scalars(select(IngestRun.status)).all() == ["failed"]


def test_an_unconfigured_source_is_skipped_not_failed(
    db: Session, registered: type[CliConnector], capsys: pytest.CaptureFixture[str]
) -> None:
    registered.ready = False
    assert cli.main(["run", "fake-monuments"]) == 0
    assert "not configured, so it was skipped" in capsys.readouterr().out
    assert db.scalars(select(IngestRun)).all() == []


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["run"],
        ["dance"],
        ["run", "fake-monuments", "--bbox", "1,2,3"],
        ["run", "fake-monuments", "--bbox", "a,b,c,d"],
        ["run", "fake-monuments", "--bbox", "1,51,-1,52"],
        ["run", "fake-monuments", "--limit", "0"],
        ["run", "fake-monuments", "--limit", "many"],
    ],
)
def test_bad_usage_exits_with_2(arguments: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(arguments)
    assert caught.value.code == 2
    assert "usage: fieldclub-ingest" in capsys.readouterr().err


def test_parse_bbox() -> None:
    assert cli.parse_bbox("-2,51,-1.5,51.6") == (-2.0, 51.0, -1.5, 51.6)
    assert cli.parse_bbox(" -2 , 51 , -1.5 , 51.6 ") == (-2.0, 51.0, -1.5, 51.6)


def test_a_bbox_with_a_negative_longitude_works_with_or_without_an_equals_sign(
    db: Session, registered: type[CliConnector]
) -> None:
    for arguments in (["--bbox", "-2,51,-1.5,51.6"], ["--bbox=-2,51,-1.5,51.6"]):
        registered.last_call = {}
        assert cli.main(["run", "fake-monuments", *arguments]) == 0
        assert registered.last_call["bbox"] == (-2.0, 51.0, -1.5, 51.6)
    with pytest.raises(SystemExit):
        cli.main(["run", "fake-monuments", "--bbox"])


def test_the_console_script_is_installed(db: Session) -> None:
    result = subprocess.run(
        ["fieldclub-ingest", "list"], capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[:5] == ["KEY", "CATEGORY", "ACCESS", "READY", "NAME"]
