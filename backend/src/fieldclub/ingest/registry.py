"""The connectors that exist, by source key."""

from __future__ import annotations

import importlib
import pkgutil

from fieldclub.errors import NotFoundError
from fieldclub.ingest.base import Connector, SourceInfo

_registry: dict[str, type[Connector]] = {}
_discovered = False


class UnknownConnectorError(NotFoundError):
    code = "unknown_connector"
    message = "There is no connector with that key."


def register[C: type[Connector]](cls: C) -> C:
    """Class decorator: make a connector available under its source key."""
    assert isinstance(getattr(cls, "source", None), SourceInfo), f"{cls.__name__} must declare its source"
    key = cls.source.key
    existing = _registry.get(key)
    assert existing is None or existing is cls, f"two connectors claim the source key {key!r}"
    _registry[key] = cls
    return cls


def unregister(key: str) -> None:
    """Forget a connector. Used by tests that register fakes."""
    _registry.pop(key, None)


def discover() -> None:
    """Import every module under `fieldclub.ingest.connectors` so their connectors register."""
    global _discovered
    if _discovered:
        return
    import fieldclub.ingest.connectors as package

    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        importlib.import_module(info.name)
    _discovered = True


def get(key: str) -> type[Connector]:
    discover()
    try:
        return _registry[key]
    except KeyError:
        known = ", ".join(sorted(_registry)) or "none are registered"
        raise UnknownConnectorError(f"No connector called {key!r}. Known connectors: {known}.") from None


def all_connectors() -> list[type[Connector]]:
    """Every registered connector, ordered by source key."""
    discover()
    return [_registry[key] for key in sorted(_registry)]
