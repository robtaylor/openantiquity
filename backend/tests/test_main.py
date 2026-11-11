"""The app factory: router discovery, errors, health, the SPA fallback and the commands."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import fieldclub.api
from fieldclub import __version__, main
from fieldclub.config import get_settings
from fieldclub.errors import ConflictError, NotFoundError, RateLimitedError
from fieldclub.main import create_app, discover_routers, mount_frontend
from tests.helpers import BASE_URL, WEB

# --------------------------------------------------------------------------
# Router discovery
# --------------------------------------------------------------------------


def test_every_module_in_fieldclub_api_with_a_router_is_discovered() -> None:
    discovered = discover_routers()
    found = {item.module: item for item in discovered if not item.dev_only}
    assert {"auth", "meta"} <= set(found)
    assert "deps" not in found, "a module without a router is left alone"
    assert all(isinstance(item.router, APIRouter) for item in discovered)
    assert not found["meta"].at_root
    # The only routes kept apart for development are the auth module's.
    assert [item.module for item in discovered if item.dev_only] == ["auth"]


def test_routers_are_mounted_under_api_v1(client: TestClient) -> None:
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert {"/api/v1/meta", "/api/v1/auth/me", "/api/v1/auth/logout"} <= paths
    # Tile endpoints sit at the root so a CDN can cache them by path.
    assert all(path.startswith(("/api/v1/", "/tiles/")) for path in paths)
    assert client.get("/meta").status_code == 404


def test_dev_routers_are_mounted_only_for_the_development_login(db: Session) -> None:
    def paths(app: FastAPI) -> set[str]:
        return set(TestClient(app, base_url=BASE_URL).get("/api/openapi.json").json()["paths"])

    on = get_settings()
    off = on.model_copy(update={"dev_login": False})
    assert on.dev_login_enabled
    assert "/api/v1/auth/dev-login" in paths(create_app(on))
    assert "/api/v1/auth/dev-login" not in paths(create_app(off))
    assert "/api/v1/auth/dev-login" in paths(create_app(off, include_dev_routes=True))
    assert "/api/v1/auth/dev-login" not in paths(create_app(on, include_dev_routes=False))
    # Everything else is there either way.
    assert paths(create_app(on)) - paths(create_app(off)) == {"/api/v1/auth/dev-login"}


def test_a_warning_is_logged_when_the_development_login_is_on(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="fieldclub.main"):
        create_app(get_settings().model_copy(update={"dev_login": False}))
    assert caplog.records == []
    with caplog.at_level("WARNING", logger="fieldclub.main"):
        create_app()
    assert any("FIELDCLUB_DEV_LOGIN is on" in record.getMessage() for record in caplog.records)


@pytest.fixture
def extra_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Three more modules in fieldclub.api: a normal router, a root-mounted one, and one without a router."""
    (tmp_path / "zz_things.py").write_text(
        "from fastapi import APIRouter\n"
        "from fieldclub.errors import ConflictError\n"
        "router = APIRouter(tags=['things'])\n"
        "@router.get('/things')\n"
        "def list_things() -> list[str]:\n"
        "    return ['barrow']\n"
        "@router.post('/things')\n"
        "def create_thing() -> dict[str, bool]:\n"
        "    return {'created': True}\n"
        "@router.get('/things/clash')\n"
        "def clash() -> None:\n"
        "    raise ConflictError('Already there.', code='thing_exists')\n"
        "@router.get('/things/crash')\n"
        "def crash() -> None:\n"
        "    raise RuntimeError('secret internal detail')\n"
        "dev_router = APIRouter(tags=['things'])\n"
        "@dev_router.post('/things/reset')\n"
        "def reset_things() -> dict[str, bool]:\n"
        "    return {'reset': True}\n"
    )
    (tmp_path / "zz_tiles.py").write_text(
        "from fastapi import APIRouter\n"
        "from starlette.responses import Response\n"
        "MOUNT_AT_ROOT = True\n"
        "router = APIRouter(tags=['tiles'])\n"
        "@router.get('/tiles/test/{z}/{x}/{y}.png')\n"
        "def tile(z: int, x: int, y: int) -> Response:\n"
        "    return Response(b'png', media_type='image/png')\n"
        "@router.post('/tiles/purge')\n"
        "def purge() -> dict[str, bool]:\n"
        "    return {'purged': True}\n"
        "def raw_purge(request):\n"
        "    return Response(b'raw purge')\n"
        "router.add_route('/tiles/raw-purge', raw_purge, methods=['POST', 'DELETE'])\n"
    )
    (tmp_path / "zz_helpers.py").write_text("VALUE = 1\n")
    monkeypatch.setattr(fieldclub.api, "__path__", [*fieldclub.api.__path__, str(tmp_path)])
    yield
    for name in ("zz_things", "zz_tiles", "zz_helpers"):
        sys.modules.pop(f"fieldclub.api.{name}", None)


