"""Archaeological visualisations of elevation, as pure numpy functions.

These reimplement algorithms and presets of the Relief Visualization Toolbox
(`rvt_py`, Apache-2.0), as read for the browser-terrain-rendering spike. Cite
Zaksek, Ostir and Kokalj 2011 (Remote Sensing 3: 398-415), Kokalj, Zaksek and
Ostir 2011 (Antiquity 85: 263-273) and Kokalj and Somrak 2019 (Remote Sensing
11(7): 747).

Every function takes elevation in metres with NaN for no data, and the ground
resolution in metres per pixel: a number, or a column of one value per row,
because a Web Mercator pixel shrinks towards the pole. Results have the input's
shape. Pixels within a kernel's radius of the edge see less than the whole
neighbourhood, so callers pass a buffered array and crop. A pixel with no
elevation gives NaN.

Radii here are in pixels. `styles.py` turns the published radii in metres
into pixels for each zoom level. Stretches are fixed and linear and never
depend on the tile's own values, so neighbouring tiles always match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter

Resolution = float | np.ndarray


def _row_resolution(res: Resolution, height: int) -> np.ndarray:
    """The resolution as a float32 column of one value per row."""
    column = np.asarray(res, dtype=np.float32)
    if column.ndim == 0:
        column = np.full((height, 1), float(column), dtype=np.float32)
    assert column.shape == (height, 1), (
        f"resolution must be a number or one value per row, got {column.shape}"
    )
    assert bool((column > 0).all()), "resolution must be positive"
    return column


def gradients(z: np.ndarray, res: Resolution) -> tuple[np.ndarray, np.ndarray]:
    """dz/d(east) and dz/d(north) by central differences, as `rvt.vis` does. NaN on the outer pixels."""
    z = np.asarray(z, dtype=np.float32)
    rows = _row_resolution(res, z.shape[0])
    east = np.full(z.shape, np.nan, dtype=np.float32)
    north = np.full(z.shape, np.nan, dtype=np.float32)
    east[:, 1:-1] = (z[:, 2:] - z[:, :-2]) / (2 * rows)
    # Rows run southwards, so north is the row above.
    north[1:-1, :] = (z[:-2, :] - z[2:, :]) / (2 * rows[1:-1])
    return east, north


def slope(z: np.ndarray, res: Resolution) -> np.ndarray:
    """Slope in degrees."""
    east, north = gradients(z, res)
    return np.degrees(np.arctan(np.hypot(east, north))).astype(np.float32)


def hillshade(z: np.ndarray, res: Resolution, azimuth: float = 315.0, altitude: float = 35.0) -> np.ndarray:
    """Illumination from a sun at `azimuth` (degrees clockwise from north) and `altitude`, from 0 to 1."""
    east, north = gradients(z, res)
    az, alt = math.radians(azimuth), math.radians(altitude)
    sun_e, sun_n, sun_up = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    # The unit normal of the surface is (-dz/de, -dz/dn, 1) / its length.
    lit = (sun_up - east * sun_e - north * sun_n) / np.sqrt(1 + east * east + north * north)
    return np.clip(lit, 0, 1).astype(np.float32)


def multi_hillshade(
    z: np.ndarray, res: Resolution, azimuths: tuple[float, ...], altitude: float = 35.0
) -> np.ndarray:
    """One hillshade per azimuth, stacked on the last axis."""
    return np.stack([hillshade(z, res, azimuth, altitude) for azimuth in azimuths], axis=-1)


def local_relief(z: np.ndarray, radius: int) -> np.ndarray:
    """Simple local relief: elevation minus the mean of the (2r+1) by (2r+1) square around it, in metres."""
    assert radius >= 1, "the local relief radius must be at least one pixel"
    z = np.asarray(z, dtype=np.float32)
    valid = np.isfinite(z)
    if not valid.any():
        return np.full(z.shape, np.nan, dtype=np.float32)
    # Taken off first so the mean is computed on small numbers.
    reference = float(np.median(z[valid]))
    filled = np.where(valid, z - reference, 0).astype(np.float64)
    size = 2 * radius + 1
    total = uniform_filter(filled, size=size, mode="constant")
    count = uniform_filter(valid.astype(np.float64), size=size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
    return np.where(valid, filled - mean, np.nan).astype(np.float32)


def ray_offsets(direction: float, r_min: int, r_max: int) -> list[tuple[int, int, float]]:
    """Integer pixel offsets along one ray, as (columns east, rows south, distance in pixels).

    Radii run from `r_min` to `r_max` in steps of a third of a pixel and are
    rounded and de-duplicated, as in `rvt.vis`.
    """
    assert 1 <= r_min <= r_max, "radii must satisfy 1 <= r_min <= r_max"
    east, north = math.sin(direction), math.cos(direction)
    seen: set[tuple[int, int]] = set()
    offsets: list[tuple[int, int, float]] = []
    for step in range(3 * r_min, 3 * r_max + 1):
        radius = step / 3
        offset = (round(radius * east), -round(radius * north))
        if offset == (0, 0) or offset in seen:
            continue
        seen.add(offset)
        offsets.append((offset[0], offset[1], math.hypot(*offset)))
    return offsets


def sky_view_and_openness(
    z: np.ndarray, res: Resolution, r_max: int, r_min: int = 1, directions: int = 16
) -> tuple[np.ndarray, np.ndarray]:
    """Sky-view factor (0 to 1) and positive openness (degrees), from one horizon search.

    For each of `directions` rays the steepest elevation angle g to any point
    between `r_min` and `r_max` pixels away is found. Sky-view factor is the
    mean of 1 - sin(max(g, 0)), and positive openness is 90 minus the mean of
    g, so a ditch is dark in sky-view and a bank or mound bright.
    """
    z = np.asarray(z, dtype=np.float32)
    height, width = z.shape
    rows = _row_resolution(res, height)
    padded = np.pad(z, r_max, constant_values=np.nan)
    svf = np.zeros(z.shape, dtype=np.float32)
    angle_sum = np.zeros(z.shape, dtype=np.float32)
    steepest = np.empty(z.shape, dtype=np.float32)
    rise = np.empty(z.shape, dtype=np.float32)
    for index in range(directions):
        steepest.fill(-np.inf)
        for dx, dy, distance in ray_offsets(2 * math.pi * index / directions, r_min, r_max):
            shifted = padded[r_max + dy : r_max + dy + height, r_max + dx : r_max + dx + width]
            np.subtract(shifted, z, out=rise)
            rise *= np.float32(1 / distance)
            # fmax ignores NaN, so a neighbour with no data doesn't count.
            np.fmax(steepest, rise, out=steepest)
        steepest /= rows
        lifted = np.maximum(steepest, 0)
        svf += 1 - lifted / np.sqrt(1 + lifted * lifted)
        angle_sum += np.arctan(steepest)
    no_data = ~np.isfinite(z)
    svf /= directions
    openness = 90 - np.degrees(angle_sum / directions)
    svf[no_data] = np.nan
    openness[no_data] = np.nan
    return svf, openness.astype(np.float32)


def stretch(values: np.ndarray, low: float, high: float, *, invert: bool = False) -> np.ndarray:
    """A fixed linear stretch of [low, high] onto [0, 1], clipped. NaN stays NaN."""
    assert high > low, "a stretch needs high above low"
    out = np.clip((values - low) / (high - low), 0, 1).astype(np.float32)
    return 1 - out if invert else out


# Blend modes as `rvt/blend_func.py` defines them, for greyscale layers from 0 to 1.


def blend_multiply(top: np.ndarray, base: np.ndarray) -> np.ndarray:
    return top * base


def blend_overlay(top: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Overlay, decided on the base layer."""
    return np.where(base > 0.5, 1 - (1 - 2 * (base - 0.5)) * (1 - top), 2 * base * top).astype(np.float32)


