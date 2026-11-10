"""The application factory and the `fieldclub-api` and `fieldclub-openapi` commands."""

from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import sys
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
from fieldclub import APP_NAME, __version__, http
from fieldclub.api.deps import PRIVATE_CACHE
from fieldclub.auth.csrf import ClientHeaderMiddleware
from fieldclub.auth.oauth import FORM_POST_CALLBACK_PATHS
from fieldclub.config import Settings, get_settings
from fieldclub.db import create_schema
from fieldclub.errors import install_error_handlers

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

# Paths the single-page app never owns. An unknown URL under one of these is a
# JSON 404, not the app's index.html.
RESERVED_ROOTS = frozenset({"api", "tiles", "healthz", "assets"})


# The paths that take a POST without the client header: exactly the OAuth
# callbacks a provider reaches with a cross-site POST (Apple's), which `state`
# protects instead. See fieldclub.auth.csrf and fieldclub.auth.flow.
CLIENT_HEADER_EXEMPT: frozenset[str] = frozenset(FORM_POST_CALLBACK_PATHS)


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


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.should_create_schema:
        await run_in_threadpool(create_schema)
    try:
        yield
    finally:
        http.close_client()


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
    `X-FieldClub-Client` header.

    `include_dev_routes` says whether `dev_router`s are mounted, which today
    means `POST /auth/dev-login`. Left as None it follows the settings: only
    with `FIELDCLUB_DEV_LOGIN` on, and never in production.
    """
    settings = settings or get_settings()
    if include_dev_routes is None:
        include_dev_routes = settings.dev_login_enabled
    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        summary="A collaborative map for finding and checking archaeological earthworks in UK LIDAR data.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    # Middleware, not router dependencies, so that no route can be added without them.
    app.add_middleware(ClientHeaderMiddleware, exempt=CLIENT_HEADER_EXEMPT)
    app.add_middleware(PrivateByDefaultMiddleware)

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

    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "fieldclub.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        # The client address comes from X-Forwarded-For under our own rules
        # (see fieldclub.auth.deps.client_ip), not uvicorn's.
        proxy_headers=False,
    )


def print_openapi() -> None:
    """`fieldclub-openapi`: write the OpenAPI schema to stdout, for the frontend's type generation.

    The development-only routes are always in it, whatever the settings, so
    that the generated client is the same on every machine. The schema served
    at `/api/openapi.json` lists only what that server really has.
    """
    schema = create_app(include_dev_routes=True).openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