def test_new_router_modules_are_registered_without_touching_main(extra_modules: None, db: Session) -> None:
    found = {item.module: item.at_root for item in discover_routers()}
    assert found["zz_things"] is False
    assert found["zz_tiles"] is True
    assert "zz_helpers" not in found

    client = TestClient(create_app(), base_url=BASE_URL, headers=WEB)
    assert client.get("/api/v1/things").json() == ["barrow"]
    assert client.get("/things").status_code == 404

    tile = client.get("/tiles/test/14/8107/5448.png")
    assert (tile.status_code, tile.content, tile.headers["content-type"]) == (200, b"png", "image/png")
    assert client.get("/api/v1/tiles/test/14/8107/5448.png").status_code == 404

    paths = client.get("/api/openapi.json").json()["paths"]
    assert paths["/api/v1/things"]["get"]["operationId"] == "things_list_things"
    assert "/tiles/test/{z}/{x}/{y}.png" in paths


def test_every_router_refuses_mutations_without_the_client_header(extra_modules: None, db: Session) -> None:
    bare = TestClient(create_app(), base_url=BASE_URL)
    # The third is a plain Starlette route on a router, which a router
    # dependency would never have reached.
    for path in ("/api/v1/things", "/tiles/purge", "/tiles/raw-purge", "/api/v1/things/reset"):
        refused = bare.post(path)
        assert refused.status_code == 403, path
        assert refused.json()["error"]["code"] == "client_header_required"
        assert bare.post(path, headers=WEB).status_code == 200
    assert bare.delete("/tiles/raw-purge").status_code == 403
    assert bare.get("/api/v1/things").status_code == 200


def test_routes_declared_on_the_app_itself_need_the_client_header_too(db: Session) -> None:
    app = create_app()

    @app.post("/on-the-app")
    def on_the_app() -> dict[str, bool]:
        return {"ok": True}

    bare = TestClient(app, base_url=BASE_URL)
    refused = bare.post("/on-the-app")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "client_header_required"
    assert bare.post("/on-the-app", headers=WEB).status_code == 200


def test_a_modules_dev_router_is_left_out_unless_dev_routes_are_wanted(
    extra_modules: None, db: Session
) -> None:
    off = get_settings().model_copy(update={"dev_login": False})
    without = TestClient(create_app(off), base_url=BASE_URL, headers=WEB)
    assert without.post("/api/v1/things/reset").status_code == 404
    assert without.get("/api/v1/things").status_code == 200


def test_a_router_that_is_not_a_router_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "zz_broken.py").write_text("router = 'not a router'\n")
    monkeypatch.setattr(fieldclub.api, "__path__", [*fieldclub.api.__path__, str(tmp_path)])
    try:
        with pytest.raises(AssertionError, match="is not an APIRouter"):
            discover_routers()
    finally:
        sys.modules.pop("fieldclub.api.zz_broken", None)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


def test_app_errors_use_the_json_envelope(extra_modules: None, db: Session) -> None:
    client = TestClient(create_app(), base_url=BASE_URL)
    response = client.get("/api/v1/things/clash")
    assert response.status_code == 409
    assert response.json() == {"error": {"code": "thing_exists", "message": "Already there."}}


