"""Elevation, the mirror it is read from, visualisations, and tile rendering.

See Decision 0006. Elevation is read only from a mirror of cloud-optimised
GeoTIFFs (`mirror.py`), filled from Defra's bulk supply on first use
(`sftp.py`) or from source files already on disk, in a local folder or a
bucket (`blobs.py`). `national.py` builds the overview zooms below 13 read,
and `overview.py` reads it. `sources.py` reads elevation onto any Web
Mercator grid, `visualise.py` holds the pure numpy visualisations,
`styles.py` the served styles and their versions, and `render.py` turns a map
tile into a PNG through two caches in `Storage`. `years.py` and
`attribution.py` give the coverage layer its capture years and the LIDAR its
`sources` rows.
"""
