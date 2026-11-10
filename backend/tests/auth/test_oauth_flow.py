"""Provider sign-in over HTTP, from the start redirect to the session cookie, for every provider."""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import httpx2
import pytest
import respx
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import ECKey, OctKey, RSAKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth import accounts, signin
from fieldclub.auth.oidc import JWKS_MIN_REFRESH_S
from fieldclub.auth.tokens import hash_token
from fieldclub.config import SESSION_COOKIE
from fieldclub.models import AuthIdentity, User, UserSession
from tests.auth.conftest import MICROSOFT_TENANT
from tests.auth.fakes import (
    PUBLIC_URL,
    FakeFacebook,
    FakeIdP,
    Provider,
    callback,
    flow_cookie_value,
    query_of,
    sign_in,
    signin_error,
    start,
)
from tests.helpers import ClientFor, MakeUser, count

Idps = dict[str, Provider]

# What each provider says about the same person, Ann.
ANN: dict[str, dict[str, Any]] = {
    "google": {
        "sub": "g-ann",
        "email": "ann@example.org",
        "email_verified": True,
        "name": "Ann Barrow",
        "picture": "https://lh3.example/ann.png",
    },
    "microsoft": {"sub": "m-ann", "email": "ann@example.org", "name": "Ann Barrow"},
    "apple": {"sub": "a-ann", "email": "ann@example.org", "email_verified": "true"},
    "osm": {"sub": "12345", "preferred_username": "annmaps"},
    "facebook": {
        "id": "10101",
        "name": "Ann Barrow",
        "email": "ann@example.org",
        "picture": {"data": {"url": "https://fb.example/ann.jpg", "is_silhouette": False}},
    },
}
APPLE_USER = json.dumps({"name": {"firstName": "Ann", "lastName": "Barrow"}, "email": "spoofed@evil.example"})
# (display name, avatar, email on the account) after a first sign-in.
EXPECTED = {
    "google": ("Ann Barrow", "https://lh3.example/ann.png", "ann@example.org"),
    # Microsoft's address isn't verified without the domain-owner flag.
    "microsoft": ("Ann Barrow", None, None),
    # Apple's name comes from the posted form; its address from the identity token, never the form.
    "apple": ("Ann Barrow", None, "ann@example.org"),
    "osm": ("annmaps", None, None),
    # Facebook never verifies an address.
    "facebook": ("Ann Barrow", "https://fb.example/ann.jpg", None),
}
SUBJECTS = {"google": "g-ann", "microsoft": "m-ann", "apple": "a-ann", "osm": "12345", "facebook": "10101"}
PROVIDERS = list(SUBJECTS)


@pytest.fixture
def browser(app: FastAPI, client_for: ClientFor) -> TestClient:
    """A signed-out browser that sends the client header, as the web app does."""
    return client_for(app)


def complete(browser: TestClient, idps: Idps, provider: str, claims: dict[str, Any] | None = None, **kw: Any):
    """Sign in with `provider` using Ann's details, or `claims`."""
    claims = ANN[provider] if claims is None else claims
    if provider == "apple":
        kw.setdefault("method", "POST")
        kw.setdefault("user", APPLE_USER)
    return sign_in(browser, idps[provider], claims, **kw)


