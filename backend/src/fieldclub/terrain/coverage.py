"""Where LIDAR exists, as GeoJSON a map can draw (Decision 0006, point 7).

One square per 5 km source tile in the catalogue, with the edition, its
resolution and the years the surveys behind it were flown (`years.py`). A
tile the survey index doesn't reach has an empty list of years. `mirrored`
says whether the tile is in the elevation mirror yet: where it isn't, the map
is told `elevation_preparing` the first time it asks for 1 m tiles there,
and can say the area is being prepared.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from fieldclub.gridref import transformer
from fieldclub.terrain.catalogue import Catalogue, SourceTile
from fieldclub.terrain.years import england_years, years_edition

CAPTURE = "2022 composite"
RESOLUTION_M = 1


def _feature(tile: SourceTile, years: tuple[int, ...]) -> dict[str, Any]:
    west, south, east, north = tile.bounds
    lons, lats = transformer(27700, 4326).transform(
        [west, east, east, west, west], [south, south, north, north, south]
    )
    ring = [[round(lon, 6), round(lat, 6)] for lon, lat in zip(lons, lats, strict=True)]
    return {
        "type": "Feature",
        "id": tile.name,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "tile": tile.name,
            "capture": CAPTURE,
            "resolution_m": RESOLUTION_M,
            "years": list(years),
        },
    }


@lru_cache(maxsize=4)
def _features(catalogue: Catalogue) -> tuple[tuple[dict[str, Any], tuple[float, float, float, float]], ...]:
    """Each tile's feature with its WGS84 bounding box, built once per catalogue."""
    years = england_years()
    found = []
    for tile in catalogue:
        feature = _feature(tile, years.get(tile.name, ()))
        ring = feature["geometry"]["coordinates"][0]
        lons, lats = [point[0] for point in ring], [point[1] for point in ring]
        found.append((feature, (min(lons), min(lats), max(lons), max(lats))))
    return tuple(found)


def coverage_edition(catalogue: Catalogue, mirrored: frozenset[str] = frozenset()) -> str:
    """Changes whenever the coverage could: the catalogue's edition, the capture years or the mirror."""
    held = ",".join(sorted(name for name in mirrored if catalogue.get(name) is not None))
    return hashlib.sha256(f"{catalogue.edition}/{years_edition()}/{held}".encode()).hexdigest()[:16]


def coverage(
    catalogue: Catalogue,
    bbox: tuple[float, float, float, float] | None = None,
    mirrored: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """A FeatureCollection of the tiles that touch a WGS84 box, or of all of them.

    Each says whether `mirrored`, the tiles in the elevation mirror, holds it.
    """
    if bbox is None:
        found = [feature for feature, _ in _features(catalogue)]
    else:
        west, south, east, north = bbox
        found = [
            feature
            for feature, (fw, fs, fe, fn) in _features(catalogue)
            if fw <= east and fe >= west and fs <= north and fn >= south
        ]
    # The cached features are shared, so each answer gets properties of its own.
    features = [
        {**feature, "properties": {**feature["properties"], "mirrored": feature["id"] in mirrored}}
        for feature in found
    ]
    return {"type": "FeatureCollection", "edition": catalogue.edition, "features": features}
