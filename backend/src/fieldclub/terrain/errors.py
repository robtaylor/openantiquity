"""Errors the terrain service raises on purpose."""

from __future__ import annotations

from fieldclub.errors import AppError, DataIntegrityError, UpstreamError


class ElevationUnavailableError(AppError):
    """Elevation that should exist can't be read right now. Nothing is cached when this is raised."""

    status_code = 503
    code = "elevation_unavailable"
    message = "Elevation for this area can't be read right now. Try again shortly."


class CredentialsMissingError(ElevationUnavailableError):
    code = "elevation_credentials_missing"
    message = "This area isn't in the elevation mirror yet, and the bulk supply's credentials aren't set."


class FetchFailedError(UpstreamError):
    code = "elevation_fetch_failed"
    message = "Elevation for this area couldn't be fetched from the bulk supply."


class SupplyRefusedError(FetchFailedError):
    """The bulk supply refused the login or showed the wrong host key. Asking again won't help."""


class SourceUnreadableError(DataIntegrityError):
    """Every copy of a source tile that could be found was the right size but couldn't be decoded."""


class ReadTooLargeError(AppError):
    """A read would cover far more ground than any tile or profile does. A bug, refused before any fetch."""

    code = "elevation_read_too_large"
    message = "That area is too large to read elevation for."
