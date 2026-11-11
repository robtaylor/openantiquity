"""Converting source GeoTIFFs to the mirror's cloud-optimised format.

Every mirror file is a COG with 512-pixel blocks and internal overviews,
compressed with LERC_ZSTD at a maximum error of 1 cm. Measured on SU16nw
(48.20 MB of LZW source) that came to 24.38 MB with a real maximum error of
0.0100 m, against 52.53 MB for lossless ZSTD with the floating-point predictor.
Where GDAL can't write LERC, the conversion falls back to lossless ZSTD.

A 5 km tile at 1 m gets exactly three overviews, at 2, 4 and 8 m. Each is a
whole number of pixels (2,500, 1,250 and 625), so neighbouring tiles' overviews
sit on one grid and can be laid side by side without resampling.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
import rasterio.shutil
from affine import Affine
from rasterio._err import CPLE_AppDefinedError, CPLE_NotSupportedError, CPLE_OpenFailedError
from rasterio.errors import RasterioError
from rasterio.transform import from_origin

from fieldclub.errors import DataIntegrityError

logger = logging.getLogger(__name__)

BLOCK_SIZE = 512
MAX_Z_ERROR_M = 0.01
# Bumped when the encoding changes, because it changes the values read back.
COG_FORMAT = "c1"
# What GDAL raises for a file it can't decode. A decode error part-way through
# the data is a `CPLE_AppDefinedError`, which isn't a `RasterioError`. Errors
# of the machine rather than the file (out of memory, a full disk) are left
# out, so they never get a good source set aside.
UNREADABLE_ERRORS: tuple[type[Exception], ...] = (
    RasterioError,
    CPLE_AppDefinedError,
    CPLE_OpenFailedError,
    CPLE_NotSupportedError,
    DataIntegrityError,
)


@lru_cache(maxsize=1)
def lerc_supported() -> bool:
    """Whether the installed GDAL can write LERC_ZSTD."""
    path = f"/vsimem/lerc-probe-{uuid.uuid4().hex}.tif"
    try:
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=16,
            height=16,
            count=1,
            dtype="float32",
            transform=from_origin(0, 16, 1, 1),
            compress="LERC_ZSTD",
            max_z_error=MAX_Z_ERROR_M,
        ) as probe:
            probe.write(np.zeros((1, 16, 16), dtype=np.float32))
        return True
    except RasterioError:
        logger.warning("GDAL can't write LERC_ZSTD; the mirror falls back to lossless ZSTD")
        return False
    finally:
        if rasterio.shutil.exists(path):
            rasterio.shutil.delete(path)


def creation_options(*, overview_count: int | None, threads: int | str = 2) -> dict[str, object]:
    options: dict[str, object] = {
        "driver": "COG",
        "BLOCKSIZE": BLOCK_SIZE,
        "OVERVIEW_RESAMPLING": "AVERAGE",
        "NUM_THREADS": threads,
        "BIGTIFF": "IF_SAFER",
    }
    if overview_count is not None:
        options["OVERVIEW_COUNT"] = overview_count
    if lerc_supported():
        options.update(COMPRESS="LERC_ZSTD", MAX_Z_ERROR=MAX_Z_ERROR_M)
    else:
        options.update(COMPRESS="ZSTD", PREDICTOR=3)
    return options


@dataclass(frozen=True)
class CogSummary:
    width: int
    height: int
    overviews: list[int]
    compression: str
    nodata: float | None
    transform: Affine


def to_cog(
    src: str | Path, dst: Path, *, overview_count: int | None = 3, threads: int | str = 2
) -> CogSummary:
    """Write `src` as a COG at `dst`, through a temporary file beside it, and check the result.

    `dst` appears only once the copy is complete and has been read back.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp.tif")
    try:
        with rasterio.open(src) as source:
            if source.count != 1:
                raise DataIntegrityError(f"{src} has {source.count} bands, expected one.")
            if source.dtypes[0] != "float32":
                raise DataIntegrityError(f"{src} is {source.dtypes[0]}, expected float32.")
            shape = (source.height, source.width)
            transform = source.transform
        rasterio.shutil.copy(
            str(src), str(tmp), **creation_options(overview_count=overview_count, threads=threads)
        )
        summary = check_cog(tmp)
        if (summary.height, summary.width) != shape or summary.transform != transform:
            raise DataIntegrityError(f"The COG of {src} doesn't have the source's grid.")
        tmp.replace(dst)
        return summary
    finally:
        tmp.unlink(missing_ok=True)


def check_cog(path: str | Path) -> CogSummary:
    """Read a mirror file's layout and refuse one that isn't what the readers expect."""
    with rasterio.open(path) as ds:
        if ds.block_shapes[0] != (BLOCK_SIZE, BLOCK_SIZE) and min(ds.width, ds.height) > BLOCK_SIZE:
            raise DataIntegrityError(f"{path} has blocks of {ds.block_shapes[0]}, expected {BLOCK_SIZE}.")
        if ds.compression is None:
            raise DataIntegrityError(f"{path} isn't compressed.")
        return CogSummary(ds.width, ds.height, ds.overviews(1), ds.compression.name, ds.nodata, ds.transform)