def blend_luminosity(top: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Over a greyscale base, luminosity returns the top layer."""
    return top


def with_opacity(blended: np.ndarray, base: np.ndarray, opacity: float) -> np.ndarray:
    assert 0 <= opacity <= 1, "opacity runs from 0 to 1"
    return blended * opacity + base * (1 - opacity)


@dataclass(frozen=True)
class VatPreset:
    """One Visualization for Archaeological Topography preset (`settings/blender_VAT.json`)."""

    sun_altitude: float
    slope_max: float
    openness: tuple[float, float]
    sky_view: tuple[float, float]


# The `general` and `flat` blocks of RVT's default_terrains_settings.json.
VAT_GENERAL = VatPreset(sun_altitude=35, slope_max=50, openness=(68, 93), sky_view=(0.7, 1.0))
VAT_FLAT = VatPreset(sun_altitude=15, slope_max=15, openness=(85, 93), sky_view=(0.9, 1.0))


def vat(z: np.ndarray, res: Resolution, preset: VatPreset, r_max: int, r_min: int = 1) -> np.ndarray:
    """The VAT blend, from 0 to 1.

    From the base up: hillshade from 315 degrees at Normal 100%, slope
    inverted at Luminosity 50%, positive openness at Overlay 50%, and sky-view
    factor at Multiply 25%.
    """
    svf, openness = sky_view_and_openness(z, res, r_max, r_min)
    out = hillshade(z, res, 315, preset.sun_altitude)
    out = with_opacity(
        blend_luminosity(stretch(slope(z, res), 0, preset.slope_max, invert=True), out), out, 0.5
    )
    out = with_opacity(blend_overlay(stretch(openness, *preset.openness), out), out, 0.5)
    out = with_opacity(blend_multiply(stretch(svf, *preset.sky_view), out), out, 0.25)
    return out.astype(np.float32)


def combined_vat(
    z: np.ndarray, res: Resolution, general_r_max: int, flat_r_max: int, flat_r_min: int
) -> np.ndarray:
    """Combined VAT: VAT general at 50% over VAT flat, which is the mean of the two (`VAT_combined.py`)."""
    general = vat(z, res, VAT_GENERAL, general_r_max)
    flat = vat(z, res, VAT_FLAT, flat_r_max, flat_r_min)
    return (0.5 * general + 0.5 * flat).astype(np.float32)