def issued_session(response: httpx2.Response) -> str:
    """The session token a response sets."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("no session cookie was set")


def session_rows(db: Session) -> list[UserSession]:
    db.expire_all()
    return list(db.scalars(select(UserSession)))


# --------------------------------------------------------------------------
# The whole flow, per provider
# --------------------------------------------------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_first_sign_in_creates_an_account_that_still_needs_the_welcome_step(
    provider: str, browser: TestClient, idps: Idps, db: Session
) -> None:
    response = complete(browser, idps, provider, next_path="/f/7K3QXM")
    assert signin_error(response) is None
    assert response.headers["location"] == f"{PUBLIC_URL}/f/7K3QXM"

    me = browser.get("/api/v1/auth/me").json()
    name, avatar, email = EXPECTED[provider]
    assert me["display_name"] == name
    assert me["avatar_url"] == avatar
    assert me["email"] == email
    assert me["email_verified"] is (email is not None)
    assert me["needs_welcome"] is True
    assert me["age_band"] is None
    assert me["terms_accepted_at"] is None
    assert me["handle"] != name

    identity = db.scalars(select(AuthIdentity)).one()
    assert (identity.provider, identity.subject) == (provider, SUBJECTS[provider])
    assert count(db, User) == 1
    assert len(session_rows(db)) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_welcome_step_applies_after_a_provider_sign_in(
    provider: str, browser: TestClient, idps: Idps
) -> None:
    complete(browser, idps, provider)
    refused = browser.patch("/api/v1/auth/me", json={"bio": "I like barrows"})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "onboarding_required"
    welcomed = browser.post("/api/v1/auth/welcome", json={"age_band": "18_plus", "accept_terms": True})
    assert welcomed.status_code == 200
    assert welcomed.json()["needs_welcome"] is False


@pytest.mark.parametrize("provider", PROVIDERS)
def test_signing_in_again_finds_the_same_account_with_a_new_session(
    provider: str, app: FastAPI, client_for: ClientFor, idps: Idps, db: Session
) -> None:
    first, second = client_for(app), client_for(app)
    complete(first, idps, provider)
    # Apple sends the name only the first time.
    again = (
        complete(second, idps, provider, user=None)
        if provider == "apple"
        else complete(second, idps, provider)
    )
    assert signin_error(again) is None
    assert count(db, User) == 1
    assert count(db, AuthIdentity) == 1
    assert first.cookies[SESSION_COOKIE] != second.cookies[SESSION_COOKIE]
    assert len(session_rows(db)) == 2
    assert second.get("/api/v1/auth/me").json()["display_name"] == EXPECTED[provider][0]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_start_sends_state_and_a_pkce_challenge_and_sets_the_flow_cookie(
    provider: str, browser: TestClient, idps: Idps
) -> None:
    response = start(browser, provider, "/f/ABC")
    assert response.status_code == 302
    query = query_of(response.headers["location"])
    assert len(query["state"]) >= 43
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert query["redirect_uri"] == f"{PUBLIC_URL}/api/v1/auth/oauth/{provider}/callback"
    if provider == "facebook":
        assert "nonce" not in query
    else:
        assert len(query["nonce"]) >= 43
    if provider == "apple":
        assert query["response_mode"] == "form_post"
        assert query["scope"] == "name email"

    cookie = next(h for h in response.headers.get_list("set-cookie") if h.startswith("fieldclub_oauth="))
    attributes = {part.strip().split("=", 1)[0].lower(): part for part in cookie.split(";")}
    assert "httponly" in attributes
    assert attributes["path"].strip() == f"Path=/api/v1/auth/oauth/{provider}/callback"
    assert attributes["max-age"].strip() == "Max-Age=600"
    assert "secure" in attributes
    assert attributes["samesite"].strip().lower() == (
        "samesite=none" if provider == "apple" else "samesite=lax"
    )
    # The verifier and nonce are in the cookie, never in the address the provider sees.
    assert flow_cookie_value(response) not in response.headers["location"]


def test_the_flow_cookie_is_cleared_by_the_callback(browser: TestClient, idps: Idps) -> None:
    response = complete(browser, idps, "google")
    cleared = [h for h in response.headers.get_list("set-cookie") if h.startswith("fieldclub_oauth=")]
    assert len(cleared) == 1
    assert "Max-Age=0" in cleared[0] or 'fieldclub_oauth=""' in cleared[0]
    assert "fieldclub_oauth" not in browser.cookies


def test_the_redirect_address_and_the_session_cookie_are_right(browser: TestClient, idps: Idps) -> None:
    response = complete(browser, idps, "google")
    assert response.status_code == 303
    session_cookie = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{SESSION_COOKIE}=")
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie or "samesite=lax" in session_cookie.lower()


# --------------------------------------------------------------------------
# State: forged, missing, from another browser, expired, edited
# --------------------------------------------------------------------------


def assert_nobody_signed_in(db: Session, browser: TestClient) -> None:
    assert count(db, User) == 0
    assert count(db, UserSession) == 0
    assert SESSION_COOKIE not in browser.cookies
    assert browser.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_forged_state_is_refused(provider: str, browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, provider)
    code, _ = idps[provider].authorise(started.headers["location"], ANN[provider])
    method = "POST" if provider == "apple" else "GET"
    response = callback(browser, provider, method=method, code=code, state="forged-" + "x" * 40)
    assert signin_error(response) == "state_mismatch"
    assert_nobody_signed_in(db, browser)
    # The code was never spent: the state check comes before the exchange.
    assert code not in idps[provider].spent


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_missing_state_is_refused(provider: str, browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, provider)
    code, _ = idps[provider].authorise(started.headers["location"], ANN[provider])
    assert signin_error(callback(browser, provider, code=code)) == "state_mismatch"
    assert signin_error(callback(browser, provider, code=code, state="")) == "state_mismatch"
    assert_nobody_signed_in(db, browser)


def test_a_callback_in_a_browser_that_did_not_start_the_flow_is_refused(
    app: FastAPI, client_for: ClientFor, idps: Idps, db: Session
) -> None:
    """Login CSRF: an attacker's own code and state, delivered to a victim's browser."""
    attacker, victim = client_for(app), client_for(app)
    started = start(attacker, "google")
    code, state = idps["google"].authorise(started.headers["location"], ANN["google"])
    assert signin_error(callback(victim, "google", code=code, state=state)) == "state_mismatch"
    assert_nobody_signed_in(db, victim)


def test_a_flow_cookie_for_another_provider_is_refused(browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, "osm")
    code, state = idps["osm"].authorise(started.headers["location"], ANN["osm"])
    # Replay osm's cookie and state against google's callback.
    browser.cookies.set(
        "fieldclub_oauth", flow_cookie_value(started), path="/api/v1/auth/oauth/google/callback"
    )
    assert signin_error(callback(browser, "google", code=code, state=state)) == "state_mismatch"
    assert_nobody_signed_in(db, browser)


def test_an_edited_flow_cookie_is_refused(browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, "google")
    code, state = idps["google"].authorise(started.headers["location"], ANN["google"])
    body, signature = flow_cookie_value(started).split(".")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    data["next"] = "//evil.example"
    edited = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    path = "/api/v1/auth/oauth/google/callback"
    browser.cookies.clear()
    browser.cookies.set("fieldclub_oauth", f"{edited}.{signature}", path=path)
    response = callback(browser, "google", code=code, state=state)
    assert signin_error(response) == "state_mismatch"
    assert response.headers["location"].startswith(f"{PUBLIC_URL}/?")
    assert_nobody_signed_in(db, browser)


def test_a_flow_older_than_ten_minutes_is_refused(browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, "google")
    code, state = idps["google"].authorise(started.headers["location"], ANN["google"])
    with time_machine.travel(time.time() + 601, tick=False):
        assert signin_error(callback(browser, "google", code=code, state=state)) == "state_mismatch"
    assert_nobody_signed_in(db, browser)


# --------------------------------------------------------------------------
# Codes and identity tokens
# --------------------------------------------------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_replayed_code_is_refused(provider: str, browser: TestClient, idps: Idps, db: Session) -> None:
    started = start(browser, provider)
    flow_cookie = flow_cookie_value(started)
    code, state = idps[provider].authorise(started.headers["location"], ANN[provider])
    method = "POST" if provider == "apple" else "GET"
    assert signin_error(callback(browser, provider, method=method, code=code, state=state)) is None
    sessions_after_first = len(session_rows(db))

    # The same cookie, code and state a second time, as an attacker who copied them would send.
    browser.cookies.clear()
    path = f"/api/v1/auth/oauth/{provider}/callback"
    browser.cookies.set("fieldclub_oauth", flow_cookie, path=path)
    replay = callback(browser, provider, method=method, code=code, state=state)
    assert signin_error(replay) == "provider_error"
    assert len(session_rows(db)) == sessions_after_first
    assert SESSION_COOKIE not in browser.cookies


OIDC_PROVIDERS = ["google", "microsoft", "apple", "osm"]


def oidc_sign_in(browser: TestClient, idp: FakeIdP, claims: dict[str, Any]) -> httpx2.Response:
    provider = idp.provider
    form = {"method": "POST"} if provider == "apple" else {}
    return sign_in(browser, idp, {"sub": "s-1"} | claims, **form)


@pytest.mark.parametrize("provider", OIDC_PROVIDERS)
@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"nonce": "not-the-flows-nonce"}, id="nonce-mismatch"),
        pytest.param({"nonce": None}, id="nonce-missing"),
        pytest.param({"iss": "https://evil.example"}, id="wrong-issuer"),
        pytest.param({"aud": "someone-elses-client"}, id="wrong-audience"),
        pytest.param({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, id="expired"),
        pytest.param({"iat": int(time.time()) + 3600, "exp": int(time.time()) + 7200}, id="issued-in-future"),
        pytest.param({"exp": None}, id="no-expiry"),
        pytest.param({"sub": None}, id="no-subject"),
    ],
)
def test_identity_tokens_that_fail_a_check_are_refused(
    provider: str, claims: dict[str, Any], browser: TestClient, idps: Idps, db: Session
) -> None:
    idp = idps[provider]
    assert isinstance(idp, FakeIdP)
    response = oidc_sign_in(browser, idp, claims)
    assert signin_error(response) == "invalid_token"
    assert_nobody_signed_in(db, browser)


def test_an_audience_list_needs_us_as_the_authorised_party(
    browser: TestClient, idps: Idps, db: Session
) -> None:
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    both = ["google-client", "other-client"]
    assert signin_error(oidc_sign_in(browser, idp, {"aud": both})) == "invalid_token"
    assert signin_error(oidc_sign_in(browser, idp, {"aud": both, "azp": "other-client"})) == "invalid_token"
    assert (
        signin_error(oidc_sign_in(browser, idp, {"aud": "google-client", "azp": "other"})) == "invalid_token"
    )
    assert count(db, User) == 0
    assert signin_error(oidc_sign_in(browser, idp, {"aud": both, "azp": "google-client"})) is None


def b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def unsigned(claims: dict[str, Any]) -> str:
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."


@pytest.mark.parametrize("provider", OIDC_PROVIDERS)
def test_an_unsigned_identity_token_is_refused(
    provider: str, browser: TestClient, idps: Idps, db: Session
) -> None:
    idp = idps[provider]
    assert isinstance(idp, FakeIdP)
    idp.forge = unsigned
    assert signin_error(oidc_sign_in(browser, idp, {})) == "invalid_token"
    assert_nobody_signed_in(db, browser)


def test_a_token_signed_with_the_public_key_as_an_hmac_secret_is_refused(
    browser: TestClient, idps: Idps, db: Session, rsa_keys: list[RSAKey]
) -> None:
    """The classic confusion: HS256 keyed with the provider's published key."""
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    public = json.dumps(rsa_keys[0].as_dict(private=False)).encode()
    secret = OctKey.import_key(public)

    def hs256(claims: dict[str, Any]) -> str:
        return jwt.encode({"alg": "HS256", "kid": rsa_keys[0].kid}, claims, secret, algorithms=["HS256"])

    idp.forge = hs256
    assert signin_error(oidc_sign_in(browser, idp, {})) == "invalid_token"
    assert_nobody_signed_in(db, browser)