def test_unknown_api_paths_are_json_404s(client: TestClient) -> None:
    for path in ("/api/v1/nope", "/api/nope", "/tiles/nope/1/2/3.png", "/nope"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_wrong_method_is_a_json_405(client: TestClient) -> None:
    response = client.delete("/api/v1/meta")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_malformed_json_is_a_json_422(client: TestClient) -> None:
    client.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    response = client.patch(
        "/api/v1/auth/me", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unexpected_errors_are_a_plain_500_that_leaks_nothing(
    extra_modules: None, db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False)
    response = client.get("/api/v1/things/crash")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Something went wrong."}}
    assert "secret internal detail" not in response.text
    assert any(
        "secret internal detail" in str(record.exc_info) for record in caplog.records if record.exc_info
    )


def test_http_exceptions_keep_their_status_and_headers(db: Session) -> None:
    app = create_app()

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="Short and stout", headers={"X-Kind": "tea"})

    response = TestClient(app, base_url=BASE_URL).get("/teapot")
    assert response.status_code == 418
    assert response.json() == {"error": {"code": "http_error", "message": "Short and stout"}}
    assert response.headers["x-kind"] == "tea"


def test_error_classes_carry_status_code_and_details() -> None:
    assert NotFoundError().to_body() == {"error": {"code": "not_found", "message": "That doesn't exist."}}
    custom = ConflictError("Taken.", code="handle_taken", details={"field": "handle"})
    assert custom.status_code == 409
    assert custom.to_body() == {
        "error": {"code": "handle_taken", "message": "Taken.", "details": {"field": "handle"}}
    }
    assert str(custom) == "Taken."
    limited = RateLimitedError(retry_after_s=0.2)
    assert (limited.status_code, limited.headers) == (429, {"Retry-After": "1"})


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
    assert "/healthz" not in client.get("/api/openapi.json").json()["paths"]


def test_the_server_stops_within_seconds_even_with_a_request_open() -> None:
    from fieldclub.config import Settings

    # Cloud Run gives a stopping instance ten seconds before it kills it. The grace is how long
    # uvicorn waits for open requests, and the test of run() below checks it gets there.
    assert 0 < Settings.model_fields["shutdown_grace_s"].default < 10


# --------------------------------------------------------------------------
# The frontend
# --------------------------------------------------------------------------


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    built = tmp_path / "dist"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text("<!doctype html><title>Field Club</title><div id=root></div>")
    (built / "assets" / "index-abc123.js").write_text("console.log('app')")
    (built / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build")
    return built


@pytest.fixture
def spa(dist: Path, db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = get_settings().model_copy(update={"frontend_dist": dist})
    return TestClient(create_app(settings), base_url=BASE_URL, headers=WEB)


def test_nothing_is_served_when_the_frontend_is_not_built(client: TestClient, tmp_path: Path) -> None:
    assert mount_frontend(FastAPI(), tmp_path / "missing") is False
    assert client.get("/").status_code == 404
    assert client.get("/f/7K3QXM").status_code == 404


def test_index_is_served_at_the_root_and_must_be_revalidated(spa: TestClient) -> None:
    response = spa.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Field Club" in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "path", ["/f/7K3QXM", "/review", "/scan", "/u/QuietBarrow42", "/i/ABC123/", "/about"]
)
def test_client_side_routes_fall_back_to_index(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 200
    assert "<div id=root>" in response.text


def test_hashed_assets_are_cached_for_good(spa: TestClient) -> None:
    response = spa.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log('app')"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_other_real_files_are_served_as_they_are(spa: TestClient) -> None:
    response = spa.get("/favicon.svg")
    assert response.status_code == 200
    assert response.text == "<svg/>"
    assert response.headers["content-type"].startswith("image/svg")


@pytest.mark.parametrize("path", ["/assets/missing.js", "/missing.png", "/f/thing.json", "/robots.txt"])
def test_missing_files_are_404s_not_the_app(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("path", ["/api/v1/nope", "/api", "/api/", "/tiles/nope", "/tiles"])
def test_the_fallback_never_swallows_api_or_tile_paths(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"


def test_api_and_health_still_work_with_the_frontend_mounted(spa: TestClient) -> None:
    assert spa.get("/healthz").json()["status"] == "ok"
    assert spa.get("/api/v1/meta").json()["app"]["name"] == "Field Club"
    assert spa.post("/api/v1/auth/dev-login", json={"handle": "TestRob"}).status_code == 200
    assert spa.get("/api/v1/auth/me").json()["handle"] == "TestRob"
    assert spa.get("/api/openapi.json").status_code == 200


# What a request gets must not depend on whether the frontend has been built.
SAME_EITHER_WAY = [
    # An unknown path under the API or the tiles is a 404, whatever the method.
    ("POST", "/api/v1/nope", 404, "not_found"),
    ("PUT", "/api/v1/nope", 404, "not_found"),
    ("PATCH", "/api/v1/nope/ABC123", 404, "not_found"),
    ("DELETE", "/tiles/nope/1/2/3.png", 404, "not_found"),
    ("GET", "/api/v1/nope", 404, "not_found"),
    # A known path with the wrong method is a 405.
    ("DELETE", "/api/v1/meta", 405, "method_not_allowed"),
    ("POST", "/api/v1/meta", 405, "method_not_allowed"),
    ("GET", "/api/v1/auth/logout", 405, "method_not_allowed"),
    ("PUT", "/api/v1/auth/me", 405, "method_not_allowed"),
    ("POST", "/healthz", 405, "method_not_allowed"),
    # And the routes themselves still answer.
    ("GET", "/healthz", 200, None),
    ("GET", "/api/v1/meta", 200, None),
    ("POST", "/api/v1/auth/logout", 204, None),
]


@pytest.mark.parametrize(("method", "path", "status", "code"), SAME_EITHER_WAY)
def test_the_api_answers_the_same_with_and_without_a_built_frontend(
    client: TestClient, spa: TestClient, method: str, path: str, status: int, code: str | None
) -> None:
    without, mounted = client.request(method, path), spa.request(method, path)
    for name, response in (("no frontend", without), ("frontend mounted", mounted)):
        assert response.status_code == status, name
        if code is not None:
            assert response.headers["content-type"] == "application/json", name
            assert response.json()["error"]["code"] == code, name
    assert mounted.content == without.content, "the same body, byte for byte"
    assert mounted.headers.get("allow") == without.headers.get("allow")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/", "/f/7K3QXM", "/favicon.svg", "/about"])
def test_the_app_shell_is_never_served_for_a_request_that_changes_data(
    spa: TestClient, method: str, path: str
) -> None:
    response = spa.request(method, path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_the_fallback_works_below_a_root_path(dist: Path, db: Session) -> None:
    # Served behind a proxy that strips a prefix, the app is told its root path.
    settings = get_settings().model_copy(update={"frontend_dist": dist})
    browser = TestClient(create_app(settings), base_url=BASE_URL, root_path="/club")
    assert "<div id=root>" in browser.get("/club/f/7K3QXM").text
    assert browser.get("/club/favicon.svg").text == "<svg/>"
    assert browser.get("/club/api/v1/nope").status_code == 404
    assert browser.get("/club/healthz").json()["status"] == "ok"


def test_a_websocket_to_nowhere_is_closed_not_served_the_app(spa: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), spa.websocket_connect("/f/7K3QXM"):
        pass


def test_head_works_for_the_app_shell_and_its_files(spa: TestClient) -> None:
    shell = spa.head("/f/7K3QXM")
    assert shell.status_code == 200
    assert shell.headers["cache-control"] == "no-cache"
    assert shell.content == b""
    assert spa.head("/favicon.svg").status_code == 200
    assert spa.head("/api/v1/nope").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/%00",
        "/f/%00",
        "/favicon.svg%00",
        "/" + "a" * 256,
        "/f/" + "a" * 5000,
        "/" + "a/" * 2000 + "b",
        "/%ff%fe",
    ],
)
def test_paths_the_file_system_cannot_look_up_are_404s_not_errors(
    dist: Path, db: Session, path: str, caplog: pytest.LogCaptureFixture
) -> None:
    settings = get_settings().model_copy(update={"frontend_dist": dist})
    # Server errors are re-raised by this client, so a 500 fails the test outright.
    browser = TestClient(create_app(settings), base_url=BASE_URL)
    response = browser.get(path)
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        assert "<div id=root>" in response.text
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


def test_a_nul_or_an_overlong_name_is_a_404(spa: TestClient) -> None:
    for path in ("/%00", "/" + "a" * 256, "/f/" + "a" * 5000):
        response = spa.get(path)
        assert response.status_code == 404, path[:20]
        assert response.json()["error"]["code"] == "not_found"
    assert spa.get("/" + "a" * 255).status_code == 200, "the longest name a file system allows"


@pytest.mark.parametrize(
    "path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt", "//etc/passwd"]
)
def test_paths_cannot_escape_the_build_directory(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert "outside the build" not in response.text
    assert "root:" not in response.text


# --------------------------------------------------------------------------
# Start-up and the commands
# --------------------------------------------------------------------------


def test_startup_builds_the_schema_only_when_asked(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(main, "create_schema", lambda: calls.append(1))

    with TestClient(create_app(), base_url=BASE_URL) as client:
        assert client.get("/healthz").status_code == 200
    assert calls == [], "the test environment does not build the schema at start-up"

    monkeypatch.setattr(
        main, "get_settings", lambda: get_settings().model_copy(update={"auto_create_schema": True})
    )
    with TestClient(create_app(), base_url=BASE_URL) as client:
        assert client.get("/healthz").status_code == 200
    assert calls == [1]


def test_print_openapi_writes_the_schema_as_json(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    main.print_openapi()
    schema = json.loads(capsys.readouterr().out)
    assert schema["info"]["title"] == "Field Club"
    assert schema["info"]["version"] == __version__
    assert "/api/v1/meta" in schema["paths"]
    assert "Meta" in schema["components"]["schemas"]


def test_fieldclub_openapi_command_needs_no_database() -> None:
    env = {
        "FIELDCLUB_DATABASE_URL": "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        "FIELDCLUB_ENV_FILE": "",
    }
    import os

    result = subprocess.run(
        ["fieldclub-openapi"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(result.stdout)
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/auth/me" in schema["paths"]
    assert "/api/v1/auth/guest" not in schema["paths"]


@pytest.mark.parametrize("dev_login", ["true", "false"])
def test_the_printed_schema_is_the_same_whatever_the_settings(dev_login: str) -> None:
    # The frontend generates its client from this, so it must not change with
    # the machine it is run on. The development login is always in it.
    import os

    env = {
        "FIELDCLUB_DATABASE_URL": "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        "FIELDCLUB_ENV_FILE": "",
        "FIELDCLUB_ENV": "dev",
        "FIELDCLUB_DEV_LOGIN": dev_login,
    }
    result = subprocess.run(
        ["fieldclub-openapi"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, result.stderr
    paths = json.loads(result.stdout)["paths"]
    assert "/api/v1/auth/dev-login" in paths
    assert {"get", "patch", "delete"} == set(paths["/api/v1/auth/me"])


def test_run_starts_uvicorn_with_the_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict = {}
    fake = types.ModuleType("uvicorn")

    class Config:
        def __init__(self, app: str, **options: object) -> None:
            started.update(app=app, **options)

    class Server:
        def __init__(self, config: Config) -> None:
            self.config = config

        def run(self) -> None:
            started["ran"] = True
            started["server"] = self

        async def shutdown(self, sockets: object = None) -> None:
            started["shut_down"] = True

    fake.Config = Config  # type: ignore[attr-defined]
    fake.Server = Server  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    monkeypatch.setattr(main.logging, "basicConfig", lambda **options: None)
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: get_settings().model_copy(update={"host": "0.0.0.0", "port": 8080, "shutdown_grace_s": 7}),
    )

    main.run()
    assert (started["app"], started["factory"]) == ("fieldclub.main:create_app", True)
    assert (started["host"], started["port"]) == ("0.0.0.0", 8080)
    assert started["proxy_headers"] is False
    assert started["timeout_graceful_shutdown"] == 7
    assert started["ran"] is True

    # Uvicorn's own shutdown runs even if ending the event streams fails.
    async def failing_stop() -> None:
        raise RuntimeError("the hub went wrong")

    monkeypatch.setattr(main.events, "stop_hub", failing_stop)
    with pytest.raises(RuntimeError, match="the hub went wrong"):
        asyncio.run(started["server"].shutdown())
    assert started["shut_down"] is True
