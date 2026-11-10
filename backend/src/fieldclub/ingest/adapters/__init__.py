"""Readers that connectors share, one per kind of upstream service or file.

Each reader yields `Feature` objects: a plain dict of properties and a shapely
geometry in WGS84, longitude first. None of them knows about our tables. A
connector turns features into `RecordIn` and nothing else, so most connectors
are a few lines on top of one of these:

| Module | Reads |
|--------|-------|
| `arcgis` | ArcGIS feature and map services, paged by offset or by object id ranges |
| `download` | A published file, cached under `var/` and resumed after a dropped connection |
| `files` | GeoPackage, shapefile and other OGR formats through pyogrio, CSV and newline-delimited JSON |
| `wfs` | OGC Web Feature Service 2.0, paged with `count` and `startIndex` |
| `sparql` | SPARQL endpoints, paged with `LIMIT` and `OFFSET`, with WKT literals parsed |

Requests go through `Polite`, which spaces them out, retries what is worth
retrying and honours `Retry-After`. See `ingest/connectors/README.md` for how
to write a connector with them.
"""

from fieldclub.ingest.adapters.common import (
    AdapterError,
    Feature,
    IncompleteReadError,
    Polite,
    UpstreamFormatError,
    cache_dir,
    to_wgs84,
)

__all__ = [
    "AdapterError",
    "Feature",
    "IncompleteReadError",
    "Polite",
    "UpstreamFormatError",
    "cache_dir",
    "to_wgs84",
]
