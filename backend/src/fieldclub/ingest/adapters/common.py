"""What every reader shares: the feature shape, errors, reprojection and polite requests."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable, Sequence
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
from fieldclub.ingest.errors import AdapterError as AdapterError
from fieldclub.ingest.errors import UpstreamFormatError as UpstreamFormatError

logger = logging.getLogger(__name__)

WGS84 = CRS.from_epsg(4326)

# Statuses worth asking again for. Anything else in the 4xx range is our
# mistake or a refusal, and asking again would be rude.
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


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
    `native` is the same shape in the source's own projected CRS, before it was
    reprojected, when the reader had it. `FeatureKeys` hashes that, because a
    reprojection moves with the PROJ version and datum grids installed, and an
    id must not.
    """

    properties: dict[str, Any]
    geometry: BaseGeometry | None
    id: str | int | None = None
    native: BaseGeometry | None = None


@lru_cache(maxsize=32)
def _transformer(crs: str) -> Transformer | None:
    source = CRS.from_user_input(crs)
    if source == WGS84 or source.to_epsg() == 4326 or source.name == "WGS 84 (CRS84)":
        return None
    return Transformer.from_crs(source, WGS84, always_xy=True)


@lru_cache(maxsize=32)
def _from_wgs84(crs: str) -> Transformer:
    return Transformer.from_crs(WGS84, crs, always_xy=True)


def bbox_from_wgs84(bbox: tuple[float, float, float, float], crs: str) -> tuple[float, float, float, float]:
    """A WGS84 box, longitude first, as the box that covers it in `crs`."""
    return _from_wgs84(crs).transform_bounds(*bbox, densify_pts=21)


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


def native_in(geometry: BaseGeometry, crs: str) -> BaseGeometry | None:
    """`geometry` when `crs` is a CRS that `to_wgs84` will move, None when it is WGS84 already."""
    return None if _transformer(crs) is None else geometry


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


def json_body(response: httpx.Response, where: str) -> Any:
    """The response parsed as JSON, or `UpstreamFormatError` naming `where`."""
    try:
        return response.json()
    except ValueError:
        raise UpstreamFormatError(f"{where} did not answer with JSON.") from None


class FeatureKeys:
    """Stable external ids for a source that publishes none, built from what names each feature.

    `key(parts, geometry, native=...)` hashes the text `parts` (upstream fields
    that name the thing and survive a republish) with the shape. The shape is
    `native` when the reader has it, rounded to a tenth of a metre, and
    otherwise `geometry` in WGS84 rounded to seven decimal places of a degree,
    about a centimetre. Prefer `native`: a reprojection moves every vertex by
    metres or by 1e-5 degrees when the PROJ version or its datum grids change,
    and that would give every feature a new id, and so delete every record and
    its links on the next full run. The same feature gives the same key in
    every run.

    Features that agree in every part and in their shape are not always the
    same drawing entered twice: in the detailed mapping they often differ in
    type or period. `key` numbers such repeats `-2`, `-3` in read order, which
    is only right when they are identical. `distinct_key` takes `detail`, the
    rest of the feature's attributes. A repeat with the same detail as one
    already given is a true duplicate and gets None, for the connector to
    skip. A repeat with different detail is named for it, `-` and a hash of
    the detail, so a re-export in another order doesn't swap the ids of two
    interpretations. Which of them keeps the bare key still follows read order.
    Duplicates and repeats are counted in `repeats`, for the connector to report.
    """

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}
        self._details: dict[str, set[str]] = {}
        self.repeats = 0

    @staticmethod
    def _digest(
        parts: Sequence[str | None], geometry: BaseGeometry | None, native: BaseGeometry | None
    ) -> str:
        if native is not None:
            wkt = shapely.to_wkt(native, rounding_precision=1, trim=True)
        elif geometry is not None:
            wkt = shapely.to_wkt(geometry, rounding_precision=7, trim=True)
        else:
            wkt = ""
        text = "|".join((part or "").strip().lower() for part in parts) + "|" + wkt
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]

    def key(
        self,
        parts: Sequence[str | None],
        geometry: BaseGeometry | None,
        *,
        native: BaseGeometry | None = None,
    ) -> str:
        digest = self._digest(parts, geometry, native)
        count = self._seen.get(digest, 0) + 1
        self._seen[digest] = count
        if count == 1:
            return digest
        self.repeats += 1
        return f"{digest}-{count}"

    def distinct_key(
        self,
        parts: Sequence[str | None],
        geometry: BaseGeometry | None,
        detail: Sequence[str | None],
        *,
        native: BaseGeometry | None = None,
    ) -> str | None:
        """A key, or None when a feature with the same parts, shape and `detail` was already given."""
        digest = self._digest(parts, geometry, native)
        fingerprint = hashlib.sha256("|".join(part or "" for part in detail).encode("utf-8")).hexdigest()[:8]
        seen = self._details.setdefault(digest, set())
        if fingerprint in seen:
            self.repeats += 1
            return None
        seen.add(fingerprint)
        if len(seen) == 1:
            return digest
        self.repeats += 1
        return f"{digest}-{fingerprint}"


def json_ready(properties: dict[str, Any], *, drop_empty: bool = False) -> dict[str, Any]:
    """A copy of `properties` that `json.dumps` accepts: datetimes as ISO 8601 text.

    `drop_empty` leaves out values that are None or blank text, for a layer
    that is mostly empty fields.
    """
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in properties.items()
        if not (drop_empty and (value is None or (isinstance(value, str) and not value.strip())))
    }


def text_of(properties: dict[str, Any], field: str) -> str:
    """A text property trimmed, or an empty string when it is missing or null."""
    return str(properties.get(field) or "").strip()


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
