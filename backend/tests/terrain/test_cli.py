"""`fieldclub-terrain`: mirror, warm and info, over a small synthetic mirror."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldclub.terrain import cli
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.errors import FetchFailedError, SupplyRefusedError
from fieldclub.terrain.mirror import Fetched
from fieldclub.terrain.service import Terrain
from tests.terrain.fakes import TO_LONLAT, local_mirror, local_terrain, write_source_tile


@pytest.fixture
def terrain(tmp_path: Path) -> Terrain:
    for name in ("SU16nw", "SU16ne"):
        write_source_tile(tmp_path / "src", name)
    return local_terrain(local_mirror(tmp_path), tmp_path / "tiles")


def test_mirror_named_tiles_then_info(terrain: Terrain, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["mirror", "SU16nw", "SV00sw"], terrain=terrain) == 0
    out = capsys.readouterr()
    assert "SV00sw: not in the test-edition catalogue" in out.out
    assert "mirror 1/1" in out.err
    assert terrain.mirror.store.names() == ["SU16nw"]
    assert cli.main(["info"], terrain=terrain) == 0
    info = capsys.readouterr().out
    assert "mirrored     1 tiles" in info
    assert "national     not built" in info


def test_mirror_a_box_skips_what_is_already_there(
    terrain: Terrain, capsys: pytest.CaptureFixture[str]
) -> None:
    terrain.mirror.ensure("SU16nw")
    west, south = TO_LONLAT.transform(414_000, 166_000)
    east, north = TO_LONLAT.transform(416_000, 168_000)
    assert cli.main(["mirror", f"--bbox={west},{south},{east},{north}"], terrain=terrain) == 0
    assert "2 tiles asked for, 1 to add" in capsys.readouterr().out
    assert terrain.mirror.store.names() == ["SU16ne", "SU16nw"]


def test_warm_renders_and_caches_tiles(terrain: Terrain, tmp_path: Path) -> None:
    west, south = TO_LONLAT.transform(412_000, 167_000)
    east, north = TO_LONLAT.transform(412_200, 167_200)
    bbox = f"{west},{south},{east},{north}"
    assert cli.main(["warm", f"--bbox={bbox}", "--zooms", "14", "--styles", "slope"], terrain=terrain) == 0
    pngs = list((tmp_path / "tiles").rglob("*.png"))
    assert {path.parts[len((tmp_path / "tiles").parts)] for path in pngs} == {"lidar", "dem"}
    assert cli.main(["warm", f"--bbox={bbox}", "--styles", "nope"], terrain=terrain) == 2


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

    assert cli.run_parallel(range(7), work, 1, "test", max_failures_in_a_row=3) == 5
