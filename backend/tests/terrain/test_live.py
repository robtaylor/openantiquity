"""Live check against Defra's bulk supply. Run with `uv run pytest -m live tests/terrain`.

Needs DEFRA_SFTP_HOST, DEFRA_SFTP_USER and DEFRA_SFTP_PASSWORD in the
environment or the repository's .env, which the test session otherwise
ignores, and the pinned host key in var/defra_known_hosts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import rasterio

from fieldclub.config import DefraSftpSettings
from fieldclub.terrain import sftp
from fieldclub.terrain.catalogue import england_catalogue

# The smallest tile in the supply: 539,296 bytes of Suffolk coast.
SMALL_TILE = "TM58se"
REPO_ENV = Path(__file__).resolve().parents[3] / ".env"


@pytest.mark.live
def test_one_small_real_tile_comes_from_the_bulk_supply(tmp_path: Path) -> None:
    tile = england_catalogue().get(SMALL_TILE)
    assert tile is not None
    credentials = DefraSftpSettings(_env_file=REPO_ENV)  # pyright: ignore[reportCallIssue]
    connect = sftp.defra_connector(credentials)
    path = sftp.download(connect, tile.remote_path, tmp_path / tile.source_filename, expected_size=tile.size)
    assert path.stat().st_size == tile.size
    with rasterio.open(path) as ds:
        # Coastal tiles are cropped to the land, so only the grid and bounds are fixed.
        assert ds.res == (1.0, 1.0)
        assert ds.crs.to_epsg() == 27700
        west, south, east, north = tile.bounds
        assert west <= ds.bounds.left < ds.bounds.right <= east
        assert south <= ds.bounds.bottom < ds.bounds.top <= north
