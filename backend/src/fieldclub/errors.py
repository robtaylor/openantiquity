"""The error hierarchy and the JSON error handler.

Every error raised on purpose is a subclass of `AppError` with a stable `code`.
The handler turns them into `{"error": {"code": ..., "message": ...}}`.

This module is imported by services, so it keeps FastAPI and Starlette imports
inside `install_error_handlers`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for every deliberate error.

    Subclasses set `status_code`, `code` and a default `message`. A raise site
    can override the message, and the code when a more specific one helps the
    client decide what to do.
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Something went wrong."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.details = details
        self.headers = headers
        super().__init__(self.message)

    def to_body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "The request could not be understood."


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"
    message = "Some of the values sent were not valid."


class InvalidBboxError(BadRequestError):
    """A `bbox` that isn't four finite numbers running west to east and south to north."""

    code = "invalid_bbox"
    message = "bbox must be west,south,east,north in degrees, with west < east and south < north."


class InvalidCursorError(BadRequestError):
    """A page cursor that this server didn't make, or that asks for a page out of range."""

    code = "invalid_cursor"
    message = "That page cursor isn't valid. Start again from the first page."


class UnauthorisedError(AppError):
    status_code = 401
    code = "unauthorised"
    message = "You need to sign in to do that."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You're not allowed to do that."


class BannedError(ForbiddenError):
    code = "banned"
    message = "This account has been suspended."


class ClientHeaderRequiredError(ForbiddenError):
    code = "client_header_required"
    message = "Requests that change data must carry the X-FieldClub-Client header."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "That doesn't exist."


class TileNotFoundError(NotFoundError):
    """A map tile address outside the zooms or the grid a tile set has."""

    code = "tile_not_found"
    message = "There is no tile with that address."


class MediaNotFoundError(NotFoundError):
    """A photo that doesn't exist or that this viewer may not see: the two answer alike."""

    code = "media_not_found"
    message = "There's no photo with that id."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "That conflicts with something that already exists."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "You're doing that too often. Try again shortly."

    def __init__(self, retry_after_s: float, message: str | None = None) -> None:
        assert retry_after_s >= 0, "retry_after_s must not be negative"
        self.retry_after_s = retry_after_s
        # Round up so a client that waits this long is never told to wait again.
        seconds = max(1, int(-(-retry_after_s // 1)))
        super().__init__(message, headers={"Retry-After": str(seconds)})


class UpstreamError(AppError):
    status_code = 502
    code = "upstream_error"
    message = "A service we depend on didn't answer properly."


class FetchRefusedError(AppError):
    """An address someone else chose that `safe_fetch` won't fetch."""

    status_code = 422
    code = "fetch_refused"
    message = "That address can't be fetched."


class FetchFailedError(AppError):
    """A fetch `safe_fetch` allowed that gave no usable answer. `services.unfurl` raises it too."""

    status_code = 502
    code = "fetch_failed"
    message = "That address didn't answer usefully."


class ConfigError(AppError):
    code = "config_error"
    message = "The server is misconfigured."


class DataIntegrityError(AppError):
    """Stored data broke an assumption the code relies on."""

    code = "data_integrity_error"
    message = "Stored data is not in the expected shape."


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorised",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
}


def install_error_handlers(app: FastAPI) -> None:
    """Make every error leave the app as `{"error": {"code", "message"}}`.

    The handlers are `async` because they do no blocking work. Starlette would
    run a plain function in the thread pool, beside the sync endpoints.
    """
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def app_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        if exc.status_code >= 500:
            logger.error("%s: %s", type(exc).__name__, exc.message, exc_info=exc)
        return JSONResponse(exc.to_body(), status_code=exc.status_code, headers=exc.headers)

    async def validation_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        details = [
            {"field": ".".join(str(part) for part in err.get("loc", ())), "message": err.get("msg", "")}
            for err in exc.errors()
        ]
        failed = ValidationFailedError(details=details)
        return JSONResponse(failed.to_body(), status_code=failed.status_code)

    async def http_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = _STATUS_CODES.get(exc.status_code, "http_error" if exc.status_code < 500 else "internal_error")
        body = {"error": {"code": code, "message": str(exc.detail)}}
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error", exc_info=exc)
        return JSONResponse(AppError().to_body(), status_code=500)

    app.add_exception_handler(AppError, app_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unexpected_error)
