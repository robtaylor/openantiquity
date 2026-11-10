"""The sign-in providers that are switched on.

`/meta` lists every provider from `provider_statuses()`, each marked enabled
or not, so the frontend only offers what works. `vocab.SIGN_IN_PROVIDERS`
names every provider there can be, with its label and its place on the
sign-in sheet. A provider is enabled only once its flow has registered here
and its credentials are configured.

A provider module registers itself when it is imported:

    register_provider(SignInProvider.GOOGLE, lambda settings: bool(settings.google_client_id))

The built-in modules (`fieldclub.auth.oauth` for the five providers and
`fieldclub.auth.email_link` for the emailed link) are imported the first time
anyone asks, so `/meta` is right whether or not the routers were loaded.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from fieldclub.config import Settings, get_settings
from fieldclub.vocab import SIGN_IN_PROVIDERS, SignInProvider, SignInProviderInfo

_providers: dict[SignInProvider, Callable[[Settings], bool]] = {}

_BUILTIN_MODULES = ("fieldclub.auth.oauth", "fieldclub.auth.email_link")


def _load_builtin() -> None:
    """Import the modules that register the built-in providers. Cheap after the first time."""
    for name in _BUILTIN_MODULES:
        importlib.import_module(name)


def register_provider(provider: SignInProvider | str, is_enabled: Callable[[Settings], bool]) -> None:
    """Declare a provider and how to tell from the settings whether it is usable."""
    assert provider in SignInProvider, (
        f"unknown sign-in provider {provider!r}; add it to vocab.SignInProvider and SIGN_IN_PROVIDERS"
    )
    _providers[SignInProvider(provider)] = is_enabled


def is_enabled(provider: SignInProvider, settings: Settings) -> bool:
    _load_builtin()
    check = _providers.get(provider)
    return check is not None and bool(check(settings))


def provider_statuses(settings: Settings | None = None) -> list[tuple[SignInProviderInfo, bool]]:
    """Every provider with whether it is usable, in the order the sign-in sheet shows them."""
    _load_builtin()
    settings = settings or get_settings()
    return [(info, is_enabled(info.id, settings)) for info in SIGN_IN_PROVIDERS]
