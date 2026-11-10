"""Reading from the bulk supply in windows, through drops and failures."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

import paramiko
import pytest
from pydantic import SecretStr

from fieldclub.config import DefraSftpSettings, get_defra_sftp_settings
from fieldclub.errors import ConfigError
from fieldclub.terrain import sftp
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.errors import CredentialsMissingError, FetchFailedError, SupplyRefusedError
from tests.terrain.fakes import MIB, FakeServer

REMOTE = SourceTile("SU16nw", 0).remote_path


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
    pauses: list[float] = []
    dest = sftp.download(
        server.connect, REMOTE, tmp_path / "SU16nw.tif", expected_size=len(big), sleep=pauses.append
    )
    assert dest.read_bytes() == big
    assert server.connections == 3
    # Each failure came after progress, so neither pause grew.
    assert pauses == [sftp.RETRY_DELAY, sftp.RETRY_DELAY]


def test_failures_in_a_row_wait_longer_each_time(big: bytes, tmp_path: Path) -> None:
    server = FakeServer({REMOTE: big}, stuck_at=0)
    pauses: list[float] = []
    with pytest.raises(FetchFailedError, match="4 times in a row"):
        sftp.download(
            server.connect, REMOTE, tmp_path / "a.tif", max_failures=4, retry_delay=1.5, sleep=pauses.append
        )
    assert pauses == [1.5, 3.0, 6.0]
    assert server.connections == 4
    long = FakeServer({REMOTE: big}, stuck_at=0)
    pauses.clear()
    with pytest.raises(FetchFailedError):
        sftp.download(long.connect, REMOTE, tmp_path / "a.tif", max_failures=9, sleep=pauses.append)
    assert max(pauses) == sftp.RETRY_DELAY_CAP


def test_a_partial_download_is_resumed_and_never_appears_complete(big: bytes, tmp_path: Path) -> None:
    dest = tmp_path / "SU16nw.tif"
    part = tmp_path / "SU16nw.tif.part"
    part.write_bytes(big[: 13 * MIB + 7])
    server = FakeServer({REMOTE: big}, stuck_at=30 * MIB)
    with pytest.raises(FetchFailedError):
        sftp.download(
            server.connect, REMOTE, dest, expected_size=len(big), max_failures=3, sleep=lambda _: None
        )
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


def refused_settings(known_hosts: Path) -> DefraSftpSettings:
    # Nothing listens on port 1 of the loopback address, so the connection is refused at once.
    return DefraSftpSettings(
        defra_sftp_host="127.0.0.1",
        defra_sftp_port=1,
        defra_sftp_user="someone",
        defra_sftp_password=SecretStr("not-a-real-password"),
        defra_sftp_known_hosts=known_hosts,
    )


def test_a_connection_failure_names_only_the_file_in_errors_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("")
    connect = sftp.defra_connector(refused_settings(known_hosts))
    logged = caplog.at_level("WARNING", logger="fieldclub.terrain.sftp")
    with logged, pytest.raises(FetchFailedError) as raised:
        sftp.download(connect, REMOTE, tmp_path / "a.tif", max_failures=2, sleep=lambda _: None)
    body = str(raised.value.to_body())
    assert "SU16nw_DTM_1m.tif" in body
    for secret in ("127.0.0.1", "port 1", "composite/", "not-a-real-password", "someone"):
        assert secret not in body, secret
        assert secret not in caplog.text, secret
    assert "Reading SU16nw_DTM_1m.tif failed (NoValidConnectionsError" in caplog.text


def test_a_missing_host_key_file_is_not_named_to_the_client(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as raised:
        sftp.defra_connector(refused_settings(tmp_path / "nowhere" / "known_hosts"))
    assert "nowhere" not in str(raised.value.to_body())


class FakeSshClient:
    """Stands in for `paramiko.SSHClient`, recording how the connection is set up."""

    instances: ClassVar[list[FakeSshClient]] = []
    refuse: ClassVar[BaseException | None] = None

    def __init__(self) -> None:
        self.keepalive: int | None = None
        self.read_timeout: float | None = None
        self.connect_options: dict[str, Any] = {}
        self.closed = False
        FakeSshClient.instances.append(self)

    def load_host_keys(self, path: str) -> None:
        pass

    def set_missing_host_key_policy(self, policy: object) -> None:
        assert isinstance(policy, paramiko.RejectPolicy)

    def connect(self, host: str, **options: Any) -> None:
        self.connect_options = options
        if FakeSshClient.refuse is not None:
            raise FakeSshClient.refuse

    def get_transport(self) -> Any:
        client = self

        class Transport:
            def set_keepalive(self, interval: int) -> None:
                client.keepalive = interval

        return Transport()

    def open_sftp(self) -> Any:
        client = self

        class Channel:
            def settimeout(self, seconds: float) -> None:
                client.read_timeout = seconds

        class Sftp:
            def get_channel(self) -> Channel:
                return Channel()

            def close(self) -> None:
                pass

        return Sftp()

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> sftp.Connect:
    FakeSshClient.instances = []
    FakeSshClient.refuse = None
    monkeypatch.setattr(paramiko, "SSHClient", FakeSshClient)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("")
    return sftp.defra_connector(refused_settings(known_hosts))


def test_a_connection_gives_up_on_a_silent_server_and_keeps_itself_alive(ssh: sftp.Connect) -> None:
    ssh().close()
    [client] = FakeSshClient.instances
    # Without a read timeout a stalled read would hold the fetch for ever.
    assert client.read_timeout == sftp.READ_TIMEOUT
    assert client.keepalive == sftp.KEEPALIVE_INTERVAL
    assert client.connect_options["timeout"] == sftp.READ_TIMEOUT
    assert client.connect_options["auth_timeout"] == sftp.READ_TIMEOUT


@pytest.mark.parametrize(
    "refusal",
    [
        paramiko.AuthenticationException("no"),
        paramiko.BadHostKeyException("h", paramiko.PKey(), paramiko.PKey()),
    ],
    ids=["login", "host key"],
)
def test_a_refused_login_or_host_key_is_never_retried(
    ssh: sftp.Connect, refusal: BaseException, tmp_path: Path
) -> None:
    FakeSshClient.refuse = refusal
    pauses: list[float] = []
    with pytest.raises(SupplyRefusedError):
        sftp.download(ssh, REMOTE, tmp_path / "a.tif", sleep=pauses.append)
    assert len(FakeSshClient.instances) == 1
    assert FakeSshClient.instances[0].closed
    assert pauses == []


def test_a_pool_signs_in_once_for_many_files(tmp_path: Path) -> None:
    files = {f"{REMOTE}.{i}": bytes([i]) * 1000 for i in range(5)}
    server = FakeServer(files)
    pool = sftp.SessionPool(server.connect, 2)
    for i, remote in enumerate(files):
        sftp.download(pool.connect, remote, tmp_path / f"{i}.tif", expected_size=1000)
    assert server.connections == 1
    pool.close()


def test_a_pool_drops_a_session_that_failed(big: bytes, tmp_path: Path) -> None:
    server = FakeServer({REMOTE: big}, fail_at={10 * MIB})
    pool = sftp.SessionPool(server.connect, 2)
    sftp.download(pool.connect, REMOTE, tmp_path / "a.tif", expected_size=len(big), sleep=lambda _: None)
    sftp.download(pool.connect, REMOTE, tmp_path / "b.tif", expected_size=len(big))
    # The failed session was closed, its replacement kept and used again.
    assert server.connections == 2
    pool.close()
