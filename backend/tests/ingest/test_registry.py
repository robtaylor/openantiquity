"""Connectors register by key and are discovered by import."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest

from fieldclub.ingest import registry
from fieldclub.ingest.base import Connector
from fieldclub.ingest.registry import UnknownConnectorError
from tests.ingest.fakes import SOURCE, FakeConnector


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    """Each test starts with no connectors registered, and the real ones come back after it."""
    registry.discover()
    saved = dict(registry._registry)
    registry._registry.clear()
    yield
    registry._registry.clear()
    registry._registry.update(saved)


def test_an_emptied_registry_lists_nothing() -> None:
    assert registry.all_connectors() == []


def test_register_makes_a_connector_available_by_key() -> None:
    registered = registry.register(FakeConnector)
    assert registered is FakeConnector
    assert registry.get("fake-monuments") is FakeConnector
    assert registry.all_connectors() == [FakeConnector]


def test_register_works_as_a_decorator_and_lists_in_key_order() -> None:
    @registry.register
    class Zebra(FakeConnector):
        source = dataclasses.replace(SOURCE, key="zebra")

    @registry.register
    class Aardvark(FakeConnector):
        source = dataclasses.replace(SOURCE, key="aardvark")

    assert registry.all_connectors() == [Aardvark, Zebra]


def test_registering_the_same_class_twice_is_harmless() -> None:
    registry.register(FakeConnector)
    registry.register(FakeConnector)
    assert registry.all_connectors() == [FakeConnector]


def test_two_connectors_cannot_claim_one_key() -> None:
    registry.register(FakeConnector)

    class Impostor(FakeConnector):
        pass

    with pytest.raises(AssertionError, match="two connectors claim"):
        registry.register(Impostor)


def test_a_connector_without_a_source_cannot_register() -> None:
    class Sourceless(Connector):
        def fetch(self, *, bbox=None, limit=None):
            yield from ()

    with pytest.raises(AssertionError, match="must declare its source"):
        registry.register(Sourceless)


def test_unknown_keys_say_what_is_known() -> None:
    with pytest.raises(UnknownConnectorError, match="none are registered"):
        registry.get("nope")
    registry.register(FakeConnector)
    with pytest.raises(UnknownConnectorError, match="Known connectors: fake-monuments") as caught:
        registry.get("nope")
    assert caught.value.status_code == 404


def test_unregister() -> None:
    registry.register(FakeConnector)
    registry.unregister("fake-monuments")
    registry.unregister("fake-monuments")
    assert registry.all_connectors() == []


def test_discover_imports_modules_in_the_connectors_package(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fieldclub.ingest.connectors as package

    (tmp_path / "discovered_fake.py").write_text(
        "import dataclasses\n"
        "from fieldclub.ingest import registry\n"
        "from tests.ingest.fakes import SOURCE, FakeConnector\n"
        "\n"
        "@registry.register\n"
        "class Discovered(FakeConnector):\n"
        "    source = dataclasses.replace(SOURCE, key='discovered-fake')\n"
    )
    monkeypatch.setattr(package, "__path__", [*package.__path__, str(tmp_path)])
    monkeypatch.setattr(registry, "_discovered", False)

    assert registry.get("discovered-fake").__name__ == "Discovered"
    assert registry._discovered is True
