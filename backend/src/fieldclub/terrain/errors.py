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
    """The bulk supply refused the login or showed the wrong host key. Asking again won't help.

    Its own code and a 503, unlike the 502 of one tile's failed fetch: no tile
    can be fetched until the supply's credentials are put right, so a map
    should stop asking for 1 m tiles rather than retry each one.
    """

    status_code = 503
    code = "elevation_supply_refused"
    message = "The bulk supply of elevation is refusing us just now, so no new area can be prepared."


class SourceUnreadableError(DataIntegrityError):
    """Every copy of a source tile that could be found was the right size but couldn't be decoded."""


# How long a map or a profile is told to wait before asking again for elevation being added to the
# mirror. A 5 km tile takes from 13 seconds to three minutes to fetch and convert.
PREPARING_RETRY_S = 20


class ElevationPreparingError(AppError):
    """Elevation for the area is being added to the mirror in the background. Nothing waited for it.

    `details.tiles` names the 5 km tiles still missing. The answer carries
    `Retry-After`, and like every error it is sent `no-cache`.
    """

    status_code = 503
    code = "elevation_preparing"
    message = "Elevation for this area is being prepared. Try again in a minute."
    expected = True

    def __init__(self, tiles: list[str], retry_after_s: int = PREPARING_RETRY_S) -> None:
        assert tiles, "something must be missing for an area to be being prepared"
        super().__init__(details={"tiles": tiles}, headers={"Retry-After": str(retry_after_s)})


class TilesBusyError(AppError):
    """Every slot for drawing terrain tiles is taken and the queue for them is full."""

    status_code = 503
    code = "tiles_busy"
    message = "The map is busy. Try again in a moment."
    expected = True

    def __init__(self) -> None:
        super().__init__(headers={"Retry-After": "1"})


class ReadTooLargeError(AppError):
    """A read would cover far more ground than any tile or profile does. A bug, refused before any fetch."""

    code = "elevation_read_too_large"
    message = "That area is too large to read elevation for."
