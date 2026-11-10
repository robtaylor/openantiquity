"""The national overview: built from the mirror's 8 m copies, chunk by chunk, resumable, replaced whole."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling
from rasterio.io import DatasetReader

from fieldclub.terrain import national
from fieldclub.terrain.blobs import LocalFolder
from fieldclub.terrain.mirror import Mirror
from fieldclub.terrain.national import (
    ALIGN_M,
    MANIFEST,
    OVERVIEW_COUNT,
    RESOLUTION_M,
    Builder,
    Manifest,
    NationalStore,
    NothingToBuildError,
    build_id,
    chunk_of,
)
from tests.terrain.fakes import local_mirror, write_source_tile

# Two tiles in one 50 km chunk, one in the chunk to the south.
NORTH_CHUNK = ("SU16nw", "SU16ne")
SOUTH_CHUNK = ("SU14se",)


def slope(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 100 + 0.002 * (east - 400_000) + 0.001 * (north - 140_000) + np.sin(east / 90.0)


@pytest.fixture
def sources(tmp_path: Path) -> Path:
    folder = tmp_path / "src"
    for name in (*NORTH_CHUNK, *SOUTH_CHUNK, "SU17sw"):
        write_source_tile(folder, name, formula=slope)
    return folder


def mirror_of(tmp_path: Path, sources: Path, names: tuple[str, ...]) -> Mirror:
    mirror = local_mirror(tmp_path, sources=sources)
    for name in names:
        mirror.ensure(name)
    return mirror


def builder(mirror: Mirror, tmp_path: Path) -> Builder:
    return Builder(mirror, NationalStore(LocalFolder(tmp_path / "national")), tmp_path / "work", threads=1)


def test_the_tiles_fall_in_fifty_kilometre_chunks() -> None:
    assert chunk_of("SU16nw") == chunk_of("SU16ne") == (8, 3)
    assert chunk_of("SU14se") == (8, 2)


def test_a_build_lays_the_mirror_8m_copies_on_one_aligned_grid(tmp_path: Path, sources: Path) -> None:
    mirror = mirror_of(tmp_path, sources, (*NORTH_CHUNK, *SOUTH_CHUNK))
    report = builder(mirror, tmp_path).build()
    assert not report.up_to_date
    assert report.read == 3
    store = NationalStore(LocalFolder(tmp_path / "national"))
    manifest = store.manifest()
    assert manifest is not None
    assert manifest.tiles == {*NORTH_CHUNK, *SOUTH_CHUNK}
    assert manifest.build == report.build == build_id(mirror.edition, manifest.tiles)
    with rasterio.open(store.gdal_path(manifest)) as ds:
        assert ds.res == (RESOLUTION_M, RESOLUTION_M)
        assert ds.crs.to_epsg() == 27700
        assert len(ds.overviews(1)) == OVERVIEW_COUNT
        # Every overview level is a whole number of pixels on one global grid.
        for edge in (ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top):
            assert edge % ALIGN_M == 0
        window = ds.window(410_000, 165_000, 415_000, 170_000)
        built = ds.read(1, window=window)
    with rasterio.open(mirror.store.gdal_path("SU16nw")) as tile:
        expected = tile.read(1, out_shape=(625, 625), resampling=Resampling.average)
    # Only the overview's own 1 cm encoding lies between them.
    assert np.abs(built - expected).max() <= 0.0101


def test_a_second_build_with_nothing_new_reads_nothing(tmp_path: Path, sources: Path) -> None:
    mirror = mirror_of(tmp_path, sources, NORTH_CHUNK)
    first = builder(mirror, tmp_path).build()
    again = builder(mirror, tmp_path).build()
    assert again.up_to_date
    assert again.read == 0
    assert again.build == first.build


def test_a_tile_added_to_the_mirror_is_the_only_one_read_and_old_builds_are_pruned(
    tmp_path: Path, sources: Path
) -> None:
    mirror = mirror_of(tmp_path, sources, NORTH_CHUNK)
    folder = LocalFolder(tmp_path / "national")
    first = builder(mirror, tmp_path).build()
    mirror.ensure("SU17sw")
    second = builder(mirror, tmp_path).build()
    assert second.read == 1
    assert second.build != first.build
    # The previous build stays for readers that haven't looked at national.json again.
    assert folder.names(".tif") == sorted([f"england-{first.build}.tif", f"england-{second.build}.tif"])
    mirror.ensure("SU14se")
    third = builder(mirror, tmp_path).build()
    assert third.read == 1
    assert folder.names(".tif") == sorted([f"england-{second.build}.tif", f"england-{third.build}.tif"])


def test_an_interrupted_build_resumes_from_the_last_chunk_it_finished(
    tmp_path: Path, sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mirror = mirror_of(tmp_path, sources, (*NORTH_CHUNK, *SOUTH_CHUNK))
    store = NationalStore(LocalFolder(tmp_path / "national"))
    real_paste = national.paste
    pasted: list[str] = []

    def paste_then_stop(ds: DatasetReader, res: float, data: np.ndarray, west: float, north: float) -> None:
        pasted.append(Path(ds.name).stem)
        # The south chunk is first. Halfway through the north chunk the machine goes away.
        if Path(ds.name).stem == "SU16ne":
            raise KeyboardInterrupt
        real_paste(ds, res, data, west, north)

    monkeypatch.setattr(national, "paste", paste_then_stop)
    with pytest.raises(KeyboardInterrupt):
        Builder(mirror, store, tmp_path / "work", workers=1, threads=1).build()
    assert store.manifest() is None
    assert not list((tmp_path / "national").glob("*.tif"))
    monkeypatch.setattr(national, "paste", real_paste)
    resumed = Builder(mirror, store, tmp_path / "work", workers=1, threads=1).build()
    # The finished south chunk wasn't read again; the north chunk was read whole.
    assert resumed.read == 2
    manifest = store.manifest()
    assert manifest is not None
    assert manifest.tiles == {*NORTH_CHUNK, *SOUTH_CHUNK}


def test_a_chunk_of_another_edition_is_started_again(tmp_path: Path, sources: Path) -> None:
    mirror = mirror_of(tmp_path, sources, NORTH_CHUNK)
    builder(mirror, tmp_path).build()
    chunk = national.chunk_path(tmp_path / "work" / "national" / "chunks", (8, 3))
    data, held = national.read_chunk(chunk, mirror.edition)
    assert held == set(NORTH_CHUNK)
    assert np.isfinite(data).any()
    _, other = national.read_chunk(chunk, "another-edition")
    assert other == set()


def test_a_manifest_of_another_format_is_ignored(tmp_path: Path) -> None:
    folder = LocalFolder(tmp_path)
    folder.write(MANIFEST, b'{"format": "n0", "build": "x"}', "application/json")
    assert NationalStore(folder).manifest() is None
    manifest = Manifest("abc", "england-abc.tif", "e", frozenset({"SU16nw"}), "2026-11-10T00:00:00+00:00")
    assert Manifest.from_json(manifest.to_json()) == manifest


def test_an_empty_mirror_has_nothing_to_build(tmp_path: Path, sources: Path) -> None:
    with pytest.raises(NothingToBuildError):
        builder(local_mirror(tmp_path, sources=sources), tmp_path).build()
