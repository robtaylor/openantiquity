"""Sign-in providers: Google, Microsoft, Apple and OpenStreetMap over OpenID Connect, and Facebook.

Every provider runs the same server-side authorisation-code flow with
`state` and PKCE (see `fieldclub.auth.flow`). Each adapter knows two things:
where to send the browser, and how to turn the callback into a verified
`ProviderIdentity`. Finding or creating the account is `fieldclub.auth.signin`'s
job, and is the same for every provider.

Quirks each adapter handles:

- Google may write its issuer with or without `https://`.
- Microsoft's multi-tenant issuer is a template, `.../{tenantid}/v2.0`, filled
  from the token's `tid`. Its `email` claim is whatever the directory holds and
  is not verified, so an address counts as verified only when the token says
  the domain owner verified it (`xms_edov`). Without that it never links.
- Apple's client secret is a short-lived ES256 token signed with the team's
  private key. Asking for name or email makes Apple return with a cross-site
  POST (`response_mode=form_post`). The name arrives once, in the `user` form
  field of the first sign-in, and only there. `email_verified` may be the
  string "true". Only the identity token's email is used, never the form's.
- OpenStreetMap gives a stable subject and a username, and no email.
- Facebook is plain OAuth 2 with a profile call. It never asserts that an
  address is verified, so its email never links accounts or lands on a user.

A provider is offered only when every setting it needs is present.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import urlencode

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import ECKey

from fieldclub.auth.failures import (
    InvalidIdentityError,
    ProviderError,
    ProviderUnavailableError,
    SignInCancelledError,
)
from fieldclub.auth.flow import Flow
from fieldclub.auth.oidc import Discovery, OidcClient, get_oidc_client, request_json
from fieldclub.auth.providers import register_provider
from fieldclub.config import Settings
from fieldclub.errors import ConfigError
from fieldclub.vocab import SignInProvider

logger = logging.getLogger(__name__)

# Mounted under /api/v1 by fieldclub.main; tests check the two agree.
CALLBACK_PATH = "/api/v1/auth/oauth/{provider}/callback"

MAX_SUBJECT = 255
MAX_EMAIL = 320
MAX_NAME = 200
# Apple's `user` form field is a few dozen bytes of JSON. Anything bigger is not Apple's.
MAX_APPLE_USER_FIELD = 2000

_GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_GUID_PATTERN = re.compile(_GUID)


@dataclass(frozen=True)
class ProviderIdentity:
    """Who the provider says this is. `email_verified` is True only on the provider's word."""

    provider: SignInProvider
    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None


@dataclass(frozen=True)
class Callback:
    """What came back to the callback, from the query string or a posted form."""

    code: str | None = None
    state: str | None = None
    error: str | None = None
    # Apple's first sign-in only: JSON with the person's name.
    user: str | None = None


def callback_path(provider: SignInProvider) -> str:
    """The path a provider returns the browser to, which is also where its flow cookie is sent."""
    return CALLBACK_PATH.format(provider=provider.value)


def redirect_uri(settings: Settings, provider: SignInProvider) -> str:
    return settings.public_url.rstrip("/") + callback_path(provider)


def _secret(value: Any) -> str | None:
    return value.get_secret_value() if value is not None else None


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 0 < len(value) <= limit else None


def _email(value: object) -> str | None:
    email = _text(value, MAX_EMAIL)
    return email if email and email.count("@") == 1 and not email.startswith("@") else None


