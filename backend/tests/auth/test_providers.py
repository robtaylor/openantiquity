"""The list of sign-in providers that `/meta` reports."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fieldclub import vocab
from fieldclub.auth import providers
from fieldclub.config import Settings, get_settings
from fieldclub.vocab import SignInProvider, SignInProviderInfo


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    # Load the built-in providers first, so that putting the registry back
    # afterwards keeps them for the tests that follow.
    providers._load_builtin()
    saved = dict(providers._providers)
    providers._providers.clear()
    yield
    providers._providers.clear()
    providers._providers.update(saved)


def enabled_providers(settings: Settings | None = None) -> list[SignInProviderInfo]:
    return [info for info, is_on in providers.provider_statuses(settings) if is_on]


def enabled() -> list[tuple[str, str]]:
    return [(info.id.value, info.label) for info in enabled_providers()]


def test_nothing_is_enabled_until_a_provider_registers() -> None:
    assert enabled_providers() == []


def test_every_provider_in_the_contract_can_register() -> None:
    for provider in ("email", "osm", "facebook", "microsoft", "apple", "google"):
        providers.register_provider(provider, lambda settings: True)
    # Listed in the order of the sign-in sheet, however they registered.
    assert enabled() == [
        ("google", "Google"),
        ("apple", "Apple"),
        ("microsoft", "Microsoft"),
        ("facebook", "Facebook"),
        ("osm", "OpenStreetMap"),
        ("email", "Email link"),
    ]
    assert [info.id for info in vocab.SIGN_IN_PROVIDERS] == list(SignInProvider)


def test_a_provider_is_listed_only_while_its_settings_enable_it() -> None:
    providers.register_provider(SignInProvider.OSM, lambda settings: True)
    providers.register_provider("google", lambda settings: False)
    providers.register_provider("email", lambda settings: settings.env == "test")
    assert enabled_providers(get_settings()) == [
        vocab.SignInProviderInfo(SignInProvider.OSM, "OpenStreetMap"),
        vocab.SignInProviderInfo(SignInProvider.EMAIL, "Email link"),
    ]


@pytest.mark.parametrize("provider", ["myspace", "guest", ""])
def test_unknown_providers_are_refused(provider: str) -> None:
    with pytest.raises(AssertionError, match="unknown sign-in provider"):
        providers.register_provider(provider, lambda settings: True)


def test_provider_statuses_lists_every_provider_in_order_with_its_state() -> None:
    providers.register_provider("osm", lambda settings: True)
    providers.register_provider("apple", lambda settings: False)
    statuses = providers.provider_statuses(get_settings())
    assert [(info.id.value, enabled) for info, enabled in statuses] == [
        ("google", False),
        ("apple", False),
        ("microsoft", False),
        ("facebook", False),
        ("osm", True),
        ("email", False),
    ]
