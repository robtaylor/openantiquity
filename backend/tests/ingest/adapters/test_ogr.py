from __future__ import annotations

from tests.helpers import run_fresh


def test_elevation_files_still_write_after_the_vector_reader_is_loaded() -> None:
    # rasterio and pyogrio each bring their own GDAL. With pyogrio's loaded first, writing a
    # LERC-compressed file aborts the process, so `ogr` loads rasterio first. A fresh process
    # is the only place the order can be tested: this one has both loaded already.
    code = (
        "from fieldclub.ingest.adapters import files, wfs\n"
        "from fieldclub.terrain import cog\n"
        "assert cog.lerc_supported()\n"
    )
    run_fresh(code)