def _subject(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    subject = _text(value, MAX_SUBJECT)
    if subject is None:
        raise InvalidIdentityError("The provider gave no usable account id.")
    return subject


def claim_is_true(value: object) -> bool:
    """A boolean claim that some providers send as a string: True or "true", nothing else."""
    return value is True or value == "true"


class OAuthProvider:
    """One sign-in provider. Subclasses fill in the specifics."""

    id: ClassVar[SignInProvider]
    scope: ClassVar[str]
    # True when the provider returns with a cross-site POST.
    form_post: ClassVar[bool] = False

    # The names of the settings holding this provider's client id and secret.
    id_setting: ClassVar[str]
    secret_setting: ClassVar[str]

    def is_configured(self, settings: Settings) -> bool:
        return bool(getattr(settings, self.id_setting) and _secret(getattr(settings, self.secret_setting)))

    def client_id(self, settings: Settings) -> str:
        value = getattr(settings, self.id_setting)
        assert value, f"{self.id.value} is only used once {self.id_setting} is set"
        return value

    def client_secret(self, settings: Settings) -> str:
        secret = _secret(getattr(settings, self.secret_setting))
        assert secret, f"{self.id.value} is only used once {self.secret_setting} is set"
        return secret

    def authorization_url(self, settings: Settings, flow: Flow) -> str:
        raise NotImplementedError

    def complete(self, settings: Settings, flow: Flow, callback: Callback) -> ProviderIdentity:
        raise NotImplementedError

    def _authorization_params(self, settings: Settings, flow: Flow) -> dict[str, str]:
        return {
            "response_type": "code",
            "client_id": self.client_id(settings),
            "redirect_uri": redirect_uri(settings, self.id),
            "scope": self.scope,
            "state": flow.state,
            "code_challenge": flow.challenge,
            "code_challenge_method": "S256",
        }

    def _exchange(self, settings: Settings, flow: Flow, token_endpoint: str, code: str) -> dict[str, Any]:
        """Swap the code for tokens. A code that was already spent is refused by the provider."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(settings, self.id),
            "client_id": self.client_id(settings),
            "client_secret": self.client_secret(settings),
            "code_verifier": flow.verifier,
        }
        return request_json("POST", token_endpoint, f"The {self.id.value} token endpoint", data=data)


def _with_query(endpoint: str, params: Mapping[str, str]) -> str:
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}"


def _check_callback(callback: Callback) -> str:
    """The authorisation code, once the callback is known not to be an error."""
    if callback.error:
        if callback.error in ("access_denied", "user_cancelled_authorize"):
            raise SignInCancelledError()
        logger.info("Provider returned error %.100r", callback.error)
        raise ProviderError()
    if not callback.code:
        raise ProviderError("The provider sent no authorisation code.")
    return callback.code


class OidcProvider(OAuthProvider):
    """A provider that speaks OpenID Connect: everything comes from the verified identity token."""

    def oidc(self, settings: Settings) -> OidcClient:
        raise NotImplementedError

    def identity(self, claims: dict[str, Any], callback: Callback) -> ProviderIdentity:
        raise NotImplementedError

    def authorization_url(self, settings: Settings, flow: Flow) -> str:
        discovery = self.oidc(settings).discovery()
        params = self._authorization_params(settings, flow) | {"nonce": flow.nonce}
        return _with_query(discovery.authorization_endpoint, params)

    def complete(self, settings: Settings, flow: Flow, callback: Callback) -> ProviderIdentity:
        code = _check_callback(callback)
        client = self.oidc(settings)
        tokens = self._exchange(settings, flow, client.discovery().token_endpoint, code)
        claims = client.verify_id_token(
            tokens.get("id_token"),
            client_id=self.client_id(settings),
            nonce=flow.nonce,
        )
        return self.identity(claims, callback)


# --------------------------------------------------------------------------
# Google
# --------------------------------------------------------------------------

GOOGLE_ISSUER = "https://accounts.google.com"


def _google_issuers(discovery: Discovery, claims: dict[str, Any]) -> tuple[str, ...]:
    return (discovery.issuer, "accounts.google.com")


class Google(OidcProvider):
    id = SignInProvider.GOOGLE
    scope = "openid email profile"

    id_setting = "google_client_id"
    secret_setting = "google_client_secret"

    def oidc(self, settings: Settings) -> OidcClient:
        return get_oidc_client(
            f"{GOOGLE_ISSUER}/.well-known/openid-configuration",
            expected_issuer=GOOGLE_ISSUER,
            issuers=_google_issuers,
        )

    def identity(self, claims: dict[str, Any], callback: Callback) -> ProviderIdentity:
        return ProviderIdentity(
            provider=self.id,
            subject=_subject(claims.get("sub")),
            email=_email(claims.get("email")),
            email_verified=claims.get("email_verified") is True,
            display_name=_text(claims.get("name"), MAX_NAME),
        )


# --------------------------------------------------------------------------
# Microsoft
# --------------------------------------------------------------------------

MICROSOFT_LOGIN = "https://login.microsoftonline.com"
# What a multi-tenant discovery document calls its issuer, or one tenant's own.
_MICROSOFT_ISSUER = re.compile(re.escape(MICROSOFT_LOGIN) + r"/(\{tenantid\}|" + _GUID + r")/v2\.0")
TENANT_PLACEHOLDER = "{tenantid}"


def _microsoft_issuers(discovery: Discovery, claims: dict[str, Any]) -> tuple[str, ...]:
    """The one issuer this token may carry: the template filled from its own `tid`."""
    if TENANT_PLACEHOLDER not in discovery.issuer:
        return (discovery.issuer,)
    tenant = claims.get("tid")
    if not isinstance(tenant, str) or not _GUID_PATTERN.fullmatch(tenant):
        return ()
    return (discovery.issuer.replace(TENANT_PLACEHOLDER, tenant),)


class Microsoft(OidcProvider):
    id = SignInProvider.MICROSOFT
    scope = "openid email profile"

    id_setting = "microsoft_client_id"
    secret_setting = "microsoft_client_secret"

    def oidc(self, settings: Settings) -> OidcClient:
        tenant = settings.microsoft_tenant
        expected: str | re.Pattern[str] = (
            f"{MICROSOFT_LOGIN}/{tenant}/v2.0" if _GUID_PATTERN.fullmatch(tenant) else _MICROSOFT_ISSUER
        )
        return get_oidc_client(
            f"{MICROSOFT_LOGIN}/{tenant}/v2.0/.well-known/openid-configuration",
            expected_issuer=expected,
            issuers=_microsoft_issuers,
        )

    def identity(self, claims: dict[str, Any], callback: Callback) -> ProviderIdentity:
        # `email` is a directory attribute anyone with admin rights in a tenant
        # can set to any address. Trust it only with the domain-owner flag.
        verified = claim_is_true(claims.get("xms_edov"))
        return ProviderIdentity(
            provider=self.id,
            subject=_subject(claims.get("sub")),
            email=_email(claims.get("email")),
            email_verified=verified,
            display_name=_text(claims.get("name"), MAX_NAME),
        )


# --------------------------------------------------------------------------
# Apple
# --------------------------------------------------------------------------

APPLE_ISSUER = "https://appleid.apple.com"
# Apple allows up to six months. A few minutes is all one exchange needs.
APPLE_CLIENT_SECRET_LIFETIME_S = 300


def apple_client_secret(settings: Settings, *, now: int | None = None) -> str:
    """The ES256 token Apple takes as a client secret, signed with the team's private key."""
    pem = _secret(settings.apple_private_key)
    assert pem, "Apple is only offered with a private key"
    assert settings.apple_key_id
    assert settings.apple_team_id
    assert settings.apple_client_id
    # A key pasted into one environment variable often has its line breaks escaped.
    pem = pem.replace("\\n", "\n")
    try:
        key = ECKey.import_key(pem)
    except (JoseError, ValueError, TypeError) as exc:
        raise ConfigError("FIELDCLUB_APPLE_PRIVATE_KEY is not an EC private key in PEM form.") from exc
    issued = int(time.time()) if now is None else now
    return jwt.encode(
        {"alg": "ES256", "kid": settings.apple_key_id},
        {
            "iss": settings.apple_team_id,
            "iat": issued,
            "exp": issued + APPLE_CLIENT_SECRET_LIFETIME_S,
            "aud": APPLE_ISSUER,
            "sub": settings.apple_client_id,
        },
        key,
        algorithms=["ES256"],
    )


def apple_name(user_field: str | None) -> str | None:
    """The name in Apple's `user` form field, sent on the first sign-in only."""
    if not user_field or len(user_field) > MAX_APPLE_USER_FIELD:
        return None
    try:
        data = json.loads(user_field)
    except ValueError:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, dict):
        return None
    parts = [_text(name.get(part), MAX_NAME) for part in ("firstName", "lastName")]
    joined = " ".join(part for part in parts if part)
    return joined[:MAX_NAME] or None


