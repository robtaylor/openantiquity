"""The short-lived state of one provider sign-in, carried in a signed cookie.

`GET /auth/oauth/{provider}/start` makes a fresh `state`, OpenID Connect
`nonce` and PKCE verifier, and puts them, with the provider and the `next`
path, in the `fieldclub_oauth` cookie. The callback reads the cookie back and
refuses to go on unless the `state` the provider returned is the one in it.

Why a cookie and not a database row:

- It binds the flow to the browser that started it. A row looked up by
  `state` alone would let someone start a flow, sign in at the provider as
  themselves, and hand the callback address to a victim, who would then be
  signed in to the attacker's account (login CSRF). With the cookie, the
  callback only succeeds in the browser that pressed the button.
- It costs no write per click, so a bot pressing "start" fills no table.
- It needs no cleaning up. It expires on its own after ten minutes.

The cookie is HMAC-signed with a key derived from `FIELDCLUB_SECRET_KEY`, so
it can't be forged or edited. It isn't encrypted: everything in it is meant
for the browser that holds it, and it is HttpOnly. It is scoped to the
provider's callback path and cleared on every callback, success or failure.
A replayed callback (the same cookie and code a second time) reaches the
provider's token endpoint with a code that has already been spent, which the
provider refuses.

Apple returns to the callback with a cross-site POST, and a SameSite=Lax
cookie isn't sent on one. Apple's flow cookie is therefore SameSite=None and
Secure. It is still bound to the callback path, and still useless without the
matching `state`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass

from fieldclub.config import get_settings

FLOW_COOKIE = "fieldclub_oauth"
FLOW_LIFETIME_S = 600
# Large enough for every field with a long `next`, small enough for any browser.
MAX_COOKIE_LENGTH = 3800
_KEY_PURPOSE = b"fieldclub/oauth-flow/v1"


@dataclass(frozen=True)
class Flow:
    provider: str
    state: str
    nonce: str
    verifier: str
    next: str
    expires_at: int

    @property
    def challenge(self) -> str:
        """The PKCE S256 challenge for this flow's verifier."""
        return pkce_challenge(self.verifier)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_flow(provider: str, next_path: str, *, now: float | None = None) -> Flow:
    """A fresh flow. The verifier is 64 characters, inside PKCE's 43 to 128."""
    issued = time.time() if now is None else now
    return Flow(
        provider=provider,
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(48),
        next=next_path,
        expires_at=int(issued) + FLOW_LIFETIME_S,
    )


def _key() -> bytes:
    secret = get_settings().secret_key.get_secret_value().encode("utf-8")
    return hmac.new(secret, _KEY_PURPOSE, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def seal(flow: Flow) -> str:
    """The cookie value: the flow as JSON, then its signature, both base64url."""
    body = _b64(json.dumps(asdict(flow), separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_key(), body.encode("ascii"), hashlib.sha256).digest())
    sealed = f"{body}.{signature}"
    assert len(sealed) <= MAX_COOKIE_LENGTH, "the flow cookie is too large; is `next` capped?"
    return sealed


def unseal(value: str | None, *, now: float | None = None) -> Flow | None:
    """The flow in a cookie value, or None if it is missing, forged, edited or expired."""
    if not value or len(value) > MAX_COOKIE_LENGTH or value.count(".") != 1:
        return None
    body, signature = value.split(".")
    expected = _b64(hmac.new(_key(), body.encode("ascii", "replace"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature.encode("utf-8"), expected.encode("ascii")):
        return None
    try:
        data = json.loads(_unb64(body))
        flow = Flow(**data)
    except (ValueError, TypeError):
        # Signed by us, so this means the format changed under a live cookie.
        return None
    if not all(isinstance(field, str) for field in (flow.provider, flow.state, flow.nonce, flow.verifier)):
        return None
    if not isinstance(flow.expires_at, int) or flow.expires_at <= (time.time() if now is None else now):
        return None
    return flow


def state_matches(flow: Flow, returned: str | None) -> bool:
    return bool(returned) and hmac.compare_digest(flow.state.encode(), (returned or "").encode())