def test_a_token_signed_with_an_algorithm_outside_the_allow_list_is_refused(
    browser: TestClient, idps: Idps, db: Session, rsa_keys: list[RSAKey]
) -> None:
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    # A real signature by the provider's own key, but with PS256, which we don't accept.
    idp.forge = lambda claims: idp.id_token(claims, alg="PS256")
    assert signin_error(oidc_sign_in(browser, idp, {})) == "invalid_token"
    assert_nobody_signed_in(db, browser)


def test_a_token_signed_by_a_key_the_provider_never_published_is_refused(
    browser: TestClient, idps: Idps, db: Session, rsa_keys: list[RSAKey]
) -> None:
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    stranger = rsa_keys[2]
    idp.forge = lambda claims: idp.id_token(claims, key=stranger)
    assert signin_error(oidc_sign_in(browser, idp, {})) == "invalid_token"
    # A forged key id with the published key's signature.
    idp.forge = lambda claims: jwt.encode(
        {"alg": "RS256", "kid": rsa_keys[0].kid}, claims, stranger, algorithms=["RS256"]
    )
    assert signin_error(oidc_sign_in(browser, idp, {})) == "invalid_token"
    assert_nobody_signed_in(db, browser)


def test_an_es256_token_from_a_provider_that_publishes_ec_keys_is_accepted(
    browser: TestClient, idps: Idps
) -> None:
    idp = idps["osm"]
    assert isinstance(idp, FakeIdP)
    idp.rotate(ECKey.generate_key("P-256", auto_kid=True))
    assert signin_error(oidc_sign_in(browser, idp, {})) is None


