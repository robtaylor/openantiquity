"""The current session and the signed-in person's own account, over HTTP."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth.tokens import hash_token
from fieldclub.config import SESSION_COOKIE, get_settings
from fieldclub.main import create_app
from fieldclub.models import AuthIdentity, User, UserSession
from tests.findings.support import create
from tests.helpers import WEB, ClientAs, ClientFor, MakeFinding, MakeUser, count, error_code, nested

ME_KEYS = {
    "id",
    "handle",
    "display_name",
    "role",
    "email",
    "email_verified",
    "reputation",
    "bio",
    "settings",
    "created_at",
    "age_band",
    "terms_accepted_at",
    "needs_welcome",
}


# --------------------------------------------------------------------------
# There are no guest accounts
# --------------------------------------------------------------------------


def test_there_is_no_guest_endpoint(client: TestClient, db: Session) -> None:
    response = client.post("/api/v1/auth/guest")
    assert response.status_code == 404
    assert "set-cookie" not in response.headers
    assert count(db, User) == 0
    assert count(db, UserSession) == 0


def test_no_auth_response_mentions_guests(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").text
    assert "guest" not in schema.lower()


# --------------------------------------------------------------------------
# POST /auth/dev-login
# --------------------------------------------------------------------------


def test_dev_login_creates_a_named_member_and_signs_them_in(client: TestClient, db: Session) -> None:
    response = client.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ME_KEYS
    assert (body["handle"], body["display_name"], body["role"]) == ("TestRob", "TestRob", "member")
    assert (body["email"], body["email_verified"]) == (None, False)
    assert (body["reputation"], body["bio"], body["settings"]) == (0.0, None, {})

    user = db.scalars(select(User)).one()
    assert user.handle == "TestRob"
    session = db.scalars(select(UserSession)).one()
    assert session.user_id == user.id
    assert session.user_agent == "testclient"
    assert session.ip_hash is not None

    # The cookie now identifies them.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == body


def test_dev_login_signs_in_an_existing_user(client: TestClient, make_user: MakeUser, db: Session) -> None:
    make_user("expert", handle="DrTrowel", display_name="Dr Trowel")
    response = client.post("/api/v1/auth/dev-login", json={"handle": "drtrowel"})
    assert response.status_code == 200
    assert (response.json()["handle"], response.json()["role"]) == ("DrTrowel", "expert")
    assert response.json()["display_name"] == "Dr Trowel"
    assert count(db, User) == 1


def test_dev_login_can_set_a_role_and_a_display_name(client: TestClient, db: Session) -> None:
    body = {"handle": "TestMod", "role": "moderator", "display_name": "Test Mod"}
    response = client.post("/api/v1/auth/dev-login", json=body)
    assert (response.json()["role"], response.json()["display_name"]) == ("moderator", "Test Mod")
    again = client.post("/api/v1/auth/dev-login", json={"handle": "TestMod", "role": "trusted"})
    assert again.json()["role"] == "trusted"
    assert count(db, User) == 1
    # The second sign-in ended the session the browser presented, as every sign-in does.
    assert count(db, UserSession) == 1


def test_dev_login_ends_the_session_the_browser_presented(client: TestClient, db: Session) -> None:
    from fieldclub.config import SESSION_COOKIE

    client.post("/api/v1/auth/dev-login", json={"handle": "TestAnn"})
    first = client.cookies[SESSION_COOKIE]
    client.post("/api/v1/auth/dev-login", json={"handle": "TestBob"})
    assert client.cookies[SESSION_COOKIE] != first
    assert client.get("/api/v1/auth/me").json()["handle"] == "TestBob"
    stale = TestClient(client.app, base_url=str(client.base_url), cookies={SESSION_COOKIE: first})
    assert stale.get("/api/v1/auth/me").status_code == 401
    assert count(db, UserSession) == 1


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({}, "validation_error"),
        ({"handle": "ab"}, "validation_error"),
        ({"handle": "no spaces"}, "invalid_handle"),
        ({"handle": "admin"}, "invalid_handle"),
        ({"handle": "TestRob", "role": "guest"}, "validation_error"),
        ({"handle": "TestRob", "role": "wizard"}, "validation_error"),
        ({"handle": "TestRob", "display_name": "Administrator"}, "invalid_display_name"),
        ({"handle": "TestRob", "is_guest": True}, "validation_error"),
    ],
)
def test_dev_login_refuses_bad_requests(client: TestClient, db: Session, body: dict, code: str) -> None:
    response = client.post("/api/v1/auth/dev-login", json=body)
    assert response.status_code == 422
    assert error_code(response) == code
    assert "set-cookie" not in response.headers
    assert count(db, User) == 0


def test_the_session_cookie_is_httponly_lax_and_secure(client: TestClient, db: Session) -> None:
    response = client.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    cookie = response.headers["set-cookie"]
    name, _, rest = cookie.partition("=")
    token, _, attributes = rest.partition(";")
    # `__Host-`: the browser takes it only Secure, for the whole site and this host alone.
    assert name == SESSION_COOKIE == "__Host-openantiquity_session"
    flags = {part.strip().lower() for part in attributes.split(";")}
    assert {"httponly", "samesite=lax", "secure", "path=/"} <= flags
    assert f"max-age={90 * 24 * 3600}" in flags
    assert "domain" not in attributes.lower()

    # The cookie holds the token. The database holds only its hash.
    stored = db.scalars(select(UserSession.token_hash)).one()
    assert stored == hash_token(token)
    assert stored != token
    assert len(token) >= 40


def test_the_cookie_is_not_secure_in_development(app: FastAPI, env: Callable[..., None]) -> None:
    env(ENV="dev")
    local = TestClient(app, base_url="http://localhost:8000", headers=WEB)
    response = local.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert response.status_code == 200
    assert "secure" not in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert local.get("/api/v1/auth/me").status_code == 200


def test_each_browser_has_its_own_session(app: FastAPI, client_for: ClientFor) -> None:
    def browser() -> TestClient:
        return client_for(app)

    first, second = browser(), browser()
    first.post("/api/v1/auth/dev-login", json={"handle": "Alice"})
    second.post("/api/v1/auth/dev-login", json={"handle": "Bob"})
    assert first.get("/api/v1/auth/me").json()["handle"] == "Alice"
    assert second.get("/api/v1/auth/me").json()["handle"] == "Bob"
    assert browser().get("/api/v1/auth/me").status_code == 401


def test_dev_login_needs_the_client_header(app: FastAPI, db: Session, client_for: ClientFor) -> None:
    bare = client_for(app, with_header=False)
    response = bare.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert response.status_code == 403
    assert error_code(response) == "client_header_required"
    assert count(db, User) == 0


def test_dev_login_does_not_exist_unless_it_was_asked_for(db: Session, client_for: ClientFor) -> None:
    settings = get_settings().model_copy(update={"dev_login": False})
    assert settings.dev_login_enabled is False
    browser = client_for(create_app(settings))
    response = browser.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert response.status_code == 404
    assert "/api/v1/auth/dev-login" not in browser.get("/api/openapi.json").json()["paths"]
    assert count(db, User) == 0


def test_dev_login_signs_nobody_in_when_mounted_by_mistake(
    db: Session, env: Callable[..., None], client_for: ClientFor
) -> None:
    # The route re-checks the settings, so mounting its router is not enough.
    env(DEV_LOGIN="false")
    browser = client_for(create_app(include_dev_routes=True))
    response = browser.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert response.status_code == 404
    assert "set-cookie" not in response.headers
    assert count(db, User) == 0


# --------------------------------------------------------------------------
# GET /auth/me
# --------------------------------------------------------------------------


def test_me_is_a_401_when_signed_out(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorised", "message": "You need to sign in to do that."}
    }


def test_me_shows_private_fields_to_their_owner(client_as: ClientAs, make_user: MakeUser) -> None:
    user = make_user(
        "trusted",
        handle="RidgewayRob",
        display_name="Rob",
        avatar_url="https://example.org/rob.png",
        email="rob@example.org",
        email_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        reputation=62.5,
        bio="Walks the Ridgeway.",
        settings={"units": "metric"},
    )
    body = client_as(user).get("/api/v1/auth/me").json()
    assert set(body) == ME_KEYS
    assert body | {"created_at": None} == {
        "id": user.id,
        "handle": "RidgewayRob",
        "display_name": "Rob",
        "role": "trusted",
        "email": "rob@example.org",
        "email_verified": True,
        "reputation": 62.5,
        "bio": "Walks the Ridgeway.",
        "settings": {"units": "metric"},
        "created_at": None,
        "age_band": "18_plus",
        "terms_accepted_at": body["terms_accepted_at"],
        "needs_welcome": False,
    }
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None


def test_me_with_a_junk_or_revoked_cookie_is_a_401(
    client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    client.cookies.set(SESSION_COOKIE, "junk")
    assert client.get("/api/v1/auth/me").status_code == 401

    signed_in = client_as(make_user())
    assert signed_in.post("/api/v1/auth/logout").status_code == 204
    signed_in.cookies.set(SESSION_COOKIE, "still-junk")
    assert signed_in.get("/api/v1/auth/me").status_code == 401


def test_banned_users_are_refused(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    user = make_user()
    browser = client_as(user)
    user.banned_at = datetime.now(UTC)
    db.commit()
    response = browser.get("/api/v1/auth/me")
    assert response.status_code == 403
    assert error_code(response) == "banned"
    assert browser.patch("/api/v1/auth/me", json={"bio": "Still here"}).status_code == 403


# --------------------------------------------------------------------------
# PATCH /auth/me
# --------------------------------------------------------------------------


def test_patch_me_changes_only_what_is_sent(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    user = make_user(handle="QuietBarrow42", bio="Old bio", settings={"units": "metric"})
    browser = client_as(user)

    response = browser.patch("/api/v1/auth/me", json={"display_name": "  Rob T  "})
    assert response.status_code == 200
    body = response.json()
    assert (body["handle"], body["display_name"], body["bio"]) == ("QuietBarrow42", "Rob T", "Old bio")
    assert body["settings"] == {"units": "metric"}

    response = browser.patch(
        "/api/v1/auth/me", json={"bio": "", "settings": {"layer": "slope", "units": None}}
    )
    assert (response.json()["bio"], response.json()["settings"]) == (None, {"layer": "slope"})
    db.refresh(user)
    assert (user.display_name, user.bio, user.settings) == ("Rob T", None, {"layer": "slope"})


def test_patch_me_can_change_the_handle(client_as: ClientAs, make_user: MakeUser) -> None:
    browser = client_as(make_user(handle="QuietBarrow42"))
    response = browser.patch("/api/v1/auth/me", json={"handle": "RidgewayRob"})
    assert response.status_code == 200
    assert (response.json()["handle"], response.json()["display_name"]) == ("RidgewayRob", "RidgewayRob")
    assert browser.get("/api/v1/auth/me").json()["handle"] == "RidgewayRob"


def test_patch_me_refuses_a_taken_handle(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    make_user(handle="RidgewayRob")
    user = make_user(handle="QuietBarrow42")
    response = client_as(user).patch("/api/v1/auth/me", json={"handle": "RIDGEWAYROB", "bio": "Hello"})
    assert response.status_code == 409
    assert response.json() == {"error": {"code": "handle_taken", "message": "Someone already has that name."}}
    db.refresh(user)
    assert (user.handle, user.bio) == ("QuietBarrow42", None)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"handle": "no spaces"}, "invalid_handle"),
        ({"handle": "admin"}, "invalid_handle"),
        ({"handle": "ab"}, "validation_error"),
        ({"display_name": ""}, "validation_error"),
        ({"display_name": "x" * 61}, "validation_error"),
        ({"bio": "x" * 1001}, "validation_error"),
        ({"role": "admin"}, "validation_error"),
        ({"email": "new@example.org"}, "validation_error"),
        ({"is_guest": False}, "validation_error"),
        ({"avatar_url": "https://example.org/x.png"}, "validation_error"),
        ({"deleted_at": None}, "validation_error"),
        ({"reputation": 999}, "validation_error"),
        ({"settings": "not an object"}, "validation_error"),
        ({"settings": {"blob": "x" * 9000}}, "validation_error"),
        ({"display_name": "Moderator"}, "invalid_display_name"),
        ({"display_name": "\u202egnp.exe"}, "invalid_display_name"),
        ({"display_name": "a\u200bb"}, "invalid_display_name"),
        ({"display_name": "line\nbreak"}, "invalid_display_name"),
        ({"display_name": "nul\x00byte"}, "validation_error"),
        ({"bio": "nul\x00byte"}, "validation_error"),
        ({"settings": {"note": "nul\x00byte"}}, "validation_error"),
        ({"settings": {"nul\x00key": 1}}, "validation_error"),
    ],
)
def test_patch_me_refuses_bad_or_forbidden_fields(
    client_as: ClientAs, make_user: MakeUser, db: Session, body: dict, code: str
) -> None:
    user = make_user(handle="QuietBarrow42")
    response = client_as(user).patch("/api/v1/auth/me", json=body)
    assert response.status_code == 422
    assert error_code(response) == code
    db.refresh(user)
    assert (user.handle, user.display_name, user.role, user.email, user.reputation) == (
        "QuietBarrow42",
        "QuietBarrow42",
        "member",
        None,
        0.0,
    )
    assert (user.bio, user.settings, user.avatar_url, user.deleted_at) == (None, None, None, None)


@pytest.mark.parametrize("depth", [7, 40, 300])
def test_deeply_nested_settings_are_refused_and_never_stored(
    client_as: ClientAs, make_user: MakeUser, db: Session, depth: int
) -> None:
    # Stored, these would make every later read of the account fail to serialise.
    user = make_user()
    browser = client_as(user)
    response = browser.patch("/api/v1/auth/me", json={"settings": {"deep": nested(depth)}})
    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    db.refresh(user)
    assert user.settings is None
    assert browser.get("/api/v1/auth/me").status_code == 200


def test_a_body_nested_past_the_parser_is_a_client_error(client_as: ClientAs, make_user: MakeUser) -> None:
    browser = client_as(make_user())
    body = b'{"settings":' + b'{"a":' * 100_000 + b"1" + b"}" * 100_000 + b"}"
    response = browser.patch("/api/v1/auth/me", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code in (400, 422)
    assert browser.get("/api/v1/auth/me").status_code == 200


def test_profile_updates_are_rate_limited_per_user(
    client_as: ClientAs, make_user: MakeUser, limits_on: None
) -> None:
    alice, bob = client_as(make_user()), client_as(make_user())
    statuses = [alice.patch("/api/v1/auth/me", json={"bio": f"Edit {n}"}).status_code for n in range(121)]
    assert statuses == [200] * 120 + [429]
    assert bob.patch("/api/v1/auth/me", json={"bio": "Mine"}).status_code == 200


def test_handle_changes_have_a_small_budget_of_their_own(
    client_as: ClientAs, make_user: MakeUser, db: Session, limits_on: None
) -> None:
    user = make_user(handle="QuietBarrow42")
    browser = client_as(user)
    statuses = [
        browser.patch("/api/v1/auth/me", json={"handle": f"Changed{n}"}).status_code for n in range(6)
    ]
    assert statuses == [200] * 5 + [429]
    db.refresh(user)
    assert user.handle == "Changed4", "the refused change was not stored"
    # Sending the handle they already have is no change, and other edits still work.
    assert browser.patch("/api/v1/auth/me", json={"handle": "Changed4", "bio": "Hi"}).status_code == 200


def test_mistyped_and_taken_handles_do_not_use_up_the_budget(
    client_as: ClientAs, make_user: MakeUser, limits_on: None
) -> None:
    make_user(handle="RidgewayRob")
    browser = client_as(make_user(handle="QuietBarrow42"))
    for _ in range(4):
        assert browser.patch("/api/v1/auth/me", json={"handle": "no spaces"}).status_code == 422
        assert browser.patch("/api/v1/auth/me", json={"handle": "RidgewayRob"}).status_code == 409
    statuses = [
        browser.patch("/api/v1/auth/me", json={"handle": f"Changed{n}"}).status_code for n in range(6)
    ]
    assert statuses == [200] * 5 + [429]


def test_validation_errors_name_the_field(client_as: ClientAs, make_user: MakeUser) -> None:
    response = client_as(make_user()).patch("/api/v1/auth/me", json={"display_name": "x" * 61})
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "body.display_name"
    assert error["details"][0]["message"]


def test_patch_me_with_nulls_leaves_handle_and_name_alone(client_as: ClientAs, make_user: MakeUser) -> None:
    browser = client_as(make_user(handle="QuietBarrow42", bio="Hello"))
    response = browser.patch("/api/v1/auth/me", json={"handle": None, "display_name": None, "settings": None})
    assert response.status_code == 200
    assert (response.json()["handle"], response.json()["display_name"], response.json()["bio"]) == (
        "QuietBarrow42",
        "QuietBarrow42",
        "Hello",
    )


def test_patch_me_needs_a_session_and_the_client_header(
    client: TestClient, app: FastAPI, client_as: ClientAs, make_user: MakeUser
) -> None:
    assert client.patch("/api/v1/auth/me", json={"bio": "x"}).status_code == 401
    signed_in = client_as(make_user())
    del signed_in.headers["X-OpenAntiquity-Client"]
    response = signed_in.patch("/api/v1/auth/me", json={"bio": "x"})
    assert response.status_code == 403
    assert error_code(response) == "client_header_required"


# --------------------------------------------------------------------------
# DELETE /auth/me
# --------------------------------------------------------------------------


def test_delete_me_removes_the_account_and_signs_out_everywhere(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    user = make_user(handle="RidgewayRob", display_name="Rob Taylor", email="rob@example.org", bio="Hello")
    finding = make_finding(user)
    db.add(AuthIdentity(user_id=user.id, provider="google", subject="123", email="rob@example.org"))
    db.commit()
    phone, laptop = client_as(user), client_as(user)

    response = phone.delete("/api/v1/auth/me")
    assert response.status_code == 204
    assert response.content == b""
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith(f"{SESSION_COOKIE.lower()}=")
    assert "max-age=0" in cleared

    assert phone.get("/api/v1/auth/me").status_code == 401
    assert laptop.get("/api/v1/auth/me").status_code == 401, "every device is signed out"
    assert count(db, UserSession) == 0
    assert count(db, AuthIdentity) == 0

    db.refresh(user)
    assert user.deleted_at is not None
    assert (user.email, user.bio, user.display_name) == (None, None, "Former member")
    assert user.handle.startswith("Former-")
    # What they contributed stays, with the same author row.
    assert count(db, User) == 1
    db.refresh(finding)
    assert finding.author_id == user.id


def test_a_deleted_account_cannot_come_back_through_dev_login(
    client: TestClient, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    user = make_user(handle="RidgewayRob")
    assert client_as(user).delete("/api/v1/auth/me").status_code == 204
    db.refresh(user)

    refused = client.post("/api/v1/auth/dev-login", json={"handle": user.handle})
    assert refused.status_code == 422
    assert error_code(refused) == "invalid_handle"
    # The old name now belongs to nobody, so asking for it makes a new account.
    fresh = client.post("/api/v1/auth/dev-login", json={"handle": "RidgewayRob"})
    assert fresh.status_code == 200
    assert count(db, User) == 2


def test_delete_me_needs_a_session_and_the_client_header(
    client: TestClient, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    assert client.delete("/api/v1/auth/me").status_code == 401
    user = make_user()
    signed_in = client_as(user)
    del signed_in.headers["X-OpenAntiquity-Client"]
    response = signed_in.delete("/api/v1/auth/me")
    assert response.status_code == 403
    assert error_code(response) == "client_header_required"
    db.refresh(user)
    assert user.deleted_at is None


# --------------------------------------------------------------------------
# GET /auth/handle-suggestion
# --------------------------------------------------------------------------


def test_handle_suggestion_offers_a_free_generated_handle(
    client: TestClient, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    response = client.get("/api/v1/auth/handle-suggestion")
    assert response.status_code == 200
    assert list(response.json()) == ["handle"]
    handle = response.json()["handle"]
    assert re.fullmatch(r"[A-Z][a-z]+[A-Z][a-z]+\d{2}", handle)
    assert count(db, User) == 0, "a suggestion reserves nothing"

    # It can be saved as it is.
    browser = client_as(make_user())
    assert browser.patch("/api/v1/auth/me", json={"handle": handle}).json()["handle"] == handle
    assert browser.get("/api/v1/auth/handle-suggestion").status_code == 200


def test_handle_suggestions_vary(client: TestClient) -> None:
    handles = {client.get("/api/v1/auth/handle-suggestion").json()["handle"] for _ in range(20)}
    assert len(handles) > 15


def test_handle_suggestion_is_rate_limited_per_address(
    app: FastAPI, limits_on: None, client_for: ClientFor
) -> None:
    # One client without cookies or the client header: the route sets no cookie.
    bare = client_for(app, with_header=False)

    def ask(address: str) -> int:
        return bare.get("/api/v1/auth/handle-suggestion", headers={"X-Forwarded-For": address}).status_code

    assert [ask("203.0.113.5") for _ in range(121)] == [200] * 120 + [429]
    assert ask("203.0.113.6") == 200
    # A caller can't escape the limit by sending a forwarded-for line of their own.
    lines = [("X-Forwarded-For", "198.51.100.77"), ("X-Forwarded-For", "203.0.113.5")]
    assert bare.get("/api/v1/auth/handle-suggestion", headers=lines).status_code == 429


# --------------------------------------------------------------------------
# POST /auth/logout
# --------------------------------------------------------------------------


def test_logout_ends_the_session_and_clears_the_cookie(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    user = make_user()
    phone, laptop = client_as(user), client_as(user)
    assert count(db, UserSession) == 2

    response = phone.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith(f"{SESSION_COOKIE.lower()}=")
    assert "max-age=0" in cleared
    assert "httponly" in cleared

    assert phone.get("/api/v1/auth/me").status_code == 401
    assert laptop.get("/api/v1/auth/me").status_code == 200, "other devices stay signed in"
    assert count(db, UserSession) == 1
    assert count(db, User) == 1


def test_signing_out_everywhere_ends_every_session_of_that_person_only(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    """A session left open on a lost or shared device can be ended without deleting the account."""
    user, other = make_user(), make_user()
    phone, laptop, theirs = client_as(user), client_as(user), client_as(other)
    response = phone.post("/api/v1/auth/logout-everywhere")
    assert response.status_code == 204
    assert response.headers["set-cookie"].lower().startswith(f"{SESSION_COOKIE.lower()}=")
    assert phone.get("/api/v1/auth/me").status_code == 401
    assert laptop.get("/api/v1/auth/me").status_code == 401
    assert theirs.get("/api/v1/auth/me").status_code == 200
    assert count(db, UserSession) == 1
    assert count(db, User) == 2


def test_signing_out_everywhere_needs_a_session(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout-everywhere").status_code == 401


def test_a_replayed_cookie_does_not_work_after_logout(
    client_as: ClientAs, make_user: MakeUser, app: FastAPI, client_for: ClientFor
) -> None:
    browser = client_as(make_user())
    token = browser.cookies.get(SESSION_COOKIE)
    assert token
    browser.post("/api/v1/auth/logout")
    thief = client_for(app, with_header=False)
    thief.cookies.set(SESSION_COOKIE, token)
    assert thief.get("/api/v1/auth/me").status_code == 401


def test_logout_when_signed_out_is_harmless(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_logout_needs_the_client_header(
    app: FastAPI, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    browser = client_as(make_user())
    del browser.headers["X-OpenAntiquity-Client"]
    assert browser.post("/api/v1/auth/logout").status_code == 403
    assert count(db, UserSession) == 1


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def test_auth_routes_are_in_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    auth = {path: sorted(methods) for path, methods in paths.items() if path.startswith("/api/v1/auth/")}
    assert auth == {
        "/api/v1/auth/dev-login": ["post"],
        "/api/v1/auth/dev-outbox": ["get"],
        "/api/v1/auth/email/start": ["post"],
        "/api/v1/auth/email/verify": ["post"],
        "/api/v1/auth/handle-suggestion": ["get"],
        "/api/v1/auth/logout": ["post"],
        "/api/v1/auth/logout-everywhere": ["post"],
        "/api/v1/auth/me": ["delete", "get", "patch"],
        "/api/v1/auth/oauth/{provider}/callback": ["get", "post"],
        "/api/v1/auth/oauth/{provider}/start": ["get"],
        "/api/v1/auth/session": ["get"],
        "/api/v1/auth/welcome": ["post"],
    }
    assert paths["/api/v1/auth/welcome"]["post"]["operationId"] == "auth_welcome"
    assert paths["/api/v1/auth/me"]["get"]["operationId"] == "auth_get_me"
    assert paths["/api/v1/auth/me"]["patch"]["operationId"] == "auth_update_me"
    assert paths["/api/v1/auth/me"]["delete"]["operationId"] == "auth_delete_me"
    assert paths["/api/v1/auth/logout"]["post"]["operationId"] == "auth_logout"
    assert paths["/api/v1/auth/handle-suggestion"]["get"]["operationId"] == "auth_handle_suggestion"
    assert paths["/api/v1/auth/dev-login"]["post"]["operationId"] == "auth_dev_login"
    assert set(paths["/api/v1/auth/logout"]["post"]["responses"]) == {"204"}
    assert set(paths["/api/v1/auth/me"]["delete"]["responses"]) == {"204"}


# --------------------------------------------------------------------------
# The welcome step
# --------------------------------------------------------------------------


def test_a_new_account_is_told_it_needs_the_welcome_step(client_as: ClientAs, newcomer: User) -> None:
    body = client_as(newcomer).get("/api/v1/auth/me").json()
    assert (body["age_band"], body["terms_accepted_at"], body["needs_welcome"]) == (None, None, True)


def test_a_bio_needs_the_welcome_step_but_other_changes_and_clearing_do_not(
    client_as: ClientAs, newcomer: User, db: Session
) -> None:
    client = client_as(newcomer)
    refused = client.patch("/api/v1/auth/me", json={"bio": "hi"})
    assert refused.status_code == 403
    assert error_code(refused) == "onboarding_required"
    db.refresh(newcomer)
    assert newcomer.bio is None
    # Settings, and clearing a bio, store no free text.
    assert client.patch("/api/v1/auth/me", json={"settings": {"units": "metric"}}).status_code == 200
    assert client.patch("/api/v1/auth/me", json={"bio": ""}).status_code == 200


def test_welcome_records_handle_name_band_and_terms(client_as: ClientAs, newcomer: User, db: Session) -> None:
    client = client_as(newcomer)
    response = client.post(
        "/api/v1/auth/welcome",
        json={"handle": "RidgewayRob", "display_name": "Rob", "age_band": "18_plus", "accept_terms": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == ME_KEYS
    assert (body["handle"], body["display_name"], body["age_band"]) == ("RidgewayRob", "Rob", "18_plus")
    assert body["needs_welcome"] is False
    assert datetime.fromisoformat(body["terms_accepted_at"]).tzinfo is not None
    db.refresh(newcomer)
    assert (newcomer.handle, newcomer.age_band) == ("RidgewayRob", "18_plus")
    assert newcomer.terms_accepted_at is not None
    assert client.get("/api/v1/auth/me").json()["needs_welcome"] is False


def test_welcome_as_16_or_17_drops_the_provider_name_and_picture(client_as: ClientAs, newcomer: User) -> None:
    body = (
        client_as(newcomer)
        .post("/api/v1/auth/welcome", json={"age_band": "16_17", "accept_terms": True})
        .json()
    )
    assert (body["handle"], body["display_name"]) == ("QuietBarrow42", "QuietBarrow42")


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"age_band": "18_plus", "accept_terms": False}, 422, "terms_not_accepted"),
        ({"age_band": "18_plus"}, 422, "validation_error"),
        ({"accept_terms": True}, 422, "validation_error"),
        ({"age_band": "13_15", "accept_terms": True}, 422, "validation_error"),
        ({"age_band": "18_plus", "accept_terms": True, "role": "admin"}, 422, "validation_error"),
        ({"age_band": "18_plus", "accept_terms": True, "avatar_url": "x"}, 422, "validation_error"),
    ],
)
def test_welcome_refuses_bad_requests_and_stores_nothing(
    client_as: ClientAs, newcomer: User, db: Session, body: dict, status: int, code: str
) -> None:
    response = client_as(newcomer).post("/api/v1/auth/welcome", json=body)
    assert (response.status_code, error_code(response)) == (status, code)
    db.refresh(newcomer)
    assert (newcomer.age_band, newcomer.terms_accepted_at, newcomer.role) == (None, None, "member")


def test_welcome_refuses_a_band_under_the_minimum_age(
    client_as: ClientAs, newcomer: User, env: Callable[..., None]
) -> None:
    client = client_as(newcomer)
    env(MIN_AGE="18")
    response = client.post("/api/v1/auth/welcome", json={"age_band": "16_17", "accept_terms": True})
    assert (response.status_code, error_code(response)) == (403, "below_minimum_age")


def test_welcome_happens_once(client_as: ClientAs, newcomer: User) -> None:
    client = client_as(newcomer)
    first = client.post("/api/v1/auth/welcome", json={"age_band": "16_17", "accept_terms": True})
    assert first.status_code == 200
    again = client.post("/api/v1/auth/welcome", json={"age_band": "18_plus", "accept_terms": True})
    assert (again.status_code, error_code(again)) == (409, "already_welcomed")


def test_welcome_with_a_taken_handle_stores_nothing(
    client_as: ClientAs, newcomer: User, make_user: MakeUser, db: Session
) -> None:
    make_user(handle="TakenName")
    response = client_as(newcomer).post(
        "/api/v1/auth/welcome", json={"handle": "TakenName", "age_band": "18_plus", "accept_terms": True}
    )
    assert (response.status_code, error_code(response)) == (409, "handle_taken")
    db.refresh(newcomer)
    assert (newcomer.handle, newcomer.age_band) == ("QuietBarrow42", None)


def test_welcome_needs_a_session_and_the_client_header(
    app: FastAPI, client: TestClient, newcomer: User, client_for: ClientFor
) -> None:
    body = {"age_band": "18_plus", "accept_terms": True}
    response = client.post("/api/v1/auth/welcome", json=body)
    assert (response.status_code, error_code(response)) == (401, "unauthorised")
    bare = client_for(app, with_header=False)
    response = bare.post("/api/v1/auth/welcome", json=body)
    assert (response.status_code, error_code(response)) == (403, "client_header_required")


def test_the_account_routes_stay_open_before_the_welcome_step(client_as: ClientAs, newcomer: User) -> None:
    # Someone who hasn't finished the welcome step can still see, change,
    # sign out of and delete their account. Only a bio, which is public free
    # text, waits for the welcome step.
    client = client_as(newcomer)
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.patch("/api/v1/auth/me", json={"display_name": "Rob"}).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204


# --------------------------------------------------------------------------
# The id, the provider's picture, and asking who is signed in without an error
# --------------------------------------------------------------------------


def test_me_carries_an_id_that_stays_when_the_handle_changes(
    client_as: ClientAs, make_user: MakeUser
) -> None:
    user = make_user(handle="FirstName")
    browser = client_as(user)
    before = browser.get("/api/v1/auth/me").json()["id"]
    assert before == user.id
    assert browser.patch("/api/v1/auth/me", json={"handle": "SecondName"}).json()["id"] == before
    assert browser.get("/api/v1/auth/me").json()["id"] == before


def test_the_id_is_never_part_of_the_public_face_of_a_person(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    user = make_user(handle="PublicFace")
    finding = create(db, user)
    profile = client.get("/api/v1/users/PublicFace")
    assert profile.status_code == 200
    assert "id" not in profile.json()
    author = client.get(f"/api/v1/findings/{finding.public_id}").json()["author"]
    assert "id" not in author
    schema = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert "id" not in schema["PublicUser"]["properties"]


def test_a_picture_kept_from_before_goes_at_the_next_sign_in(
    app: FastAPI, client_for: ClientFor, make_user: MakeUser, db: Session
) -> None:
    """Provider pictures aren't shown, so an address kept from before is personal data nothing uses."""
    user = make_user(handle="TestRob", avatar_url="https://example.org/face.png")
    assert client_for(app).post("/api/v1/auth/dev-login", json={"handle": "TestRob"}).status_code == 200
    db.refresh(user)
    assert user.avatar_url is None


def test_session_answers_null_when_signed_out_and_the_person_when_signed_in(
    client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    signed_out = client.get("/api/v1/auth/session")
    assert signed_out.status_code == 200
    assert signed_out.json() is None
    user = make_user(handle="SessionSam")
    browser = client_as(user)
    signed_in = browser.get("/api/v1/auth/session")
    assert signed_in.status_code == 200
    assert signed_in.json() == browser.get("/api/v1/auth/me").json()
    assert signed_in.headers["cache-control"].startswith("private")


def test_session_answers_null_for_a_stale_cookie_or_a_banned_account(
    client: TestClient, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    client.cookies.set(SESSION_COOKIE, "junk")
    assert client.get("/api/v1/auth/session").json() is None
    user = make_user()
    browser = client_as(user)
    user.banned_at = datetime.now(UTC)
    db.commit()
    response = browser.get("/api/v1/auth/session")
    assert (response.status_code, response.json()) == (200, None)
    # /auth/me keeps its errors.
    assert browser.get("/api/v1/auth/me").status_code == 403
