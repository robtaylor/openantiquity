"""Every route the app serves, with what is expected of it, so none can be added without saying.

`ROUTES` names each route by method and path, as the app lists them, with:

- `leak_test`: the test that calls it as every kind of viewer against every
  sensitivity level, when the route returns a finding or anything derived
  from a finding's position (Decision 0005). None when it returns neither.
  A bare name is a test in `tests/findings/test_leaks.py`. A test in
  another module is named in full, as `tests.activity.test_leaks:test_the_feed`.
- `writer`: for a route that changes data, `CONTRIBUTOR` when it stores a
  contribution and so needs the welcome step (Decision 0009), or why it
  doesn't. None for a read.
- `sample`: an address to call it at, for the cache check. `{finding}`,
  `{record}` and `{investigation}` are filled in with ones the test makes,
  the investigation public. A read that says
  nothing about caching is sent private (`main.PrivateByDefaultMiddleware`).
  One sent as publicly cacheable must give a signed-in member exactly what it
  gives a signed-out visitor.

The tests fail when the app has a route this table doesn't list, so a new
route has to come with its expectations. Add its row here, and its leak test
if it carries a position.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.routing import Mount, Route, WebSocketRoute

from fieldclub.auth.deps import current_contributor
from fieldclub.main import create_app, mount_frontend
from fieldclub.services import record_tiles
from fieldclub.vocab import Visibility
from tests.findings import test_leaks
from tests.findings.support import create
from tests.helpers import MakeUser, add_record, add_source
from tests.investigations.support import make

CONTRIBUTOR = "contributor"
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MENTIONS = "tests.mentions.test_recent:"


@dataclass(frozen=True)
class Expect:
    leak_test: str | None = None
    writer: str | None = None
    # `{finding}`, `{record}`, `{person}` and `{investigation}` are filled in with ones the test makes.
    sample: str | None = None
    # Why there is no sample, when there isn't one for a read.
    unsampled: str | None = None


F = "/api/v1/findings/{finding}"
OWN_ACCOUNT = "changes only the caller's own account, which needs no welcome step"
SIGN_IN = "signs someone in, before any welcome step"
NOT_STORED = "stores nothing: a read that needs a body"
NEEDS_MIRROR = "needs a mirror: tests/terrain/test_api.py checks its caching"
ACTIVITY_LEAKS = "tests.activity.test_leaks:"
U = "/api/v1/users/{person}"
INV = "/api/v1/investigations/{investigation}"
INVESTIGATION_LEAKS = "tests.investigations.test_leaks:"
ITEMS_SHOWN = INVESTIGATION_LEAKS + "test_items_show_what_the_page_shows"
ITEM_WRITES = INVESTIGATION_LEAKS + "test_item_writes_answer_with_what_the_writer_may_see"

ROUTES: dict[tuple[str, str], Expect] = {
    # Accounts
    ("GET", "/api/v1/auth/me"): Expect(sample="/api/v1/auth/me"),
    ("PATCH", "/api/v1/auth/me"): Expect(writer=OWN_ACCOUNT + "; a bio checks it itself"),
    ("DELETE", "/api/v1/auth/me"): Expect(writer=OWN_ACCOUNT),
    ("POST", "/api/v1/auth/welcome"): Expect(writer="is the welcome step"),
    ("POST", "/api/v1/auth/logout"): Expect(writer=OWN_ACCOUNT),
    ("GET", "/api/v1/auth/handle-suggestion"): Expect(sample="/api/v1/auth/handle-suggestion"),
    ("GET", "/api/v1/auth/oauth/{provider}/start"): Expect(unsampled="a redirect, tested in tests/auth"),
    ("GET", "/api/v1/auth/oauth/{provider}/callback"): Expect(unsampled="a redirect, tested in tests/auth"),
    ("POST", "/api/v1/auth/oauth/{provider}/callback"): Expect(writer=SIGN_IN),
    ("POST", "/api/v1/auth/email/start"): Expect(writer=SIGN_IN),
    ("POST", "/api/v1/auth/email/verify"): Expect(writer=SIGN_IN),
    ("POST", "/api/v1/auth/dev-login"): Expect(writer=SIGN_IN),
    # Findings
    ("GET", "/api/v1/findings"): Expect("test_lists_and_the_map", sample="/api/v1/findings"),
    ("POST", "/api/v1/findings"): Expect("test_writes_answer_with_what_the_writer_may_see", CONTRIBUTOR),
    ("GET", "/api/v1/findings/export"): Expect(
        "test_downloads_of_a_filtered_set", sample="/api/v1/findings/export"
    ),
    ("GET", "/api/v1/findings/{public_id}"): Expect("test_a_finding_page", sample=F),
    ("PATCH", "/api/v1/findings/{public_id}"): Expect("test_a_finding_page", CONTRIBUTOR),
    ("POST", "/api/v1/findings/{public_id}/withdraw"): Expect("test_a_finding_page", CONTRIBUTOR),
    ("PUT", "/api/v1/findings/{public_id}/sensitivity"): Expect("test_a_finding_page", CONTRIBUTOR),
    ("GET", "/api/v1/findings/{public_id}/export"): Expect(
        "test_downloads_of_one_finding", sample=F + "/export"
    ),
    # Second looks
    ("PUT", "/api/v1/findings/{public_id}/observation"): Expect(
        "test_writes_answer_with_what_the_writer_may_see", CONTRIBUTOR
    ),
    ("DELETE", "/api/v1/findings/{public_id}/observation"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/findings/{public_id}/observations"): Expect(
        "test_comments_and_answers_carry_no_position", sample=F + "/observations"
    ),
    ("GET", "/api/v1/review/next"): Expect(
        "test_review_cards_are_only_for_findings_the_viewer_sees_exactly", sample="/api/v1/review/next"
    ),
    ("GET", "/api/v1/review/tasks"): Expect("test_help_wanted", sample="/api/v1/review/tasks"),
    # Evidence
    ("POST", "/api/v1/findings/{public_id}/evidence"): Expect(
        "test_writes_answer_with_what_the_writer_may_see", CONTRIBUTOR
    ),
    ("DELETE", "/api/v1/evidence/{evidence_id}"): Expect(writer=CONTRIBUTOR),
    ("PUT", "/api/v1/evidence/{evidence_id}/vote"): Expect(writer=CONTRIBUTOR),
    ("POST", "/api/v1/evidence/{evidence_id}/verify"): Expect("test_a_finding_page", CONTRIBUTOR),
    # Discussion
    ("GET", "/api/v1/findings/{public_id}/comments"): Expect(
        "test_comments_and_answers_carry_no_position", sample=F + "/comments"
    ),
    ("POST", "/api/v1/findings/{public_id}/comments"): Expect(
        "test_writes_answer_with_what_the_writer_may_see", CONTRIBUTOR
    ),
    ("DELETE", "/api/v1/comments/{comment_id}"): Expect(writer=CONTRIBUTOR),
    ("PUT", "/api/v1/findings/{public_id}/follow"): Expect(writer=CONTRIBUTOR),
    ("DELETE", "/api/v1/findings/{public_id}/follow"): Expect(writer=CONTRIBUTOR),
    # Investigations
    ("GET", "/api/v1/investigations"): Expect(sample="/api/v1/investigations"),
    ("POST", "/api/v1/investigations"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/investigations/{public_id}"): Expect(sample=INV),
    ("PATCH", "/api/v1/investigations/{public_id}"): Expect(writer=CONTRIBUTOR),
    ("DELETE", "/api/v1/investigations/{public_id}"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/investigations/{public_id}/items"): Expect(ITEMS_SHOWN, sample=INV + "/items"),
    ("POST", "/api/v1/investigations/{public_id}/items"): Expect(ITEM_WRITES, CONTRIBUTOR),
    ("PATCH", "/api/v1/investigations/{public_id}/items/{item_id}"): Expect(ITEM_WRITES, CONTRIBUTOR),
    ("POST", "/api/v1/investigations/{public_id}/items/{item_id}/move"): Expect(ITEM_WRITES, CONTRIBUTOR),
    ("DELETE", "/api/v1/investigations/{public_id}/items/{item_id}"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/investigations/{public_id}/members"): Expect(sample=INV + "/members"),
    ("PUT", "/api/v1/investigations/{public_id}/members/{handle}"): Expect(writer=CONTRIBUTOR),
    ("DELETE", "/api/v1/investigations/{public_id}/members/{handle}"): Expect(
        writer="removes a membership and stores nothing, so leaving or declining needs only a session"
    ),
    ("POST", "/api/v1/investigations/{public_id}/invitation"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/investigations/{public_id}/export"): Expect(
        INVESTIGATION_LEAKS + "test_downloads_follow_the_download_rule", sample=INV + "/export"
    ),
    # Scan a square
    ("GET", "/api/v1/squares/next"): Expect(sample="/api/v1/squares/next?lon=-1.85&lat=51.43"),
    ("PUT", "/api/v1/squares/{ref}"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/squares/coverage"): Expect(sample="/api/v1/squares/coverage?bbox=-1.9,51.4,-1.8,51.45"),
    # Mentions
    ("GET", "/api/v1/findings/{public_id}/mentions"): Expect(
        MENTIONS + "test_a_findings_own_list_carries_no_position", sample=F + "/mentions"
    ),
    ("POST", "/api/v1/findings/{public_id}/mentions"): Expect(writer=CONTRIBUTOR),
    ("DELETE", "/api/v1/mentions/{mention_id}"): Expect(writer=CONTRIBUTOR),
    # Stores nothing, but makes the server fetch an address a member typed.
    ("POST", "/api/v1/mentions/preview"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/mentions/recent"): Expect(
        MENTIONS + "test_the_feed_shows_each_position_as_the_viewer_may_see_it",
        sample="/api/v1/mentions/recent",
    ),
    # Records
    ("GET", "/api/v1/records/search"): Expect(sample="/api/v1/records/search?q=barrow"),
    ("GET", "/api/v1/records/nearby"): Expect(sample="/api/v1/records/nearby?lon=-1.85&lat=51.43"),
    ("GET", "/api/v1/records/{record_id}"): Expect(sample="/api/v1/records/{record}"),
    ("GET", "/api/v1/sources"): Expect(sample="/api/v1/sources"),
    ("GET", "/api/v1/findings/{public_id}/suggested-records"): Expect(
        "test_suggested_records", sample=F + "/suggested-records"
    ),
    ("GET", "/tiles/records/{z}/{x}/{y}.mvt"): Expect(sample="/tiles/records/0/0/0.mvt"),
    # Context and geography
    ("GET", "/api/v1/context/live-sources"): Expect(sample="/api/v1/context/live-sources"),
    ("GET", "/api/v1/context/links"): Expect(sample="/api/v1/context/links?lon=-1.85&lat=51.43"),
    ("GET", "/api/v1/geo/search"): Expect(
        "test_the_search_box_flies_to_what_the_viewer_may_see", sample="/api/v1/geo/search?q={finding}"
    ),
    ("GET", "/api/v1/geo/point"): Expect(sample="/api/v1/geo/point?lon=-1.85&lat=51.43"),
    ("GET", "/api/v1/meta"): Expect(sample="/api/v1/meta"),
    # Terrain
    ("POST", "/api/v1/terrain/profile"): Expect(writer=NOT_STORED),
    ("GET", "/api/v1/terrain/coverage"): Expect(sample="/api/v1/terrain/coverage?bbox=-1.9,51.4,-1.8,51.45"),
    ("GET", "/tiles/lidar/{style}/{z}/{x}/{y}.png"): Expect(unsampled=NEEDS_MIRROR),
    ("GET", "/tiles/dem/{z}/{x}/{y}.png"): Expect(unsampled=NEEDS_MIRROR),
    # People
    ("GET", "/api/v1/users/{handle}"): Expect(
        ACTIVITY_LEAKS + "test_profiles_findings_and_contributions", sample=U
    ),
    ("GET", "/api/v1/users/{handle}/findings"): Expect(
        ACTIVITY_LEAKS + "test_profiles_findings_and_contributions", sample=U + "/findings"
    ),
    ("GET", "/api/v1/users/{handle}/contributions"): Expect(
        ACTIVITY_LEAKS + "test_profiles_findings_and_contributions", sample=U + "/contributions"
    ),
    ("GET", "/api/v1/users/{handle}/points"): Expect(ACTIVITY_LEAKS + "test_points", sample=U + "/points"),
    # Activity
    ("GET", "/api/v1/activity"): Expect(ACTIVITY_LEAKS + "test_the_feed", sample="/api/v1/activity"),
    ("GET", "/api/v1/notifications"): Expect(
        ACTIVITY_LEAKS + "test_notifications", sample="/api/v1/notifications"
    ),
    ("POST", "/api/v1/notifications/read"): Expect(writer=CONTRIBUTOR),
    ("GET", "/api/v1/events/stream"): Expect(
        ACTIVITY_LEAKS + "test_stream_payloads_carry_no_position",
        unsampled="a stream that stays open: tests/activity/test_events.py checks it is sent no-cache",
    ),
    # The app itself
    ("GET", "/healthz"): Expect(sample="/healthz"),
}


def framework_paths(app: FastAPI) -> set[str]:
    """The pages FastAPI adds for itself: the schema and the interactive docs."""
    paths = {app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url}
    return {path for path in paths if path is not None}


def app_routes(app: FastAPI) -> Iterator[tuple[str, str, APIRoute]]:
    """Every method and path the app routes to a FastAPI endpoint, wherever its router is mounted.

    Anything else the app routes to fails the walk, so a plain Starlette route,
    a mount or a WebSocket can't slip past `ROUTES`. The exceptions are
    FastAPI's own pages and the built frontend's static files.
    """
    allowed = framework_paths(app)
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if not isinstance(route, APIRoute):
            path = getattr(route, "path", None)
            known_page = type(route) is Route and path in allowed
            static = isinstance(route, Mount) and isinstance(route.app, StaticFiles)
            kind = type(route).__name__
            assert known_page or static, f"{kind} {path} isn't a FastAPI route, so ROUTES can't check it"
            continue
        assert context.path is not None, f"{route.name} has no path"
        assert context.methods, f"{route.name} has no methods"
        for method in sorted(context.methods - {"HEAD"}):
            yield method, context.path, route


def test_the_walk_refuses_a_route_it_cannot_check(tmp_path: Path) -> None:
    async def stream(request: Any) -> Any:
        raise AssertionError("never called")

    for add in (
        lambda app: app.add_route("/api/v1/events/stream", stream),
        lambda app: app.router.routes.append(WebSocketRoute("/api/v1/live", stream)),
        lambda app: app.mount("/elsewhere", create_app()),
    ):
        app = create_app()
        add(app)
        with pytest.raises(AssertionError, match="isn't a FastAPI route"):
            list(app_routes(app))
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html>")
    built = create_app()
    assert mount_frontend(built, tmp_path)
    assert {path for _, path, _ in app_routes(built)} == {path for _, path, _ in app_routes(create_app())}


@pytest.fixture(scope="module")
def every_route() -> dict[tuple[str, str], APIRoute]:
    routes = {
        (method, path): route for method, path, route in app_routes(create_app(include_dev_routes=True))
    }
    assert len(routes) > 40, "the walk found too few routes to be looking in the right place"
    return routes


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def test_every_route_the_app_serves_has_a_stated_expectation(
    every_route: dict[tuple[str, str], APIRoute],
) -> None:
    unlisted = sorted(set(every_route) - set(ROUTES))
    assert not unlisted, f"add these routes to ROUTES in tests/test_routes.py: {unlisted}"
    gone = sorted(set(ROUTES) - set(every_route))
    assert not gone, f"ROUTES lists routes the app no longer has: {gone}"


def leak_test(name: str) -> Callable[..., Any] | None:
    """The test a row names: `test_name` in tests/findings/test_leaks.py, or `module:test_name`."""
    module_name, _, test_name = name.rpartition(":")
    module = importlib.import_module(module_name) if module_name else test_leaks
    return getattr(module, test_name, None)


def test_each_route_that_returns_a_position_has_a_leak_test() -> None:
    for key, expect in ROUTES.items():
        if expect.leak_test is not None:
            test = leak_test(expect.leak_test)
            assert callable(test), f"{key}: there is no {expect.leak_test}"


def test_every_write_says_who_may_make_it_and_every_read_how_it_is_checked() -> None:
    for (method, path), expect in ROUTES.items():
        assert (expect.writer is not None) is (method in MUTATING), f"{method} {path}"
        if method == "GET":
            assert (expect.sample is None) is (expect.unsampled is not None), f"{method} {path}"


def test_every_route_that_stores_a_contribution_needs_the_welcome_step(
    every_route: dict[tuple[str, str], APIRoute],
) -> None:
    for key, route in every_route.items():
        needs_welcome = current_contributor in set(_calls(route.dependant))
        assert needs_welcome is (ROUTES[key].writer == CONTRIBUTOR), f"{key}: {ROUTES[key].writer}"


def test_every_write_is_rate_limited(every_route: dict[tuple[str, str], APIRoute]) -> None:
    for (method, path), route in every_route.items():
        if method in MUTATING:
            names = {getattr(call, "__qualname__", "") for call in _calls(route.dependant)}
            assert "rate_limit.<locals>.dependency" in names, f"{method} {path} has no rate limit"


def test_every_route_documents_what_it_returns(every_route: dict[tuple[str, str], APIRoute]) -> None:
    """A response model, or for a body that isn't JSON, the media types it is sent as."""
    for (method, path), route in every_route.items():
        documented = (
            route.response_model is not None
            or route.status_code == 204
            or bool(route.responses.get(200, {}).get("content"))
            or not route.include_in_schema
            or route.response_class.__name__ == "RedirectResponse"  # pyright: ignore[reportAttributeAccessIssue]
        )
        assert documented, f"{method} {path} has no response model"


