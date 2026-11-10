"""Fixtures for sign-in tests: keys made here, and every provider faked through respx."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import respx
from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from fieldclub.auth import oidc
from fieldclub.auth.mailer import LogMailer
from tests.auth.fakes import PUBLIC_URL, FakeFacebook, FakeIdP

MICROSOFT_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
APPLE_TEAM = "TEAM123456"
APPLE_KEY_ID = "KEY1234567"


@pytest.fixture(scope="session")
def rsa_keys() -> list[RSAKey]:
    """Signing keys for the fake providers. Made once, because RSA key generation is slow."""
    return [RSAKey.generate_key(2048, auto_kid=True) for _ in range(3)]


@pytest.fixture(scope="session")
def apple_team_key() -> ECKey:
    """The team's private key that signs Apple client secrets."""
    return ECKey.generate_key("P-256", auto_kid=True)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    oidc.reset_caches()
    LogMailer.outbox.clear()
    yield
    oidc.reset_caches()
    LogMailer.outbox.clear()


@pytest.fixture
def mock_http() -> Iterator[respx.MockRouter]:
    """Every outbound request is answered by a fake, and anything unexpected fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
def providers_on(env: Callable[..., None], apple_team_key: ECKey) -> None:
    """Settings for all six sign-in methods."""
    env(
        PUBLIC_URL=PUBLIC_URL,
        GOOGLE_CLIENT_ID="google-client",
        GOOGLE_CLIENT_SECRET="google-secret",
        MICROSOFT_CLIENT_ID="microsoft-client",
        MICROSOFT_CLIENT_SECRET="microsoft-secret",
        APPLE_CLIENT_ID="test.fieldclub.signin",
        APPLE_TEAM_ID=APPLE_TEAM,
        APPLE_KEY_ID=APPLE_KEY_ID,
        APPLE_PRIVATE_KEY=apple_team_key.as_pem(private=True).decode(),
        FACEBOOK_APP_ID="facebook-app",
        FACEBOOK_APP_SECRET="facebook-secret",
        OSM_CLIENT_ID="osm-client",
        OSM_CLIENT_SECRET="osm-secret",
        MAIL_BACKEND="log",
    )


def _check_apple_secret(team_key: ECKey) -> Callable[[str], None]:
    def check(secret: str) -> None:
        token = jwt.decode(secret, team_key, algorithms=["ES256"])
        assert token.header["kid"] == APPLE_KEY_ID
        claims = token.claims
        assert claims["iss"] == APPLE_TEAM
        assert claims["sub"] == "test.fieldclub.signin"
        assert claims["aud"] == "https://appleid.apple.com"
        assert 0 < claims["exp"] - claims["iat"] <= 600, "Apple's client secret should be short-lived"

    return check


@pytest.fixture
def idps(
    providers_on: None, mock_http: respx.MockRouter, rsa_keys: list[RSAKey], apple_team_key: ECKey
) -> dict[str, FakeIdP | FakeFacebook]:
    """A fake for every provider, installed and matching `providers_on`."""
    key = rsa_keys[0]
    fakes: dict[str, FakeIdP | FakeFacebook] = {
        "google": FakeIdP(
            provider="google",
            issuer="https://accounts.google.com",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id="google-client",
            client_secret="google-secret",
            keys=[key],
            signing_key=key,
        ),
        "microsoft": FakeIdP(
            provider="microsoft",
            issuer=f"https://login.microsoftonline.com/{MICROSOFT_TENANT}/v2.0",
            discovery_issuer="https://login.microsoftonline.com/{tenantid}/v2.0",
            discovery_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            client_id="microsoft-client",
            client_secret="microsoft-secret",
            keys=[key],
            signing_key=key,
            extra_claims={"tid": MICROSOFT_TENANT},
        ),
        "apple": FakeIdP(
            provider="apple",
            issuer="https://appleid.apple.com",
            discovery_url="https://appleid.apple.com/.well-known/openid-configuration",
            client_id="test.fieldclub.signin",
            client_secret=None,
            secret_check=_check_apple_secret(apple_team_key),
            keys=[key],
            signing_key=key,
        ),
        "osm": FakeIdP(
            provider="osm",
            issuer="https://www.openstreetmap.org",
            discovery_url="https://www.openstreetmap.org/.well-known/openid-configuration",
            client_id="osm-client",
            client_secret="osm-secret",
            keys=[key],
            signing_key=key,
        ),
        "facebook": FakeFacebook(app_id="facebook-app", app_secret="facebook-secret", version="v23.0"),
    }
    for fake in fakes.values():
        fake.install(mock_http)
    return fakes
