"""Fetching an address someone else chose, without letting it reach inside our network.

`fetch()` is for a URL that came from a person or a feed: a link a member
typed, or the address a page redirects to. It has a client of its own, with a
small connection pool, so a stalled stranger's server never takes a connection
from the shared client in `fieldclub.http`. It carries the project
`User-Agent`, and adds these guards against server-side request forgery:

- Only `http` and `https`, only on ports 80 and 443, and no user name or
  password in the address.
- The host is resolved once. If any address it resolves to is private,
  loopback, link-local, shared, reserved, multicast or a cloud metadata
  address, in any notation (IPv4 written as one number or in hex, IPv4 inside
  IPv6), the fetch is refused. Names such as `localhost` and `*.internal` are
  refused without asking DNS.
- The connection is made to the address that was checked, with the name sent
  as `Host` and as the TLS server name, so a second DNS answer can't swap in
  another address (DNS rebinding).
- Redirects are followed by hand, at most `max_redirects` of them, and every
  hop passes the same checks.
- The content type must be one the caller expects and the body is read with
  a hard cap.
- The whole fetch has a deadline as well as a timeout on each read. The
  deadline bounds every socket operation, the status line and headers
  included, so a server that drips bytes can't hold a thread, and the name
  lookup runs in a worker that is given up on after a few seconds.

A refusal raises `FetchRefusedError`. Anything else that goes wrong (a
timeout, a 404, a reset connection) raises `FetchFailedError`. Neither is
meant to reach a person as an error: a caller saves what it can without the
fetched data.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
import typing
import zlib
from collections.abc import Callable, Collection, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpcore
import httpx

from fieldclub.config import get_settings
from fieldclub.errors import FetchFailedError as FetchFailedError
from fieldclub.errors import FetchRefusedError as FetchRefusedError

logger = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Resolves a host name to the addresses it would connect to. Tests pass their own.
Resolver = Callable[[str, int], list[str]]

DEFAULT_PORTS = {"http": 80, "https": 443}

# Names that only ever mean something inside a network.
_INTERNAL_NAMES = frozenset({"localhost", "metadata", "metadata.google.internal", "instance-data"})
_INTERNAL_SUFFIXES = (".localhost", ".internal", ".local", ".localdomain", ".home.arpa", ".lan", ".intranet")

# Metadata services that sit at addresses the checks below don't already refuse.
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),  # AWS, Google Cloud, Azure, others
        ipaddress.ip_address("fd00:ec2::254"),  # AWS over IPv6
        ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud
    }
)
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))
# IPv4-compatible (deprecated) and SIIT IPv4-translated addresses. Python calls
# them global, but where they route at all they reach the IPv4 address inside.
_REFUSED_V6 = (ipaddress.ip_network("::/96"), ipaddress.ip_network("::ffff:0:0:0/96"))

# Something `inet_aton` reads as an IPv4 address: decimal, octal or hex parts.
_NUMERIC_HOST = re.compile(r"[0-9a-fA-FxX.]+")


@dataclass(frozen=True)
class FetchLimits:
    """How far a fetch may go. The defaults suit a page someone linked to."""

    max_redirects: int = 3
    # Each connect and each read.
    timeout_s: float = 5.0
    # The whole fetch, redirects and body included.
    deadline_s: float = 10.0
    max_bytes: int = 512 * 1024
    # Stop at `max_bytes` and keep what was read, instead of failing. For HTML,
    # whose useful part comes first.
    truncate: bool = False

    def __post_init__(self) -> None:
        assert 0 <= self.max_redirects <= 10, "max_redirects must be between 0 and 10"
        assert self.timeout_s > 0, "timeout_s must be positive"
        assert self.deadline_s >= self.timeout_s, "deadline_s must be at least timeout_s"
        assert self.max_bytes > 0, "max_bytes must be positive"


@dataclass(frozen=True)
class Fetched:
    # The address that answered, after redirects, with its host name (not its IP address).
    url: str
    status: int
    content_type: str
    headers: Mapping[str, str]
    content: bytes
    # True when the body was cut off at `max_bytes`.
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)

    @property
    def not_modified(self) -> bool:
        return self.status == 304

    def text(self) -> str:
        """The body as text, in the charset the server named, or UTF-8."""
        match = re.search(r"charset=([\w.-]+)", self.headers.get("content-type", ""), re.IGNORECASE)
        encoding = match.group(1) if match else "utf-8"
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


# `getaddrinfo` has no timeout of its own, so it runs in one of these and is
# given up on after `_RESOLVE_TIMEOUT_S`. A lookup given up on still finishes
# in its worker, so there are few workers: a slow resolver can't take many threads.
_RESOLVE_TIMEOUT_S = 5.0
_resolver_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="safe-fetch-dns")


def system_resolver(host: str, port: int) -> list[str]:
    """Every address the system resolver gives for `host`, or `FetchFailedError` after a few seconds."""
    lookup = _resolver_pool.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    try:
        infos = lookup.result(timeout=_RESOLVE_TIMEOUT_S)
    except FutureTimeoutError as exc:
        lookup.cancel()
        raise FetchFailedError(f"Looking up {host} took too long.") from exc
    except (socket.gaierror, UnicodeError) as exc:
        raise FetchFailedError(f"{host} doesn't resolve.") from exc
    return [str(info[4][0]) for info in infos]


# --------------------------------------------------------------------------
# A deadline on every socket operation
# --------------------------------------------------------------------------

# When the fetch running in this context must end, by `time.monotonic()`.
_deadline: ContextVar[float | None] = ContextVar("safe_fetch_deadline", default=None)


@contextmanager
def _deadline_of(deadline: float) -> Iterator[None]:
    token = _deadline.set(deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def _within_deadline(timeout: float | None, error: type[Exception]) -> float | None:
    """`timeout` cut to what is left of the deadline, or `error` once it has passed."""
    deadline = _deadline.get()
    if deadline is None:
        return timeout
    left = deadline - time.monotonic()
    if left <= 0:
        raise error("The fetch ran out of time.")
    return left if timeout is None else min(timeout, left)


class _DeadlineStream(httpcore.NetworkStream):
    """A socket whose every read and write ends by the fetch's deadline."""

    def __init__(self, stream: httpcore.NetworkStream) -> None:
        self._stream = stream

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, _within_deadline(timeout, httpcore.ReadTimeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(buffer, _within_deadline(timeout, httpcore.WriteTimeout))

    def close(self) -> None:
        self._stream.close()

    def start_tls(
        self, ssl_context: typing.Any, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.NetworkStream:
        timeout = _within_deadline(timeout, httpcore.ConnectTimeout)
        return _DeadlineStream(self._stream.start_tls(ssl_context, server_hostname, timeout))

    def get_extra_info(self, info: str) -> typing.Any:
        return self._stream.get_extra_info(info)


class _DeadlineBackend(httpcore.NetworkBackend):
    """The usual sockets, each bounded by the deadline of the fetch that opened it.

    A per-read timeout alone lets a server send one byte just inside each
    timeout for as long as it likes, while the status line and headers arrive.
    """

    def __init__(self) -> None:
        self._backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[typing.Any] | None = None,
    ) -> httpcore.NetworkStream:
        timeout = _within_deadline(timeout, httpcore.ConnectTimeout)
        return _DeadlineStream(self._backend.connect_tcp(host, port, timeout, local_address, socket_options))

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[typing.Any] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("Fetches never use a Unix socket.")

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


# Few connections, so fetches from strangers' servers wait for each other
# rather than for everything else this process asks of the outside world.
_POOL_SIZE = 8
_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _build_client() -> httpx.Client:
    transport = httpx.HTTPTransport(retries=0)
    # httpx doesn't take a network backend, so its pool is replaced by one that does.
    assert isinstance(transport._pool, httpcore.ConnectionPool), "httpx's transport has changed shape"
    transport._pool = httpcore.ConnectionPool(
        ssl_context=httpx.create_ssl_context(),
        max_connections=_POOL_SIZE,
        max_keepalive_connections=0,
        network_backend=_DeadlineBackend(),
    )
    # With a transport given, httpx ignores proxy settings in the environment.
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": get_settings().outbound_user_agent},
        follow_redirects=False,
    )


