"""`fieldclub-terrain`: mirror, warm and info, over a small synthetic mirror."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldclub.terrain import cli
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
