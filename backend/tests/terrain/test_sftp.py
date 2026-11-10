"""Reading from the bulk supply in windows, through drops and failures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fieldclub.config import DefraSftpSettings, get_defra_sftp_settings
from fieldclub.terrain import sftp
from fieldclub.terrain.errors import CredentialsMissingError, FetchFailedError
from tests.terrain.fakes import MIB, FakeServer

REMOTE = "composite/2022/GeoTiffs/1m/DTM/SU16nw_DTM_1m.tif"


@pytest.fixture(scope="module")
def big() -> bytes:
    # Larger than the 52 MiB at which the server drops a whole-file read.
    return os.urandom(60 * MIB + 12_345)


def test_a_whole_file_read_is_dropped_at_52_mib(big: bytes) -> None:
    server = FakeServer({REMOTE: big})
    handle = server.connect().open(REMOTE, "rb")
    with pytest.raises(EOFError):
        b"".join(handle.readv([(offset, 32_768) for offset in range(0, len(big), 32_768)]))


def test_reading_in_windows_gets_past_the_drop(big: bytes, tmp_path: Path) -> None:
    server = FakeServer({REMOTE: big})
    seen: list[int] = []
    dest = sftp.download(
        server.connect,
        REMOTE,
        tmp_path / "SU16nw.tif",
        expected_size=len(big),
        on_progress=lambda n, _: seen.append(n),
    )
    assert dest.read_bytes() == big
    assert server.connections == 1
    # One handle per 8 MiB window.
    assert server.opens == -(-len(big) // sftp.WINDOW_BYTES)
    assert seen[-1] == len(big)
    assert not (tmp_path / "SU16nw.tif.part").exists()


def test_a_failure_mid_window_reconnects_and_resumes_from_the_partial_file(
    big: bytes, tmp_path: Path
) -> None:
    middle = 20 * MIB + 5 * 32_768 + 100
    server = FakeServer({REMOTE: big}, fail_at={middle, 41 * MIB})
    dest = sftp.download(server.connect, REMOTE, tmp_path / "SU16nw.tif", expected_size=len(big))
    assert dest.read_bytes() == big
    assert server.connections == 3


def test_a_partial_download_is_resumed_and_never_appears_complete(big: bytes, tmp_path: Path) -> None:
    dest = tmp_path / "SU16nw.tif"
    part = tmp_path / "SU16nw.tif.part"
    part.write_bytes(big[: 13 * MIB + 7])
    server = FakeServer({REMOTE: big}, stuck_at=30 * MIB)
    with pytest.raises(FetchFailedError):
        sftp.download(server.connect, REMOTE, dest, expected_size=len(big), max_failures=3)
    assert not dest.exists()
    assert big.startswith(part.read_bytes())
    # Everything up to the chunk holding the bad offset is kept.
    assert 30 * MIB - 32_768 < part.stat().st_size <= 30 * MIB
    healthy = FakeServer({REMOTE: big})
    sftp.download(healthy.connect, REMOTE, dest, expected_size=len(big))
    assert dest.read_bytes() == big
    # Only what was missing was read again.
    assert healthy.opens < -(-len(big) // sftp.WINDOW_BYTES)


def test_a_file_whose_size_differs_from_the_catalogue_is_refused(tmp_path: Path) -> None:
    server = FakeServer({REMOTE: b"x" * 1000})
    with pytest.raises(FetchFailedError, match="catalogue"):
        sftp.download(server.connect, REMOTE, tmp_path / "a.tif", expected_size=999)
    assert not (tmp_path / "a.tif").exists()


def test_a_missing_remote_file_is_an_error_without_retries(tmp_path: Path) -> None:
    server = FakeServer({})
    with pytest.raises(FetchFailedError, match="isn't on the bulk supply"):
        sftp.download(server.connect, REMOTE, tmp_path / "a.tif")
    assert server.connections == 1


def test_missing_credentials_are_named_before_any_connection() -> None:
    with pytest.raises(CredentialsMissingError) as raised:
        sftp.defra_connector(DefraSftpSettings(defra_sftp_host="sftp.example", defra_sftp_user=None))
    assert "DEFRA_SFTP_USER" in raised.value.message
    assert "DEFRA_SFTP_PASSWORD" in raised.value.message
    assert "DEFRA_SFTP_HOST" not in raised.value.message
    assert raised.value.status_code == 503


def test_credentials_come_from_the_environment_without_the_fieldclub_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEFRA_SFTP_HOST", "sftp.example")
    monkeypatch.setenv("DEFRA_SFTP_USER", "someone")
    monkeypatch.setenv("DEFRA_SFTP_PASSWORD", "not-a-real-password")
    settings = get_defra_sftp_settings()
    assert settings.missing == []
    assert "not-a-real-password" not in repr(settings)
