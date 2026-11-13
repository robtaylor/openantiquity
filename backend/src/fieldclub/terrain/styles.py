"""The visualisations served as map tiles, with their parameters and versions.

Radii are in ground metres and become pixels for each zoom level at the
reference latitude (`grid.nominal_ground_resolution`). At zoom 16 a 512-pixel
tile has pixels of about 0.73 m, close to the 1 m data, and the published
radii apply as written. RVT's radii are pixel counts on a 1 m DTM, so its
defaults of 10 and 20 pixels are 10 m and 20 m here, which is how the
National Library of Scotland built its England Combined VAT. At lower zooms a
radius in metres would shrink below a pixel, so each has a floor in pixels,
which makes the kernel cover more ground as the map zooms out.

A style's `version` is part of its cache key and its tile URL. Change it
whenever anything that alters its pixels changes: a parameter, a stretch, a
floor, the blend, or the shared code in `visualise.py` and `grid.py`.
`tests/terrain/test_versions.py` fails when the pixels change and the
version doesn't.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from fieldclub.terrain import visualise as vis
from fieldclub.terrain.grid import nominal_ground_resolution

# Zoom levels the lidar styles and the elevation tiles are served at.
MINZOOM = 7
MAXZOOM = 16
# From this zoom up, elevation comes from the 1 m mirror. Below it, from the
# national overview. See `service.py` for the measurements behind it.
FINE_MINZOOM = 13
# The layer the map opens on, and the one `fieldclub-terrain warm` renders unless told otherwise.
# Multi-direction shade, which the owner asked for on 2026-11-13 as "by far the most useful":
# lit from three sides, it hides nothing that happens to run along the light.
DEFAULT_STYLE = "multi_shade"


@dataclass(frozen=True)
class Radius:
    """A kernel radius in ground metres, and the fewest pixels it may become."""

    metres: float
    floor_px: int
    ceiling_px: int = 1_000

    def pixels(self, zoom: int) -> int:
        wanted = round(self.metres / nominal_ground_resolution(zoom))
        return int(min(self.ceiling_px, max(self.floor_px, wanted)))


# VAT general and the sky-view style: RVT's default search radius, 10 px on 1 m.
SVF_GENERAL = Radius(10, floor_px=5)
# VAT flat: 20 px on 1 m, ignoring the nearest 40% (noise level 3).
SVF_FLAT = Radius(20, floor_px=10)
FLAT_NOISE_FRACTION = 0.4
# Simple local relief: Kokalj and Hesse's 10 m for general terrain. RVT's
# default of 20 px saturated Avebury's henge bank and ditch at the +/-2 m
# stretch. RVT's own floor of 10 px made a 58 m radius at zoom 13, which
# picked up whole dry valleys, so the floor is 3 px.
SLRM = Radius(10, floor_px=3, ceiling_px=50)

# RVT's three-band multiple-direction hillshade lights red, green and blue from these azimuths.
MULTI_AZIMUTHS = (315.0, 22.5, 90.0)

# Rendered values from 0 to 1, greyscale (H, W) or colour (H, W, 3), on the
# buffered array. Arguments: buffered elevation, ground resolution per row, zoom.
Renderer = Callable[[np.ndarray, np.ndarray, int], np.ndarray]


@dataclass(frozen=True)
class Style:
    id: str
    version: str
    render: Renderer
    radii: tuple[Radius, ...]

    def buffer(self, zoom: int) -> int:
        """Pixels of real data needed round the tile: the largest radius, plus one for the gradients."""
        return max((radius.pixels(zoom) for radius in self.radii), default=0) + 1


def _flat_radii(zoom: int) -> tuple[int, int]:
    r_max = SVF_FLAT.pixels(zoom)
    return r_max, max(1, round(FLAT_NOISE_FRACTION * r_max))


def _composite(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    flat_max, flat_min = _flat_radii(zoom)
    return vis.combined_vat(z, res, SVF_GENERAL.pixels(zoom), flat_max, flat_min)


# RVT's 8-bit stretch for SLRM, +/-2 m, applies at the published 10 m radius.
SLRM_STRETCH_M = 2.0


def local_relief_stretch(zoom: int) -> float:
    """The half-range of the local relief stretch, in metres, for the radius used at a zoom.

    Below zoom 15 the pixel floor makes the radius cover more ground, and
    relief grows about in proportion to it: over the same 2 km of real ground
    the 5-95% spread was 0.09 of the stretch at zoom 16, 0.14 at 13 and over
    0.84 at 11, where 8% of pixels clipped. So the stretch widens with the
    radius, which keeps the contrast steady across zooms.
    """
    radius_m = SLRM.pixels(zoom) * nominal_ground_resolution(zoom)
    return SLRM_STRETCH_M * radius_m / SLRM.metres


def _local_relief(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    half = local_relief_stretch(zoom)
    return vis.stretch(vis.local_relief(z, SLRM.pixels(zoom)), -half, half)


def _sky_view(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    svf, _ = vis.sky_view_and_openness(z, res, SVF_GENERAL.pixels(zoom))
    # The VAT general stretch. RVT's 8-bit default of 0.6375 to 1 left the
    # Fyfield Down field systems near white, and VAT flat's 0.9 to 1 filled
    # Avebury's henge ditch with solid black at zoom 16.
    return vis.stretch(svf, 0.7, 1.0)


# VAT flat's stretch for positive openness, in degrees. RVT's 8-bit default of 60 to 95
# drew real ground flat grey: over Avebury, Silbury Hill and Fyfield Down at zooms 13
# to 16 the 5th to 95th percentiles ran from 79.8 to 90.1 degrees, which that stretch
# put between 0.57 and 0.86. This one puts the same ground between 0 and 0.64, and the
# field systems on Fyfield Down show.
OPENNESS_STRETCH = (85.0, 93.0)


def _openness(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    _, openness = vis.sky_view_and_openness(z, res, SVF_GENERAL.pixels(zoom))
    return vis.stretch(openness, *OPENNESS_STRETCH)


def _multi_shade(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    # RVT's sun elevation 35 and its red, green and blue azimuths, stretched 0 to 1.
    return vis.multi_hillshade(z, res, MULTI_AZIMUTHS, 35.0)


# The slope stretch's steepest end, in degrees: between VAT flat's 15 and VAT general's
# 50. RVT's 8-bit 0 to 51 drew near-flat ground white: the median slope over Avebury,
# Silbury Hill and Fyfield Down at zooms 13 to 16 was 1.3 to 6 degrees, which it put
# above 0.88. VAT flat's 15 shows lynchets and field banks best but draws Silbury Hill
# and the henge bank as solid black. At 25 the same median ground lies between 0.76 and
# 0.95, and the mound and the bank keep their shape.
SLOPE_MAX_DEGREES = 25.0


def _slope(z: np.ndarray, res: np.ndarray, zoom: int) -> np.ndarray:
    # Inverted as in VAT, so steep ground is dark.
    return vis.stretch(vis.slope(z, res), 0.0, SLOPE_MAX_DEGREES, invert=True)


STYLES: dict[str, Style] = {
    style.id: style
    for style in (
        Style("composite", "2", _composite, (SVF_GENERAL, SVF_FLAT)),
        Style("local_relief", "2", _local_relief, (SLRM,)),
        Style("sky_view", "2", _sky_view, (SVF_GENERAL,)),
        Style("multi_shade", "1", _multi_shade, ()),
        Style("slope", "2", _slope, ()),
        Style("openness", "3", _openness, (SVF_GENERAL,)),
    )
}


def elevation_buffer(zoom: int) -> int:
    """The buffer the cached elevation carries, enough for every style at this zoom."""
    return max(style.buffer(zoom) for style in STYLES.values())
