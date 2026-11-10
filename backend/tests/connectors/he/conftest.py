"""Fixtures for the Historic England connector tests."""

from __future__ import annotations

import pytest

from tests.ingest.adapters.support import NoWait


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ArcGIS reader leaves a second between requests. A test has no one to be polite to."""
    monkeypatch.setattr("fieldclub.ingest.adapters.arcgis.Polite", NoWait)