def test_rotated_keys_are_fetched_again(
    app: FastAPI, client_for: ClientFor, idps: Idps, rsa_keys: list[RSAKey]
) -> None:
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    assert idp.jwks_route is not None
    assert signin_error(oidc_sign_in(client_for(app), idp, {"sub": "one"})) is None
    assert idp.jwks_route.call_count == 1
    # Later, the provider starts signing with a key we haven't seen.
    later = time.time() + JWKS_MIN_REFRESH_S + 1
    idp.rotate(rsa_keys[1])
    with time_machine.travel(later, tick=False):
        assert signin_error(oidc_sign_in(client_for(app), idp, {"sub": "two"})) is None
        assert idp.jwks_route.call_count == 2
        # The new key is cached now.
        assert signin_error(oidc_sign_in(client_for(app), idp, {"sub": "three"})) is None
        assert idp.jwks_route.call_count == 2
    # A token still signed with the retired key no longer verifies.
    idp.forge = lambda claims: idp.id_token(claims, key=rsa_keys[0])
    with time_machine.travel(later + 1, tick=False):
        assert signin_error(oidc_sign_in(client_for(app), idp, {"sub": "four"})) == "invalid_token"


def test_unknown_key_ids_fetch_the_key_set_at_most_once_a_minute(
    app: FastAPI, client_for: ClientFor, idps: Idps, rsa_keys: list[RSAKey]
) -> None:
    idp = idps["google"]
    assert isinstance(idp, FakeIdP)
    assert idp.jwks_route is not None
    stranger = rsa_keys[2]
    idp.forge = lambda claims: idp.id_token(claims, key=stranger)
    for _ in range(3):
        assert signin_error(oidc_sign_in(client_for(app), idp, {})) == "invalid_token"
    assert idp.jwks_route.call_count == 1
    with time_machine.travel(time.time() + JWKS_MIN_REFRESH_S + 1, tick=False):
        for _ in range(3):
            assert signin_error(oidc_sign_in(client_for(app), idp, {})) == "invalid_token"
    assert idp.jwks_route.call_count == 2


def test_a_discovery_document_that_names_another_issuer_is_refused(
    browser: TestClient, idps: Idps, mock_http: respx.MockRouter
) -> None:
    mock_http.get("https://accounts.google.com/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": "https://evil.example",
                "authorization_endpoint": "https://evil.example/a",
                "token_endpoint": "https://evil.example/t",
                "jwks_uri": "https://evil.example/k",
            },
        )
    )
    response = start(browser, "google")
    assert response.status_code == 303
    assert query_of(response.headers["location"])["signin_error"] == "provider_error"


def test_microsofts_issuer_must_carry_the_tokens_own_tenant(
    browser: TestClient, idps: Idps, db: Session
) -> None:
    idp = idps["microsoft"]
    assert isinstance(idp, FakeIdP)
    other = "72f988bf-86f1-41af-91ab-2d7cd011db47"
    # An issuer for one tenant on a token claiming another.
    assert signin_error(oidc_sign_in(browser, idp, {"tid": other})) == "invalid_token"
    assert signin_error(oidc_sign_in(browser, idp, {"tid": "not-a-guid"})) == "invalid_token"
    assert signin_error(oidc_sign_in(browser, idp, {"tid": None})) == "invalid_token"
    assert count(db, User) == 0
    issuer = f"https://login.microsoftonline.com/{other}/v2.0"
    assert signin_error(oidc_sign_in(browser, idp, {"tid": other, "iss": issuer})) is None
    assert MICROSOFT_TENANT not in issuer


# --------------------------------------------------------------------------
# Linking by email
# --------------------------------------------------------------------------


