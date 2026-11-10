"""Tokens are random, and only their hashes are kept."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from fieldclub.auth.tokens import MAX_TOKEN_LENGTH, hash_ip, hash_presented, hash_token, new_token


def test_tokens_are_long_random_and_url_safe() -> None:
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert 40 <= len(token) <= MAX_TOKEN_LENGTH
        assert token.replace("-", "").replace("_", "").isalnum()


def test_hash_is_stable_and_is_not_the_token() -> None:
    token = new_token()
    digest = hash_token(token)
    assert digest == hash_token(token)
    assert digest != token
    assert len(digest) == 64
    assert hash_token(new_token()) != digest


def test_hashing_nothing_is_refused() -> None:
    with pytest.raises(AssertionError):
        hash_token("")


def test_ip_hash_is_keyed_by_the_server_secret(env: Callable[..., None]) -> None:
    first = hash_ip("203.0.113.5")
    assert first == hash_ip("203.0.113.5")
    assert first != hash_ip("203.0.113.6")
    assert "203.0.113.5" not in first
    env(SECRET_KEY="another-secret")
    assert hash_ip("203.0.113.5") != first


def test_a_presented_token_is_hashed_only_when_it_could_be_one_of_ours() -> None:
    token = new_token()
    assert hash_presented(token) == hash_token(token)
    assert hash_presented("a" * MAX_TOKEN_LENGTH) == hash_token("a" * MAX_TOKEN_LENGTH)
    for bad in (None, "", "a" * (MAX_TOKEN_LENGTH + 1)):
        assert hash_presented(bad) is None
