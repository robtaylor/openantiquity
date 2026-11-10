"""The national 10 m composite: a resumable download and a conversion straight from the zip."""

from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pytest
import rasterio
import respx

from fieldclub.terrain import national
from fieldclub.terrain.errors import FetchFailedError
from tests.terrain.fakes import write_source_tile

URL = "https://example.test/national.zip"
BODY = bytes(range(256)) * 400


def test_a_download_resumes_with_a_range_request(tmp_path: Path) -> None:
    dest = tmp_path / "national.zip"
    (tmp_path / "national.zip.part").write_bytes(BODY[:1000])
    with respx.mock:
        route = respx.get(URL).mock(return_value=httpx.Response(206, content=BODY[1000:]))
        national.download(dest, url=URL, expected_size=len(BODY), client=httpx.Client())
    assert route.calls.last.request.headers["Range"] == "bytes=1000-"
    assert dest.read_bytes() == BODY
    assert not (tmp_path / "national.zip.part").exists()


def test_a_server_that_ignores_range_restarts_from_the_beginning(tmp_path: Path) -> None:
    dest = tmp_path / "national.zip"
    (tmp_path / "national.zip.part").write_bytes(b"stale" * 100)
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(200, content=BODY))
        national.download(dest, url=URL, expected_size=len(BODY), client=httpx.Client())
    assert dest.read_bytes() == BODY


def test_a_transfer_cut_short_every_time_fails_and_leaves_no_complete_file(tmp_path: Path) -> None:
    dest = tmp_path / "national.zip"
    with respx.mock:
        route = respx.get(URL).mock(return_value=httpx.Response(200, content=BODY[:5000]))
        with pytest.raises(FetchFailedError, match="5000 of"):
            national.download(dest, url=URL, expected_size=len(BODY), attempts=2, client=httpx.Client())
    assert route.call_count == 2
    assert not dest.exists()


def test_the_zip_is_converted_without_unpacking_it(tmp_path: Path) -> None:
    tif = write_source_tile(tmp_path / "src", "SU16nw", res=10.0)
    archive = tmp_path / national.ZIP_NAME
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("LIDAR_Composite_10m_DTM_2022.tfw", "10\n0\n0\n-10\n410005\n169995\n")
        out.write(tif, "LIDAR_Composite_10m_DTM_2022.tif")
    assert national.tif_inside(archive) == f"/vsizip/{archive}/LIDAR_Composite_10m_DTM_2022.tif"
    dest = tmp_path / "national.tif"
    national.convert(archive, dest)
    with rasterio.open(dest) as cog, rasterio.open(tif) as source:
        assert cog.transform == source.transform
        assert abs(cog.read(1) - source.read(1)).max() <= 0.0101
