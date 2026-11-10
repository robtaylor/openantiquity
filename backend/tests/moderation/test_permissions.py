"""Every moderation route against every kind of caller, signed out included.

Moderation routes are for moderators and admins. The photo approval queue is
shared with trusted members and experts (Decision 0009). Reporting is open to
every contributor. A banned account and one that hasn't finished the welcome
step are refused whatever their role.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import Report
from fieldclub.vocab import Role
from tests.findings.support import add_desk_evidence
from tests.helpers import ClientFor, MakeFinding, MakeUser, error_code
from tests.moderation.support import API, REASON, comment, jpeg, mention, photo

CALLERS = ("signed_out", "newcomer", "banned", "member", "trusted", "expert", "moderator", "admin")
MODERATORS = {"moderator", "admin"}
APPROVERS = {"trusted", "expert", "moderator", "admin"}
CONTRIBUTORS = {"member", "trusted", "expert", "moderator", "admin"}


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    body: dict[str, Any] | None
    allowed: set[str]


@pytest.fixture
def routes(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> list[Route]:
    """Each route, aimed at something that exists and belongs to someone other than the caller."""
    owner = make_user(handle="Owner")
    target = make_user(handle="Target")
    approver = make_user(Role.MODERATOR, handle="EarlierModerator")
    finding = make_finding(owner)
    said = comment(db, finding, owner)
    evidence, _ = add_desk_evidence(db, finding, make_user())
    talked = mention(db, finding, owner)
    waiting = photo(db, owner)
    refused = photo(db, owner, data=jpeg(colour=(10, 200, 30)))
    shown = photo(db, owner, approved_by=approver)
    report = Report(reporter_id=owner.id, target_kind="comment", target_id=said.id, reason="spam")
    db.add(report)
    db.commit()
    pid = finding.public_id
    hide_targets = {
        "findings": pid,
        "comments": said.id,
        "evidence": evidence.id,
        "mentions": talked.id,
        "media": shown.id,
    }
    found = [
        Route("GET", "/mod/reports", None, MODERATORS),
        Route(
            "POST", f"/mod/reports/{report.id}/resolve", {"outcome": "upheld", "note": "Spam."}, MODERATORS
        ),
        Route("PUT", f"/mod/findings/{pid}/sensitivity", {"level": "restricted", **REASON}, MODERATORS),
        Route("GET", "/mod/users/eligible", None, MODERATORS),
        Route("PUT", "/mod/users/Target/role", {"role": "expert", **REASON}, MODERATORS),
        Route("POST", "/mod/users/Target/ban", REASON, MODERATORS),
        Route("POST", "/mod/users/Target/unban", REASON, MODERATORS),
        Route("GET", "/mod/actions", None, MODERATORS),
        Route("GET", "/mod/media", None, APPROVERS),
        Route("POST", f"/mod/media/{waiting.id}/approve", None, APPROVERS),
        Route("POST", f"/mod/media/{refused.id}/reject", REASON, APPROVERS),
        Route(
            "POST",
            "/reports",
            {"target_kind": "user", "target_id": target.handle, "reason": "abuse"},
            CONTRIBUTORS,
        ),
    ]
    found.extend(
        Route("POST", f"/mod/{segment}/{ref}/{verb}", REASON, MODERATORS)
        for segment, ref in hide_targets.items()
        for verb in ("hide", "unhide")
    )
    return found


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
        if who in route.allowed:
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
