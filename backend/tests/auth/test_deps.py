"""The auth dependencies, exercised through a small app of their own."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
import time_machine
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth.deps import CurrentUser, OptionalUser, client_ip, require_role
from fieldclub.config import SESSION_COOKIE
from fieldclub.errors import install_error_handlers
from fieldclub.models import User, UserSession
from fieldclub.vocab import Role
from tests.helpers import ClientAs, ClientFor, MakeUser, error_code

START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
def deps_app(db: Session) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/optional")
    def optional(user: OptionalUser) -> dict[str, str | None]:
        return {"handle": user.handle if user else None}

    @app.get("/required")
    def required(user: CurrentUser) -> dict[str, str]:
        return {"handle": user.handle}

    @app.get("/mods")
    def mods(user: Annotated[User, Depends(require_role(Role.MODERATOR, Role.ADMIN))]) -> dict[str, str]:
        return {"handle": user.handle}

    @app.get("/ip")
    def ip(request: Request) -> dict[str, str | None]:
        return {"ip": client_ip(request)}

    return app


@pytest.fixture
def sign_in(deps_app: FastAPI, client_for: ClientFor) -> ClientAs:
    return lambda user: client_for(deps_app, user)


@pytest.fixture
def anonymous(deps_app: FastAPI, client_for: ClientFor) -> TestClient:
    return client_for(deps_app)


def test_optional_user_is_none_without_a_session(anonymous: TestClient) -> None:
    assert anonymous.get("/optional").json() == {"handle": None}


def test_optional_user_is_none_for_a_junk_cookie(anonymous: TestClient) -> None:
    anonymous.cookies.set(SESSION_COOKIE, "junk")
    response = anonymous.get("/optional")
    assert response.status_code == 200
    assert response.json() == {"handle": None}


def test_signed_in_user_is_resolved(sign_in: ClientAs, make_user: MakeUser) -> None:
    client = sign_in(make_user(handle="QuietBarrow42"))
    assert client.get("/optional").json() == {"handle": "QuietBarrow42"}
    assert client.get("/required").json() == {"handle": "QuietBarrow42"}


def test_current_user_is_a_401_when_signed_out(anonymous: TestClient) -> None:
    response = anonymous.get("/required")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorised", "message": "You need to sign in to do that."}
    }


def test_banned_users_are_rejected(sign_in: ClientAs, make_user: MakeUser, db: Session) -> None:
    user = make_user()
    client = sign_in(user)
    assert client.get("/required").status_code == 200

    user.banned_at = datetime.now(UTC)
    db.commit()
    response = client.get("/required")
    assert response.status_code == 403
    assert error_code(response) == "banned"
    # Where signing in is optional, a banned user is simply treated as signed out.
    assert client.get("/optional").json() == {"handle": None}
    assert client.get("/mods").status_code == 403


def test_someone_who_deleted_their_account_is_signed_out(
    sign_in: ClientAs, make_user: MakeUser, db: Session
) -> None:
    user = make_user()
    client = sign_in(user)
    assert client.get("/required").status_code == 200
    user.deleted_at = datetime.now(UTC)
    db.commit()
    assert client.get("/required").status_code == 401
    assert client.get("/optional").json() == {"handle": None}


def test_expired_sessions_are_signed_out(sign_in: ClientAs, make_user: MakeUser) -> None:
    with time_machine.travel(START, tick=False):
        client = sign_in(make_user())
        assert client.get("/required").status_code == 200
    with time_machine.travel(START + timedelta(days=366), tick=False):
        assert client.get("/required").status_code == 401


def test_using_a_session_refreshes_it_and_resends_the_cookie(
    sign_in: ClientAs, make_user: MakeUser, db: Session
) -> None:
    with time_machine.travel(START, tick=False):
        client = sign_in(make_user())
        quiet = client.get("/required")
    assert "set-cookie" not in quiet.headers

    later = START + timedelta(days=30)
    with time_machine.travel(later, tick=False):
        refreshed = client.get("/required")
    assert refreshed.status_code == 200
    cookie = refreshed.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie
    assert f"Max-Age={365 * 24 * 3600}" in cookie
    db.expire_all()
    row = db.scalars(select(UserSession)).one()
    assert row.expires_at == later + timedelta(days=365)


@pytest.mark.parametrize(
    ("role", "status"),
    [("member", 403), ("trusted", 403), ("expert", 403), ("moderator", 200), ("admin", 200)],
)
def test_require_role(sign_in: ClientAs, make_user: MakeUser, role: str, status: int) -> None:
    response = sign_in(make_user(role)).get("/mods")
    assert response.status_code == status
    if status == 403:
        assert error_code(response) == "forbidden"


def test_require_role_is_a_401_when_signed_out(anonymous: TestClient) -> None:
    assert anonymous.get("/mods").status_code == 401


def test_require_role_needs_roles() -> None:
    with pytest.raises(AssertionError):
        require_role()


# --------------------------------------------------------------------------
# Caller address
# --------------------------------------------------------------------------


@pytest.fixture
def proxy_hops(env: Callable[..., None]) -> Callable[[int], None]:
    return lambda hops: env(TRUSTED_PROXY_HOPS=str(hops))


def test_client_ip_ignores_forwarded_headers_by_default(anonymous: TestClient) -> None:
    response = anonymous.get("/ip", headers={"X-Forwarded-For": "203.0.113.5"})
    assert response.json() == {"ip": "testclient"}


def test_client_ip_trusts_only_the_entries_our_proxies_wrote(
    anonymous: TestClient, proxy_hops: Callable[[int], None]
) -> None:
    spoofed = {"X-Forwarded-For": "6.6.6.6, 203.0.113.5, 10.0.0.1"}
    proxy_hops(1)
    assert anonymous.get("/ip", headers=spoofed).json() == {"ip": "10.0.0.1"}
    proxy_hops(2)
    assert anonymous.get("/ip", headers=spoofed).json() == {"ip": "203.0.113.5"}
    # Fewer entries than proxies means the header can't be trusted at all.
    proxy_hops(5)
    assert anonymous.get("/ip", headers=spoofed).json() == {"ip": "testclient"}
    proxy_hops(1)
    assert anonymous.get("/ip").json() == {"ip": "testclient"}


def test_client_ip_reads_every_forwarded_for_line(
    anonymous: TestClient, proxy_hops: Callable[[int], None]
) -> None:
    # A proxy may add its entry as a second header line. The lines are one
    # list, so the line the client sent first must not be the one believed.
    lines = [("X-Forwarded-For", "6.6.6.6"), ("X-Forwarded-For", "203.0.113.5")]
    proxy_hops(1)
    assert anonymous.get("/ip", headers=lines).json() == {"ip": "203.0.113.5"}
    more = [("X-Forwarded-For", "6.6.6.6, 7.7.7.7"), ("X-Forwarded-For", "203.0.113.5 , 10.0.0.1")]
    assert anonymous.get("/ip", headers=more).json() == {"ip": "10.0.0.1"}
    proxy_hops(2)
    assert anonymous.get("/ip", headers=more).json() == {"ip": "203.0.113.5"}
    proxy_hops(3)
    assert anonymous.get("/ip", headers=more).json() == {"ip": "7.7.7.7"}


# What Fly's proxy passes on for a visitor at 203.0.113.5 who forged both
# headers: it overwrites Fly-Client-IP, and appends the visitor's address and
# then its own edge's to whatever X-Forwarded-For the visitor sent.
FLY_FORWARDED = {
    "Fly-Client-IP": "203.0.113.5",
    "X-Forwarded-For": "6.6.6.6, 7.7.7.7, 203.0.113.5, 66.241.124.11",
}


def test_client_ip_reads_the_proxy_s_own_header_when_told_to(
    anonymous: TestClient, env: Callable[..., None]
) -> None:
    env(CLIENT_IP_HEADER="Fly-Client-IP")
    assert anonymous.get("/ip", headers=FLY_FORWARDED).json() == {"ip": "203.0.113.5"}
    # The hop count no longer matters: the forged X-Forwarded-For entries are never read.
    env(TRUSTED_PROXY_HOPS="4")
    assert anonymous.get("/ip", headers=FLY_FORWARDED).json() == {"ip": "203.0.113.5"}
    assert anonymous.get("/ip", headers={"fly-client-ip": "2001:db8::7"}).json() == {"ip": "2001:db8::7"}


def test_on_fly_the_visitor_is_second_from_the_right_of_x_forwarded_for(
    anonymous: TestClient, proxy_hops: Callable[[int], None]
) -> None:
    # Without the header setting, two hops is the rule that matches Fly's proxy.
    proxy_hops(2)
    assert anonymous.get("/ip", headers=FLY_FORWARDED).json() == {"ip": "203.0.113.5"}


def test_a_forged_client_ip_header_is_not_believed_where_it_isn_t_the_proxy_s(
    anonymous: TestClient, proxy_hops: Callable[[int], None]
) -> None:
    forged = {"Fly-Client-IP": "6.6.6.6", "X-Forwarded-For": "203.0.113.5"}
    assert anonymous.get("/ip", headers=forged).json() == {"ip": "testclient"}
    proxy_hops(1)
    assert anonymous.get("/ip", headers=forged).json() == {"ip": "203.0.113.5"}


@pytest.mark.parametrize(
    "headers",
    [
        # Not through the proxy at all, as from another machine on the private network.
        [],
        # Two lines: the proxy didn't overwrite what came in, so neither is believed.
        [("Fly-Client-IP", "6.6.6.6"), ("Fly-Client-IP", "203.0.113.5")],
        [("Fly-Client-IP", "6.6.6.6, 203.0.113.5")],
        [("Fly-Client-IP", "not-an-address")],
        [("Fly-Client-IP", "")],
    ],
)
def test_a_client_ip_header_without_one_address_is_the_socket_s(
    anonymous: TestClient, env: Callable[..., None], headers: list[tuple[str, str]]
) -> None:
    env(CLIENT_IP_HEADER="Fly-Client-IP")
    sent = [*headers, ("X-Forwarded-For", "6.6.6.6")]
    assert anonymous.get("/ip", headers=sent).json() == {"ip": "testclient"}
