"""Each visualisation responds to known earthworks the way the literature says it should."""

from __future__ import annotations

import math

import numpy as np
import pytest

from fieldclub.terrain import visualise as vis
from tests.terrain.fakes import earthworks, ground

SHAPE = (160, 240)
# Positions in pixels (row, column) on a 1 m grid.
MOUND = (60, 60)
DITCH = (120, 140)
BANK = (120, 180)
FLAT = (120, 100)
R = 10


@pytest.fixture(scope="module")
def land() -> np.ndarray:
    return earthworks(*ground(SHAPE))


@pytest.fixture(scope="module")
def sloping_land() -> np.ndarray:
    return earthworks(*ground(SHAPE), slope=0.05)


def test_a_tilted_plane_gives_its_exact_slope() -> None:
    east, north = ground((50, 50), res=0.5)
    for gradient in (0.01, 0.1, 1.0):
        plane = (3.0 * east * gradient / 5 + 4.0 * north * gradient / 5).astype(np.float64)
        degrees = vis.slope(plane.astype(np.float32), 0.5)[1:-1, 1:-1]
        assert np.allclose(degrees, math.degrees(math.atan(gradient)), atol=1e-3)


def test_slope_uses_the_resolution_of_each_row() -> None:
    plane = np.tile(np.arange(20, dtype=np.float32), (6, 1))
    rows = np.array([[1.0], [1.0], [2.0], [2.0], [4.0], [4.0]], dtype=np.float32)
    degrees = vis.slope(plane, rows)[1:-1, 1:-1]
    expected = np.degrees(np.arctan(1 / rows[1:-1]))
    assert np.allclose(degrees, np.broadcast_to(expected, degrees.shape), atol=1e-4)


def test_flat_ground_is_lit_by_the_sine_of_the_sun_altitude() -> None:
    flat = np.full((10, 10), 50, dtype=np.float32)
    assert np.allclose(vis.hillshade(flat, 1.0, 315, 35)[1:-1, 1:-1], math.sin(math.radians(35)), atol=1e-6)


def test_a_slope_facing_the_sun_is_brighter_than_one_facing_away() -> None:
    east, north = ground((20, 20))
    # Falls towards the north-west: faces a sun in the north-west.
    facing = (-(-east + north) * 0.3).astype(np.float32)
    away = (-facing).astype(np.float32)
    lit = vis.hillshade(facing, 1.0, 315, 35)[5, 5]
    dark = vis.hillshade(away, 1.0, 315, 35)[5, 5]
    flat = math.sin(math.radians(35))
    assert lit > flat > dark


def test_a_ridge_running_towards_the_sun_vanishes_in_single_hillshade_but_not_in_multi_direction() -> None:
    east, north = ground((60, 60))
    # A ridge running north-west to south-east, along the light from 315.
    distance = (east + north) / math.sqrt(2)
    ridge = np.exp(-((distance) ** 2) / 18).astype(np.float32)
    single = vis.hillshade(ridge, 1.0, 315, 35)
    assert np.ptp(single[10:50, 10:50]) < 0.02
    multi = vis.multi_hillshade(ridge, 1.0, (315.0, 22.5, 90.0), 35)
    assert multi.shape == (60, 60, 3)
    assert np.ptp(multi[10:50, 10:50, 1]) > 0.2


def test_local_relief_is_positive_on_a_mound_and_bank_and_negative_in_a_ditch(
    sloping_land: np.ndarray,
) -> None:
    relief = vis.local_relief(sloping_land, 20)
    assert relief[MOUND] > 1.0
    assert relief[BANK] > 0.4
    assert relief[DITCH] < -0.5


def test_local_relief_removes_a_regional_slope() -> None:
    east, north = ground((80, 80))
    plane = (100 + 0.2 * east - 0.1 * north).astype(np.float32)
    relief = vis.local_relief(plane, 10)
    assert np.abs(relief[15:-15, 15:-15]).max() < 1e-3


def test_sky_view_is_dark_in_a_ditch_and_open_on_flat_ground_and_mounds(land: np.ndarray) -> None:
    svf, openness = vis.sky_view_and_openness(land, 1.0, R)
    assert svf[FLAT] > 0.999
    assert svf[MOUND] > 0.999
    assert svf[DITCH] < 0.97
    assert svf[DITCH] < svf[FLAT]
    # Positive openness: highest on raised ground, lowest in a hollow.
    assert openness[MOUND] > openness[FLAT] > openness[DITCH]
    assert openness[BANK] > openness[FLAT]
    assert openness[FLAT] == pytest.approx(90.0, abs=0.01)


def test_sky_view_on_a_tilted_plane_matches_the_value_its_rays_see() -> None:
    res, gradient = 2.0, 0.2
    east, _ = ground((60, 60), res=res)
    plane = (gradient * east).astype(np.float32)
    svf, openness = vis.sky_view_and_openness(plane, res, 10, directions=16)
    # Along an offset (dx, dy) the ground rises by gradient * dx * res over dist * res.
    steepest = [
        max(gradient * dx / distance for dx, _, distance in vis.ray_offsets(2 * math.pi * k / 16, 1, 10))
        for k in range(16)
    ]
    rise = np.maximum(steepest, 0)
    assert svf[30, 30] == pytest.approx(np.mean(1 - rise / np.sqrt(1 + rise**2)), abs=1e-5)
    assert openness[30, 30] == pytest.approx(90 - np.degrees(np.mean(np.arctan(steepest))), abs=1e-3)
    # A plane facing the light sees less sky than flat ground, by roughly half its slope's share.
    assert 0.9 < svf[30, 30] < 1