def get_client() -> httpx.Client:
    """The client for fetches of untrusted addresses. Thread-safe, and lives for the process."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def close_client() -> None:
    """Close the fetch client. The next `get_client()` builds a fresh one."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address carried inside an IPv6 one, by any of the usual schemes."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address.teredo is not None:
        return address.teredo[1]
    if any(address in network for network in _NAT64):
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def is_public_address(address: IPAddress) -> bool:
    """Whether an address is somewhere on the public internet that we may connect to."""
    if address in _METADATA_ADDRESSES:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.scope_id or any(address in network for network in _REFUSED_V6):
            return False
        embedded = _embedded_ipv4(address)
        if embedded is not None and not is_public_address(embedded):
            return False
    return address.is_global and not address.is_multicast


def _literal_address(host: str) -> IPAddress | None:
    """The address a host names directly, or None for a name. Odd IPv4 notations are refused."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if _NUMERIC_HOST.fullmatch(host):
        try:
            socket.inet_aton(host)
        except OSError:
            return None
        # `2130706433`, `0x7f.1` or `0177.0.0.1`: an address in disguise.
        raise FetchRefusedError("That address is written in an unusual way, so it isn't fetched.")
    return None


def check_host(host: str, port: int, resolver: Resolver) -> IPAddress:
    """The checked address to connect to for `host`, or `FetchRefusedError`."""
    host = host.rstrip(".").lower()
    if not host:
        raise FetchRefusedError("That address has no host.")
    literal = _literal_address(host)
    if literal is not None:
        addresses = [literal]
    else:
        if host in _INTERNAL_NAMES or host.endswith(_INTERNAL_SUFFIXES) or "." not in host:
            raise FetchRefusedError("That address is on a private network.")
        resolved = resolver(host, port)
        try:
            addresses = [ipaddress.ip_address(item.split("%", 1)[0]) for item in resolved]
        except ValueError as exc:
            raise FetchFailedError(f"{host} resolved to something that isn't an address.") from exc
        # A zone index (`fe80::1%en0`) only ever comes with a link-local address.
        if any("%" in item for item in resolved):
            raise FetchRefusedError("That address is on a private network.")
    if not addresses:
        raise FetchFailedError(f"{host} doesn't resolve.")
    # All of them, not just the first: the client might be steered to any.
    if not all(is_public_address(address) for address in addresses):
        raise FetchRefusedError("That address is on a private network.")
    return addresses[0]


def check_url(raw: str | httpx.URL) -> httpx.URL:
    """The URL parsed, if its scheme, port and credentials are allowed, or `FetchRefusedError`."""
    try:
        url = raw if isinstance(raw, httpx.URL) else httpx.URL(raw)
    except (httpx.InvalidURL, TypeError, ValueError) as exc:
        raise FetchRefusedError("That isn't a web address.") from exc
    if url.scheme not in DEFAULT_PORTS:
        raise FetchRefusedError("Only http and https addresses are fetched.")
    # httpx drops a port that is the scheme's default, so any port left is another one.
    if url.port is not None and url.port != DEFAULT_PORTS[url.scheme]:
        raise FetchRefusedError("Only the standard web ports are fetched.")
    if url.userinfo:
        raise FetchRefusedError("Addresses with a user name or password aren't fetched.")
    if not url.host:
        raise FetchRefusedError("That address has no host.")
    return url


def _media_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _decoder(encoding: str) -> zlib._Decompress | None:
    """A decompressor for the response's content encoding. Only what we ask for is accepted."""
    encoding = encoding.strip().lower()
    if encoding in ("", "identity"):
        return None
    if encoding in ("gzip", "x-gzip"):
        return zlib.decompressobj(zlib.MAX_WBITS | 16)
    raise FetchFailedError(f"The server sent an encoding that wasn't asked for: {encoding}.")