@pytest.fixture
def ann(make_user: MakeUser) -> User:
    """An existing member whose address is verified."""
    return make_user(
        handle="AnnExisting", email="ann@example.org", email_verified_at=datetime(2026, 1, 1, tzinfo=UTC)
    )


def me(browser: TestClient) -> dict[str, Any]:
    response = browser.get("/api/v1/auth/me")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("provider", ["google", "apple"])
def test_a_verified_email_links_to_the_account_that_has_it_verified(
    provider: str, browser: TestClient, idps: Idps, ann: User, db: Session
) -> None:
    assert signin_error(complete(browser, idps, provider)) is None
    assert me(browser)["handle"] == "AnnExisting"
    assert count(db, User) == 1
    identity = db.scalars(select(AuthIdentity)).one()
    assert identity.user_id == ann.id


def test_microsoft_links_only_when_the_domain_owner_verified_the_address(
    app: FastAPI, client_for: ClientFor, idps: Idps, ann: User, db: Session
) -> None:
    unverified = client_for(app)
    complete(unverified, idps, "microsoft")
    assert me(unverified)["handle"] != "AnnExisting"
    verified = client_for(app)
    complete(verified, idps, "microsoft", {"sub": "m-ann-2", "email": "ann@example.org", "xms_edov": True})
    assert me(verified)["handle"] == "AnnExisting"


@pytest.mark.parametrize(
    ("provider", "claims"),
    [
        pytest.param(
            "google", {"sub": "g-x", "email": "ann@example.org", "email_verified": False}, id="google-false"
        ),
        pytest.param(
            "google", {"sub": "g-x", "email": "ann@example.org", "email_verified": "true"}, id="google-str"
        ),
        pytest.param("google", {"sub": "g-x", "email": "ann@example.org"}, id="google-absent"),
        pytest.param(
            "apple", {"sub": "a-x", "email": "ann@example.org", "email_verified": "false"}, id="apple-false"
        ),
        pytest.param("microsoft", {"sub": "m-x", "email": "ann@example.org"}, id="microsoft"),
        pytest.param("osm", {"sub": "o-x", "email": "ann@example.org", "email_verified": True}, id="osm"),
        pytest.param("facebook", ANN["facebook"], id="facebook"),
    ],
)
def test_an_unverified_email_never_links_or_lands_on_the_new_account(
    provider: str, claims: dict[str, Any], browser: TestClient, idps: Idps, ann: User, db: Session
) -> None:
    assert signin_error(complete(browser, idps, provider, claims)) is None
    mine = me(browser)
    assert mine["handle"] != "AnnExisting"
    assert mine["email"] is None
    assert count(db, User) == 2
    db.refresh(ann)
    assert ann.email == "ann@example.org"
    identity = db.scalars(select(AuthIdentity)).one()
    assert identity.user_id != ann.id


def test_a_verified_email_does_not_link_to_an_account_holding_it_unverified(
    browser: TestClient, idps: Idps, make_user: MakeUser, db: Session
) -> None:
    holder = make_user(handle="Holder", email="ann@example.org")
    assert signin_error(complete(browser, idps, "google")) is None
    mine = me(browser)
    assert mine["handle"] != "Holder"
    # The address stays with whoever had it.
    assert mine["email"] is None
    db.refresh(holder)
    assert holder.email == "ann@example.org"


# --------------------------------------------------------------------------
# Apple's cross-site POST and the client-header exemption
# --------------------------------------------------------------------------


def test_apples_callback_is_a_post_without_the_client_header(
    app: FastAPI, client_for: ClientFor, idps: Idps, db: Session
) -> None:
    # A browser following Apple's form post sends no X-FieldClub-Client header.
    browser = client_for(app, with_header=False)
    response = complete(browser, idps, "apple")
    assert signin_error(response) is None
    assert browser.get("/api/v1/auth/me").json()["display_name"] == "Ann Barrow"


def test_apples_posted_form_is_still_guarded_by_state(
    app: FastAPI, client_for: ClientFor, idps: Idps, db: Session
) -> None:
    attacker, victim = client_for(app), client_for(app, with_header=False)
    started = start(attacker, "apple")
    code, state = idps["apple"].authorise(started.headers["location"], ANN["apple"])
    response = callback(victim, "apple", method="POST", code=code, state=state, user=APPLE_USER)
    assert signin_error(response) == "state_mismatch"
    assert_nobody_signed_in(db, victim)


def test_apples_name_is_taken_from_the_first_sign_in_only(
    app: FastAPI, client_for: ClientFor, idps: Idps
) -> None:
    first = client_for(app, with_header=False)
    complete(first, idps, "apple")
    later = client_for(app, with_header=False)
    renamed = json.dumps({"name": {"firstName": "Someone", "lastName": "Else"}})
    complete(later, idps, "apple", user=renamed)
    assert me(later)["display_name"] == "Ann Barrow"


