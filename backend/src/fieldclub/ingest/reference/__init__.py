"""Reference loaders: the outside datasets that fill `places` and `admin_areas`, not `records`.

A connector feeds the record index. A loader feeds one of the tables the map
looks things up in: the gazetteer behind the search box (`places`) and the
nation and county boundaries (`admin_areas`). Both are replaced whole on each
run, because neither table keeps an upstream identifier to upsert on. The
licence and attribution go into `sources` first, as for a connector, and each
run is written to `ingest_runs`.

`fieldclub-ingest run <key>` runs a loader as it runs a connector. Every
module in this package is imported by `discover()`, so a loader registers by
being here, as connectors do in `ingest/connectors/`.
"""

from __future__ import annotations

import importlib
import pkgutil

from fieldclub.ingest.reference.base import Loader

_loaders: dict[str, type[Loader]] = {}
_discovered = False


def register[L: type[Loader]](cls: L) -> L:
    """Class decorator: make a loader available under its source key."""
    key = cls.source.key
    existing = _loaders.get(key)
    assert existing is None or existing is cls, f"two loaders claim the source key {key!r}"
    _loaders[key] = cls
    return cls


def discover() -> None:
    global _discovered
    if _discovered:
        return
    for info in pkgutil.iter_modules(__path__, prefix=f"{__name__}."):
        importlib.import_module(info.name)
    _discovered = True


def get(key: str) -> type[Loader] | None:
    """The loader for a source key, or None when the key isn't a loader's."""
    discover()
    return _loaders.get(key)


def all_loaders() -> list[type[Loader]]:
    """Every registered loader, ordered by source key."""
    discover()
    return [_loaders[key] for key in sorted(_loaders)]
