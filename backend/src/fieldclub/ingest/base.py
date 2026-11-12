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
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ClassVar

import httpx
from shapely.geometry import GeometryCollection, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry
from shapely.prepared import prep

from fieldclub import credits, http
from fieldclub.config import Settings, get_settings
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

# West, south, east, north in degrees.
BBox = tuple[float, float, float, float]

# Britain and Ireland with their islands, and a little room. A record outside
# this box nearly always means swapped axes or grid coordinates sent as degrees.
BRITISH_ISLES: BBox = (-11.5, 49.0, 2.5, 61.5)


def point_in_bbox(bbox: BBox, lon: float, lat: float) -> bool:
    """Whether a point falls in a west, south, east, north box."""
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


# The islands' box without the open Atlantic south-west of Cornwall, so the
# ocean's names that Pleiades pins to a corner fall outside it.
ISLES_BOX: BBox = (-11.5, 49.1, 2.5, 61.5)

# A coarse outline of the Continent's coast from Cherbourg to Dunkirk, drawn
# through mid-Channel and east of Dover, so Kent, Sussex and the Channel
# Islands (whose eastern edge is at 2.0 W) lie outside it and Normandy,
# Picardy, the Pas-de-Calais and the Oise valley lie inside.
_CONTINENT = prep(
    Polygon(
        [
            (-1.9, 48.0),
            (-1.9, 49.6),
            (0.0, 50.2),
            (1.0, 50.6),
            (1.45, 50.95),
            (1.5, 51.1),
            (2.6, 51.3),
            (2.6, 48.0),
        ]
    )
)


def in_britain_and_ireland(lon: float, lat: float) -> bool:
    """Whether a point is in the islands' box and not on the Continent's side of the Channel.

    The one coarse test every research connector uses to leave out France
    and the Low Countries, which `BRITISH_ISLES` (the runner's box) also holds.
    """
    return point_in_bbox(ISLES_BOX, lon, lat) and not _CONTINENT.intersects(Point(lon, lat))


def geometry_in_britain_and_ireland(geometry: BaseGeometry) -> bool:
    """Whether a shape lies wholly in the islands' box and touches nothing on the Continent.

    A sea lane from Dover to Boulogne has no vertex in the Channel's middle
    that the box could catch, so any vertex or crossing on the Continent counts.
    """
    return bbox_in_bbox(ISLES_BOX, geometry.bounds) and not _CONTINENT.intersects(geometry)


def bbox_in_bbox(outer: BBox, inner: tuple[float, float, float, float]) -> bool:
    """Whether `inner`, such as a geometry's `.bounds`, lies wholly inside `outer`."""
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


_MULTIPART_TYPES: dict[str, Callable[[Any], BaseGeometry]] = {
    "MultiPoint": MultiPoint,
    "MultiLineString": MultiLineString,
    "MultiPolygon": MultiPolygon,
    "GeometryCollection": GeometryCollection,
}


def without_empty_parts(geom: BaseGeometry) -> tuple[BaseGeometry, bool]:
    """A geometry without its empty members and empty holes, and whether any were removed.

    Every shape from a publisher goes through this before it is stored or tested
    against another: the runner's records and the reference loaders' rows.

    PostGIS takes the point for `centroid` from the highest-dimension member,
    so `GEOMETRYCOLLECTION(POINT(...), POLYGON EMPTY)` would be stored with an
    empty centroid and never be found by a distance query.

    A polygon with an empty hole is valid to GEOS, which then crashes the
    process in `contains`, `covers`, `within` and `relate`
    (https://github.com/libgeos/geos/issues/1604). PostGIS refuses to store
    one, which would fail the whole run for one publisher's slip.
    """
    if isinstance(geom, Polygon):
        holes = [ring for ring in geom.interiors if not ring.is_empty]
        if geom.is_empty or len(holes) == len(geom.interiors):
            return geom, False
        return Polygon(geom.exterior, holes), True
    if not isinstance(geom, BaseMultipartGeometry):
        return geom, False
    kept: list[BaseGeometry] = []
    changed = False
    for part in geom.geoms:
        # A collection holding nothing but empty members is itself empty.
        if part.is_empty:
            changed = True
            continue
        part, part_changed = without_empty_parts(part)
        changed = changed or part_changed
        kept.append(part)
    if not changed:
        return geom, False
    rebuild = _MULTIPART_TYPES.get(geom.geom_type)
    assert rebuild is not None, f"don't know how to rebuild a {geom.geom_type}"
    return rebuild(kept), True


_KEY_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def fill_attribution(text: str, obtained: date) -> str:
    """`text` with `[year]` and `[date]`, such as "10 November 2026", filled in from `obtained`.

    Work-list attributions carry `[year]`, and Historic England's currency
    statement `[date]`. A connector copies the text as it stands, and the
    runner fills both in when it stores the `sources` row, so it never goes stale.
    """
    return text.replace("[year]", str(obtained.year)).replace("[date]", f"{obtained.day} {obtained:%B %Y}")


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
    # What a visitor is shown: the licence's short name and a credit line. Taken
    # from `fieldclub.credits` by the key when not given here.
    licence_label: str | None = None
    credit: str | None = None

    def __post_init__(self) -> None:
        assert _KEY_PATTERN.fullmatch(self.key), (
            f"source key {self.key!r} must be lower-case words joined by hyphens"
        )
        for name in ("name", "publisher", "licence", "attribution"):
            assert getattr(self, name).strip(), f"source {self.key} needs a {name}"
        assert self.access in SourceAccess, f"source {self.key} has unknown access {self.access!r}"
        assert self.reuse in SourceReuse, f"source {self.key} has unknown reuse class {self.reuse!r}"
        assert self.category, f"source {self.key} needs a category"
        shown = credits.credit_for(self.key)
        if shown is not None:
            # A frozen dataclass sets its own fields this way.
            if self.licence_label is None:
                object.__setattr__(self, "licence_label", shown.licence_label)
            if self.credit is None:
                object.__setattr__(self, "credit", shown.credit)


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
        # When the data `fetch()` read was obtained from upstream, such as a
        # cached download's fetch time. The runner fills the attribution's
        # `[date]` and `[year]` from it, or from the run's start when it is None.
        self.obtained_at: datetime | None = None

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
