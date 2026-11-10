"""The shared outbound HTTP client."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx

from fieldclub import __version__, http
from fieldclub.config import get_settings


@pytest.fixture(autouse=True)
def fresh_client() -> Iterator[None]:
    http.close_client()
    yield
    http.close_client()


def test_client_is_shared() -> None:
    assert http.get_client() is http.get_client()


def test_client_sends_the_project_user_agent_and_has_a_timeout() -> None:
    client = http.get_client()
    assert client.headers["User-Agent"] == f"FieldClub/{__version__}"
    assert client.timeout.read == get_settings().http_timeout_s
    assert client.timeout.connect is not None
    assert client.timeout.connect <= 10
    assert client.follow_redirects is True


@respx.mock
def test_requests_carry_the_user_agent() -> None:
    route = respx.get("https://upstream.example/records").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    response = http.get_client().get("https://upstream.example/records")
    assert response.json() == {"ok": True}
    assert route.calls.last.request.headers["user-agent"] == f"FieldClub/{__version__}"


def test_close_client_makes_way_for_a_new_one() -> None:
    first = http.get_client()
    http.close_client()
    assert first.is_closed
    second = http.get_client()
    assert second is not first
    assert not second.is_closed
    http.close_client()
    http.close_client()
