"""The application factory and the `fieldclub-api` and `fieldclub-openapi` commands."""

from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import socket
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import fieldclub.api
from fieldclub import APP_NAME, __version__, http, request_ids, safe_fetch, security
from fieldclub.api.deps import PRIVATE_CACHE
from fieldclub.auth.csrf import ClientHeaderMiddleware
from fieldclub.auth.oauth import FORM_POST_CALLBACK_PATHS
from fieldclub.config import Environment, Settings, get_settings
from fieldclub.db import create_schema, describe
from fieldclub.errors import install_error_handlers
from fieldclub.redirects import CanonicalHostMiddleware
from fieldclub.services import events

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
DOCS_URL = "/api/docs"
OPENAPI_URL = "/api/openapi.json"

# Paths the single-page app never owns. An unknown URL under one of these is a
# JSON 404, not the app's index.html.
RESERVED_ROOTS = frozenset({"api", "tiles", "healthz", "assets"})


# The paths that take a POST without the client header: exactly the OAuth
# callbacks a provider reaches with a cross-site POST (Apple's), which `state`
# protects instead. See fieldclub.auth.csrf and fieldclub.auth.flow.
CLIENT_HEADER_EXEMPT: frozenset[str] = frozenset(FORM_POST_CALLBACK_PATHS)


# Sent on any response that sets a cookie.
NO_STORE = "private, no-store"


def _varies_by_cookie(headers: MutableHeaders) -> bool:
    """Whether `Vary` already names `Cookie`, as `deps.private` sets it, so it isn't added twice."""
    names = (name.strip().lower() for line in headers.getlist("vary") for name in line.split(","))
    return "cookie" in names


class PrivateByDefaultMiddleware:
    """Send a response that says nothing about caching as `private, no-cache`, varying by cookie.

    Most API answers depend on who is asking: a position (Decision 0005),
    whether answers show (Decision 0008), a hidden finding a moderator can
    open. A route that forgets `deps.private` must not let a shared cache hand
    one viewer's answer to another, so private is the default and a route that
    is the same for everyone, such as a tile, says so with its own
    `Cache-Control`. Every private response varies by cookie.

    A response that sets a cookie is never stored by anyone, whatever the
    route said: a shared cache that kept a public answer carrying a
    refreshed session cookie would hand that session to the next visitor.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "set-cookie" in headers:
                    headers["Cache-Control"] = NO_STORE
                headers.setdefault("Cache-Control", PRIVATE_CACHE)
                if headers["Cache-Control"].startswith("private") and not _varies_by_cookie(headers):
                    headers.add_vary_header("Cookie")
            await send(message)

        await self.app(scope, receive, send_with_policy)


@dataclass(frozen=True)
class DiscoveredRouter:
    module: str
    router: APIRouter
    at_root: bool
    # True for a module's `dev_router`, which is mounted only for the development login.
    dev_only: bool = False


def discover_routers() -> list[DiscoveredRouter]:
    """Import every module in `fieldclub.api` and collect the routers they expose.

    A module's `router` is always mounted. Its `dev_router`, if it has one,
    holds routes that must not exist in production.
    """
    found: list[DiscoveredRouter] = []
    for info in sorted(pkgutil.iter_modules(fieldclub.api.__path__), key=lambda module: module.name):
        module = importlib.import_module(f"{fieldclub.api.__name__}.{info.name}")
        at_root = bool(getattr(module, "MOUNT_AT_ROOT", False))
        for attribute, dev_only in (("router", False), ("dev_router", True)):
            router = getattr(module, attribute, None)
            if router is None:
                continue
            assert isinstance(router, APIRouter), f"fieldclub.api.{info.name}.{attribute} is not an APIRouter"
            found.append(DiscoveredRouter(info.name, router, at_root, dev_only))
    return found


def _operation_id(route: APIRoute) -> str:
    """Short, stable operation ids such as `auth_get_me` for the generated client."""
    tag = str(route.tags[0]) if route.tags else "api"
    return f"{tag}_{route.name}"


def _look_at_the_mirror() -> None:
    """List the elevation mirror once at start-up. It never stops the server.

    A server that can't add tiles then says in the log from the start which
    tiles the mirror lacks (`terrain/overview.py`). It runs on a thread of its
    own, so a slow bucket can't keep the server from answering.
    """
    # Imported here, so that importing this module alone loads no GDAL.
    from fieldclub.terrain import service

    try:
        service.get_terrain().overview.mirrored()
    except Exception:
        logger.exception("Couldn't look at the mirror at start-up")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Imported here, so that importing this module alone loads no GDAL.
    from fieldclub.terrain.blobs import configure_gdal_for_s3

    settings = get_settings()
    # Before any other thread is started: GDAL reads these from the process's environment.
    configure_gdal_for_s3()
    if settings.should_create_schema:
        await run_in_threadpool(create_schema)
    if not settings.terrain_api_fetch:
        threading.Thread(target=_look_at_the_mirror, name="mirror-look", daemon=True).start()
    try:
        yield
    finally:
        # Imported here, so that importing this module alone loads no GDAL.
        from fieldclub.terrain.service import close_terrain

        await events.stop_hub()
        http.close_client()
        safe_fetch.close_client()
        close_terrain()


class _HashedAssets(StaticFiles):
    """Vite names build assets by content hash, so they can be cached for good."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return response


