"""Fingerprints of what each cache version stands for, so a change of pixels can't keep its version.

Each style is rendered over a fixed synthetic landscape with an edge of no
data, at three zooms, and the elevation read is fingerprinted from a
synthetic mirror. When a test here fails, something changed the pixels: a
parameter, a stretch, a floor, `visualise.py`, `grid.py`, the sampler. Bump
the style's `version` in `styles.py` (or `ELEVATION_FORMAT` or `DEM_VERSION`
in `render.py`) and record the new fingerprint and version here. Changing the
fingerprint without the version would serve old tiles from every cache.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fieldclub.storage import LocalStorage
from fieldclub.terrain.grid import Window, tile_at
from fieldclub.terrain.mirror import Mirror
from fieldclub.terrain.render import DEM_VERSION, ELEVATION_FORMAT, render_values, terrarium_decode
from fieldclub.terrain.sources import mirror_source
from fieldclub.terrain.styles import STYLES, elevation_buffer
from tests.helpers import AVEBURY
from tests.terrain.fakes import (
    TO_LONLAT,
    FunctionSource,
    decode_png,
    laplacian,
    local_mirror,
    rolling_hills,
    single_source_renderer,
    small_cog,
    write_source_tile,
)

ZOOMS = (11, 13, 16)

# Style id: (version, {zoom: (mean, standard deviation)} of its values over the landscape).
STYLE_FINGERPRINTS: dict[str, tuple[str, dict[int, tuple[float, float]]]] = {
    "composite": ("2", {11: (0.69819, 0.02935), 13: (0.67168, 0.05361), 16: (0.66631, 0.05585)}),
    "local_relief": ("2", {11: (0.49999, 0.03228), 13: (0.5, 0.03634), 16: (0.49945, 0.02935)}),
    "sky_view": ("2", {11: (0.92678, 0.03765), 13: (0.91335, 0.03687), 16: (0.91814, 0.03498)}),
    "multi_shade": ("1", {11: (0.57293, 0.02505), 13: (0.57271, 0.03433), 16: (0.57934, 0.03496)}),
    "slope": ("1", {11: (0.95483, 0.02097), 13: (0.93937, 0.02955), 16: (0.93686, 0.03152)}),
    "openness": ("2", {11: (0.82633, 0.02232), 13: (0.82689, 0.02304), 16: (0.83545, 0.01325)}),
}

# ELEVATION_FORMAT and {zoom: (mean height, mean |Laplacian|)} read from the synthetic mirror.
ELEVATION_FINGERPRINT = ("e2", {13: (103.9479, 0.22964), 16: (105.0787, 0.00373)})

# DEM_VERSION and {zoom: (mean height, share of sea level)} of a Terrarium tile partly without data.
DEM_FINGERPRINT = ("2", {15: (69.9681, 0.38477)})


def landscape(zoom: int) -> tuple[np.ndarray, Window]:
    x, y = tile_at(*AVEBURY, zoom)
    window = Window.tile(zoom, x, y, elevation_buffer(zoom))
    edge = window.x_centres()[window.width * 3 // 4]
    source = FunctionSource(lambda xs, ys: np.where(xs < edge, rolling_hills(xs, ys), np.nan))
    return source.read(window.bounds, window.width, window.height), window


def style_fingerprint(style_id: str, zoom: int) -> tuple[float, float]:
    elevation, window = landscape(zoom)
    values = render_values(STYLES[style_id], elevation, window, elevation_buffer(zoom))
    return round(float(np.nanmean(values)), 5), round(float(np.nanstd(values)), 5)


def curved(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 100 + 3 * np.sin(east / 23.0) * np.cos(north / 17.0) + 0.002 * (east - 410_000)


@pytest.fixture(scope="module")
def synthetic_mirror(tmp_path_factory: pytest.TempPathFactory) -> Mirror:
    root = tmp_path_factory.mktemp("versions")
    write_source_tile(root / "src", "SU16nw", res=2.0, formula=curved)
    return local_mirror(root, convert=small_cog(overview_count=2))


def elevation_fingerprint(mirror: Mirror, zoom: int) -> tuple[float, float]:
    x, y = tile_at(*TO_LONLAT.transform(412_500, 167_500), zoom)
    window = Window(zoom, x * 512 + 128, y * 512 + 128, 128, 128)
    z = mirror_source(mirror).read(window.bounds, window.width, window.height).astype(np.float64)
    return round(float(np.mean(z)), 4), round(float(np.mean(np.abs(laplacian(z)))), 5)


def dem_fingerprint(tmp_path: Path) -> tuple[float, float]:
    x, y = tile_at(*AVEBURY, 15)
    edge = Window.tile(15, x, y).x_centres()[300]
    source = FunctionSource(lambda xs, ys: np.where(xs < edge, rolling_hills(xs, ys), np.nan))
    renderer = single_source_renderer(source, LocalStorage(tmp_path))
    rgb = decode_png(renderer.dem_png(15, x, y).png)
    heights = terrarium_decode(rgb)
    return round(float(heights.mean()), 4), round(float((heights == 0).mean()), 5)


def _changed(found: dict[int, tuple[float, float]], recorded: dict[int, tuple[float, float]]) -> bool:
    """Whether a fingerprint moved by more than rounding and platform differences explain."""
    assert set(found) == set(recorded), "fingerprints must cover the same zooms"
    return not np.allclose([found[z] for z in recorded], list(recorded.values()), rtol=1e-5, atol=2e-4)


def test_every_style_has_a_fingerprint() -> None:
    assert set(STYLE_FINGERPRINTS) == set(STYLES)


@pytest.mark.parametrize("style_id", list(STYLES))
def test_a_style_whose_pixels_changed_has_a_new_version(style_id: str) -> None:
    version, recorded = STYLE_FINGERPRINTS[style_id]
    found = {zoom: style_fingerprint(style_id, zoom) for zoom in ZOOMS}
    assert STYLES[style_id].version == version, (
        f"record {style_id}'s fingerprint {found} with version {STYLES[style_id].version!r}"
    )
    assert not _changed(found, recorded), (
        f"{style_id}'s pixels changed to {found}: bump its version in styles.py and record both here"
    )


def test_elevation_whose_values_changed_has_a_new_format(synthetic_mirror: Mirror) -> None:
    version, recorded = ELEVATION_FINGERPRINT
    found = {zoom: elevation_fingerprint(synthetic_mirror, zoom) for zoom in recorded}
    assert version == ELEVATION_FORMAT, f"record the fingerprint {found} with {ELEVATION_FORMAT!r}"
    assert not _changed(found, recorded), (
        f"the elevation read changed to {found}: bump ELEVATION_FORMAT in render.py and record both here"
    )


def test_dem_tiles_whose_values_changed_have_a_new_version(tmp_path: Path) -> None:
    version, recorded = DEM_FINGERPRINT
    found = {15: dem_fingerprint(tmp_path)}
    assert version == DEM_VERSION, f"record the fingerprint {found} with {DEM_VERSION!r}"
    assert not _changed(found, recorded), (
        f"Terrarium tiles changed to {found}: bump DEM_VERSION in render.py and record both here"
    )
