"""The client-header check covers every path, whatever kind of route serves it."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from fieldclub.auth.csrf import MUTATING_METHODS, ClientHeaderMiddleware
from fieldclub.config import CLIENT_HEADER
from fieldclub.errors import install_error_handlers
from tests.helpers import BASE_URL, WEB

ALL_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]


def raw(request: Request) -> JSONResponse:
    return JSONResponse({"raw": True})


@pytest.fixture
def csrf_app() -> FastAPI:
    """One route of every kind a route can be, behind the middleware."""
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(ClientHeaderMiddleware, exempt=["/callback/apple"])

    @app.api_route("/on-app", methods=ALL_METHODS)
    def on_app() -> dict[str, bool]:
        return {"ok": True}

    router = APIRouter()

    @router.api_route("/on-router", methods=ALL_METHODS)
    def on_router() -> dict[str, bool]:
        return {"ok": True}

    # A plain Starlette route on a router. A router dependency never reaches one of these.
    router.add_route("/raw", raw, methods=ALL_METHODS)
    app.include_router(router, prefix="/api")
    app.add_route("/raw-on-app", raw, methods=ALL_METHODS)
    app.mount("/mounted", Starlette(routes=[Route("/thing", raw, methods=ALL_METHODS)]))
    app.router.routes.append(Mount("/plain", app=PlainTextResponse("plain")))
    app.add_route("/callback/{provider}", raw, methods=["GET", "POST"])
    app.add_route("/callback/{provider}/extra", raw, methods=["POST"])
    return app


PATHS = ["/on-app", "/api/on-router", "/api/raw", "/raw-on-app", "/mounted/thing", "/plain/anything"]


def test_the_methods_that_change_data() -> None:
    assert frozenset({"POST", "PUT", "PATCH", "DELETE"}) == MUTATING_METHODS


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("method", sorted(MUTATING_METHODS))
def test_requests_that_change_data_need_the_header_on_every_kind_of_route(
    csrf_app: FastAPI, path: str, method: str
) -> None:
    bare = TestClient(csrf_app, base_url=BASE_URL)
    refused = bare.request(method, path)
    assert refused.status_code == 403
    assert refused.json() == {
        "error": {
            "code": "client_header_required",
            "message": "Requests that change data must carry the X-FieldClub-Client header.",
        }
    }
    assert bare.request(method, path, headers={CLIENT_HEADER: "nope"}).status_code == 403
    assert bare.request(method, path, headers={CLIENT_HEADER: ""}).status_code == 403
    assert bare.request(method, path, headers=WEB).status_code == 200
    assert bare.request(method, path, headers={"x-fieldclub-client": "web"}).status_code == 200


@pytest.mark.parametrize("path", PATHS)
def test_reads_do_not_need_the_header(csrf_app: FastAPI, path: str) -> None:
    bare = TestClient(csrf_app, base_url=BASE_URL)
    assert bare.get(path).status_code == 200
    assert bare.head(path).status_code == 200
    assert bare.options(path).status_code == 200


def test_a_path_that_does_not_exist_is_refused_before_it_is_looked_up(csrf_app: FastAPI) -> None:
    bare = TestClient(csrf_app, base_url=BASE_URL)
    assert bare.post("/nowhere").status_code == 403
    assert bare.post("/nowhere", headers=WEB).status_code == 404
    assert bare.get("/nowhere").status_code == 404


def test_only_an_exempt_path_itself_is_exempt(csrf_app: FastAPI) -> None:
    bare = TestClient(csrf_app, base_url=BASE_URL)
    # A provider posting back to its callback can't send the header.
    assert bare.post("/callback/apple").status_code == 200
    # Exempt paths are paths, not patterns, so no other callback is.
    assert bare.post("/callback/google").status_code == 403
    assert bare.post("/callback/apple/extra").status_code == 403
    assert bare.post("/callback/apple/").status_code == 403
    assert bare.post("/callback/APPLE").status_code == 403
    assert bare.post("/x/callback/apple").status_code == 403
    assert bare.post("/on-app").status_code == 403


def test_nothing_is_exempt_by_default() -> None:
    assert ClientHeaderMiddleware(FastAPI()).exempt == frozenset()


def test_an_exempt_path_is_a_path_not_a_pattern() -> None:
    with pytest.raises(AssertionError, match="exact path"):
        ClientHeaderMiddleware(FastAPI(), exempt=[r"/callback/[a-z]+"])


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_an_exempt_path_is_exempt_for_post_only(csrf_app: FastAPI, method: str) -> None:
    # A provider only ever posts back. Nothing else may use the exemption.
    bare = TestClient(csrf_app, base_url=BASE_URL)
    assert bare.request(method, "/callback/apple").status_code == 403
    assert bare.post("/callback/apple").status_code == 200
