from __future__ import annotations

import subprocess
import sys


def test_elevation_files_still_write_after_the_vector_reader_is_loaded() -> None:
    # rasterio and pyogrio each bring their own GDAL. With pyogrio's loaded first, writing a
    # LERC-compressed file aborts the process, so `ogr` loads rasterio first. A fresh process
    # is the only place the order can be tested: this one has both loaded already.
    code = (
        "from fieldclub.ingest.adapters import files, wfs\n"
        "from fieldclub.terrain import cog\n"
        "assert cog.lerc_supported()\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