class Apple(OidcProvider):
    id = SignInProvider.APPLE
    scope = "name email"
    form_post = True
    id_setting = "apple_client_id"
    # The private key that signs the client secret; see `apple_client_secret`.
    secret_setting = "apple_private_key"

    def is_configured(self, settings: Settings) -> bool:
        return bool(
            settings.apple_client_id
            and settings.apple_team_id
            and settings.apple_key_id
            and _secret(settings.apple_private_key)
        )

    def client_secret(self, settings: Settings) -> str:
        return apple_client_secret(settings)

    def oidc(self, settings: Settings) -> OidcClient:
        discovery = f"{APPLE_ISSUER}/.well-known/openid-configuration"
        return get_oidc_client(discovery, expected_issuer=APPLE_ISSUER)

    def _authorization_params(self, settings: Settings, flow: Flow) -> dict[str, str]:
        # Apple refuses a request for name or email unless the answer is posted.
        return super()._authorization_params(settings, flow) | {"response_mode": "form_post"}

    def identity(self, claims: dict[str, Any], callback: Callback) -> ProviderIdentity:
        return ProviderIdentity(
            provider=self.id,
            subject=_subject(claims.get("sub")),
            # The identity token's address, never the one in the posted form.
            email=_email(claims.get("email")),
            email_verified=claim_is_true(claims.get("email_verified")),
            display_name=apple_name(callback.user),
        )


