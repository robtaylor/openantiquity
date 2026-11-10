"""Elevation, the mirror it is read from, visualisations, and tile rendering.

See Decision 0006. Elevation is read only from a mirror of cloud-optimised
GeoTIFFs (`mirror.py`), filled from Defra's bulk supply on first use
(`sftp.py`) or from source files already on disk. `sources.py` reads it onto
any Web Mercator grid, `visualise.py` holds the pure numpy visualisations,
`styles.py` the served styles and their versions, and `render.py` turns a map
tile into a PNG through two caches in `Storage`.
"""
