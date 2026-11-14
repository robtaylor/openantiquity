"""Each request's id: made by the server, sent on every response and on each log line written for it."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.types import Message, Receive, Scope, Send

from fieldclub import request_ids
from fieldclub.errors import ConflictError
from fieldclub.main import create_app
from fieldclub.security import BODY_MAX_BYTES
from fieldclub.terrain.workers import TileWorkers
from tests.helpers import BASE_URL, WEB

ID = re.compile(r"[0-9a-f]{16}")

logger = logging.getLogger("tests.request_ids")


@pytest.fixture
def app_with_routes(db: Session) -> FastAPI:
    """The real app, with routes of the test's own: two that log, one that refuses, one that crashes."""
    app = create_app()

    @app.get("/api/v1/test/logs")
    def logs() -> dict[str, str]:
        # A plain `def` runs in the thread pool, as every endpoint does.
        logger.info("Handling the request")
        return {"ok": "yes"}

    @app.get("/api/v1/test/logs-async")
    async def logs_async() -> dict[str, str]:
        logger.info("Handling the request on the loop")
        return {"ok": "yes"}

    @app.get("/api/v1/test/clash")
    def clash() -> None:
        raise ConflictError("Already there.", code="thing_exists")

    @app.get("/api/v1/test/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
def plain(app_with_routes: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_with_routes, base_url=BASE_URL, headers=WEB, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def tagged(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """caplog, with the filter the server puts on its log handler."""
    tagger = request_ids.RequestIdFilter()
    caplog.handler.addFilter(tagger)
    caplog.set_level("INFO")
    yield caplog
    caplog.handler.removeFilter(tagger)


def request_id_of(response: object) -> str:
    headers = response.headers  # type: ignore[attr-defined]
    value = headers[request_ids.HEADER]
    assert ID.fullmatch(value), value
    return value


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/v1/meta", 200),
        ("GET", "/healthz", 200),
        ("GET", "/api/v1/nope", 404),
        ("GET", "/tiles/nope/1/2/3.png", 404),
        ("DELETE", "/api/v1/meta", 405),
        ("GET", "/api/v1/test/clash", 409),
        ("GET", "/api/v1/test/crash", 500),
    ],
)
def test_every_response_carries_a_request_id(plain: TestClient, method: str, path: str, status: int) -> None:
    response = plain.request(method, path)
    assert response.status_code == status
    request_id_of(response)


def test_each_request_gets_its_own_id(plain: TestClient) -> None:
    ids = {request_id_of(plain.get("/healthz")) for _ in range(5)}
    assert len(ids) == 5


def test_an_id_sent_by_the_client_is_never_taken(plain: TestClient) -> None:
    response = plain.get("/healthz", headers={request_ids.HEADER: "chosen-by-the-client"})
    assert request_id_of(response) != "chosen-by-the-client"
    assert response.headers.get_list(request_ids.HEADER) == [response.headers[request_ids.HEADER]]


@pytest.mark.parametrize("path", ["/api/v1/nope", "/api/v1/test/clash", "/api/v1/test/crash"])
def test_an_error_body_repeats_the_id_beside_its_code_and_message(plain: TestClient, path: str) -> None:
    response = plain.get(path)
    error = response.json()["error"]
    assert set(error) == {"code", "message", "request_id"}
    assert error["request_id"] == request_id_of(response)


def test_a_validation_error_keeps_its_details_and_gains_the_id(plain: TestClient) -> None:
    response = plain.get("/api/v1/findings", params={"limit": "many"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]
    assert error["request_id"] == request_id_of(response)


def test_refusals_made_before_the_routes_carry_it_too(app_with_routes: FastAPI) -> None:
    with TestClient(app_with_routes, base_url=BASE_URL) as client:
        # No client header: refused by the middleware, outside the app's error handlers.
        refused = client.post("/api/v1/auth/logout")
        too_big = client.post("/api/v1/auth/logout", headers=WEB, content=b"x" * (BODY_MAX_BYTES + 1))
    for response, code in ((refused, "client_header_required"), (too_big, "request_too_large")):
        error = response.json()["error"]
        assert error["code"] == code
        assert error["request_id"] == request_id_of(response)


def test_log_lines_written_while_handling_a_request_carry_its_id(
    plain: TestClient, tagged: pytest.LogCaptureFixture
) -> None:
    for path, message in (
        ("/api/v1/test/logs", "Handling the request"),
        ("/api/v1/test/logs-async", "Handling the request on the loop"),
    ):
        tagged.clear()
        response = plain.get(path)
        lines = [record for record in tagged.records if record.getMessage() == message]
        assert len(lines) == 1
        assert lines[0].request_id == request_id_of(response)  # type: ignore[attr-defined]


def test_the_log_line_of_an_unexpected_error_carries_the_id(
    plain: TestClient, tagged: pytest.LogCaptureFixture
) -> None:
    response = plain.get("/api/v1/test/crash")
    assert response.status_code == 500
    lines = [record for record in tagged.records if record.getMessage() == "Unhandled error"]
    assert len(lines) == 1
    assert lines[0].request_id == request_id_of(response)  # type: ignore[attr-defined]


def test_a_line_written_outside_any_request_has_none(
    plain: TestClient, tagged: pytest.LogCaptureFixture
) -> None:
    plain.get("/api/v1/test/logs")
    assert request_ids.current() is None
    logger.info("Between requests")
    (line,) = [record for record in tagged.records if record.getMessage() == "Between requests"]
    assert line.request_id == "-"  # type: ignore[attr-defined]


def test_the_server_s_own_line_for_a_response_is_written_with_the_id(
    tagged: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uvicorn writes its access line when the response starts, inside the request, as this server does."""
    # A test that started uvicorn with its own configuration can stop its access lines, or raise their level.
    monkeypatch.setattr(logging.getLogger("uvicorn.access"), "propagate", True)
    monkeypatch.setattr(logging.getLogger("uvicorn.access"), "disabled", False)
    tagged.set_level("INFO", logger="uvicorn.access")

    async def answer(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[Message] = []

    async def server_send(message: Message) -> None:
        if message["type"] == "http.response.start":
            logging.getLogger("uvicorn.access").info('"GET / HTTP/1.1" %d', message["status"])
        sent.append(message)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = request_ids.RequestIdMiddleware(answer)
    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    asyncio.run(middleware(scope, receive, server_send))
    header = dict(sent[0]["headers"])[request_ids.HEADER.lower().encode()].decode()
    lines = [record for record in tagged.records if record.getMessage() == '"GET / HTTP/1.1" 204']
    assert lines
    assert {line.request_id for line in lines} == {header}  # type: ignore[attr-defined]
    assert request_ids.current() is None


def test_a_tile_drawn_on_the_tile_threads_is_drawn_inside_the_request() -> None:
    workers = TileWorkers(workers=1, queue=0)

    async def draw_one() -> str | None:
        with request_ids.bound("0123456789abcdef"):
            return await workers.run(request_ids.current)

    try:
        assert asyncio.run(draw_one()) == "0123456789abcdef"
    finally:
        workers.close()