def _route_path(scope: Scope) -> str:
    """The request path below wherever the app is mounted."""
    path: str = scope["path"]
    root: str = scope.get("root_path", "")
    if root and path.startswith(root + "/"):
        return path[len(root) :]
    return path


class _SpaFallback:
    """What the router does when no route matches, once the frontend is built.

    It takes the place of the router's 404, so it only ever sees a request
    that nothing else wanted. Routing is therefore the same with and without
    a built frontend: a known path with the wrong method is still a 405, and
    an unknown path that isn't the app's is still a 404.
    """

    def __init__(self, dist: Path, not_found: ASGIApp) -> None:
        self.dist = dist
        self.index = dist / "index.html"
        self.not_found = not_found

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = None
        if scope["type"] == "http":
            response = await run_in_threadpool(self.find, scope["method"].upper(), _route_path(scope))
        if response is None:
            # The same 404 the router gives without a frontend.
            await self.not_found(scope, receive, send)
            return
        await response(scope, receive, send)

    def find(self, method: str, route_path: str) -> Response | None:
        """The file or the app shell to answer with, or None when the path isn't the app's."""
        path = route_path.lstrip("/")
        first, _, _ = path.partition("/")
        if method not in ("GET", "HEAD") or first in RESERVED_ROOTS:
            return None
        try:
            candidate = (self.dist / path).resolve()
            is_file = bool(path) and candidate.is_relative_to(self.dist) and candidate.is_file()
        except (ValueError, OSError):
            # A NUL in the path, or a name too long for the file system.
            return None
        if is_file:
            return FileResponse(candidate)
        if "." in path.rsplit("/", 1)[-1]:
            # It looks like a file and there isn't one. Sending HTML in its
            # place would hide a broken link.
            return None
        # The entry page must be revalidated, or a deploy would leave browsers
        # pointing at asset hashes that no longer exist.
        return FileResponse(self.index, headers={"Cache-Control": "no-cache"})


def mount_frontend(app: FastAPI, dist: Path) -> bool:
    """Serve the built single-page app from `dist`, if it has been built.

    Real files are served as they are. Every other path that no route claims
    gets `index.html`, so a deep link such as `/f/7K3QXM` loads the app and
    the app's router takes over. Returns whether anything was mounted.
    """
    index = dist / "index.html"
    if not index.is_file():
        return False
    dist = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", _HashedAssets(directory=dist / "assets"), name="assets")
    app.router.default = _SpaFallback(dist, app.router.default)
    logger.info("Serving the frontend from %s", dist)
    return True