@pytest.mark.parametrize("user_field", ["not json", "[]", '{"name": "Ann"}', "{}", json.dumps({"name": {}})])
def test_a_malformed_apple_user_field_leaves_the_generated_name(
    user_field: str, app: FastAPI, client_for: ClientFor, idps: Idps
) -> None:
    browser = client_for(app, with_header=False)
    assert signin_error(complete(browser, idps, "apple", user=user_field)) is None
    mine = me(browser)
    assert mine["display_name"] == mine["handle"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/auth/oauth/google/callback"),
        ("POST", "/api/v1/auth/oauth/osm/callback"),
        ("POST", "/api/v1/auth/oauth/facebook/callback"),
        ("POST", "/api/v1/auth/oauth/microsoft/callback"),
        ("POST", "/api/v1/auth/oauth/apple/callback/"),
        ("POST", "/api/v1/auth/oauth/apple/callbackx"),
        ("POST", "/api/v1/auth/oauth/APPLE/callback"),
        ("POST", "/api/v1/auth/oauth/apple/start"),
        ("POST", "/api/v1/auth/oauth/apple/callback/../../../welcome"),
        ("POST", "/api/v1/auth/oauth/apple/callback%2F..%2F..%2F..%2Fwelcome"),
        ("POST", "/x/api/v1/auth/oauth/apple/callback"),
        ("POST", "/api/v1/auth/welcome"),
        ("POST", "/api/v1/auth/email/start"),
        ("POST", "/api/v1/auth/logout"),
        ("PUT", "/api/v1/auth/oauth/apple/callback"),
        ("PATCH", "/api/v1/auth/oauth/apple/callback"),
        ("DELETE", "/api/v1/auth/oauth/apple/callback"),
    ],
)
def test_nothing_but_a_post_to_apples_callback_skips_the_client_header(
    method: str, path: str, app: FastAPI, client_for: ClientFor, idps: Idps
) -> None:
    bare = client_for(app, with_header=False)
    response = bare.request(method, path, follow_redirects=False)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "client_header_required"


def test_the_exempt_paths_are_exactly_apples_callback() -> None:
    from fieldclub.main import CLIENT_HEADER_EXEMPT

    assert CLIENT_HEADER_EXEMPT == (r"/api/v1/auth/oauth/apple/callback",)


def test_the_callback_path_the_providers_are_given_is_the_routed_one(browser: TestClient) -> None:
    from fieldclub.auth.oauth import CALLBACK_PATH

    paths = browser.get("/api/openapi.json").json()["paths"]
    assert set(paths[CALLBACK_PATH]) == {"get", "post"}
    assert set(paths[CALLBACK_PATH.replace("callback", "start")]) == {"get"}


# --------------------------------------------------------------------------
# Where sign-in lands: never off this site
# --------------------------------------------------------------------------

OPEN_REDIRECTS = [
    "https://evil.example/",
    "http://evil.example",
    "//evil.example",
    "//evil.example/f/1",
    "///evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "\\/evil.example",
    "/\\/evil.example",
    "/%5Cevil.example",
    "/%5cevil.example",
    "/%2F%2Fevil.example",
    "/%2f/evil.example",
    "/%252F%252Fevil.example",
    "/%25252F%25252Fevil.example",
    "%2F%2Fevil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "/\r\n/evil.example",
    "/\x00/evil.example",
    "/%09/evil.example",
    "/%0a/evil.example",
    "/%00",
    "/\u202e/evil",
    "/\u3000/evil",
    "/ /evil.example",
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,hi",
    "evil.example",
    "f/7K3QXM",
    "",
    "/" + "a" * 2001,
]


@pytest.mark.parametrize("target", OPEN_REDIRECTS)
def test_an_unsafe_next_lands_at_the_home_page(target: str, browser: TestClient, idps: Idps) -> None:
    response = complete(browser, idps, "google", next_path=target)
    assert signin_error(response) is None
    assert response.headers["location"] == f"{PUBLIC_URL}/"


@pytest.mark.parametrize("target", OPEN_REDIRECTS[:8])
def test_an_unsafe_next_lands_at_the_home_page_on_failure_too(
    target: str, browser: TestClient, idps: Idps
) -> None:
    started = start(browser, "google", target)
    code, _ = idps["google"].authorise(started.headers["location"], ANN["google"])
    response = callback(browser, "google", code=code, state="forged")
    assert response.headers["location"] == f"{PUBLIC_URL}/?signin_error=state_mismatch"


@pytest.mark.parametrize(
    "target",
    ["/", "/f/7K3QXM", "/f/7K3QXM?layer=slope&zoom=16", "/u/QuietBarrow42#findings", "/review", "/f/a%20b"],
)
def test_a_relative_next_is_kept(target: str, browser: TestClient, idps: Idps) -> None:
    response = complete(browser, idps, "google", next_path=target)
    assert response.headers["location"] == PUBLIC_URL + target


def test_a_failure_returns_to_next_with_only_a_short_code(browser: TestClient, idps: Idps) -> None:
    started = start(browser, "google", "/f/7K3QXM?layer=slope")
    code, _ = idps["google"].authorise(started.headers["location"], ANN["google"])
    response = callback(browser, "google", code=code, state="forged")
    assert response.status_code == 303
    assert response.headers["location"] == f"{PUBLIC_URL}/f/7K3QXM?layer=slope&signin_error=state_mismatch"
    assert response.content == b""


# --------------------------------------------------------------------------
# Who may sign in
# --------------------------------------------------------------------------


