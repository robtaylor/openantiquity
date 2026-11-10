"""What every reader shares: the feature shape, errors, reprojection and polite requests."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from fieldclub.config import Settings
from fieldclub.ingest.errors import IngestError

logger = logging.getLogger(__name__)

WGS84 = CRS.from_epsg(4326)

# Statuses worth asking again for. Anything else in the 4xx range is our
# mistake or a refusal, and asking again would be rude.
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class AdapterError(IngestError):
    """An upstream service or file could not be read."""

    code = "ingest_adapter_error"
    message = "An upstream source could not be read."


class UpstreamFormatError(AdapterError):
    """The upstream answered, but not in the shape the reader relies on."""

    code = "ingest_upstream_format"


class IncompleteReadError(AdapterError):
    """A reader got fewer features than the upstream said it had."""

    code = "ingest_incomplete_read"


class Tally:
    """The distinct features a paged read has given, so a repeat can't stand in for one that was skipped.

    When the data shifts between pages, an offset can give one feature twice
    and never give another. Counting every feature would then look complete.
    `add` takes each feature's id, and `check` compares the distinct count
    with what the upstream said it had. A feature without an id counts once
    each time, because there is nothing to tell it by.
    """

    def __init__(self, where: str, expected: int, tolerance: float = 0.0, what: str = "features") -> None:
        assert expected >= 0, "the expected count can't be negative"
        assert 0 <= tolerance < 1, "tolerance is a share between 0 and 1"
        self.where = where
        self.expected = expected
        self.tolerance = tolerance
        self.what = what
        self.repeats = 0
        self._ids: set[Any] = set()
        self._without_id = 0

    def add(self, key: Any) -> None:
        if key is None:
            self._without_id += 1
        elif key in self._ids:
            self.repeats += 1
        else:
            self._ids.add(key)

    @property
    def distinct(self) -> int:
        return len(self._ids) + self._without_id

    def check(self) -> None:
        """Raise `IncompleteReadError` when fewer distinct features came than were promised."""
        if self.distinct >= self.expected * (1 - self.tolerance):
            return
        repeats = f", and {self.repeats} more that repeated one already given" if self.repeats else ""
        raise IncompleteReadError(
            f"{self.where} said it had {self.expected} {self.what} and gave {self.distinct}{repeats}."
        )


@dataclass(frozen=True)
class Feature:
    """One upstream feature: plain properties and a WGS84 geometry, longitude first.

    `geometry` is None when the upstream row has no position. Property values
    are plain Python: str, int, float, bool, None, or a timezone-aware
    datetime. NaN is turned into None, because the runner stores `raw` as JSON.
    """

    properties: dict[str, Any]
    geometry: BaseGeometry | None
    id: str | int | None = None


@lru_cache(maxsize=32)
def _transformer(crs: str) -> Transformer | None:
    source = CRS.from_user_input(crs)
    if source == WGS84 or source.to_epsg() == 4326 or source.name == "WGS 84 (CRS84)":
        return None
    return Transformer.from_crs(source, WGS84, always_xy=True)


def to_wgs84(geometry: BaseGeometry, crs: str) -> BaseGeometry:
    """`geometry` from `crs` (any form pyproj reads, such as `EPSG:27700`) into WGS84, x first."""
    transformer = _transformer(crs)
    if transformer is None:
        return geometry
    result = shapely.transform(
        geometry, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1]))
    )
    assert isinstance(result, BaseGeometry), "shapely.transform returns a geometry for a geometry"
    return result


def plain(value: Any) -> Any:
    """A property value as plain Python: numpy scalars unwrapped, NaN and NaT as None, datetimes in UTC.

    A datetime without a zone is taken to be UTC, which is what OGR gives
    for the `Z` suffix and what every source read so far means.
    """
    if isinstance(value, np.datetime64):
        # At nanosecond precision `.item()` gives an int, so go through microseconds.
        value = None if np.isnat(value) else value.astype("datetime64[us]").item()
    elif isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def plain_tree(value: Any) -> Any:
    """`plain` applied all the way down through the lists and objects of a JSON value.

    Python's JSON reader accepts `NaN` and `Infinity`, so a parsed payload can
    hold values the runner refuses to store.
    """
    if isinstance(value, dict):
        return {key: plain_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain_tree(item) for item in value]
    return plain(value)


def json_ready(properties: dict[str, Any]) -> dict[str, Any]:
    """A copy of `properties` that `json.dumps` accepts: datetimes as ISO 8601 text."""
    return {
        key: value.isoformat() if isinstance(value, datetime) else value for key, value in properties.items()
    }


def cache_dir(settings: Settings, source_key: str) -> Path:
    """Where a connector keeps downloaded files: `var/ingest/<source key>/`."""
    path = Path(settings.var_dir) / "ingest" / source_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _retry_after(response: httpx.Response, now: Callable[[], datetime]) -> float | None:
    """Seconds the server asked us to wait, from `Retry-After`, or None."""
    value = response.headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now()).total_seconds())


@dataclass
class Polite:
    """How a reader treats a server: a gap between requests, and retries with backoff.

    Retries happen on a dropped connection, a timeout, 408, 429 and 5xx. A
    `Retry-After` header is honoured, up to `max_backoff_s`. Any other
    error status raises `AdapterError` at once. Tests pass a `sleep` that
    records instead of waiting.
    """

    delay_s: float = 1.0
    retries: int = 4
    backoff_s: float = 2.0
    max_backoff_s: float = 120.0
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    _last: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        assert self.delay_s >= 0, "delay_s must not be negative"
        assert self.retries >= 0, "retries must not be negative"
        assert self.backoff_s > 0, "backoff_s must be positive"

    def wait_turn(self) -> None:
        """Sleep so that requests are at least `delay_s` apart."""
        if self._last is not None and self.delay_s:
            elapsed = time.monotonic() - self._last
            if elapsed < self.delay_s:
                self.sleep(self.delay_s - elapsed)
        self._last = time.monotonic()

    def backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        """How long to wait before retry number `attempt` (1-based)."""
        asked = _retry_after(response, self.now) if response is not None else None
        wait = asked if asked is not None else self.backoff_s * 2 ** (attempt - 1)
        return min(wait, self.max_backoff_s)

    def request(self, client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send one request, retrying politely. Returns a 2xx or 3xx response, or raises `AdapterError`."""
        for attempt in range(1, self.retries + 2):
            self.wait_turn()
            try:
                response = client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt > self.retries:
                    raise AdapterError(
                        f"{method} {short_url(url)} failed: {type(exc).__name__}: {exc}"
                    ) from exc
                wait = self.backoff(attempt)
                logger.warning("%s %s failed (%s), retrying in %.0f s", method, short_url(url), exc, wait)
                self.sleep(wait)
                continue
            if response.status_code < 400:
                return response
            if response.status_code in RETRY_STATUSES and attempt <= self.retries:
                wait = self.backoff(attempt, response)
                logger.warning(
                    "%s %s answered %d, retrying in %.0f s",
                    method,
                    short_url(url),
                    response.status_code,
                    wait,
                )
                self.sleep(wait)
                continue
            raise AdapterError(
                f"{method} {short_url(url)} answered {response.status_code}: {response.text[:200]!r}"
            )
        raise AssertionError("unreachable: the loop returns or raises")


def short_url(url: str) -> str:
    """A URL without its query string, for messages."""
    return url.split("?", 1)[0]