def test_the_published_schema_covers_every_route_but_the_terrain_images(
    every_route: dict[tuple[str, str], APIRoute],
) -> None:
    schema = create_app(include_dev_routes=True).openapi()
    published = {(method.upper(), path) for path, item in schema["paths"].items() for method in item}
    left_out = set(every_route) - published
    assert left_out == {
        ("GET", "/tiles/lidar/{style}/{z}/{x}/{y}.png"),
        ("GET", "/tiles/dem/{z}/{x}/{y}.png"),
        ("GET", "/healthz"),
    }


@pytest.fixture
def samples(db: Session, make_user: MakeUser) -> dict[str, str]:
    finder = make_user()
    finding = create(db, finder)
    record = add_record(db, add_source(db), "Bowl barrow", -1.85, 51.43)
    record_tiles.refresh_counts(db)
    db.commit()
    investigation = make(db, make_user(), Visibility.PUBLIC)
    return {
        "finding": finding.public_id,
        "record": str(record.id),
        "person": finder.handle,
        "investigation": investigation.public_id,
    }


@pytest.mark.parametrize(
    "key", [key for key, expect in ROUTES.items() if expect.sample is not None], ids=" ".join
)
def test_nothing_that_depends_on_the_viewer_is_publicly_cacheable(
    key: tuple[str, str],
    samples: dict[str, str],
    client: TestClient,
    client_as: Callable[..., TestClient],
    make_user: MakeUser,
) -> None:
    sample = ROUTES[key].sample
    assert sample is not None
    path = sample.format(**samples)
    # Signed out, `/auth/me` is a 401, which must not be cached either.
    signed_out = client.get(path)
    # A moderator who hasn't answered: answers are refused, everything else is there.
    member = client_as(make_user("moderator")).get(path)
    assert member.status_code in (200, 403), f"{path}: {member.text}"
    policy = signed_out.headers["cache-control"]
    if policy.startswith("public"):
        assert member.headers["cache-control"] == policy
        assert member.content == signed_out.content, f"{path} is public but depends on the viewer"
    else:
        assert policy.startswith(("private", "no-cache", "no-store")), f"{path}: {policy}"
        for response in (signed_out, member):
            vary = [token.strip() for line in response.headers.get_list("vary") for token in line.split(",")]
            assert vary.count("Cookie") == 1, f"{path} varies by {vary}, not once by cookie"
