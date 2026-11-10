"""Opaque random tokens, and the hashes that are stored in their place."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fieldclub.config import get_settings

# 32 random bytes, which is 43 URL-safe characters.
TOKEN_BYTES = 32
MAX_TOKEN_LENGTH = 128


def new_token() -> str:
    """A fresh unguessable token for a session cookie or a magic link."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The SHA-256 of a token, as hex.

    Tokens carry 256 bits of randomness, so a plain fast hash is enough: there
    is nothing to brute-force. A database leak then exposes no usable session.
    """
    assert token, "refusing to hash an empty token"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_presented(token: str | None) -> str | None:
    """The hash of a token a browser sent, or None when it can't be one of ours (empty or overlong)."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    return hash_token(token)


def hash_ip(ip: str) -> str:
    """A keyed hash of an IP address, for rate limiting and session records.

    The key is the server secret, so the stored value can't be turned back into
    an address by trying all four billion of them.
    """
    key = get_settings().secret_key.get_secret_value().encode("utf-8")
    return hmac.new(key, ip.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
