"""`infra/jobs/mirror_shard.py` runs the shares it is given of the elevation copy, in order.

The script is loaded from its file, with the catalogue made small and
`fieldclub-terrain mirror` replaced by a stand-in that records what it was asked.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest

from fieldclub.terrain.catalogue import SourceTile

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = REPO_ROOT / "infra" / "jobs" / "mirror_shard.py"
    spec = importlib.util.spec_from_file_location("infra_mirror_shard", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shard = _load()

SIZES = {"SU16nw": 90, "SU16ne": 60, "SU16sw": 50, "SU16se": 40}
TILES = [SourceTile(name, size) for name, size in SIZES.items()]


@dataclass
class Mirror:
    """A stand-in for `fieldclub-terrain mirror`: the tile lists it was run on, and a status per tile."""

    runs: list[list[str]] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)

    def __call__(self, argv: list[str]) -> int:
        assert argv[0] == "mirror"
        assert argv[-3:] == ["--concurrency", "1", "--skip-sources"]
        tiles = argv[1:-3]
        self.runs.append(tiles)
        return max((self.statuses.get(tile, 0) for tile in tiles), default=0)


@pytest.fixture
def mirror(monkeypatch: pytest.MonkeyPatch) -> Mirror:
    stand_in = Mirror()
    monkeypatch.setattr(shard, "england_catalogue", lambda: iter(TILES))
    monkeypatch.setattr(shard.cli, "main", stand_in)
    return stand_in


def test_shares_are_of_about_equal_bytes_and_hold_every_tile_once() -> None:
    split = shard.shares(TILES, 2)

    assert split == [["SU16nw", "SU16se"], ["SU16ne", "SU16sw"]]


def test_the_named_shares_run_in_the_order_given(mirror: Mirror) -> None:
    assert shard.main(["--shares", "2", "--share", "2", "--share", "1"]) == 0

    assert mirror.runs == [["SU16ne", "SU16sw"], ["SU16nw", "SU16se"]]


def test_a_failed_share_stops_the_run_with_its_status(mirror: Mirror) -> None:
    mirror.statuses["SU16ne"] = 3

    assert shard.main(["--shares", "2", "--share", "2", "--share", "1"]) == 3

    assert mirror.runs == [["SU16ne", "SU16sw"]]


def test_a_share_that_failed_is_run_again_by_naming_it(mirror: Mirror) -> None:
    assert shard.main(["--shares", "4", "--share", "3"]) == 0

    assert mirror.runs == [shard.shares(TILES, 4)[2]]


@pytest.mark.parametrize(
    "argv",
    [
        ["--shares", "4"],
        ["--shares", "4", "--share", "0"],
        ["--shares", "4", "--share", "5"],
        ["--shares", "0", "--share", "1"],
        ["--shares", "4", "--share", "1", "--concurrency", "9"],
    ],
)
def test_bad_arguments_are_refused(mirror: Mirror, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        shard.main(argv)

    assert exited.value.code == 2
    assert mirror.runs == []
