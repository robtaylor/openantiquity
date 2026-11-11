"""Fetching an address a member typed can't reach inside our network (`fieldclub.safe_fetch`).

These live with the mention tests because mentions are what fetch such addresses.
"""

from __future__ import annotations

import gzip
import ipaddress
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import respx

from fieldclub import __version__, http, safe_fetch
from fieldclub.safe_fetch import FetchFailedError, FetchLimits, FetchRefusedError, fetch
from tests.mentions.support import ARTICLE_URL, DNS, ip_of, serve

# Taken before the fixtures swap in the fake resolver.
real_system_resolver = safe_fetch.system_resolver

HTML = ("text/html",)
ARTICLE_HOST = "www.wiltshire-gazette.example"


def test_a_public_page_is_fetched_from_the_address_that_was_checked(offline: respx.MockRouter) -> None:
    route = serve(ARTICLE_HOST, "/news/lost-enclosure", b"<title>Hi</title>", "text/html; charset=utf-8")
    fetched = fetch(ARTICLE_URL, content_types=HTML)
    assert fetched.status == 200
    assert fetched.content == b"<title>Hi</title>"
    assert fetched.url == ARTICLE_URL
    request = route.calls.last.request
    # The connection goes to the checked address, never to a second lookup of the name.
    assert request.url.host == ip_of(ARTICLE_HOST)
    assert request.headers["host"] == ARTICLE_HOST
    assert request.extensions["sni_hostname"] == ARTICLE_HOST
    assert request.headers["user-agent"] == f"OpenAntiquity/{__version__}"
    assert request.headers["accept-encoding"] == "gzip"


def test_an_ipv6_host_is_connected_to_by_its_address(offline: respx.MockRouter) -> None:
    route = respx.get(host="2606:4700:4700::1111", path="/").mock(
        return_value=httpx.Response(200, content=b"ok", headers={"content-type": "text/html"})
    )
    fetch("https://v6.example/", content_types=HTML)
    assert route.calls.last.request.headers["host"] == "v6.example"


PRIVATE_LITERALS = [
    "127.0.0.1",
    "127.10.20.30",
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.1",
    "169.254.169.254",
    "100.100.100.200",
    "100.64.0.1",
    "0.0.0.0",
    "192.0.2.10",
    "198.18.0.1",
    "224.0.0.1",
    "255.255.255.255",
    "[::1]",
    "[::]",
    "[fe80::1]",
    "[fc00::1]",
    "[fd00:ec2::254]",
    "[::ffff:127.0.0.1]",
    "[::ffff:a9fe:a9fe]",
    "[::ffff:10.0.0.1]",
    "[64:ff9b::a9fe:a9fe]",
    "[64:ff9b::7f00:1]",
    "[2002:7f00:1::]",
    "[2001:0:4136:e378:8000:63bf:80ff:fffe]",
    # IPv4-compatible and SIIT IPv4-translated addresses, which Python calls global.
    "[::127.0.0.1]",
    "[::a9fe:a9fe]",
    "[0:0:0:0:0:0:127.0.0.1]",
    "[::8.8.8.8]",
    "[::ffff:0:127.0.0.1]",
    "[::ffff:0:808:808]",
    "[ff02::1]",
    # IPv4 in the notations inet_aton accepts.
    "2130706433",
    "0x7f000001",
    "0x7f.1",
    "017700000001",
    "0177.0.0.1",
    "127.1",
    "2852039166",
    "0xa9.0xfe.0xa9.0xfe",
]


@pytest.mark.parametrize("host", PRIVATE_LITERALS)
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_private_and_metadata_addresses_are_refused_in_every_notation(
    host: str, scheme: str, offline: respx.MockRouter
) -> None:
    with pytest.raises(FetchRefusedError):
        fetch(f"{scheme}://{host}/latest/meta-data/", content_types=HTML)
    assert offline.calls.call_count == 0


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "LOCALHOST",
        "db.localhost",
        "metadata",
        "metadata.google.internal",
        "printer.local",
        "intranet",
    ],
)
def test_internal_names_are_refused_without_asking_dns(host: str, offline: respx.MockRouter) -> None:
    asked: list[str] = []

    def resolver(name: str, port: int) -> list[str]:
        asked.append(name)
        return ["93.184.215.14"]

    with pytest.raises(FetchRefusedError):
        fetch(f"http://{host}/", content_types=HTML, resolver=resolver)
    assert asked == []
    assert offline.calls.call_count == 0


