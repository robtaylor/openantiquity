"""How the error handler answers and logs deliberate errors."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldclub.errors import AppError, UpstreamError, install_error_handlers
from fieldclub.terrain.errors import (
    ElevationPreparingError,
    ElevationUnavailableError,
    FetchFailedError,
    TilesBusyError,
)


def answer_with(error: AppError) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


def errors_logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelname in ("ERROR", "CRITICAL")]


@pytest.mark.parametrize(
    "error",
    [
        ElevationPreparingError(["SU16nw"]),
        TilesBusyError(),
        ElevationUnavailableError("SU16ne couldn't be added a short while ago.", expected=True),
    ],
    ids=["preparing", "busy", "remembered"],
)
def test_an_expected_5xx_is_logged_at_info_without_a_traceback(
    error: AppError, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        response = answer_with(error).get("/fail")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == error.code
    assert errors_logged(caplog) == []
    assert "Traceback" not in caplog.text
    assert any(record.levelname == "INFO" and error.code in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("error", [FetchFailedError(), UpstreamError(), AppError()])
def test_an_unexpected_5xx_is_logged_as_an_error_with_its_traceback(
    error: AppError, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        response = answer_with(error).get("/fail")
    assert response.status_code == error.status_code
    assert len(errors_logged(caplog)) == 1
    assert "Traceback" in caplog.text
