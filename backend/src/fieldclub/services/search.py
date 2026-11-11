"""The map's search box: one query, read as whatever it most likely is.

`geo_search` tries, in order:

1. a British or Irish grid reference, such as `SU 1025 6996` or `J 338 740`,
2. a latitude and longitude, such as `51.4286, -1.8542` or `51.43N 1.85W`,
3. a British grid easting and northing, such as `410132 170023`,
4. a finding's public id, such as `7K3QXM`,
5. place names from the `places` gazetteer,
6. record names from the record index.

The first four give at most one result each and come first. Places and
records follow, ranked together by how well their names match the query
(`by_name`). Each of their queries is cut off at
`records.SEARCH_TIMEOUT_MS`, and a query that runs out of time leaves the
names out, not an error. The limit holds for each statement, not for the
names as a whole. A finding is placed where this viewer may see
it (Decision 0005), never more exactly. A hidden finding is found only by
those who may see it, as on `GET /findings`, and a withdrawn one never.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from geoalchemy2.shape import to_shape
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Place, Source, User
from fieldclub.schemas.records import GeoResultType
from fieldclub.services import findings, ids, records, sensitivity
from fieldclub.vocab import FindingState

logger = logging.getLogger(__name__)

PLACE_LIMIT = 5
RECORD_LIMIT = 5
# How many places like the query, by spelling, are ranked at most. A common
# word such as "hill" is like tens of thousands of names.
PLACE_CANDIDATES = 2000

# How far in to zoom for a grid square of each size, in metres.
GRIDREF_ZOOM = {10_000: 11, 1000: 14, 100: 16, 10: 17, 1: 18}
PLACE_ZOOM = {"city": 11, "town": 13, "village": 14, "hamlet": 15}
POINT_ZOOM = 16

_NUMBER = r"[-+]?\d{1,3}(?:\.\d+)?"
_LAT_LON = re.compile(
    rf"^\s*({_NUMBER})\s*°?\s*([NSEW])?\s*[,;\s]\s*({_NUMBER})\s*°?\s*([NSEW])?\s*$", re.IGNORECASE
)
_EAST_NORTH = re.compile(r"^\s*(\d{5,6})(?:\.\d+)?\s*[,;\s]\s*(\d{5,7})(?:\.\d+)?\s*$")

# Britain and Ireland, to tell latitude-then-longitude from the other way round.
_UK_LAT = (49.0, 61.5)
_UK_LON = (-11.5, 2.5)


@dataclass(frozen=True)
class GeoHit:
    type: GeoResultType
    label: str
    lon: float
    lat: float
    zoom: int
    detail: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    ref: str | None = None
    obscured: bool = False
    # A place's or record's source, so its licence and attribution go with it.
    source: Source | None = None


def _grid_detail(lon: float, lat: float) -> str | None:
    try:
        return gridref.to_gridref(lon, lat, 8)
    except gridref.GridRefError:
        return None


def as_gridref(text: str) -> GeoHit | None:
    ref = gridref.try_parse_gridref(text)
    if ref is None:
        return None
    lon, lat = ref.centre()
    size = ref.precision_m
    what = f"{size // 1000} km square" if size >= 1000 else f"{size} m square"
    return GeoHit(
        type="gridref",
        label=ref.format(),
        detail=f"Grid reference, {what}",
        lon=lon,
        lat=lat,
        zoom=GRIDREF_ZOOM[size],
        bbox=ref.polygon().bounds,
    )


def _inside(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def as_lat_lon(text: str) -> GeoHit | None:
    """Two numbers as a position. Compass letters decide the axes; without them, Britain decides."""
    match = _LAT_LON.match(text)
    if match is None:
        return None
    first, first_letter, second, second_letter = match.groups()
    a, b = float(first), float(second)
    first_letter, second_letter = (first_letter or "").upper(), (second_letter or "").upper()
    if first_letter in ("S", "W"):
        a = -abs(a)
    if second_letter in ("S", "W"):
        b = -abs(b)
    if first_letter in ("E", "W") or second_letter in ("N", "S"):
        lon, lat = a, b
    elif first_letter or second_letter:
        lat, lon = a, b
    elif _inside(b, _UK_LAT) and _inside(a, _UK_LON) and not _inside(a, _UK_LAT):
        # Longitude first, as GeoJSON and many tools write it.
        lon, lat = a, b
    else:
        lat, lon = a, b
    if not gridref.is_lon_lat(lon, lat):
        return None
    return GeoHit(
        type="coordinates",
        label=f"{lat:.5f}, {lon:.5f}",
        detail=_grid_detail(lon, lat),
        lon=lon,
        lat=lat,
        zoom=POINT_ZOOM,
    )


def as_east_north(text: str) -> GeoHit | None:
    """An easting and northing in metres on the British National Grid."""
    match = _EAST_NORTH.match(text)
    if match is None:
        return None
    easting, northing = float(match.group(1)), float(match.group(2))
    if not (0 <= easting < 700_000 and 0 <= northing < 1_300_000):
        return None
    lon, lat = gridref.to_lonlat(gridref.GridSystem.OSGB, easting, northing)
    return GeoHit(
        type="coordinates",
        label=f"{easting:.0f}, {northing:.0f}",
        detail=_grid_detail(lon, lat),
        lon=lon,
        lat=lat,
        zoom=POINT_ZOOM,
    )


def as_finding(db: Session, text: str, viewer: User | None) -> GeoHit | None:
    public_id = ids.normalise(text)
    if public_id is None:
        return None
    try:
        finding = findings.get_finding(db, public_id, viewer)
    except findings.FindingNotFoundError:
        return None
    if finding.state == FindingState.WITHDRAWN.value:
        return None
    seen = sensitivity.visible_location(finding, viewer)
    square = seen.square_polygon()
    bbox = square.bounds if square is not None else None
    saved_zoom = finding.view_state.get("zoom") if isinstance(finding.view_state, dict) else None
    exact_zoom = int(saved_zoom) if isinstance(saved_zoom, int | float) else 17
    zoom = 14 if seen.obscured else exact_zoom
    return GeoHit(
        type="finding",
        label=sensitivity.visible_text(finding, viewer, finding.title) or "",
        detail=f"Finding {finding.public_id}",
        lon=seen.lon,
        lat=seen.lat,
        zoom=zoom,
        bbox=bbox,
        ref=finding.public_id,
        obscured=seen.obscured,
    )


def places(db: Session, text: str, limit: int = PLACE_LIMIT) -> list[GeoHit]:
    """Places whose name is like the query. A search that runs out of time gives none, not an error.

    Names that start with the query come first, bigger places first, which
    suits someone still typing. The rest come by how alike they are, then
    by size, so a misspelt village comes before a town that only shares a word.
    Only when too few names start with the query are the rest looked for,
    among at most `PLACE_CANDIDATES` of them, so a common word stays quick.
    """
    words = records.query_words(text)
    if not words:
        return []
    phrase = " ".join(words)
    # The phrase is letters, digits and single spaces, so it holds no LIKE wildcard.
    assert re.fullmatch(r"[^\W_]+( [^\W_]+)*", phrase), "the phrase must be words and spaces"
    starts = Place.name.ilike(phrase + "%")
    found = select(Place, Source, func.ST_X(Place.geom), func.ST_Y(Place.geom)).outerjoin(
        Source, Source.key == Place.source
    )
    try:
        with records.time_limit(db):
            rows = list(db.execute(found.where(starts).order_by(Place.rank.desc(), Place.id).limit(limit)))
            if len(rows) < limit:
                records.use_name_similarity(db)
                candidates = (
                    select(Place.id).where(Place.name.op("%>")(literal(phrase))).limit(PLACE_CANDIDATES)
                ).scalar_subquery()
                similarity = func.strict_word_similarity(literal(phrase), Place.name)
                rows += db.execute(
                    found.where(Place.id.in_(candidates), ~starts)
                    .order_by(similarity.desc(), Place.rank.desc(), Place.id)
                    .limit(limit - len(rows))
                ).all()
    except records.SearchTimeoutError:
        logger.warning("Place search for %r ran out of time; the search box shows no places", text)
        return []
    hits = []
    for place, source, lon, lat in rows:
        detail = ", ".join(part for part in (place.district, place.county) if part) or None
        hits.append(
            GeoHit(
                type="place",
                label=place.name,
                detail=detail,
                lon=lon,
                lat=lat,
                zoom=PLACE_ZOOM.get(place.kind.lower(), 14),
                ref=str(place.id),
                source=source,
            )
        )
    return hits


def record_hits(db: Session, text: str, limit: int = RECORD_LIMIT) -> list[GeoHit]:
    """Records named like the query. A record search that runs out of time gives none, not an error."""
    try:
        found, _ = records.search(db, text, limit=limit)
    except records.SearchTimeoutError:
        logger.warning("Record search for %r ran out of time; the search box shows no records", text)
        return []
    hits = []
    for result in found:
        record = result.record
        shape = to_shape(record.geom)
        detail = " · ".join(part for part in (record.record_type, result.source.name) if part)
        hits.append(
            GeoHit(
                type="record",
                label=record.name,
                detail=detail,
                lon=result.lon,
                lat=result.lat,
                zoom=POINT_ZOOM,
                bbox=None if shape.geom_type == "Point" else shape.bounds,
                ref=str(record.id),
                source=result.source,
            )
        )
    return hits


def geo_search(db: Session, q: str, viewer: User | None, *, limit: int = 10) -> list[GeoHit]:
    """What the search box shows for `q`, best first."""
    assert 1 <= limit <= 20, "limit must be between 1 and 20"
    text = records.clean_query(q)
    if not text:
        return []
    exact = [
        hit
        for hit in (as_gridref(text), as_lat_lon(text), as_east_north(text), as_finding(db, text, viewer))
        if hit is not None
    ]
    try:
        with records.time_limit(db, records.SEARCH_TIMEOUT_MS):
            named = by_name(db, text, places(db, text) + record_hits(db, text))
    except records.SearchTimeoutError:
        logger.warning("Place search for %r ran out of time; the search box shows no names", text)
        named = []
    return (exact + named)[:limit]


def by_name(db: Session, text: str, hits: list[GeoHit]) -> list[GeoHit]:
    """Places and records in one order, by how well each name matches the whole query.

    A name that is the query comes first, then names that start with it, then
    the rest by how alike they are. Within the first two, places keep their
    lead over records, so a town comes before a record named after it. A
    search for "Stonehenge" gives the monument before Stonehenge Works, and
    one for "Maiden Castle" the hillfort before Castle Eden.
    """
    phrase = " ".join(records.query_words(text))

    def fit(hit: GeoHit) -> int:
        name = " ".join(records.query_words(hit.label))
        return 2 if name == phrase else 1 if name.startswith(phrase) else 0

    scored = [(fit(hit), hit) for hit in hits]
    # Only the loose matches are ordered by likeness. The sort is stable, so the rest keep their order.
    loose = list(dict.fromkeys(hit.label for value, hit in scored if value == 0))
    likeness = dict(zip(loose, _likeness(db, phrase, loose), strict=True))
    ranked = sorted(scored, key=lambda pair: (-pair[0], -likeness.get(pair[1].label, 0.0)))
    return [hit for _, hit in ranked]


def _likeness(db: Session, phrase: str, labels: list[str]) -> list[float]:
    """How alike each label is to the phrase, as the gazetteer and the record index rank names."""
    if not labels:
        return []
    row = db.execute(
        select(*(func.strict_word_similarity(literal(phrase), literal(label)) for label in labels))
    ).one()
    return [float(value) for value in row]
