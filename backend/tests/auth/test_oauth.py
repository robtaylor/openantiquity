"""The provider adapters' quirks, without HTTP."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from joserfc import jwt
from joserfc.jwk import ECKey

from fieldclub.auth import oauth
from fieldclub.auth.failures import InvalidIdentityError, ProviderUnavailableError
from fieldclub.auth.oidc import Discovery
from fieldclub.errors import ConfigError
from fieldclub.vocab import SignInProvider
from tests.auth.conftest import APPLE_KEY_ID, APPLE_TEAM, MICROSOFT_TENANT
from tests.helpers import settings

NOW = 1_800_000_000


def apple_settings(team_key: ECKey, *, escaped: bool = False):
    pem = team_key.as_pem(private=True).decode()
    if escaped:
        pem = pem.replace("\n", "\\n")
    return settings(
        apple_client_id="test.fieldclub.signin",
        apple_team_id=APPLE_TEAM,
        apple_key_id=APPLE_KEY_ID,
        apple_private_key=pem,
    )


@pytest.mark.parametrize("escaped", [False, True])
def test_apples_client_secret_is_a_short_lived_es256_token(apple_team_key: ECKey, escaped: bool) -> None:
    secret = oauth.apple_client_secret(apple_settings(apple_team_key, escaped=escaped), now=NOW)
    token = jwt.decode(secret, apple_team_key, algorithms=["ES256"])
    assert token.header == {"alg": "ES256", "kid": APPLE_KEY_ID, "typ": "JWT"}
    assert token.claims == {
        "iss": APPLE_TEAM,
        "iat": NOW,
        "exp": NOW + oauth.APPLE_CLIENT_SECRET_LIFETIME_S,
        "aud": "https://appleid.apple.com",
        "sub": "test.fieldclub.signin",
    }
    assert oauth.APPLE_CLIENT_SECRET_LIFETIME_S <= 600


def test_an_unreadable_apple_key_is_a_configuration_error() -> None:
    broken = settings(apple_client_id="c", apple_team_id="t", apple_key_id="k", apple_private_key="not a key")
    with pytest.raises(ConfigError, match="APPLE_PRIVATE_KEY"):
        oauth.apple_client_secret(broken)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        (json.dumps({"name": {"firstName": "Ann", "lastName": "Barrow"}}), "Ann Barrow"),
        (json.dumps({"name": {"firstName": "Ann"}}), "Ann"),
        (json.dumps({"name": {"lastName": " Barrow "}}), "Barrow"),
        (json.dumps({"name": {"firstName": 7}}), None),
        (json.dumps({"email": "x@y"}), None),
        ("null", None),
        ("not json", None),
        ("", None),
        (None, None),
        ("x" * (oauth.MAX_APPLE_USER_FIELD + 1), None),
    ],
)
def test_apples_name_is_read_from_the_user_field(field: str | None, expected: str | None) -> None:
    assert oauth.apple_name(field) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        ("true", True),
        (False, False),
        ("false", False),
        ("True", False),
        (1, False),
        (None, False),
    ],
)
def test_a_boolean_claim_may_arrive_as_a_string(value: object, expected: bool) -> None:
    assert oauth.claim_is_true(value) is expected


def test_apple_takes_the_identity_tokens_email_not_the_forms() -> None:
    form = json.dumps({"name": {"firstName": "Ann"}, "email": "spoofed@evil.example"})
    identity = oauth.Apple().identity(
        {"sub": "a-1", "email": "ann@privaterelay.appleid.com", "email_verified": "true"},
        oauth.Callback(user=form),
    )
    assert identity.email == "ann@privaterelay.appleid.com"
    assert identity.email_verified is True
    assert identity.display_name == "Ann"


TEMPLATE = Discovery(
    issuer="https://login.microsoftonline.com/{tenantid}/v2.0",
    authorization_endpoint="https://a",
    token_endpoint="https://t",
    jwks_uri="https://k",
)


def test_microsofts_issuer_template_is_filled_from_the_tokens_tenant() -> None:
    assert oauth._microsoft_issuers(TEMPLATE, {"tid": MICROSOFT_TENANT}) == (
        f"https://login.microsoftonline.com/{MICROSOFT_TENANT}/v2.0",
    )
    for tid in (None, "", "common", "../evil", MICROSOFT_TENANT.upper(), 7):
        assert oauth._microsoft_issuers(TEMPLATE, {"tid": tid}) == ()


def test_a_single_tenant_issuer_is_used_as_it_stands() -> None:
    single = Discovery(
        f"https://login.microsoftonline.com/{MICROSOFT_TENANT}/v2.0", "https://a", "https://t", "https://k"
    )
    assert oauth._microsoft_issuers(single, {"tid": "anything"}) == (single.issuer,)


def test_a_single_tenant_setting_expects_that_tenant_in_discovery() -> None:
    client = oauth.Microsoft().oidc(settings(microsoft_tenant=MICROSOFT_TENANT))
    assert client.expected_issuer == f"https://login.microsoftonline.com/{MICROSOFT_TENANT}/v2.0"
    assert client.discovery_url.startswith(f"https://login.microsoftonline.com/{MICROSOFT_TENANT}/")


@pytest.mark.parametrize("tenant", ["contoso.onmicrosoft.com", "../common", "COMMON", ""])
def test_the_microsoft_tenant_setting_is_checked(tenant: str) -> None:
    with pytest.raises(ValueError, match="microsoft_tenant"):
        settings(microsoft_tenant=tenant)


@pytest.mark.parametrize(
    ("claims", "verified"),
    [
        ({"sub": "m", "email": "a@b.c"}, False),
        ({"sub": "m", "email": "a@b.c", "xms_edov": True}, True),
        ({"sub": "m", "email": "a@b.c", "xms_edov": "true"}, True),
        ({"sub": "m", "email": "a@b.c", "xms_edov": False}, False),
        # A plain `email_verified`, which claims mapping could add, is not the domain owner's word.
        ({"sub": "m", "email": "a@b.c", "email_verified": True}, False),
        ({"sub": "m", "email": "a@b.c", "email_verified": True, "xms_edov": False}, False),
    ],
)
def test_microsoft_email_is_verified_only_with_the_domain_owner_flag(claims: dict, verified: bool) -> None:
    assert oauth.Microsoft().identity(claims, oauth.Callback()).email_verified is verified


def test_openstreetmap_gives_a_subject_and_a_username_and_no_email() -> None:
    identity = oauth.OpenStreetMap().identity(
        {"sub": "12345", "preferred_username": "annmaps", "email": "a@b.c", "email_verified": True},
        oauth.Callback(),
    )
    assert identity == oauth.ProviderIdentity(SignInProvider.OSM, "12345", display_name="annmaps")


@pytest.mark.parametrize("sub", [None, "", "   ", "x" * (oauth.MAX_SUBJECT + 1), ["a"], True])
def test_an_identity_needs_a_usable_subject(sub: object) -> None:
    with pytest.raises(InvalidIdentityError):
        oauth.Google().identity({"sub": sub}, oauth.Callback())


def test_only_well_formed_addresses_are_kept_and_no_picture() -> None:
    identity = oauth.Google().identity(
        {"sub": "g", "email": "not-an-address", "email_verified": True, "picture": "https://x/a.png"},
        oauth.Callback(),
    )
    assert identity.email is None
    assert not hasattr(identity, "avatar_url")


@pytest.mark.parametrize("name", ["google", "apple", "microsoft", "facebook", "osm"])
def test_a_provider_is_unavailable_without_its_settings(name: str) -> None:
    with pytest.raises(ProviderUnavailableError):
        oauth.get_provider(name, settings())


def test_every_provider_is_available_with_its_settings(providers_on: None) -> None:
    from fieldclub.config import get_settings

    for name in ("google", "apple", "microsoft", "facebook", "osm"):
        assert oauth.get_provider(name, get_settings()).id == SignInProvider(name)


def test_only_apple_returns_with_a_cross_site_post() -> None:
    assert [p.id for p in oauth.PROVIDERS.values() if p.form_post] == [SignInProvider.APPLE]
    assert oauth.FORM_POST_CALLBACK_PATHS == ("/api/v1/auth/oauth/apple/callback",)


def test_every_provider_except_email_has_an_adapter() -> None:
    assert set(oauth.PROVIDERS) == set(SignInProvider) - {SignInProvider.EMAIL}


def test_the_redirect_address_is_on_the_public_url(env: Callable[..., None]) -> None:
    config = settings(public_url="https://fieldclub.example/")
    assert (
        oauth.redirect_uri(config, SignInProvider.GOOGLE)
        == "https://fieldclub.example/api/v1/auth/oauth/google/callback"
    )
