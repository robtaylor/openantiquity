"""Offline: names resolve through `fake_resolver`, the fetch cache starts empty, and a real request fails."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import respx

from fieldclub import http, safe_fetch
from fieldclub.services import unfurl
from tests.mentions.support import fake_resolver


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    monkeypatch.setattr(safe_fetch, "system_resolver", fake_resolver)
    unfurl.clear_cache()
    http.close_client()
    safe_fetch.close_client()
    # The global router, so `respx.get(...)` in a test adds to it.
    with respx.mock as router:
        yield router
    unfurl.clear_cache()
    http.close_client()
    safe_fetch.close_client()
