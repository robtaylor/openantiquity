"""The national 10 m composite for low zoom levels: download once, convert to a COG.

Defra publishes England's 2022 composite at 10 m as one zip of 5,301,314,401
bytes (dataset ac3682a1-1ead-4478-8a2d-d8402ef9ead0). The download resumes
with a Range request when the server honours one. On 2026-11-10 it didn't:
it answered every Range request with the whole file, and it closed every
transfer after about 1.08 GB, at any speed, over HTTP/1.1 and HTTP/2. Until
that changes the file can't be fetched from this address, and low zooms fall
back to the mirror's own overviews (see `service.py`).
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from fieldclub.http import get_client
from fieldclub.terrain.cog import to_cog
from fieldclub.terrain.errors import FetchFailedError

logger = logging.getLogger(__name__)

NATIONAL_URL = (
    "https://environment.data.gov.uk/file-management-open/data-sets/"
    "ac3682a1-1ead-4478-8a2d-d8402ef9ead0/files/LIDAR_Composite_10m_DTM_2022.zip"
)
NATIONAL_BYTES = 5_301_314_401
ZIP_NAME = "LIDAR_Composite_10m_DTM_2022.zip"
CHUNK = 1024 * 1024


def download(
    dest: Path,
    *,
    url: str = NATIONAL_URL,
    expected_size: int = NATIONAL_BYTES,
    attempts: int = 3,
    client: httpx.Client | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Fetch the zip to `dest`, through `dest.part`, resuming where the server allows it."""
    if dest.is_file() and dest.stat().st_size == expected_size:
        return dest
    client = client or get_client()
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.is_file() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with client.stream("GET", url, headers=headers, timeout=httpx.Timeout(60, read=120)) as response:
                if response.status_code == 206:
                    mode = "ab"
                elif response.status_code == 200:
                    if have:
                        logger.warning("The server ignored the Range request; starting from the beginning")
                    mode, have = "wb", 0
                else:
                    raise FetchFailedError(f"{url} answered HTTP {response.status_code}.")
                with part.open(mode) as out:
                    for chunk in response.iter_bytes(CHUNK):
                        out.write(chunk)
                        have += len(chunk)
                        if on_progress is not None:
                            on_progress(have, expected_size)
        except httpx.HTTPError as exc:
            logger.warning("Download attempt %d stopped at %d bytes: %s", attempt, have, exc)
            continue
        if part.stat().st_size == expected_size:
            part.replace(dest)
            return dest
        logger.warning(
            "Download attempt %d ended at %d of %d bytes", attempt, part.stat().st_size, expected_size
        )
    got = part.stat().st_size if part.is_file() else 0
    raise FetchFailedError(f"{url}: got {got} of {expected_size} bytes after {attempts} attempts.")


def tif_inside(zip_path: Path) -> str:
    """The GDAL path of the GeoTIFF inside the zip."""
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
    if len(names) != 1:
        raise FetchFailedError(f"{zip_path} holds {len(names)} GeoTIFFs, expected one.")
    return f"/vsizip/{zip_path}/{names[0]}"


def convert(zip_path: Path, dest: Path) -> None:
    """The national COG, with every overview GDAL makes, read straight from the zip."""
    to_cog(tif_inside(zip_path), dest, overview_count=None, threads="ALL_CPUS")
