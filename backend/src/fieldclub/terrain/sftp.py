"""Reading files from Defra's SFTP bulk supply.

Two behaviours of the server shape this module (`docs/sources/lidar-england-bulk-supply.md`).
It drops the connection at about 52 MiB when a whole file is requested with
the client's default read-ahead, so files are read in windows of 8 MiB with
the file handle reopened for each. And connections fail now and then, so a
download writes to `<name>.part`, resumes from whatever that file holds, and
is renamed into place only when its size matches.

`SessionPool` keeps sessions open between downloads, so copying many tiles
signs in once per connection, not once per tile.

A failed attempt is retried after a pause that doubles each time, and every
read gives up after `READ_TIMEOUT` seconds of silence, so a stalled server
can't hold a fetch for ever. A refused login or a wrong host key is never
retried: `SupplyRefusedError` says to stop asking.

The host key is pinned: a host whose key isn't in the known-hosts file is
refused. Neither the credentials nor the server's address reach a log line
or an error: an error names only the file being read, and a log line the
file, the kind of failure and its error number, because the transport's own
text can carry the host and port. For the same reason no error raised here
chains the transport's exception (`from None`): the API logs a 5xx error
with its traceback, which would print the chained one too.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from fieldclub.config import DefraSftpSettings
from fieldclub.errors import ConfigError
from fieldclub.terrain.errors import CredentialsMissingError, FetchFailedError, SupplyRefusedError

logger = logging.getLogger(__name__)

MIB = 1024 * 1024
WINDOW_BYTES = 8 * MIB
CHUNK_BYTES = 32 * 1024
# Consecutive failed attempts, with no bytes gained between them, before giving up.
MAX_FAILURES = 5
# The pause after the first failed attempt, doubled after each further one, up to the cap.
RETRY_DELAY = 2.0
RETRY_DELAY_CAP = 60.0
# Seconds of silence before a read or a connection attempt gives up.
READ_TIMEOUT = 60.0
# Seconds between keepalive packets, so an idle connection that has died is noticed.
KEEPALIVE_INTERVAL = 30


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
    retry_delay: float = RETRY_DELAY,
    sleep: Callable[[float], None] = time.sleep,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Copy `remote` to `dest`, in windows, resuming from `dest.part`.

    `dest` appears only when the whole file has arrived and its size matches
    the server's (and `expected_size`, when given). A partial file is never
    left at `dest`. After a failed attempt it waits `retry_delay` seconds,
    doubled for each further failure in a row, before connecting again.
    """
    assert window > 0, "the window must hold at least one byte"
    assert retry_delay >= 0, "a pause can't be negative"
    # What error messages call the file: never the host or the folder.
    file = Path(remote).name
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
                        f"{file} is {size} bytes on the bulk supply, but the catalogue says {expected_size}."
                    )
                if have > size:
                    logger.warning("%s is longer than %s on the server; starting again", part, file)
                    part.unlink()
                    have = 0
                _copy_windows(session, remote, part, have, size, window, on_progress)
            except FileNotFoundError:
                raise FetchFailedError(f"{file} isn't on the bulk supply.") from None
            except transient as exc:
                gained = (part.stat().st_size if part.is_file() else 0) > have
                failures = 1 if gained else failures + 1
                logger.warning(
                    "Reading %s failed (%s, errno %s), attempt %d",
                    file,
                    type(exc).__name__,
                    getattr(exc, "errno", None),
                    failures,
                )
                _discard(session)
                session = None
                if failures >= max_failures:
                    raise FetchFailedError(f"Reading {file} failed {failures} times in a row.") from None
                sleep(min(retry_delay * 2 ** (failures - 1), RETRY_DELAY_CAP))
                continue
            got = part.stat().st_size
            if got != size:
                raise FetchFailedError(f"{file}: got {got} bytes, expected {size}.")
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


def _discard(session: SftpSession | None) -> None:
    """Close a session that failed, so a pool doesn't hand it out again."""
    if session is None:
        return
    discard = getattr(session, "discard", None)
    with contextlib.suppress(Exception):
        discard() if discard is not None else session.close()


class SessionPool:
    """Sessions kept open between downloads: at most `size` idle, any number in use.

    `connect` hands out an idle session or opens one. Closing it gives it
    back. A download that fails discards it instead, and a session that died
    while idle fails on first use, is discarded and replaced.
    """

    def __init__(self, connect: Connect, size: int) -> None:
        assert size >= 1, "a pool keeps at least one session"
        self._connect = connect
        self._size = size
        self._idle: list[SftpSession] = []
        self._guard = threading.Lock()

    def connect(self) -> SftpSession:
        with self._guard:
            raw = self._idle.pop() if self._idle else None
        return _PooledSession(self, raw if raw is not None else self._connect())

    def give_back(self, raw: SftpSession) -> None:
        with self._guard:
            if len(self._idle) < self._size:
                self._idle.append(raw)
                return
        _close(raw)

    def close(self) -> None:
        with self._guard:
            idle, self._idle = self._idle, []
        for raw in idle:
            _close(raw)


class _PooledSession:
    def __init__(self, pool: SessionPool, raw: SftpSession) -> None:
        self._pool = pool
        self._raw: SftpSession | None = raw

    def _session(self) -> SftpSession:
        if self._raw is None:
            raise EOFError("the session has been given back")
        return self._raw

    def stat(self, path: str) -> Any:
        return self._session().stat(path)

    def open(self, path: str, mode: str = "r") -> RemoteFile:
        return self._session().open(path, mode)

    def close(self) -> None:
        raw, self._raw = self._raw, None
        if raw is not None:
            self._pool.give_back(raw)

    def discard(self) -> None:
        raw, self._raw = self._raw, None
        _close(raw)


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
        logger.error("The pinned host key file %s doesn't exist", known_hosts)
        raise ConfigError("The bulk supply's pinned host key file doesn't exist.")
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
                timeout=READ_TIMEOUT,
                banner_timeout=READ_TIMEOUT,
                auth_timeout=READ_TIMEOUT,
            )
            transport = client.get_transport()
            assert transport is not None, "a connected client has a transport"
            transport.set_keepalive(KEEPALIVE_INTERVAL)
            session = client.open_sftp()
            channel = session.get_channel()
            assert channel is not None, "an open SFTP session has a channel"
            # Without this a read from a server that has gone quiet blocks for ever.
            channel.settimeout(READ_TIMEOUT)
        except paramiko.AuthenticationException:
            client.close()
            logger.error("The bulk supply refused the login")
            raise SupplyRefusedError("Defra's bulk supply rejected the user name or password.") from None
        except paramiko.BadHostKeyException:
            client.close()
            logger.error("The bulk supply's host key isn't the one pinned in %s", known_hosts)
            raise SupplyRefusedError(
                "Defra's bulk supply presented a host key that isn't the pinned one."
            ) from None
        except BaseException:
            client.close()
            raise
        return _ParamikoSession(client, session)

    return connect