def test_a_banned_account_cannot_sign_in(browser: TestClient, idps: Idps, db: Session) -> None:
    complete(browser, idps, "google")
    user = db.scalars(select(User)).one()
    user.banned_at = datetime(2026, 6, 1, tzinfo=UTC)
    db.commit()
    browser.cookies.clear()
    assert signin_error(complete(browser, idps, "google")) == "banned"
    assert SESSION_COOKIE not in browser.cookies


def test_a_banned_account_cannot_be_reached_through_a_linked_email(
    browser: TestClient, idps: Idps, ann: User, db: Session
) -> None:
    ann.banned_at = datetime(2026, 6, 1, tzinfo=UTC)
    db.commit()
    assert signin_error(complete(browser, idps, "google")) == "banned"
    assert count(db, AuthIdentity) == 0
    assert count(db, User) == 1
    assert count(db, UserSession) == 0


def test_a_deleted_account_cannot_sign_in(browser: TestClient, idps: Idps, db: Session) -> None:
    complete(browser, idps, "google")
    user = db.scalars(select(User)).one()
    # Marked deleted without going through delete_account, so the identity is still there.
    user.deleted_at = datetime(2026, 6, 1, tzinfo=UTC)
    db.commit()
    browser.cookies.clear()
    assert signin_error(complete(browser, idps, "google")) == "account_deleted"
    assert SESSION_COOKIE not in browser.cookies


def test_after_deleting_an_account_the_same_person_starts_afresh(
    browser: TestClient, idps: Idps, db: Session
) -> None:
    complete(browser, idps, "google")
    old = db.scalars(select(User)).one()
    accounts.delete_account(db, old)
    db.commit()
    browser.cookies.clear()
    assert signin_error(complete(browser, idps, "google")) is None
    mine = me(browser)
    assert mine["handle"] != old.handle
    assert mine["needs_welcome"] is True
    db.refresh(old)
    assert old.is_deleted
    assert count(db, User) == 2


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


def test_a_session_presented_before_sign_in_is_ended_not_reused(
    app: FastAPI, client_for: ClientFor, idps: Idps, make_user: MakeUser, db: Session
) -> None:
    someone = make_user(handle="Someone")
    browser = client_for(app, someone)
    before = browser.cookies[SESSION_COOKIE]
    response = complete(browser, idps, "google")
    assert signin_error(response) is None
    after = issued_session(response)
    assert after != before
    assert db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(before))).first() is None
    signed_in = client_for(app)
    signed_in.cookies.set(SESSION_COOKIE, after)
    assert me(signed_in)["display_name"] == "Ann Barrow"
    # The old token signs nobody in any more.
    stale = client_for(app)
    stale.cookies.set(SESSION_COOKIE, before)
    assert stale.get("/api/v1/auth/me").status_code == 401


def test_apple_ends_the_session_the_browser_had_at_start_though_its_post_carries_no_cookie(
    app: FastAPI, client_for: ClientFor, idps: Idps, make_user: MakeUser, db: Session
) -> None:
    """Apple's callback is a cross-site POST, which a SameSite=Lax session cookie doesn't reach."""
    browser = client_for(app, make_user(handle="Someone"), with_header=False)
    before = browser.cookies[SESSION_COOKIE]
    started = start(browser, "apple")
    code, state = idps["apple"].authorise(started.headers["location"], ANN["apple"])
    # What the browser does on Apple's form post: the Lax session cookie stays home.
    browser.cookies.delete(SESSION_COOKIE)
    response = callback(browser, "apple", method="POST", code=code, state=state, user=APPLE_USER)
    assert signin_error(response) is None
    assert issued_session(response) != before
    assert db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(before))).first() is None


def test_a_planted_session_token_is_never_adopted(app: FastAPI, client_for: ClientFor, idps: Idps) -> None:
    browser = client_for(app)
    planted = "planted-token-" + "x" * 30
    browser.cookies.set(SESSION_COOKIE, planted)
    issued = issued_session(complete(browser, idps, "google"))
    assert issued != planted
    assert len(issued) >= 43


# --------------------------------------------------------------------------
# Providers that are off, cancelled, or not answering
# --------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["myspace", "email", "guest", "GOOGLE"])
def test_an_unknown_provider_redirects_with_a_code(provider: str, browser: TestClient, idps: Idps) -> None:
    response = start(browser, provider, "/f/1")
    assert response.status_code == 303
    assert response.headers["location"] == f"{PUBLIC_URL}/f/1?signin_error=provider_unavailable"
    assert "fieldclub_oauth" not in response.headers.get("set-cookie", "")
    assert signin_error(callback(browser, provider, code="c", state="s")) == "provider_unavailable"


def test_a_provider_without_its_settings_is_unavailable(
    browser: TestClient, env: Any, mock_http: respx.MockRouter
) -> None:
    env(PUBLIC_URL=PUBLIC_URL, GOOGLE_CLIENT_ID="only-the-id")
    response = start(browser, "google")
    assert query_of(response.headers["location"])["signin_error"] == "provider_unavailable"
    assert not mock_http.calls


def test_cancelling_at_the_provider_is_reported_as_cancelled(
    browser: TestClient, idps: Idps, db: Session
) -> None:
    started = start(browser, "google")
    state = query_of(started.headers["location"])["state"]
    response = callback(browser, "google", error="access_denied", state=state)
    assert signin_error(response) == "cancelled"
    assert_nobody_signed_in(db, browser)


