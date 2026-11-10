"""Stand-in sign-in providers, served through respx with keys made in the tests.

A `FakeIdP` publishes a discovery document and a key set, and runs a token
endpoint that behaves like a real one: each code works once, only for the
PKCE verifier whose challenge it was issued against, and only with the right
client id, secret and redirect address. `FakeFacebook` does the same for
Facebook's token endpoint and profile call.

`sign_in(client, idp, ...)` drives the whole browser flow: start, the
provider's consent page (simulated by `idp.authorise`), and the callback.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
import respx
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

PUBLIC_URL = "https://fieldclub.test"
CALLBACK = PUBLIC_URL + "/api/v1/auth/oauth/{provider}/callback"


def challenge_for(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def form_of(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def query_of(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


@dataclass
class Grant:
    """What the provider remembers about a code it issued."""

    challenge: str
    redirect_uri: str
    claims: dict[str, Any]
    nonce: str | None


@dataclass
class FakeIdP:
    """An OpenID Connect provider."""

    provider: str
    issuer: str
    discovery_url: str
    client_id: str
    # None means "check the secret with `secret_check` instead", for Apple.
    client_secret: str | None
    keys: list[RSAKey | ECKey]
    signing_key: RSAKey | ECKey
    secret_check: Callable[[str], None] | None = None
    discovery_issuer: str | None = None
    # Claims every token carries, such as Microsoft's tenant id.
    extra_claims: dict[str, Any] = field(default_factory=dict)
    # Given the claims, the identity token to send instead of a properly signed one.
    forge: Callable[[dict[str, Any]], str] | None = None
    grants: dict[str, Grant] = field(default_factory=dict)
    spent: set[str] = field(default_factory=set)
    token_requests: list[dict[str, str]] = field(default_factory=list)
    jwks_route: respx.Route | None = None

    @property
    def base(self) -> str:
        return self.discovery_url.removesuffix("/.well-known/openid-configuration")

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.base}/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.base}/token"

    @property
    def jwks_uri(self) -> str:
        return f"{self.base}/jwks"

    def install(self, mock: respx.MockRouter) -> None:
        mock.get(self.discovery_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "issuer": self.discovery_issuer or self.issuer,
                    "authorization_endpoint": self.authorization_endpoint,
                    "token_endpoint": self.token_endpoint,
                    "jwks_uri": self.jwks_uri,
                    "response_types_supported": ["code"],
                    "id_token_signing_alg_values_supported": ["RS256", "ES256"],
                },
            )
        )
        self.jwks_route = mock.get(self.jwks_uri).mock(side_effect=self._jwks)
        mock.post(self.token_endpoint).mock(side_effect=self._token)

    def _jwks(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [key.as_dict(private=False) for key in self.keys]})

    def rotate(self, new_key: RSAKey | ECKey, *, keep_old: bool = False) -> None:
        """Start signing with `new_key`, as a provider does when it rotates."""
        self.keys = [*self.keys, new_key] if keep_old else [new_key]
        self.signing_key = new_key

    def authorise(self, start_location: str, claims: dict[str, Any]) -> tuple[str, str]:
        """What the provider does on its consent page: returns (code, state) for the callback."""
        assert start_location.startswith(self.authorization_endpoint + "?"), start_location
        query = query_of(start_location)
        assert query["client_id"] == self.client_id
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        assert query["redirect_uri"] == CALLBACK.format(provider=self.provider)
        code = secrets.token_urlsafe(16)
        self.grants[code] = Grant(query["code_challenge"], query["redirect_uri"], claims, query.get("nonce"))
        return code, query["state"]

    def id_token(
        self, claims: dict[str, Any], *, key: RSAKey | ECKey | None = None, alg: str | None = None
    ) -> str:
        key = key or self.signing_key
        alg = alg or ("ES256" if isinstance(key, ECKey) else "RS256")
        return jwt.encode({"alg": alg, "kid": key.kid}, claims, key, algorithms=[alg])

    def standard_claims(self, nonce: str | None, **extra: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "sub": "subject-1",
            "iat": now,
            "exp": now + 600,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        claims.update(self.extra_claims)
        claims.update(extra)
        return {key: value for key, value in claims.items() if value is not None}

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = form_of(request)
        self.token_requests.append(form)
        code = form.get("code", "")
        grant = self.grants.get(code)
        if grant is None or code in self.spent:
            return httpx.Response(400, json={"error": "invalid_grant"})
        self.spent.add(code)
        if form.get("client_id") != self.client_id or form.get("grant_type") != "authorization_code":
            return httpx.Response(401, json={"error": "invalid_client"})
        if self.secret_check is not None:
            try:
                self.secret_check(form.get("client_secret", ""))
            except Exception:
                return httpx.Response(401, json={"error": "invalid_client"})
        elif form.get("client_secret") != self.client_secret:
            return httpx.Response(401, json={"error": "invalid_client"})
        if form.get("redirect_uri") != grant.redirect_uri:
            return httpx.Response(400, json={"error": "invalid_grant"})
        if challenge_for(form.get("code_verifier", "")) != grant.challenge:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
        claims = self.standard_claims(grant.nonce) | grant.claims
        claims = {key: value for key, value in claims.items() if value is not None}
        id_token = self.forge(claims) if self.forge is not None else self.id_token(claims)
        return httpx.Response(
            200, json={"access_token": "at-" + code, "token_type": "Bearer", "id_token": id_token}
        )


@dataclass
class FakeFacebook:
    app_id: str
    app_secret: str
    version: str
    profile: dict[str, Any] = field(default_factory=dict)
    grants: dict[str, Grant] = field(default_factory=dict)
    spent: set[str] = field(default_factory=set)
    profile_requests: list[httpx.Request] = field(default_factory=list)
    provider: str = "facebook"

    @property
    def authorization_endpoint(self) -> str:
        return f"https://www.facebook.com/{self.version}/dialog/oauth"

    def install(self, mock: respx.MockRouter) -> None:
        graph = f"https://graph.facebook.com/{self.version}"
        mock.post(f"{graph}/oauth/access_token").mock(side_effect=self._token)
        mock.get(f"{graph}/me").mock(side_effect=self._me)

    def authorise(self, start_location: str, claims: dict[str, Any]) -> tuple[str, str]:
        assert start_location.startswith(self.authorization_endpoint + "?"), start_location
        query = query_of(start_location)
        assert query["client_id"] == self.app_id
        assert "nonce" not in query
        code = secrets.token_urlsafe(16)
        self.grants[code] = Grant(query["code_challenge"], query["redirect_uri"], claims, None)
        return code, query["state"]

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = form_of(request)
        code = form.get("code", "")
        grant = self.grants.get(code)
        if grant is None or code in self.spent:
            return httpx.Response(400, json={"error": {"message": "This authorization code has been used."}})
        self.spent.add(code)
        if (
            form.get("client_secret") != self.app_secret
            or challenge_for(form["code_verifier"]) != grant.challenge
        ):
            return httpx.Response(400, json={"error": {"message": "bad"}})
        self.profile = grant.claims
        return httpx.Response(200, json={"access_token": "fb-" + code, "token_type": "bearer"})

    def _me(self, request: httpx.Request) -> httpx.Response:
        self.profile_requests.append(request)
        return httpx.Response(200, json=self.profile)


Provider = FakeIdP | FakeFacebook


def start(client: TestClient, provider: str, next_path: str | None = None) -> httpx2.Response:
    params = {"next": next_path} if next_path is not None else None
    return client.get(f"/api/v1/auth/oauth/{provider}/start", params=params, follow_redirects=False)


def callback(client: TestClient, provider: str, *, method: str = "GET", **values: str) -> httpx2.Response:
    path = f"/api/v1/auth/oauth/{provider}/callback"
    if method == "POST":
        return client.post(path, data=values, follow_redirects=False)
    return client.get(path, params=values, follow_redirects=False)


def sign_in(
    client: TestClient,
    idp: Provider,
    claims: dict[str, Any] | None = None,
    *,
    next_path: str | None = None,
    method: str = "GET",
    **form: str,
) -> httpx2.Response:
    """The whole flow: start, consent at the provider, callback. Returns the callback's response."""
    started = start(client, idp.provider, next_path)
    assert started.status_code == 302, started.text
    code, state = idp.authorise(started.headers["location"], claims or {})
    return callback(client, idp.provider, method=method, code=code, state=state, **form)


def signin_error(response: httpx2.Response) -> str | None:
    """The `signin_error` a callback's redirect carries, or None for success."""
    assert response.status_code == 303, response.text
    return query_of(response.headers["location"]).get("signin_error")


def flow_cookie_value(response: httpx2.Response) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("fieldclub_oauth="):
            return header.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("no flow cookie was set")
