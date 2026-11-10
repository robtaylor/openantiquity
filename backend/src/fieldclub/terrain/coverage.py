"""Where LIDAR exists, as GeoJSON a map can draw (Decision 0006, point 7).

One square per 5 km source tile in the catalogue, with the edition's capture
year and resolution. Per-survey flight dates aren't in the catalogue yet.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pyproj import Transformer

from fieldclub.terrain.catalogue import Catalogue, SourceTile

CAPTURE = "2022 composite"
RESOLUTION_M = 1


@lru_cache(maxsize=1)
def _to_wgs84() -> Transformer:
    return Transformer.from_crs(27700, 4326, always_xy=True)


def _feature(tile: SourceTile) -> dict[str, Any]:
    west, south, east, north = tile.bounds
    lons, lats = _to_wgs84().transform([west, east, east, west, west], [south, south, north, north, south])
    ring = [[round(lon, 6), round(lat, 6)] for lon, lat in zip(lons, lats, strict=True)]
    return {
        "type": "Feature",
        "id": tile.name,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"tile": tile.name, "capture": CAPTURE, "resolution_m": RESOLUTION_M},
    }


def _bbox(feature: dict[str, Any]) -> tuple[float, float, float, float]:
    ring = feature["geometry"]["coordinates"][0]
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    return min(lons), min(lats), max(lons), max(lats)


@lru_cache(maxsize=4)
def _features(catalogue: Catalogue) -> tuple[dict[str, Any], ...]:
    return tuple(_feature(tile) for tile in catalogue)


def coverage(catalogue: Catalogue, bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    """A FeatureCollection of the tiles that touch a WGS84 box, or of all of them."""
    features = list(_features(catalogue))
    if bbox is not None:
        west, south, east, north = bbox
        features = [
            feature
            for feature, (fw, fs, fe, fn) in ((f, _bbox(f)) for f in features)
            if fw <= east and fe >= west and fs <= north and fn >= south
        ]
    return {"type": "FeatureCollection", "edition": catalogue.edition, "features": features}