def create_app(settings: Settings | None = None, *, include_dev_routes: bool | None = None) -> FastAPI:
    """Build the FastAPI app.

    Routers are found by `discover_routers()`. Each is mounted under `/api/v1`,
    or at the root when its module sets `MOUNT_AT_ROOT = True`. A request that
    changes data is refused on every path unless it carries the
    `X-OpenAntiquity-Client` header.

    `include_dev_routes` says whether `dev_router`s are mounted, which today
    means `POST /auth/dev-login`. Left as None it follows the settings: only
    with `FIELDCLUB_DEV_LOGIN` on, and never in production.
    """
    settings = settings or get_settings()
    if include_dev_routes is None:
        include_dev_routes = settings.dev_login_enabled
    # The interactive docs load their scripts from a CDN, so they never run on the
    # production origin, where a signed-in visitor's session would be theirs. The
    # schema stays off with them: `fieldclub-openapi` writes it for the frontend.
    is_prod = settings.env is Environment.PROD
    # Refuses to serve without the key that signs sign-ins, which only the API needs.
    settings.require_signing_key()
    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        summary="A collaborative map for finding and checking archaeological earthworks in UK LIDAR data.",
        docs_url=None if is_prod else DOCS_URL,
        redoc_url=None,
        openapi_url=None if is_prod else OPENAPI_URL,
        swagger_ui_oauth2_redirect_url=None if is_prod else f"{DOCS_URL}/oauth2-redirect",
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    # Middleware, not router dependencies, so that no route can be added without them.
    # The last added runs first: the headers go on every answer, the body limit
    # included, and the body limit runs before anything reads a body.
    app.add_middleware(security.BodyLimitMiddleware)
    app.add_middleware(ClientHeaderMiddleware, exempt=CLIENT_HEADER_EXEMPT)
    app.add_middleware(PrivateByDefaultMiddleware)
    if settings.redirect_hosts:
        # Added after everything that reads the request, so another name gets its redirect and nothing else.
        app.add_middleware(CanonicalHostMiddleware, hosts=settings.redirect_hosts, target=settings.public_url)
    https = settings.public_url.startswith("https://")
    index = settings.frontend_dist / "index.html"
    # Added after the rest, so it runs before them: its headers go on every response, a redirect from another
    # name included.
    app.add_middleware(
        security.SecurityHeadersMiddleware,
        policy=security.content_security_policy(index if index.is_file() else None, https),
        https=https,
        # The development docs page loads Swagger UI from its CDN, which the policy refuses.
        exempt=frozenset(path for path in (app.docs_url, app.swagger_ui_oauth2_redirect_url) if path),
    )
    # Outermost of all, so that every answer above carries the request's id
    # and every line they log is written with it (`request_ids.py`).
    app.add_middleware(request_ids.RequestIdMiddleware)

    for found in discover_routers():
        if found.dev_only and not include_dev_routes:
            continue
        app.include_router(found.router, prefix="" if found.at_root else API_PREFIX)
    if include_dev_routes and settings.dev_login_enabled:
        logger.warning(
            "FIELDCLUB_DEV_LOGIN is on: POST %s/auth/dev-login signs anyone in as anyone. "
            "Never set it on a server other people can reach.",
            API_PREFIX,
        )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    # Last, because it takes over what would otherwise be a 404.
    mount_frontend(app, settings.frontend_dist)
    return app


def run() -> None:
    """`fieldclub-api`: serve the app with uvicorn."""
    import uvicorn

    class Server(uvicorn.Server):
        async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
            # Uvicorn waits for open responses before the lifespan ends, and an
            # event stream never finishes by itself, so end the streams first.
            try:
                await events.stop_hub()
            finally:
                await super().shutdown(sockets)

    settings = get_settings()
    # One handler for every logger, uvicorn's included, and on it the filter
    # that writes the request's id into each line (`request_ids.py`).
    handler = logging.StreamHandler()
    handler.addFilter(request_ids.RequestIdFilter())
    logging.basicConfig(level=settings.log_level, format=request_ids.LOG_FORMAT, handlers=[handler])
    logger.info("The database is %s", describe(settings.database_url))
    config = uvicorn.Config(
        "fieldclub.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        # Uvicorn's own configuration would give its loggers handlers of their
        # own without the filter. Without one they write through the handler above.
        log_config=None,
        # The client address comes from X-Forwarded-For under our own rules
        # (see fieldclub.auth.deps.client_ip), not uvicorn's.
        proxy_headers=False,
        # Without a limit uvicorn waits for every open connection after SIGTERM,
        # so one long request would hold each shutdown until the platform kills
        # the process.
        timeout_graceful_shutdown=settings.shutdown_grace_s,
    )
    Server(config).run()


def print_openapi() -> None:
    """`fieldclub-openapi`: write the OpenAPI schema to stdout, for the frontend's type generation.

    The development-only routes are always in it, whatever the settings, so
    that the generated client is the same on every machine. The schema served
    at `/api/openapi.json` lists only what that server really has.
    """
    schema = create_app(include_dev_routes=True).openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