def _read_body(response: httpx.Response, limits: FetchLimits, deadline: float) -> tuple[bytes, bool]:
    """The body, decompressed, with the cap applied to what it inflates to, and the deadline."""
    decoder = _decoder(response.headers.get("content-encoding", ""))
    body = bytearray()
    # No chunk size: a chunker would wait to fill each chunk, and a drip would never reach the deadline check.
    for chunk in response.iter_raw():
        if time.monotonic() > deadline:
            raise FetchFailedError("The server took too long to send its answer.")
        if decoder is None:
            body += chunk
        else:
            # Never inflate more than one byte past the cap, so a compressed bomb stays small.
            data = chunk
            while data and len(body) <= limits.max_bytes:
                body += decoder.decompress(data, limits.max_bytes + 1 - len(body))
                data = decoder.unconsumed_tail
        if len(body) > limits.max_bytes:
            if limits.truncate:
                return bytes(body[: limits.max_bytes]), True
            raise FetchFailedError("The answer was larger than we read.")
    return bytes(body), False


def fetch(
    url: str,
    *,
    content_types: Collection[str],
    accept: str | None = None,
    headers: Mapping[str, str] | None = None,
    limits: FetchLimits | None = None,
    resolver: Resolver | None = None,
    client: httpx.Client | None = None,
) -> Fetched:
    """GET `url` under every guard in the module docstring.

    `content_types` lists the media types accepted, such as `text/html`. A 304
    (for a conditional request made with `headers`) comes back with an empty
    body and no content-type check. Every other answer must be a 200.
    """
    assert content_types, "say which content types are acceptable"
    limits = limits or FetchLimits()
    resolver = resolver or system_resolver
    client = client or get_client()
    wanted = {item.lower() for item in content_types}
    deadline = time.monotonic() + limits.deadline_s
    with _deadline_of(deadline):
        return _fetch(check_url(url), wanted, accept, headers, limits, resolver, client, deadline)


