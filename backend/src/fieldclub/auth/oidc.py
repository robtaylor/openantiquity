"""One OpenID Connect relying party for every provider that speaks it.

Google, Microsoft, Apple and OpenStreetMap each publish a discovery document
and a key set. `OidcClient` fetches both, caches them, and verifies identity
tokens with joserfc:

- The signature, with a key from the provider's key set, using only the
  algorithms in `ALLOWED_ALGORITHMS`. An unsigned token (`alg: none`) and a
  token signed with a shared-secret algorithm such as HS256 are refused
  before any key is looked at, which closes the trick of verifying an HMAC
  with a public key as its secret.
- `iss`, which must be one the provider accepts for these claims (Microsoft's
  multi-tenant issuer carries the tenant id, so it is checked per token).
- `aud`, which must name our client id, and `azp`, which must be ours when
  present and is required when there are several audiences.
- `exp` and `iat`, with a minute of leeway for clock skew.
- `nonce`, which must be the one this browser's flow sent.

Keys rotate. When a token names a key id we don't hold, the key set is fetched
again, at most once every `JWKS_MIN_REFRESH_S` seconds so that tokens with
made-up key ids can't make us hammer the provider.

Caches live in the process, keyed by discovery address, and survive settings
reloads. `reset_caches()` empties them for tests.
"""

from __future__ import annotations

import hmac
import logging
import re
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import GuestProtocol, Key, KeySet

from fieldclub.auth.failures import InvalidIdentityError, ProviderError
from fieldclub.http import get_client

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")
DISCOVERY_TTL_S = 24 * 3600
JWKS_TTL_S = 24 * 3600
JWKS_MIN_REFRESH_S = 60
CLOCK_LEEWAY_S = 60


@dataclass(frozen=True)
class Discovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


def _https(document: dict[str, Any], name: str) -> str:
    value = document.get(name)
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ProviderError(f"The provider's discovery document has no https {name}.")
    return value


def fetch_json(response: httpx.Response, what: str) -> dict[str, Any]:
    """The JSON object in a successful response, or `ProviderError`."""
    if response.status_code != 200:
        logger.warning("%s answered %s: %.300s", what, response.status_code, response.text)
        raise ProviderError()
    try:
        body = response.json()
    except ValueError:
        raise ProviderError(f"{what} didn't answer with JSON.") from None
    if not isinstance(body, dict):
        raise ProviderError(f"{what} didn't answer with a JSON object.")
    return body


