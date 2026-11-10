"""Reading files from Defra's SFTP bulk supply.

Two behaviours of the server shape this module (`docs/sources/lidar-england-bulk-supply.md`).
It drops the connection at about 52 MiB when a whole file is requested with
the client's default read-ahead, so files are read in windows of 8 MiB with
the file handle reopened for each. And connections fail now and then, so a
download writes to `<name>.part`, resumes from whatever that file holds, and
is renamed into place only when its size matches.

The host key is pinned: a host whose key isn't in the known-hosts file is
refused. The password is never logged.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from fieldclub.config import DefraSftpSettings
from fieldclub.errors import ConfigError
from fieldclub.terrain.errors import CredentialsMissingError, FetchFailedError

logger = logging.getLogger(__name__)

MIB = 1024 * 1024
WINDOW_BYTES = 8 * MIB
CHUNK_BYTES = 32 * 1024
# Consecutive failed attempts, with no bytes gained between them, before giving up.
MAX_FAILURES = 5


class RemoteFile(Protocol):
    def readv(self, chunks: list[tuple[int, int]]) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class SftpSession(Protocol):
    """The part of `paramiko.SFTPClient` that a download uses, plus `close`."""

    def stat(self, path: str) -> Any: ...

    def open(self, path: str, mode: str = "r") -> RemoteFile: ...

    def close(self) -> None: ...


Connect = Callable[[], SftpSession]


def _transient_errors() -> tuple[type[BaseException], ...]:
    import paramiko

    return (OSError, EOFError, paramiko.SSHException, paramiko.SFTPError)


def download(
    connect: Connect,
    remote: str,
    dest: Path,
    *,
    expected_size: int | None = None,
    window: int = WINDOW_BYTES,
    max_failures: int = MAX_FAILURES,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Copy `remote` to `dest`, in windows, resuming from `dest.part`.

    `dest` appears only when the whole file has arrived and its size matches
    the server's (and `expected_size`, when given). A partial file is never
    left at `dest`.
    """
    assert window > 0, "the window must hold at least one byte"
    if dest.is_file() and (expected_size is None or dest.stat().st_size == expected_size):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    transient = _transient_errors()
    failures = 0
    session: SftpSession | None = None
    try:
        while True:
            have = part.stat().st_size if part.is_file() else 0
            try:
                if session is None:
                    session = connect()
                size = session.stat(remote).st_size
                assert isinstance(size, int), f"the server gave no size for {remote}"
                if expected_size is not None and size != expected_size:
                    raise FetchFailedError(
                        f"{remote} is {size} bytes on the server, but the catalogue says {expected_size}."
                    )
                if have > size:
                    logger.warning("%s is longer than %s on the server; starting again", part, remote)
                    part.unlink()
                    have = 0
                _copy_windows(session, remote, part, have, size, window, on_progress)
            except FileNotFoundError as exc:
                raise FetchFailedError(f"{remote} isn't on the bulk supply.") from exc
            except transient as exc:
                gained = (part.stat().st_size if part.is_file() else 0) > have
                failures = 1 if gained else failures + 1
                logger.warning(
                    "Reading %s failed (%s: %s), attempt %d", remote, type(exc).__name__, exc, failures
                )
                _close(session)
                session = None
                if failures >= max_failures:
                    raise FetchFailedError(f"{remote} failed {failures} times in a row: {exc}") from exc
                continue
            got = part.stat().st_size
            if got != size:
                raise FetchFailedError(f"{remote}: got {got} bytes, expected {size}.")
            part.replace(dest)
            return dest
    finally:
        _close(session)


def _copy_windows(
    session: SftpSession,
    remote: str,
    part: Path,
    offset: int,
    size: int,
    window: int,
    on_progress: Callable[[int, int], None] | None,
) -> None:
    with part.open("ab") as out:
        assert out.tell() == offset, f"{part} is {out.tell()} bytes, expected {offset}"
        while offset < size:
            length = min(window, size - offset)
            handle = session.open(remote, "rb")
            try:
                chunks = [
                    (offset + start, min(CHUNK_BYTES, length - start))
                    for start in range(0, length, CHUNK_BYTES)
                ]
                for data in handle.readv(chunks):
                    # Written as it arrives, so a failure part-way leaves a whole prefix to resume from.
                    out.write(data)
            finally:
                out.flush()
                with contextlib.suppress(*_transient_errors()):
                    handle.close()
            offset += length
            if out.tell() != offset:
                raise EOFError(f"{remote}: the server sent {out.tell()} bytes where {offset} were asked for")
            if on_progress is not None:
                on_progress(offset, size)


def _close(session: SftpSession | None) -> None:
    if session is not None:
        with contextlib.suppress(Exception):
            session.close()


class _ParamikoSession:
    def __init__(self, client: Any, sftp: Any) -> None:
        self._client = client
        self._sftp = sftp

    def stat(self, path: str) -> Any:
        return self._sftp.stat(path)

    def open(self, path: str, mode: str = "r") -> RemoteFile:
        return self._sftp.open(path, mode)

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._client.close()


def defra_connector(credentials: DefraSftpSettings) -> Connect:
    """A function that opens a session on the bulk supply, with the host key pinned.

    Raises `CredentialsMissingError` at once, before any connection, when a
    credential isn't set.
    """
    missing = credentials.missing
    if missing:
        raise CredentialsMissingError(
            f"This area isn't in the elevation mirror and {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set, so it can't be fetched from "
            "Defra's bulk supply. Set them in the environment or in the repository's .env file."
        )
    known_hosts = credentials.defra_sftp_known_hosts
    if not known_hosts.is_file():
        raise ConfigError(f"The pinned host key file {known_hosts} doesn't exist.")
    host, user, password = (
        credentials.defra_sftp_host,
        credentials.defra_sftp_user,
        credentials.defra_sftp_password,
    )
    assert host, "checked above"
    assert user, "checked above"
    assert password is not None, "checked above"

    def connect() -> SftpSession:
        import paramiko

        client = paramiko.SSHClient()
        client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                host,
                port=credentials.defra_sftp_port,
                username=user,
                password=password.get_secret_value(),
                allow_agent=False,
                look_for_keys=False,
                timeout=30,
                banner_timeout=30,
                auth_timeout=30,
            )
        except paramiko.AuthenticationException as exc:
            client.close()
            raise FetchFailedError("Defra's bulk supply rejected the user name or password.") from exc
        except paramiko.BadHostKeyException as exc:
            client.close()
            raise FetchFailedError(
                f"Defra's bulk supply presented a host key that isn't the one in {known_hosts}."
            ) from exc
        except BaseException:
            client.close()
            raise
        return _ParamikoSession(client, client.open_sftp())

    return connect
