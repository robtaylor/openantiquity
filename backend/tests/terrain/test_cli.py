"""`fieldclub-terrain`: mirror, national build, warm, years, sources and info, over a synthetic mirror."""

from __future__ import annotations

import io
import os
import signal
import threading
import time
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from fieldclub.config import DefraSftpSettings
from fieldclub.models import Source
from fieldclub.terrain import cli, sftp
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.errors import FetchFailedError, SupplyRefusedError
from fieldclub.terrain.mirror import Fetched, LocalSourceFetcher, SftpFetcher
from fieldclub.terrain.service import Terrain
from tests.terrain.fakes import TO_LONLAT, local_mirror, local_terrain, write_source_tile

NAMES = ("SU16nw", "SU16ne", "SU17sw", "SU17se")


@pytest.fixture
def sources(tmp_path: Path) -> Path:
    for name in NAMES:
        write_source_tile(tmp_path / "src", name)
    return tmp_path / "src"


@pytest.fixture
def terrain(tmp_path: Path, sources: Path) -> Terrain:
    return local_terrain(local_mirror(tmp_path), tmp_path / "tiles")


@pytest.mark.usefixtures("db")
def test_mirror_named_tiles_then_info(terrain: Terrain, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["mirror", "SU16nw", "SV00sw"], terrain=terrain) == 0
    out = capsys.readouterr()
    assert "sources rows written: defra-lidar-composite-dtm-2022-1m" in out.out
    assert "SV00sw: not in the test-edition catalogue" in out.out
    assert "mirror 1/1" in out.err
    assert terrain.mirror.store.names() == ["SU16nw"]
    assert cli.main(["info"], terrain=terrain) == 0
    info = capsys.readouterr().out
    assert "mirrored     1 tiles" in info
    assert "overview     not built" in info


@pytest.mark.usefixtures("db")
def test_mirror_a_box_skips_what_is_already_there(
    terrain: Terrain, capsys: pytest.CaptureFixture[str]
) -> None:
    terrain.mirror.ensure("SU16nw")
    west, south = TO_LONLAT.transform(414_000, 166_000)
    east, north = TO_LONLAT.transform(416_000, 168_000)
    assert cli.main(["mirror", f"--bbox={west},{south},{east},{north}"], terrain=terrain) == 0
    assert "2 tiles asked for, 1 to add" in capsys.readouterr().out
    assert terrain.mirror.store.names() == ["SU16ne", "SU16nw"]


class Flaky:
    """A local source that fails a named tile once, as a dropped run would, and counts every fetch."""

    def __init__(self, folder: Path, fail: str) -> None:
        self.inner = LocalSourceFetcher(folder)
        self.fail = fail
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        with self.lock:
            self.calls.append(tile.name)
        if tile.name == self.fail:
            self.fail = ""
            raise OSError("the machine went away")
        return self.inner.fetch(tile, work_dir)