def request_json(
    method: str, url: str, what: str, *, headers: dict[str, str] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Call a provider and return the JSON object it answers with, or raise `ProviderError`.

    `what` names the call in the log. Other keyword arguments go to httpx.
    """
    try:
        response = get_client().request(
            method, url, headers={"Accept": "application/json", **(headers or {})}, **kwargs
        )
    except httpx.HTTPError as exc:
        logger.warning("%s at %s failed: %s", what, url, exc)
        raise ProviderError() from exc
    return fetch_json(response, what)


# Given the discovery document and a token's claims, the issuers to accept.
IssuerRule = Callable[[Discovery, dict[str, Any]], Collection[str]]


def same_issuer(discovery: Discovery, claims: dict[str, Any]) -> Collection[str]:
    return (discovery.issuer,)


@dataclass
class _Cached:
    value: Any = None
    fetched_at: float = 0.0


@dataclass
class OidcClient:
    """Discovery, keys and token checks for one provider.

    `expected_issuer` is what the discovery document must call itself: a
    string to match exactly, or a pattern for the whole value. `issuers`
    decides which `iss` values a token may carry.
    """

    discovery_url: str
    expected_issuer: str | re.Pattern[str]
    issuers: IssuerRule = same_issuer
    algorithms: tuple[str, ...] = ALLOWED_ALGORITHMS
    _discovery: _Cached = field(default_factory=_Cached)
    _jwks: _Cached = field(default_factory=_Cached)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        assert self.discovery_url.startswith("https://"), "discovery must be fetched over https"
        assert self.algorithms, "an identity token needs at least one allowed algorithm"
        assert not {"none", "HS256", "HS384", "HS512"} & set(self.algorithms), (
            "identity tokens are only accepted with public-key signatures"
        )

    def discovery(self) -> Discovery:
        with self._lock:
            cached = self._discovery
            if cached.value is not None and time.time() - cached.fetched_at < DISCOVERY_TTL_S:
                return cached.value
        document = request_json("GET", self.discovery_url, "The provider's discovery document")
        issuer = document.get("issuer")
        if not isinstance(issuer, str) or not self._issuer_is_expected(issuer):
            logger.warning("Discovery at %s names issuer %r", self.discovery_url, issuer)
            raise ProviderError("The provider's discovery document names an unexpected issuer.")
        found = Discovery(
            issuer=issuer,
            authorization_endpoint=_https(document, "authorization_endpoint"),
            token_endpoint=_https(document, "token_endpoint"),
            jwks_uri=_https(document, "jwks_uri"),
        )
        with self._lock:
            self._discovery = _Cached(found, time.time())
        return found

    def _issuer_is_expected(self, issuer: str) -> bool:
        if isinstance(self.expected_issuer, str):
            return issuer == self.expected_issuer
        return self.expected_issuer.fullmatch(issuer) is not None

    def _key_set(self, *, refresh: bool = False) -> KeySet:
        """The provider's signing keys. With `refresh`, fetched again unless that happened just now."""
        now = time.time()
        with self._lock:
            cached, fetched_at = self._jwks.value, self._jwks.fetched_at
        fresh = cached is not None and now - fetched_at < JWKS_TTL_S
        if cached is not None and fresh and not (refresh and now - fetched_at >= JWKS_MIN_REFRESH_S):
            return cached
        document = request_json("GET", self.discovery().jwks_uri, "The provider's key set")
        keys = document.get("keys")
        if not isinstance(keys, list):
            raise ProviderError("The provider's key set has no keys.")
        # Only signing keys. A key marked for encryption must never verify a signature.
        signing = [key for key in keys if isinstance(key, dict) and key.get("use", "sig") == "sig"]
        try:
            key_set = KeySet.import_key_set({"keys": signing})
        except (JoseError, ValueError, TypeError) as exc:
            raise ProviderError("The provider's key set couldn't be read.") from exc
        with self._lock:
            self._jwks = _Cached(key_set, time.time())
        logger.info("Fetched %d signing keys from %s", len(key_set.keys), self.discovery_url)
        return key_set

    def _resolve_key(self, token: GuestProtocol) -> Key:
        """The key named by the token's `kid`, fetching the key set again once if it is new."""
        kid = token.headers().get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidKeyIdError("The token names no key.")
        for refresh in (False, True):
            for key in self._key_set(refresh=refresh).keys:
                if key.kid == kid:
                    return key
        raise InvalidKeyIdError(f"No key for kid {kid!r}")

    def verify_id_token(self, token: object, *, client_id: str, nonce: str) -> dict[str, Any]:
        """The claims of an identity token that passes every check, or `InvalidIdentityError`."""
        assert client_id, "verifying an identity token needs our client id"
        assert nonce, "verifying an identity token needs the flow's nonce"
        if not isinstance(token, str) or not token:
            raise InvalidIdentityError("The provider sent no identity token.")
        try:
            claims = jwt.decode(token, self._resolve_key, algorithms=list(self.algorithms)).claims
            # joserfc checks types, expiry and the audience. Issuer and nonce are
            # compared here, exactly: its "values" option treats an empty list as
            # "anything goes", and a list-valued claim as matching any element.
            jwt.JWTClaimsRegistry(
                leeway=CLOCK_LEEWAY_S,
                iss={"essential": True},
                aud={"essential": True, "value": client_id},
                exp={"essential": True},
                iat={"essential": True},
                sub={"essential": True},
                nonce={"essential": True},
            ).validate(claims)
        except (JoseError, ValueError, TypeError) as exc:
            logger.info("Identity token from %s refused: %s", self.discovery_url, exc)
            raise InvalidIdentityError() from exc
        accepted = self.issuers(self.discovery(), claims)
        if claims["iss"] not in accepted:
            logger.info("Identity token from %s has issuer %.200r", self.discovery_url, claims["iss"])
            raise InvalidIdentityError()
        sent = claims["nonce"]
        if not isinstance(sent, str) or not hmac.compare_digest(sent.encode(), nonce.encode()):
            logger.info("Identity token from %s has the wrong nonce", self.discovery_url)
            raise InvalidIdentityError()
        audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        if (len(audiences) > 1 or "azp" in claims) and claims.get("azp") != client_id:
            logger.info("Identity token from %s is for azp %r", self.discovery_url, claims.get("azp"))
            raise InvalidIdentityError()
        return claims

    def reset(self) -> None:
        with self._lock:
            self._discovery = _Cached()
            self._jwks = _Cached()


_clients: dict[str, OidcClient] = {}
_registry_lock = threading.Lock()


def get_oidc_client(
    discovery_url: str, *, expected_issuer: str | re.Pattern[str], issuers: IssuerRule = same_issuer
) -> OidcClient:
    """The process-wide client for a discovery address, made on first use."""
    with _registry_lock:
        client = _clients.get(discovery_url)
        if client is None or (client.expected_issuer, client.issuers) != (expected_issuer, issuers):
            client = _clients[discovery_url] = OidcClient(discovery_url, expected_issuer, issuers)
        return client


def reset_caches() -> None:
    """Forget every discovery document and key set."""
    with _registry_lock:
        for client in _clients.values():
            client.reset()
        _clients.clear()