def test_a_provider_error_is_reported_without_detail(browser: TestClient, idps: Idps) -> None:
    started = start(browser, "google")
    state = query_of(started.headers["location"])["state"]
    response = callback(browser, "google", error="server_error<script>", state=state)
    assert response.headers["location"] == f"{PUBLIC_URL}/?signin_error=provider_error"


def test_a_token_endpoint_that_is_down_is_a_provider_error(
    browser: TestClient, idps: Idps, mock_http: respx.MockRouter, db: Session
) -> None:
    mock_http.post("https://accounts.google.com/token").mock(side_effect=httpx.ConnectError("down"))
    assert signin_error(complete(browser, idps, "google")) == "provider_error"
    mock_http.post("https://accounts.google.com/token").mock(
        return_value=httpx.Response(500, text="Traceback")
    )
    assert signin_error(complete(browser, idps, "google")) == "provider_error"
    mock_http.post("https://accounts.google.com/token").mock(
        return_value=httpx.Response(200, text="not json")
    )
    assert signin_error(complete(browser, idps, "google")) == "provider_error"
    assert_nobody_signed_in(db, browser)


def test_discovery_that_is_down_is_a_provider_error_at_the_start(
    browser: TestClient, idps: Idps, mock_http: respx.MockRouter
) -> None:
    mock_http.get("https://accounts.google.com/.well-known/openid-configuration").mock(
        return_value=httpx.Response(503)
    )
    response = start(browser, "google", "/f/1")
    assert response.headers["location"] == f"{PUBLIC_URL}/f/1?signin_error=provider_error"


def test_an_unexpected_failure_is_a_redirect_not_a_stack_trace(
    browser: TestClient,
    idps: Idps,
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(*args: Any, **kwargs: Any) -> User:
        raise RuntimeError("database fell over")

    monkeypatch.setattr(signin, "user_for_identity", explode)
    response = complete(browser, idps, "google")
    assert response.headers["location"] == f"{PUBLIC_URL}/?signin_error=signin_failed"
    assert b"database fell over" not in response.content
    assert "database fell over" not in response.headers["location"]
    assert "database fell over" in caplog.text
    assert_nobody_signed_in(db, browser)


def test_facebook_is_called_with_an_appsecret_proof(browser: TestClient, idps: Idps) -> None:
    complete(browser, idps, "facebook")
    facebook = idps["facebook"]
    assert isinstance(facebook, FakeFacebook)
    (request,) = facebook.profile_requests
    assert request.headers["authorization"].startswith("Bearer fb-")
    assert len(query_of(str(request.url))["appsecret_proof"]) == 64
    assert "access_token" not in query_of(str(request.url))


def test_facebook_without_a_picture_gives_no_avatar(browser: TestClient, idps: Idps) -> None:
    profile = {
        "id": "2",
        "name": "No Face",
        "picture": {"data": {"url": "https://fb/s.jpg", "is_silhouette": True}},
    }
    complete(browser, idps, "facebook", profile)
    assert me(browser)["avatar_url"] is None


# --------------------------------------------------------------------------
# /meta
# --------------------------------------------------------------------------


def test_meta_lists_all_six_methods_enabled_once_configured(browser: TestClient, providers_on: None) -> None:
    listed = browser.get("/api/v1/meta").json()["auth"]["providers"]
    assert [(item["id"], item["enabled"]) for item in listed] == [
        ("google", True),
        ("apple", True),
        ("microsoft", True),
        ("facebook", True),
        ("osm", True),
        ("email", True),
    ]


def test_meta_lists_all_six_methods_disabled_without_settings(browser: TestClient) -> None:
    listed = browser.get("/api/v1/meta").json()["auth"]["providers"]
    assert [item["id"] for item in listed] == ["google", "apple", "microsoft", "facebook", "osm", "email"]
    assert not any(item["enabled"] for item in listed)


@pytest.mark.parametrize(
    ("provider", "settings"),
    [
        ("google", {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret"}),
        ("microsoft", {"MICROSOFT_CLIENT_ID": "id", "MICROSOFT_CLIENT_SECRET": "secret"}),
        (
            "apple",
            {"APPLE_CLIENT_ID": "id", "APPLE_TEAM_ID": "t", "APPLE_KEY_ID": "k", "APPLE_PRIVATE_KEY": "p"},
        ),
        ("facebook", {"FACEBOOK_APP_ID": "id", "FACEBOOK_APP_SECRET": "secret"}),
        ("osm", {"OSM_CLIENT_ID": "id", "OSM_CLIENT_SECRET": "secret"}),
        ("email", {"MAIL_BACKEND": "log"}),
    ],
)
def test_each_method_is_enabled_by_its_own_settings_and_only_all_of_them(
    provider: str, settings: dict[str, str], browser: TestClient, env: Any
) -> None:
    def enabled() -> set[str]:
        listed = browser.get("/api/v1/meta").json()["auth"]["providers"]
        return {item["id"] for item in listed if item["enabled"]}

    names = list(settings)
    env(**{name: settings[name] for name in names[:-1]})
    assert enabled() == set()
    env(**settings)
    assert enabled() == {provider}