@pytest.mark.usefixtures("db")
def test_the_whole_country_job_resumes_without_repeating_finished_tiles(
    tmp_path: Path, sources: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flaky = Flaky(sources, fail="SU17sw")
    terrain = local_terrain(local_mirror(tmp_path, fetchers=[flaky]), tmp_path / "tiles")
    assert cli.main(["mirror", "--all", "--concurrency", "2"], terrain=terrain) == 1
    out = capsys.readouterr()
    assert "4 tiles asked for, 4 to add" in out.out
    assert "1 tiles failed or weren't tried: SU17sw. Run the same command again to retry." in out.out
    assert "GB" in out.err
    assert "left" in out.err
    assert sorted(terrain.mirror.store.names()) == sorted(set(NAMES) - {"SU17sw"})
    assert cli.main(["mirror", "--all"], terrain=terrain) == 0
    again = capsys.readouterr().out
    assert "4 tiles asked for, 1 to add" in again
    assert "each read back and checked before it was published" in again
    assert sorted(flaky.calls) == sorted([*NAMES, "SU17sw"])


def test_progress_estimates_the_time_left_from_bytes() -> None:
    now = [0.0]
    out = io.StringIO()
    progress = cli.Progress(4, "mirror", total_bytes=400_000_000, out=out, clock=lambda: now[0])
    now[0] = 100.0
    progress.step("SU16nw", size=100_000_000)
    line = progress.line()
    assert "1/4 0.1/0.4 GB" in line
    assert "1.0 MB/s" in line
    assert "about 5m00s left" in line


@pytest.mark.usefixtures("db")
def test_no_credential_or_address_reaches_the_output_or_the_log(
    tmp_path: Path, sources: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("")
    settings = DefraSftpSettings(
        defra_sftp_host="127.0.0.1",
        defra_sftp_port=1,
        defra_sftp_user="someone-secret",
        defra_sftp_password=SecretStr("not-a-real-password"),
        defra_sftp_known_hosts=known_hosts,
    )
    fetcher = SftpFetcher(lambda: sftp.defra_connector(settings), max_failures=2)
    terrain = local_terrain(local_mirror(tmp_path, fetchers=[fetcher]), tmp_path / "tiles")
    with caplog.at_level("DEBUG"):
        assert cli.main(["mirror", "SU16nw"], terrain=terrain) == 1
    out = capsys.readouterr()
    for secret in ("127.0.0.1", "someone-secret", "not-a-real-password", "composite/2022"):
        assert secret not in out.out, secret
        assert secret not in out.err, secret
        assert secret not in caplog.text, secret
    assert "SU16nw" in out.out


@pytest.mark.usefixtures("db")
def test_the_national_build_and_its_report(terrain: Terrain, capsys: pytest.CaptureFixture[str]) -> None:
    for name in NAMES:
        terrain.mirror.ensure(name)
    assert cli.main(["national", "build", "--workers", "2"], terrain=terrain) == 0
    assert "built overview" in capsys.readouterr().out
    assert cli.main(["national", "build"], terrain=terrain) == 0
    assert "already holds all 4 mirrored tiles" in capsys.readouterr().out
    assert cli.main(["info"], terrain=terrain) == 0
    assert "overview     " in capsys.readouterr().out


def test_warm_renders_the_default_layer_unless_told_otherwise(terrain: Terrain, tmp_path: Path) -> None:
    west, south = TO_LONLAT.transform(412_000, 167_000)
    east, north = TO_LONLAT.transform(412_200, 167_200)
    bbox = f"{west},{south},{east},{north}"
    assert cli.main(["warm", f"--bbox={bbox}", "--zooms", "14"], terrain=terrain) == 0
    tiles = tmp_path / "tiles"
    styles = {path.relative_to(tiles).parts[1] for path in (tiles / "lidar").rglob("*.png")}
    assert styles == {"composite"}
    assert list((tiles / "dem").rglob("*.png"))
    assert cli.main(["warm", f"--bbox={bbox}", "--zooms", "14", "--styles", "slope"], terrain=terrain) == 0
    styles = {path.relative_to(tiles).parts[1] for path in (tiles / "lidar").rglob("*.png")}
    assert styles == {"composite", "slope"}
    assert cli.main(["warm", f"--bbox={bbox}", "--styles", "nope"], terrain=terrain) == 2


def test_sources_writes_the_lidar_rows(terrain: Terrain, db: Session) -> None:
    assert cli.main(["sources"], terrain=terrain) == 0
    keys = db.scalars(select(Source.key).order_by(Source.key)).all()
    assert keys == ["defra-lidar-composite-dtm-2022-1m", "defra-lidar-survey-index-catalogues"]


def test_skip_sources_leaves_the_database_alone(terrain: Terrain, db: Session) -> None:
    assert cli.main(["mirror", "SU16nw", "--skip-sources"], terrain=terrain) == 0
    assert db.scalars(select(Source)).all() == []


def test_without_a_database_a_storing_command_says_what_to_do(
    terrain: Terrain, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreachable() -> list[str]:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(cli, "_register", unreachable)
    assert cli.main(["mirror", "SU16nw"], terrain=terrain) == 1
    assert "--skip-sources" in capsys.readouterr().err
    assert terrain.mirror.store.names() == []


def test_mirror_needs_exactly_one_way_of_naming_tiles(terrain: Terrain) -> None:
    with pytest.raises(SystemExit):
        cli.main(["mirror"], terrain=terrain)
    with pytest.raises(SystemExit):
        cli.main(["mirror", "SU16nw", "--all"], terrain=terrain)


# Tiles only the catalogue knows of, so each one needs a fetch.
UNFETCHED = [f"SU{easting}{northing}sw" for easting in range(2, 6) for northing in range(2, 5)]


class FailingFetcher:
    """Fails every fetch with `error`, counting the attempts."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.attempts = 0

    def fetch(self, tile: SourceTile, work_dir: Path) -> Fetched | None:
        self.attempts += 1
        raise self.error


def failing_terrain(tmp_path: Path, fetcher: FailingFetcher) -> Terrain:
    return local_terrain(local_mirror(tmp_path, extra=UNFETCHED, fetchers=[fetcher]), tmp_path / "tiles")


def test_a_refused_login_stops_the_whole_mirror_run(tmp_path: Path) -> None:
    fetcher = FailingFetcher(SupplyRefusedError("Defra's bulk supply rejected the user name or password."))
    terrain = failing_terrain(tmp_path, fetcher)
    assert cli.main(["mirror", "--all", "--concurrency", "1"], terrain=terrain) == 1
    assert fetcher.attempts == 1


def test_a_mirror_run_stops_after_failures_in_a_row(tmp_path: Path) -> None:
    fetcher = FailingFetcher(FetchFailedError("Reading SU22sw_DTM_1m.tif failed 5 times in a row."))
    assert len(UNFETCHED) > cli.MIRROR_FAILURES_IN_A_ROW
    terrain = failing_terrain(tmp_path, fetcher)
    assert cli.main(["mirror", "--all", "--concurrency", "1"], terrain=terrain) == 1
    assert fetcher.attempts == cli.MIRROR_FAILURES_IN_A_ROW


def test_a_success_resets_the_count_of_failures_in_a_row() -> None:
    outcomes = iter([False, False, True, False, False, True, False])

    def work(item: int) -> None:
        if not next(outcomes):
            raise FetchFailedError("failed")

    assert len(cli.run_parallel(range(7), work, 1, "test", max_failures_in_a_row=3)) == 5


def test_one_job_raising_anything_fails_that_job_and_the_run_carries_on() -> None:
    def work(job: int) -> None:
        if job == 3:
            raise ValueError("a decoder blew up")

    assert cli.run_parallel(range(10), work, 2, "jobs") == ["3"]


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_an_interrupt_starts_no_new_job_and_says_what_was_left(
    signum: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    started: list[int] = []
    lock = threading.Lock()

    def work(job: int) -> None:
        with lock:
            started.append(job)
        if job == 0:
            os.kill(os.getpid(), signum)
        time.sleep(0.05)

    def run(terrain: object, args: object) -> int:
        cli.run_parallel(range(40), work, 2, "test")
        return 0

    monkeypatch.setitem(cli.COMMANDS, "info", run)
    handlers = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    assert cli.main(["info"], terrain=object()) == 130  # type: ignore[arg-type]
    # The two in hand, and the one that replaced the first if it was submitted before the signal landed.
    assert len(started) <= 3
    err = capsys.readouterr().err
    assert f"interrupted after {len(started)} jobs (0 failed), {40 - len(started)} not started" in err
    assert "Run the same command again to resume" in err
    assert (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)) == handlers


@pytest.mark.parametrize(
    "box", ["-1.9,51.4,inf,51.45", "-1.9,51.4,nan,51.45", "-1.8,51.4,-1.9,51.45", "-1.9,51.4,-1.8", "a,b,c,d"]
)
def test_a_box_is_held_to_the_one_rule_for_a_box(box: str, terrain: Terrain) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["mirror", f"--bbox={box}"], terrain=terrain)
    assert raised.value.code == 2
