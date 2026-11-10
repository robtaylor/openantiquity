"""Where LIDAR exists, as GeoJSON a map can draw (Decision 0006, point 7).

One square per 5 km source tile in the catalogue, with the edition's capture
year and resolution. Per-survey flight dates aren't in the catalogue yet.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fieldclub.terrain.catalogue import Catalogue, SourceTile
from fieldclub.terrain.sources import transformer

CAPTURE = "2022 composite"
RESOLUTION_M = 1


def _feature(tile: SourceTile) -> dict[str, Any]:
    west, south, east, north = tile.bounds
    lons, lats = transformer(27700, 4326).transform(
        [west, east, east, west, west], [south, south, north, north, south]
    )
    ring = [[round(lon, 6), round(lat, 6)] for lon, lat in zip(lons, lats, strict=True)]
    return {
        "type": "Feature",
        "id": tile.name,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"tile": tile.name, "capture": CAPTURE, "resolution_m": RESOLUTION_M},
    }


@lru_cache(maxsize=4)
def _features(catalogue: Catalogue) -> tuple[tuple[dict[str, Any], tuple[float, float, float, float]], ...]:
    """Each tile's feature with its WGS84 bounding box, built once per catalogue."""
    found = []
    for tile in catalogue:
        feature = _feature(tile)
        ring = feature["geometry"]["coordinates"][0]
        lons, lats = [point[0] for point in ring], [point[1] for point in ring]
        found.append((feature, (min(lons), min(lats), max(lons), max(lats))))
    return tuple(found)


def coverage(catalogue: Catalogue, bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    """A FeatureCollection of the tiles that touch a WGS84 box, or of all of them."""
    if bbox is None:
        features = [feature for feature, _ in _features(catalogue)]
    else:
        west, south, east, north = bbox
        features = [
            feature
            for feature, (fw, fs, fe, fn) in _features(catalogue)
            if fw <= east and fe >= west and fs <= north and fn >= south
        ]
    return {"type": "FeatureCollection", "edition": catalogue.edition, "features": features}
