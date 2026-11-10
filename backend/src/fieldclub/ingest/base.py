"""What a connector is, and the shape of what it yields.

A connector subclasses `Connector`, declares the `SourceInfo` for its `sources`
row, and implements `fetch()`. It turns one upstream payload into `RecordIn`
objects and does nothing else: no database access, no credentials of its own.
The runner validates and stores what it yields.

Assert what you assume about the upstream payload. A surprise should stop the
run, not write bad rows.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import httpx
from shapely.geometry.base import BaseGeometry

from fieldclub import http
from fieldclub.config import Settings, get_settings
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

# West, south, east, north in degrees.
BBox = tuple[float, float, float, float]

# Britain and Ireland with their islands, and a little room. A record outside
# this box nearly always means swapped axes or grid coordinates sent as degrees.
BRITISH_ISLES: BBox = (-11.5, 49.0, 2.5, 61.5)

_KEY_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@dataclass(frozen=True)
class SourceInfo:
    """The `sources` row for a connector. Licence, attribution and reuse class are required up front.

    `reuse` says what the licence allows (Decision 0004): `open`,
    `share_alike`, `non_commercial` or `link_only`. There is no default,
    because guessing a licence class is how data ends up somewhere it may not go.
    """

    key: str
    name: str
    publisher: str
    licence: str
    attribution: str
    category: RecordCategory | str
    access: SourceAccess | str
    reuse: SourceReuse | str
    licence_url: str | None = None
    homepage: str | None = None
    coverage: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        assert _KEY_PATTERN.fullmatch(self.key), (
            f"source key {self.key!r} must be lower-case words joined by hyphens"
        )
        for name in ("name", "publisher", "licence", "attribution"):
            assert getattr(self, name).strip(), f"source {self.key} needs a {name}"
        assert self.access in SourceAccess, f"source {self.key} has unknown access {self.access!r}"
        assert self.reuse in SourceReuse, f"source {self.key} has unknown reuse class {self.reuse!r}"
        assert self.category, f"source {self.key} needs a category"


@dataclass
class RecordIn:
    """One record as a connector yields it. Covers every column of `records` that a source can fill.

    `geom` is a shapely geometry in WGS84, longitude then latitude. The runner
    works out `centroid`, and sets `source_key` and `ingested_at` itself.
    """

    external_id: str
    name: str
    geom: BaseGeometry
    # Defaults to the source's category.
    category: RecordCategory | str | None = None
    summary: str | None = None
    record_type: str | None = None
    # Monument-type terms as the source gives them, usually FISH thesaurus terms.
    monument_types: Sequence[str] = ()
    # `vocab.Period` values. Map the source's own period names onto them.
    periods: Sequence[str] = ()
    # How exact the position is, in metres. 1000 for a find published to a 1 km square.
    precision_m: float | None = None
    url: str | None = None
    # The upstream payload, kept so nothing is lost. Must be JSON-serialisable.
    raw: dict[str, Any] | None = field(default=None, repr=False)
    source_updated_at: datetime | None = None


class Connector(ABC):
    """Base class for a source of records."""

    source: ClassVar[SourceInfo]
    # Every record must fall inside this box. Override for a source that
    # legitimately reaches further.
    bounds: ClassVar[BBox] = BRITISH_ISLES

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "source" in cls.__dict__:
            assert isinstance(cls.source, SourceInfo), f"{cls.__name__}.source must be a SourceInfo"

    @property
    def http(self) -> httpx.Client:
        """The shared outbound client, with the project's timeout and User-Agent."""
        return self._client or http.get_client()

    def is_configured(self) -> bool:
        """Whether the connector has what it needs to run.

        A source that needs an API key reads it from settings here and returns
        False when it is absent. The runner then skips the source.
        """
        return True

    @abstractmethod
    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        """Yield every record, or those in `bbox` when the source can filter by area.

        `bbox` and `limit` are hints that let a connector do less work. The
        runner enforces both, so a connector may ignore them.
        """