@pytest.mark.parametrize(
    "host", ["inside.example", "metadata-alias.example", "dual.example", "v6-mapped.example", "nat64.example"]
)
def test_a_name_that_resolves_to_a_private_address_is_refused(host: str, offline: respx.MockRouter) -> None:
    assert host in DNS
    with pytest.raises(FetchRefusedError):
        fetch(f"https://{host}/", content_types=HTML)
    assert offline.calls.call_count == 0


def test_the_name_is_resolved_once_so_a_rebinding_answer_is_never_used(offline: respx.MockRouter) -> None:
    answers = iter([["93.184.215.14"], ["127.0.0.1"]])
    calls: list[str] = []

    def rebinding(name: str, port: int) -> list[str]:
        calls.append(name)
        return next(answers)

    route = serve(ARTICLE_HOST, "/news/lost-enclosure", b"ok", "text/html")
    fetch(ARTICLE_URL, content_types=HTML, resolver=rebinding)
    assert calls == [ARTICLE_HOST]
    assert route.calls.last.request.url.host == "93.184.215.14"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://www.wiltshire-gazette.example/",
        "gopher://www.wiltshire-gazette.example:70/",
        "dict://www.wiltshire-gazette.example:11211/",
        "ldap://www.wiltshire-gazette.example/",
        "javascript:alert(1)",
        "//www.wiltshire-gazette.example/",
        "not a url",
    ],
)
def test_other_schemes_are_refused(url: str, offline: respx.MockRouter) -> None:
    with pytest.raises(FetchRefusedError):
        fetch(url, content_types=HTML)
    assert offline.calls.call_count == 0


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wiltshire-gazette.example:8443/",
        "http://www.wiltshire-gazette.example:8080/",
        "http://www.wiltshire-gazette.example:22/",
        "http://www.wiltshire-gazette.example:6379/",
        "https://www.wiltshire-gazette.example:80/",
        "http://www.wiltshire-gazette.example:443/",
    ],
)
def test_other_ports_are_refused(url: str, offline: respx.MockRouter) -> None:
    with pytest.raises(FetchRefusedError):
        fetch(url, content_types=HTML)
    assert offline.calls.call_count == 0


def test_credentials_in_the_address_are_refused(offline: respx.MockRouter) -> None:
    with pytest.raises(FetchRefusedError):
        fetch("https://admin:admin@www.wiltshire-gazette.example/", content_types=HTML)


def redirect(host: str, path: str, location: str, status: int = 302) -> respx.Route:
    return serve(host, path, b"", "text/html", status=status, headers={"location": location})


@pytest.mark.parametrize(
    "location",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:80/admin",
        "http://[::1]/",
        "http://2130706433/",
        "https://inside.example/",
        "http://localhost/",
        "file:///etc/passwd",
        "https://www.wiltshire-gazette.example:8443/",
    ],
)
def test_a_redirect_to_somewhere_refused_is_refused(location: str, offline: respx.MockRouter) -> None:
    redirect("redirector.example", "/go", location)
    with pytest.raises(FetchRefusedError):
        fetch("https://redirector.example/go", content_types=HTML)
    # Only the first hop was made.
    assert offline.calls.call_count == 1


def test_redirects_are_followed_with_the_same_checks(offline: respx.MockRouter) -> None:
    redirect("redirector.example", "/go", "/next", status=301)
    redirect("redirector.example", "/next", ARTICLE_URL, status=307)
    serve(ARTICLE_HOST, "/news/lost-enclosure", b"arrived", "text/html")
    fetched = fetch("https://redirector.example/go", content_types=HTML)
    assert fetched.content == b"arrived"
    assert fetched.url == ARTICLE_URL
    assert fetched.redirects == ["https://redirector.example/go", "https://redirector.example/next"]