# --------------------------------------------------------------------------
# OpenStreetMap
# --------------------------------------------------------------------------


class OpenStreetMap(OidcProvider):
    id = SignInProvider.OSM
    scope = "openid"

    id_setting = "osm_client_id"
    secret_setting = "osm_client_secret"

    def oidc(self, settings: Settings) -> OidcClient:
        issuer = settings.osm_url.rstrip("/")
        return get_oidc_client(f"{issuer}/.well-known/openid-configuration", expected_issuer=issuer)

    def identity(self, claims: dict[str, Any], callback: Callback) -> ProviderIdentity:
        # Only `openid` is asked for, so there is no email to have.
        return ProviderIdentity(
            provider=self.id,
            subject=_subject(claims.get("sub")),
            display_name=_text(claims.get("preferred_username"), MAX_NAME),
        )


# --------------------------------------------------------------------------
# Facebook
# --------------------------------------------------------------------------

FACEBOOK_DIALOG = "https://www.facebook.com"
FACEBOOK_GRAPH = "https://graph.facebook.com"


class Facebook(OAuthProvider):
    id = SignInProvider.FACEBOOK
    scope = "public_profile email"

    id_setting = "facebook_app_id"
    secret_setting = "facebook_app_secret"

    def authorization_url(self, settings: Settings, flow: Flow) -> str:
        endpoint = f"{FACEBOOK_DIALOG}/{settings.facebook_graph_version}/dialog/oauth"
        return _with_query(endpoint, self._authorization_params(settings, flow))

    def complete(self, settings: Settings, flow: Flow, callback: Callback) -> ProviderIdentity:
        code = _check_callback(callback)
        graph = f"{FACEBOOK_GRAPH}/{settings.facebook_graph_version}"
        tokens = self._exchange(settings, flow, f"{graph}/oauth/access_token", code)
        access_token = tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderError("Facebook sent no access token.")
        # Proves the call comes from the app's server, not from a stolen token elsewhere.
        secret = self.client_secret(settings).encode()
        proof = hmac.new(secret, access_token.encode(), hashlib.sha256).hexdigest()
        profile = request_json(
            "GET",
            f"{graph}/me",
            "The Facebook profile call",
            # No picture: Open Antiquity shows none, so it asks for none.
            params={"fields": "id,name,email", "appsecret_proof": proof},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return ProviderIdentity(
            provider=self.id,
            subject=_subject(profile.get("id")),
            email=_email(profile.get("email")),
            # Facebook never says an address is verified.
            email_verified=False,
            display_name=_text(profile.get("name"), MAX_NAME),
        )


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

PROVIDERS: dict[SignInProvider, OAuthProvider] = {
    provider.id: provider for provider in (Google(), Apple(), Microsoft(), Facebook(), OpenStreetMap())
}

# Callback paths a provider reaches with a cross-site POST, which can't carry
# the client header. fieldclub.main exempts exactly these, for POST only.
FORM_POST_CALLBACK_PATHS: tuple[str, ...] = tuple(
    callback_path(provider.id) for provider in PROVIDERS.values() if provider.form_post
)

for _provider in PROVIDERS.values():
    register_provider(_provider.id, _provider.is_configured)


def get_provider(name: str, settings: Settings) -> OAuthProvider:
    """The provider called `name`, if it is one and its settings are present."""
    try:
        provider = PROVIDERS[SignInProvider(name)]
    except (ValueError, KeyError):
        raise ProviderUnavailableError() from None
    if not provider.is_configured(settings):
        raise ProviderUnavailableError()
    return provider
