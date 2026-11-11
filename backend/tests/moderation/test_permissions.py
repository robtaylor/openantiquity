"""Every moderation route against every kind of caller, signed out included.

Moderation routes are for moderators and admins. The photo approval queue is
shared with trusted members and experts (Decision 0009). Reporting is open to
every contributor. A banned account is refused whatever its role. One that
hasn't finished the welcome step reads the queues and the log if its role
allows, and is refused every write, as on every other route.

The routes, each aimed at something that belongs to someone other than the
caller, come from the `routes` fixture in `conftest.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.vocab import Role
from tests.api import test_shared_rules as shared_rules
from tests.helpers import ClientFor, MakeUser, error_code
from tests.moderation.support import API, APPROVERS, MODERATORS, Route

CALLERS = ("signed_out", "newcomer", "banned", "member", "trusted", "expert", "moderator", "admin")


def caller(name: str, make_user: MakeUser, app: FastAPI, client_for: ClientFor) -> TestClient:
    if name == "signed_out":
        return client_for(app)
    if name == "newcomer":
        user = make_user(Role.MODERATOR, handle="NewModerator", age_band=None, terms_accepted_at=None)
    elif name == "banned":
        banned_at = datetime(2026, 11, 1, tzinfo=UTC)
        user = make_user(Role.MODERATOR, handle="BannedModerator", banned_at=banned_at)
    else:
        user = make_user(Role(name), handle=f"Caller{name.title()}")
    return client_for(app, user)


# How each caller who isn't let in is refused, whatever the route.
REFUSALS = {
    "signed_out": (401, "unauthorised"),
    "banned": (403, "banned"),
    "newcomer": (403, "onboarding_required"),
}


def admitted(who: str, route: Route) -> bool:
    # The newcomer is a moderator: only the welcome step stands between them and a write.
    if who == "newcomer":
        return route.method == "GET"
    return who in route.allowed


def refusal(who: str, route: Route) -> tuple[int, str]:
    if who in REFUSALS:
        return REFUSALS[who]
    return 403, "photo_approvers_only" if route.allowed == APPROVERS else "moderators_only"


def call(client: TestClient, route: Route):
    kwargs: dict[str, Any] = {"json": route.body} if route.body is not None else {}
    return client.request(route.method, API + route.path, **kwargs)


@pytest.mark.parametrize("who", CALLERS)
def test_every_route_against_every_caller(
    who: str,
    routes: list[Route],
    make_user: MakeUser,
    app: FastAPI,
    client_for: ClientFor,
    db: Session,
) -> None:
    client = caller(who, make_user, app, client_for)
    for route in routes:
        response = call(client, route)
        where = f"{who} {route.method} {route.path}"
        if admitted(who, route):
            assert response.status_code < 400 or response.status_code in (404, 409), (where, response.text)
            assert response.status_code not in (401, 403), where
        else:
            assert (response.status_code, error_code(response)) == refusal(who, route), (where, response.text)


@pytest.mark.parametrize("who", sorted(MODERATORS))
def test_moderators_get_a_real_answer_from_every_route(
    who: str, routes: list[Route], make_user: MakeUser, app: FastAPI, client_for: ClientFor
) -> None:
    # In this order each route acts on something still there: unhide follows hide.
    client = caller(who, make_user, app, client_for)
    for route in routes:
        response = call(client, route)
        assert response.status_code in (200, 201), (route.method, route.path, response.text)


def test_the_moderation_routes_are_never_cached(
    make_user: MakeUser, client_for: ClientFor, app: FastAPI
) -> None:
    client = client_for(app, make_user(Role.MODERATOR))
    for path in ("/mod/reports", "/mod/actions", "/mod/users/eligible", "/mod/media"):
        response = client.get(API + path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-cache", path


MODERATION_LISTS = {"/mod/reports": 200, "/mod/actions": 200, "/mod/users/eligible": 50, "/mod/media": 200}


@pytest.mark.parametrize("cursor", shared_rules.BAD_CURSORS)
def test_the_moderation_lists_follow_the_shared_cursor_rule(
    cursor: str, make_user: MakeUser, client_for: ClientFor, app: FastAPI
) -> None:
    client = client_for(app, make_user(Role.MODERATOR))
    for path in MODERATION_LISTS:
        response = client.get(shared_rules.with_params(API + path, cursor=cursor))
        assert (response.status_code, error_code(response)) == (400, "invalid_cursor"), path


def test_the_moderation_lists_refuse_a_limit_above_their_maximum(
    make_user: MakeUser, client_for: ClientFor, app: FastAPI
) -> None:
    client = client_for(app, make_user(Role.MODERATOR))
    for path, most in MODERATION_LISTS.items():
        assert client.get(API + path, params={"limit": most}).status_code == 200, path
        response = client.get(API + path, params={"limit": most + 1})
        assert (response.status_code, error_code(response)) == (422, "validation_error"), path
