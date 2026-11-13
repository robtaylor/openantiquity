"""Fixtures for the activity tests."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
import uvicorn
from fastapi import FastAPI

from tests.activity.support import TIMEOUT_S


@pytest.fixture
def server(app: FastAPI) -> Iterator[str]:
    """The app served by uvicorn on a free port. Close every stream before the test ends."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on", ws="none")
    running = uvicorn.Server(config)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    for _ in range(200):
        if running.started:
            break
        threading.Event().wait(0.05)
    assert running.started, "uvicorn didn't start"
    port = running.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(timeout=TIMEOUT_S)
    assert not thread.is_alive(), "uvicorn didn't stop"