def _fetch(
    current: httpx.URL,
    wanted: set[str],
    accept: str | None,
    headers: Mapping[str, str] | None,
    limits: FetchLimits,
    resolver: Resolver,
    client: httpx.Client,
    deadline: float,
) -> Fetched:
    redirects: list[str] = []
    request_headers = {
        "Accept": accept or ", ".join(sorted(wanted)),
        # Only what `_decoder` can cap.
        "Accept-Encoding": "gzip",
        # Each fetch gets its own connection, so one made for a checked name
        # is never reused for another name that shares its address.
        "Connection": "close",
        **(headers or {}),
    }

    while True:
        if time.monotonic() > deadline:
            raise FetchFailedError("The fetch took too long.")
        host = current.raw_host.decode("ascii")
        address = check_host(host, DEFAULT_PORTS[current.scheme], resolver)
        target = current.copy_with(host=str(address))
        extensions = {"sni_hostname": host} if current.scheme == "https" else {}
        request = client.build_request(
            "GET",
            target,
            headers={**request_headers, "Host": host},
            extensions=extensions,
            # Waiting for one of the few connections counts against the deadline too.
            timeout=httpx.Timeout(
                limits.timeout_s, pool=max(0.0, min(limits.timeout_s, deadline - time.monotonic()))
            ),
        )
        try:
            response = client.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise FetchFailedError(f"{host} didn't answer: {type(exc).__name__}.") from exc
        try:
            if response.is_redirect and response.status_code != 304:
                location = response.headers.get("location")
                if not location:
                    raise FetchFailedError("A redirect had nowhere to go.")
                if len(redirects) >= limits.max_redirects:
                    raise FetchFailedError("Too many redirects.")
                redirects.append(str(current))
                current = check_url(current.join(location))
                continue
            if response.status_code == 304:
                return Fetched(str(current), 304, "", dict(response.headers), b"", redirects=redirects)
            if response.status_code != 200:
                raise FetchFailedError(f"{host} answered {response.status_code}.")
            media_type = _media_type(response.headers)
            if media_type not in wanted:
                raise FetchFailedError(
                    f"{host} sent {media_type or 'no content type'}, not what was asked for."
                )
            try:
                content, truncated = _read_body(response, limits, deadline)
            except httpx.HTTPError as exc:
                raise FetchFailedError(f"{host} stopped part way: {type(exc).__name__}.") from exc
            return Fetched(
                str(current), 200, media_type, dict(response.headers), content, truncated, redirects
            )
        finally:
            response.close()