@pytest.mark.parametrize(("r_max", "r_min"), [(10, 1), (20, 8)])
def test_flat_ground_beside_no_data_is_as_open_as_flat_ground_anywhere(r_max: int, r_min: int) -> None:
    # Flat ground with no data east of column 25, as at a coast or the edge of coverage.
    flat = np.full((60, 60), 50.0, dtype=np.float32)
    flat[:, 26:] = np.nan
    svf, openness = vis.sky_view_and_openness(flat, 1.0, r_max, r_min)
    # Rays into the gap used to count as unobstructed, which read as 118 degrees next to the edge.
    assert np.nanmax(np.abs(openness[:, :26] - 90.0)) < 1e-3
    assert np.nanmax(np.abs(svf[:, :26] - 1.0)) < 1e-6
    assert np.isfinite(openness[:, :26]).all()
    assert np.isnan(openness[:, 26:]).all()


def test_a_lone_pixel_with_no_neighbours_in_reach_has_no_value() -> None:
    lone = np.full((30, 30), np.nan, dtype=np.float32)
    lone[15, 15] = 10.0
    svf, openness = vis.sky_view_and_openness(lone, 1.0, 5, r_min=1)
    assert np.isnan(svf[15, 15])
    assert np.isnan(openness[15, 15])


def test_horizon_search_ignores_points_nearer_than_r_min(land: np.ndarray) -> None:
    near, _ = vis.sky_view_and_openness(land, 1.0, 20, r_min=1)
    far, _ = vis.sky_view_and_openness(land, 1.0, 20, r_min=8)
    # The ditch walls are within 8 m of its floor, so ignoring them opens the sky.
    assert far[DITCH] > near[DITCH]


def test_ray_offsets_are_unique_and_within_the_radius() -> None:
    offsets = vis.ray_offsets(math.radians(30), 2, 10)
    assert len({(dx, dy) for dx, dy, _ in offsets}) == len(offsets)
    assert all(1.5 <= distance <= 10.5 for _, _, distance in offsets)
    # North is up: a ray at 30 degrees east of north goes up the rows.
    assert all(dy <= 0 for _, dy, _ in offsets)
    assert all(dx >= 0 for dx, _, _ in offsets)


def test_vat_and_combined_vat_stay_between_zero_and_one(land: np.ndarray) -> None:
    for out in (
        vis.vat(land, 1.0, vis.VAT_GENERAL, 10),
        vis.vat(land, 1.0, vis.VAT_FLAT, 20, 8),
        vis.combined_vat(land, 1.0, 10, 20, 8),
    ):
        inner = out[25:-25, 25:-25]
        assert np.isfinite(inner).all()
        assert inner.min() >= 0
        assert inner.max() <= 1


def test_combined_vat_shows_the_ditch_dark_against_flat_ground(land: np.ndarray) -> None:
    out = vis.combined_vat(land, 1.0, 10, 20, 8)
    assert out[DITCH] < out[FLAT] - 0.1


def test_stretches_are_fixed_and_do_not_depend_on_the_values_present() -> None:
    small = vis.stretch(np.array([0.95, 0.96], dtype=np.float32), 0.9, 1.0)
    wide = vis.stretch(np.array([0.95, 0.5, 2.0], dtype=np.float32), 0.9, 1.0)
    assert small[0] == wide[0] == pytest.approx(0.5)
    assert wide[1] == 0
    assert wide[2] == 1
    assert vis.stretch(np.array([0.0], dtype=np.float32), 0, 50, invert=True)[0] == 1


def test_blend_modes_follow_rvt() -> None:
    base = np.array([0.25, 0.75], dtype=np.float32)
    top = np.array([0.5, 0.5], dtype=np.float32)
    assert np.allclose(vis.blend_multiply(top, base), [0.125, 0.375])
    # Overlay is decided on the base layer.
    assert np.allclose(vis.blend_overlay(top, base), [2 * 0.25 * 0.5, 1 - (1 - 2 * 0.25) * 0.5])
    assert np.allclose(vis.blend_luminosity(top, base), top)
    assert np.allclose(vis.with_opacity(top, base, 0.25), 0.25 * top + 0.75 * base)


@pytest.mark.parametrize(
    "render",
    [
        lambda z: vis.slope(z, 1.0),
        lambda z: vis.hillshade(z, 1.0),
        lambda z: vis.local_relief(z, 5),
        lambda z: vis.sky_view_and_openness(z, 1.0, 5)[0],
        lambda z: vis.sky_view_and_openness(z, 1.0, 5)[1],
        lambda z: vis.combined_vat(z, 1.0, 5, 8, 3),
    ],
)
def test_no_data_never_becomes_a_number(render, land: np.ndarray) -> None:
    holed = land.copy()
    holed[40:60, 100:130] = np.nan
    out = render(holed)
    assert np.isnan(out[40:60, 100:130]).all()
    assert np.isfinite(out[100:110, 20:30]).all()
