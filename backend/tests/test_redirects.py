"""The site's other names send every request to the same path on its one address."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.types import Message, Receive, Scope, Send

from fieldclub.config import get_settings
from fieldclub.errors import ConfigError
from fieldclub.main import create_app
from fieldclub.redirects import CanonicalHostMiddleware
from tests.helpers import settings

OTHER_NAMES = '["www.openantiquity.org", "openantiquity.com", "www.openantiquity.com", "OpenAntiquity.co.uk"]'


@pytest.fixture
def client(env: Callable[..., None], db: Session) -> TestClient:
    env(PUBLIC_URL="https://openantiquity.org", REDIRECT_HOSTS=OTHER_NAMES)
    return TestClient(create_app(get_settings()), follow_redirects=False)


@pytest.mark.parametrize("host", ["www.openantiquity.org", "openantiquity.com", "openantiquity.co.uk"])
def test_another_name_is_sent_to_the_same_path_on_the_site(client: TestClient, host: str) -> None:
    response = client.get("/f/7K3QXM?tab=notes&x=%2F", headers={"Host": host})

    assert response.status_code == 308
    assert response.headers["location"] == "https://openantiquity.org/f/7K3QXM?tab=notes&x=%2F"


def test_the_name_is_matched_without_its_port_or_case(client: TestClient) -> None:
    response = client.get("/", headers={"Host": "WWW.OpenAntiquity.com:443"})

    assert response.status_code == 308
    assert response.headers["location"] == "https://openantiquity.org/"


def test_a_change_is_redirected_too_and_keeps_its_method(client: TestClient) -> None:
    # 308, not 301, so a browser repeats a POST as a POST.
    response = client.post("/api/v1/findings", headers={"Host": "openantiquity.com"})

    assert response.status_code == 308


def test_the_site_itself_and_any_other_name_are_served(client: TestClient) -> None:
    for host in ("openantiquity.org", "openantiquity.fly.dev", "172.19.0.2:8080"):
        response = client.get("/healthz", headers={"Host": host})
        assert response.status_code == 200, host


@pytest.mark.parametrize(
    ("raw_path", "location"),
    [
        (b"//elsewhere.example/x", b"https://openantiquity.org//elsewhere.example/x"),
        # A request target that isn't a path, which h11 lets through: appended
        # as it is, it would make `openantiquity.org@evil.example` the address.
        (b"@evil.example/x", b"https://openantiquity.org/"),
        (b"*", b"https://openantiquity.org/"),
        (b".evil.example/x", b"https://openantiquity.org/"),
    ],
)
def test_a_path_that_looks_like_another_host_stays_on_the_site(raw_path: bytes, location: bytes) -> None:
    # Sent as the raw request line, because an HTTP client would read `//host` as a host.
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the request should have been redirected")

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": raw_path.decode(),
        "raw_path": raw_path,
        "query_string": b"",
        "headers": [(b"host", b"openantiquity.com")],
    }
    middleware = CanonicalHostMiddleware(app, hosts=["openantiquity.com"], target="https://openantiquity.org")
    asyncio.run(middleware(scope, receive, send))

    headers = dict(sent[0]["headers"])
    assert sent[0]["status"] == 308
    assert headers[b"location"] == location


def test_no_names_means_no_redirects(env: Callable[..., None], db: Session) -> None:
    env(PUBLIC_URL="https://openantiquity.org")
    client = TestClient(create_app(get_settings()), follow_redirects=False)

    assert client.get("/healthz", headers={"Host": "openantiquity.com"}).status_code == 200


def test_the_site_s_own_name_is_refused_as_a_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDCLUB_PUBLIC_URL", "https://openantiquity.org")
    monkeypatch.setenv("FIELDCLUB_REDIRECT_HOSTS", '["openantiquity.org"]')

    with pytest.raises(ConfigError, match="FIELDCLUB_REDIRECT_HOSTS"):
        settings()


@pytest.mark.parametrize("name", ["https://openantiquity.com", "openantiquity.com/", "", "a b"])
def test_a_name_that_is_not_a_host_name_is_refused(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("FIELDCLUB_REDIRECT_HOSTS", f'["{name}"]')

    with pytest.raises(ValueError, match="redirect_hosts"):
        settings()
