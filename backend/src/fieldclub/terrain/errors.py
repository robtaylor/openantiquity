"""Errors the terrain service raises on purpose."""

from __future__ import annotations

from fieldclub.errors import AppError, UpstreamError


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