def test_redirects_are_limited(offline: respx.MockRouter) -> None:
    for hop in range(5):
        redirect("redirector.example", f"/{hop}", f"/{hop + 1}")
    with pytest.raises(FetchFailedError, match="Too many redirects"):
        fetch("https://redirector.example/0", content_types=HTML, limits=FetchLimits(max_redirects=3))
    assert offline.calls.call_count == 4


def endless() -> Iterator[bytes]:
    while True:
        yield b"<p>" + b"x" * 8192


def test_a_body_that_never_ends_is_cut_off(offline: respx.MockRouter) -> None:
    respx.get(host=ip_of(ARTICLE_HOST)).mock(
        side_effect=lambda request: httpx.Response(
            200, content=endless(), headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(FetchFailedError, match="larger"):
        fetch(ARTICLE_URL, content_types=HTML, limits=FetchLimits(max_bytes=64 * 1024))


def test_html_that_never_ends_is_read_up_to_the_cap(offline: respx.MockRouter) -> None:
    respx.get(host=ip_of(ARTICLE_HOST)).mock(
        side_effect=lambda request: httpx.Response(
            200, content=endless(), headers={"content-type": "text/html"}
        )
    )
    fetched = fetch(ARTICLE_URL, content_types=HTML, limits=FetchLimits(max_bytes=64 * 1024, truncate=True))
    assert fetched.truncated
    assert len(fetched.content) == 64 * 1024


def test_a_compressed_body_is_capped_by_what_it_inflates_to(offline: respx.MockRouter) -> None:
    bomb = gzip.compress(b"\0" * (20 * 1024 * 1024))
    assert len(bomb) < 64 * 1024
    serve(ARTICLE_HOST, "/news/lost-enclosure", bomb, "text/html", headers={"content-encoding": "gzip"})
    with pytest.raises(FetchFailedError, match="larger"):
        fetch(ARTICLE_URL, content_types=HTML, limits=FetchLimits(max_bytes=64 * 1024))


def test_a_compressed_body_within_the_cap_is_inflated(offline: respx.MockRouter) -> None:
    serve(
        ARTICLE_HOST,
        "/news/lost-enclosure",
        gzip.compress(b"<title>Hi</title>"),
        "text/html",
        headers={"content-encoding": "gzip"},
    )
    assert fetch(ARTICLE_URL, content_types=HTML).content == b"<title>Hi</title>"


def test_an_encoding_that_wasnt_asked_for_fails(offline: respx.MockRouter) -> None:
    serve(ARTICLE_HOST, "/news/lost-enclosure", b"???", "text/html", headers={"content-encoding": "br"})
    with pytest.raises(FetchFailedError, match="encoding"):
        fetch(ARTICLE_URL, content_types=HTML)


def test_a_slow_response_runs_out_of_time(offline: respx.MockRouter) -> None:
    def drip() -> Iterator[bytes]:
        while True:
            time.sleep(0.05)
            yield b"x"

    respx.get(host=ip_of(ARTICLE_HOST)).mock(
        side_effect=lambda request: httpx.Response(200, content=drip(), headers={"content-type": "text/html"})
    )
    started = time.monotonic()
    with pytest.raises(FetchFailedError, match="too long"):
        fetch(ARTICLE_URL, content_types=HTML, limits=FetchLimits(timeout_s=0.1, deadline_s=0.3))
    assert time.monotonic() - started < 2


def test_a_timeout_fails(offline: respx.MockRouter) -> None:
    respx.get(host=ip_of(ARTICLE_HOST)).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(FetchFailedError):
        fetch(ARTICLE_URL, content_types=HTML)


def test_the_timeout_is_set_on_each_request(offline: respx.MockRouter) -> None:
    route = serve(ARTICLE_HOST, "/news/lost-enclosure", b"ok", "text/html")
    fetch(ARTICLE_URL, content_types=HTML, limits=FetchLimits(timeout_s=1.5, deadline_s=3))
    assert route.calls.last.request.extensions["timeout"]["read"] == 1.5


def test_the_content_type_must_be_one_asked_for(offline: respx.MockRouter) -> None:
    serve(ARTICLE_HOST, "/news/lost-enclosure", b"\x89PNG", "image/png")
    with pytest.raises(FetchFailedError, match="image/png"):
        fetch(ARTICLE_URL, content_types=HTML)


@pytest.mark.parametrize("status", [404, 500, 403])
def test_an_error_status_fails(status: int, offline: respx.MockRouter) -> None:
    serve(ARTICLE_HOST, "/news/lost-enclosure", b"no", "text/html", status=status)
    with pytest.raises(FetchFailedError, match=str(status)):
        fetch(ARTICLE_URL, content_types=HTML)


def test_a_conditional_request_can_come_back_unchanged(offline: respx.MockRouter) -> None:
    route = serve(ARTICLE_HOST, "/news/lost-enclosure", b"", "", status=304)
    fetched = fetch(ARTICLE_URL, content_types=HTML, headers={"If-None-Match": '"abc"'})
    assert fetched.not_modified
    assert route.calls.last.request.headers["if-none-match"] == '"abc"'


def test_a_name_that_doesnt_resolve_fails(offline: respx.MockRouter) -> None:
    with pytest.raises(FetchFailedError, match="resolve"):
        fetch("https://nowhere.example/", content_types=HTML)


@pytest.mark.parametrize("address", ["93.184.215.14", "2606:4700:4700::1111", "8.8.8.8"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert safe_fetch.is_public_address(ipaddress.ip_address(address))


# --------------------------------------------------------------------------
# A server that answers slowly, on a real socket
# --------------------------------------------------------------------------


@pytest.fixture
def header_drip(monkeypatch: pytest.MonkeyPatch, offline: respx.MockRouter) -> Iterator[str]:
    """A local server that starts its headers and then sends one byte every 50 ms, for 30 s at most.

    The fetch's checks are loosened for it alone: its name resolves to
    loopback, loopback counts as public, and its port counts as standard.
    """
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        listener.settimeout(5)
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        with conn:
            conn.recv(65536)
            conn.sendall(b"HTTP/1.1 200 OK\r\nX-Drip: ")
            deadline = time.monotonic() + 30
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    conn.sendall(b"a")
                except OSError:
                    return
                stop.wait(0.05)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    monkeypatch.setitem(safe_fetch.DEFAULT_PORTS, "http", port)
    monkeypatch.setitem(DNS, "drip.example", ["127.0.0.1"])
    real_check = safe_fetch.is_public_address
    monkeypatch.setattr(
        safe_fetch,
        "is_public_address",
        lambda address: address == ipaddress.ip_address("127.0.0.1") or real_check(address),
    )
    offline.route(host="127.0.0.1").pass_through()
    yield f"http://drip.example:{port}/"
    stop.set()
    listener.close()
    thread.join(5)


def test_headers_sent_a_byte_at_a_time_run_out_of_time(header_drip: str) -> None:
    started = time.monotonic()
    with pytest.raises(FetchFailedError):
        fetch(header_drip, content_types=HTML, limits=FetchLimits(timeout_s=1, deadline_s=1.5))
    # Each byte arrives well inside the read timeout, so only the deadline stops it.
    assert time.monotonic() - started < 3


def test_a_name_lookup_that_hangs_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    def hang(*args: object, **kwargs: object) -> list[object]:
        release.wait(10)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", hang)
    monkeypatch.setattr(safe_fetch, "_RESOLVE_TIMEOUT_S", 0.2)
    started = time.monotonic()
    try:
        with pytest.raises(FetchFailedError, match="took too long"):
            real_system_resolver("slow.example", 443)
    finally:
        release.set()
    assert time.monotonic() - started < 2


def test_untrusted_fetches_have_a_client_of_their_own() -> None:
    client = safe_fetch.get_client()
    assert client is not http.get_client()
    assert client is safe_fetch.get_client()
    assert client.headers["user-agent"] == f"OpenAntiquity/{__version__}"
    safe_fetch.close_client()
    assert safe_fetch.get_client() is not client
