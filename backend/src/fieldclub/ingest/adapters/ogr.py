"""The one place pyogrio is imported, because the load order matters.

rasterio (elevation) and pyogrio (vector files) each ship their own copy of
GDAL inside their wheels: 3.12.2 and 3.12.4 at the time of writing. When
pyogrio's copy is loaded first, the process aborts the first time rasterio
writes a LERC-compressed file, which is how every mirrored elevation tile is
stored. Loaded the other way round, both work. So rasterio is imported here
before pyogrio, and everything else takes the vector reader from this module.
ruff's banned-api rule refuses a direct `import pyogrio` anywhere else, and
`tests/ingest/adapters/test_ogr.py` runs the combination in a fresh process.
"""

import rasterio  # noqa: F401  # loads rasterio's GDAL first; see the module docstring

# isort: split
import pyogrio
import pyogrio.raw
from pyogrio.errors import DataSourceError

read_info = pyogrio.read_info
read = pyogrio.raw.read
write = pyogrio.raw.write

__all__ = ["DataSourceError", "read", "read_info", "write"]
