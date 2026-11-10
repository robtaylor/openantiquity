"""The signed cookie that carries one sign-in flow's state, nonce and PKCE verifier."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable

import pytest

from fieldclub.auth.flow import FLOW_LIFETIME_S, Flow, new_flow, pkce_challenge, seal, state_matches, unseal
from fieldclub.auth.tokens import hash_token

NOW = 1_800_000_000.0


def test_a_new_flow_has_fresh_unguessable_values() -> None:
    first, second = new_flow("google", "/f/1", now=NOW), new_flow("google", "/f/1", now=NOW)
    for name in ("state", "nonce", "verifier"):
        assert getattr(first, name) != getattr(second, name)
        assert len(getattr(first, name)) >= 43
    # RFC 7636: a verifier is 43 to 128 characters.
    assert 43 <= len(first.verifier) <= 128
    assert first.expires_at == int(NOW) + FLOW_LIFETIME_S


def test_the_challenge_is_s256_of_the_verifier() -> None:
    # The example in RFC 7636, appendix B.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    flow = new_flow("osm", "/", now=NOW)
    expected = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b"=").decode()
    assert flow.challenge == expected


def test_a_sealed_flow_unseals_to_itself() -> None:
    flow = new_flow("apple", "/f/7K3QXM?layer=slope", now=NOW)
    assert unseal(seal(flow), now=NOW) == flow


def test_a_flow_keeps_only_the_hash_of_the_session_presented_at_the_start() -> None:
    token = "t" * 43
    flow = new_flow("apple", "/" + "a" * 1999, presented_session=token, now=NOW)
    assert flow.presented_session == hash_token(token)
    sealed = seal(flow)
    assert token not in sealed
    assert unseal(sealed, now=NOW) == flow
    for presented in (None, "", "x" * 129):
        assert new_flow("apple", "/", presented_session=presented, now=NOW).presented_session is None


def test_an_expired_flow_is_refused() -> None:
    flow = new_flow("google", "/", now=NOW)
    sealed = seal(flow)
    assert unseal(sealed, now=NOW + FLOW_LIFETIME_S - 1) == flow
    assert unseal(sealed, now=NOW + FLOW_LIFETIME_S) is None


def _resign(sealed: str, change: Callable[[dict], None]) -> str:
    body, signature = sealed.split(".")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    change(data)
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode() + "." + signature


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.update(next="//evil.example"),
        lambda data: data.update(expires_at=data["expires_at"] + 10**6),
        lambda data: data.update(provider="facebook"),
        lambda data: data.update(state="mine"),
    ],
)
def test_an_edited_flow_is_refused(change: Callable[[dict], None]) -> None:
    sealed = seal(new_flow("google", "/", now=NOW))
    assert unseal(_resign(sealed, change), now=NOW) is None


@pytest.mark.parametrize(
    "value",
    [None, "", ".", "a.b", "a.b.c", "x" * 5000, "\u00e9.\u00e9", "e30.", "e30.AAAA"],
)
def test_garbage_is_refused(value: str | None) -> None:
    assert unseal(value, now=NOW) is None


def test_a_flow_signed_with_another_secret_key_is_refused(env: Callable[..., None]) -> None:
    sealed = seal(new_flow("google", "/", now=NOW))
    env(SECRET_KEY="a-different-secret")
    assert unseal(sealed, now=NOW) is None


def test_state_must_match_exactly() -> None:
    flow = Flow("google", "abc", "n", "v", "/", int(NOW) + 60)
    assert state_matches(flow, "abc")
    for returned in (None, "", "abd", "abc ", "ABC", "\u00e9"):
        assert not state_matches(flow, returned)
