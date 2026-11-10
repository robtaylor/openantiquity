"""The record index: search, records near a point, one record, sources, and suggestions for a finding.

Every function returns records paired with their `Source`, so the caller can
always show the licence and attribution. Records of a disabled source are
never returned.

Text search uses two indexes. The generated `records.search` tsvector finds
records by the words of their name, types and summary, with every word of the
query treated as a prefix so a half-typed word still matches. The trigram
index on `records.name` finds names that are spelt differently from the
query. Only letters and digits from the query reach either, so quotes,
tsquery operators and control characters can't break the query or change
its meaning.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import ColumnElement, Integer, Select, cast, func, literal, or_, select, true
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import BadRequestError, NotFoundError
from fieldclub.models import Finding, Record, Source, User
from fieldclub.models.common import SRID
from fieldclub.schemas.common import decode_cursor, encode_cursor
from fieldclub.services import sensitivity
from fieldclub.vocab import MODERATOR_ROLES, FeatureClass, RecordCategory, Role

# The search box sends at most this much. The API refuses longer, and the
# service cuts anything longer that reaches it another way.
MAX_QUERY_CHARS = 200
# Words beyond these are ignored, and so is anything past this length in a word.
MAX_QUERY_WORDS = 8
MAX_WORD_CHARS = 40
# How alike a name must be to the query to match by spelling alone (pg_trgm's
# word similarity, 0 to 1). The default of 0.6 misses one wrong letter in a
# short word, such as "silbery" for "Silbury".
NAME_SIMILARITY = 0.4
# Offsets beyond this are refused. Nobody reads 2,000 search results.
MAX_OFFSET = 2000

MAX_RADIUS_M = 20_000.0
METRES_PER_DEGREE = 111_320.0

# Suggested records: how far to look from the position the viewer may see,
# or from the edge of its square, and how much the two halves of the score count.
SUGGEST_RADIUS_M = 500.0
SUGGEST_CANDIDATES = 200
DISTANCE_WEIGHT = 0.65
TYPE_WEIGHT = 0.35

_WORD = re.compile(r"[^\W_]+")
# A select of any columns. SQLAlchemy 2.1 types a select by its column types.
AnySelect = Select[*tuple[Any, ...]]


class RecordNotFoundError(NotFoundError):
    code = "record_not_found"
    message = "There is no record with that id."


class FindingNotFoundError(NotFoundError):
    code = "finding_not_found"
    message = "There is no finding with that id."


class InvalidSearchError(BadRequestError):
    code = "invalid_search"


@dataclass(frozen=True)
class RecordResult:
    record: Record
    source: Source
    lon: float
    lat: float
    # Metres from the point asked about, for a search near a point.
    distance_m: float | None = None


@dataclass(frozen=True)
class Suggestion:
    result: RecordResult
    type_fit: bool
    score: float


@dataclass(frozen=True)
class SuggestionList:
    origin: sensitivity.VisibleLocation
    items: list[Suggestion]


# --------------------------------------------------------------------------
# Query text
# --------------------------------------------------------------------------


def clean_query(text: str | None) -> str:
    """The query with control and format characters turned into spaces, trimmed and cut to length."""
    if not text:
        return ""
    cleaned = "".join(
        " " if unicodedata.category(char)[0] == "C" else char for char in text[:MAX_QUERY_CHARS]
    )
    return " ".join(cleaned.split())


def query_words(text: str) -> list[str]:
    """The words of a query that reach the database: letters and digits only, lower case."""
    return [word[:MAX_WORD_CHARS].lower() for word in _WORD.findall(text)][:MAX_QUERY_WORDS]


def prefix_tsquery(words: list[str]) -> str:
    """`to_tsquery` text matching every word as a prefix, such as `silbury:* & hil:*`.

    Safe because each word is letters and digits only. Stop words like
    "the" drop out in PostgreSQL rather than matching nothing.
    """
    assert all(_WORD.fullmatch(word) for word in words), "words must be letters and digits only"
    return " & ".join(f"{word}:*" for word in words)


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


def _base() -> AnySelect:
    """Records with their source and a point on each, from enabled sources only."""
    return (
        select(Record, Source, func.ST_X(Record.centroid), func.ST_Y(Record.centroid))
        .join(Source, Source.key == Record.source_key)
        .where(Source.enabled)
    )


def _envelope(bbox: tuple[float, float, float, float]) -> ColumnElement[Any]:
    west, south, east, north = bbox
    return func.ST_MakeEnvelope(west, south, east, north, SRID)


def check_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    if not all(math.isfinite(value) for value in bbox):
        raise InvalidSearchError("A bbox must be four finite numbers.")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise InvalidSearchError(
            "A bbox is west,south,east,north in degrees, with west < east and south < north."
        )
    return bbox


def _filters(
    statement: AnySelect,
    *,
    sources: list[str] | None,
    categories: list[str] | None,
    bbox: tuple[float, float, float, float] | None,
) -> AnySelect:
    if sources:
        statement = statement.where(Record.source_key.in_(sources))
    if categories:
        unknown = [value for value in categories if value not in RecordCategory]
        if unknown:
            raise InvalidSearchError(f"Unknown record categories: {', '.join(unknown)}.")
        statement = statement.where(Record.category.in_(categories))
    if bbox is not None:
        statement = statement.where(func.ST_Intersects(Record.geom, _envelope(check_bbox(bbox))))
    return statement


def _results(rows: Any, distance: bool = False) -> list[RecordResult]:
    return [RecordResult(row[0], row[1], row[2], row[3], float(row[4]) if distance else None) for row in rows]


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


def use_name_similarity(db: Session) -> None:
    """Make `%>` match at `NAME_SIMILARITY` for the rest of this transaction."""
    db.execute(select(func.set_config("pg_trgm.word_similarity_threshold", str(NAME_SIMILARITY), true())))


def search(
    db: Session,
    q: str | None = None,
    *,
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[RecordResult], str | None]:
    """Records matching the text, filters and box, best match first. Returns a page and the next cursor.

    Ranking puts a name that starts with the query first, then weighs the
    full-text rank (name words count most, then types, then the summary)
    with how closely the name is spelt like the query. Without text,
    records come in name order.
    """
    assert 1 <= limit <= 200, "limit must be between 1 and 200"
    offset = decode_cursor(cursor, 1)[0] if cursor else 0
    if not isinstance(offset, int) or not 0 <= offset <= MAX_OFFSET:
        raise InvalidSearchError("That page is out of range. Narrow the search instead.")
    text = clean_query(q)
    words = query_words(text)
    statement = _filters(_base(), sources=sources, categories=categories, bbox=bbox)

    if words:
        phrase = " ".join(words)
        tsquery = func.to_tsquery("english", literal(prefix_tsquery(words)))
        # Matching uses word similarity, which is what the index serves. Ranking
        # uses the strict form, which tells "Silbury" from "Ropery" for "silbery".
        similarity = func.strict_word_similarity(literal(phrase), Record.name)
        starts = func.starts_with(func.lower(Record.name), literal(phrase))
        rank = func.ts_rank_cd(Record.search, tsquery, 1) * 4 + similarity + cast(starts, Integer) * 2
        use_name_similarity(db)
        statement = statement.where(
            or_(Record.search.op("@@")(tsquery), Record.name.op("%>")(literal(phrase)))
        )
        statement = statement.order_by(rank.desc(), Record.id)
    elif text:
        # Punctuation and nothing else: nothing can match.
        return [], None
    else:
        statement = statement.order_by(Record.name, Record.id)

    rows = db.execute(statement.offset(offset).limit(limit + 1)).all()
    items = _results(rows[:limit])
    next_cursor = (
        encode_cursor([offset + limit]) if len(rows) > limit and offset + limit <= MAX_OFFSET else None
    )
    return items, next_cursor


# --------------------------------------------------------------------------
# Near a point
# --------------------------------------------------------------------------


def check_point(lon: float, lat: float) -> None:
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise InvalidSearchError("lon and lat must be a position in degrees.")


def nearby(
    db: Session,
    lon: float,
    lat: float,
    *,
    radius_m: float = 1000.0,
    limit: int = 50,
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    area: BaseGeometry | None = None,
) -> list[RecordResult]:
    """Records within `radius_m` of a point, or of `area` around it, nearest first.

    The distance is to the nearest part of the record's geometry, so a point
    inside a monument's area is 0 m from it, and so is a record inside `area`.
    The box test on `geom` uses its index. The exact test and the distance are
    on the geography.
    """
    check_point(lon, lat)
    assert 0 < radius_m <= MAX_RADIUS_M, f"radius must be between 0 and {MAX_RADIUS_M} m"
    assert 1 <= limit <= SUGGEST_CANDIDATES, "limit out of range"
    if area is None:
        here = func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID)
    else:
        assert area.covers(Point(lon, lat)), "the point must lie in the area"
        here = func.ST_GeomFromText(area.wkt, SRID)
    here_geography = func.Geography(here)
    # Degrees of latitude are all about the same length. Degrees of longitude
    # shrink with the cosine of the latitude. 2% spare covers the ellipsoid.
    dlat = radius_m / METRES_PER_DEGREE * 1.02
    dlon = radius_m / (METRES_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01)) * 1.02
    distance = func.ST_Distance(func.Geography(Record.geom), here_geography)
    statement = _filters(
        _base().add_columns(distance), sources=sources, categories=categories, bbox=None
    ).where(
        Record.geom.op("&&")(func.ST_Expand(here, dlon, dlat)),
        func.ST_DWithin(func.Geography(Record.geom), here_geography, radius_m),
    )
    rows = db.execute(statement.order_by(distance, Record.id).limit(limit)).all()
    return _results(rows, distance=True)


# --------------------------------------------------------------------------
# One record, and the sources
# --------------------------------------------------------------------------


def get_record(db: Session, record_id: int) -> RecordResult:
    row = db.execute(_base().where(Record.id == record_id)).first()
    if row is None:
        raise RecordNotFoundError()
    return _results([row])[0]


def list_sources(db: Session) -> list[Source]:
    """Every enabled source, with its stored record count."""
    return list(db.scalars(select(Source).where(Source.enabled).order_by(Source.name, Source.key)).all())


# --------------------------------------------------------------------------
# Suggested records for a finding
# --------------------------------------------------------------------------

# Words in a record's name, type or monument types that fit each feature class.
# Matched as whole words, with or without a plural s.
CLASS_TERMS: dict[FeatureClass, tuple[str, ...]] = {
    FeatureClass.ENCLOSURE: ("enclosure", "enclosed", "ringwork", "camp"),
    FeatureClass.HILLFORT: ("hillfort", "hill fort", "fort", "camp", "rampart"),
    FeatureClass.ROUND_BARROW: ("barrow", "tumulus", "tumuli", "mound", "cairn"),
    FeatureClass.LONG_BARROW: ("long barrow", "chambered tomb", "long cairn", "long mound"),
    FeatureClass.HUT_CIRCLE: ("hut circle", "roundhouse", "round house", "hut"),
    FeatureClass.SETTLEMENT: ("settlement", "village", "deserted", "shrunken", "croft", "toft", "hamlet"),
    FeatureClass.FIELD_SYSTEM: ("field system", "lynchet", "celtic field", "field boundary"),
    FeatureClass.RIDGE_AND_FURROW: ("ridge and furrow", "ridge", "furrow"),
    FeatureClass.LINEAR: ("dyke", "dike", "ditch", "bank", "linear earthwork", "boundary"),
    FeatureClass.TRACKWAY: ("trackway", "hollow way", "holloway", "track", "drove"),
    FeatureClass.ROAD: ("road", "causeway", "agger"),
    FeatureClass.MOAT: ("moat", "moated"),
    FeatureClass.MOTTE: ("motte", "castle", "bailey", "ringwork"),
    FeatureClass.PLATFORM: ("platform", "building platform"),
    FeatureClass.POND: ("fishpond", "pond", "water meadow", "leat", "dam", "mill pond"),
    FeatureClass.PIT: ("pit", "quarry", "quarries", "extractive", "chalk pit", "marl pit"),
    FeatureClass.INDUSTRIAL: ("mine", "kiln", "furnace", "tramway", "industrial", "spoil heap", "mill"),
    FeatureClass.MILITARY: ("military", "pillbox", "battery", "airfield", "trench", "defence", "gun"),
    FeatureClass.RITUAL: (
        "henge",
        "stone circle",
        "cursus",
        "stone row",
        "standing stone",
        "avenue",
        "ritual",
    ),
    FeatureClass.GARDEN: ("garden", "parterre", "terrace", "park"),
    FeatureClass.UNKNOWN: (),
}
assert set(CLASS_TERMS) == set(FeatureClass), "every feature class needs its terms, even if none"

_CLASS_PATTERNS = {
    feature_class: re.compile(r"\b(" + "|".join(re.escape(term) for term in terms) + r")s?\b")
    for feature_class, terms in CLASS_TERMS.items()
    if terms
}


def type_fits(feature_classes: list[str], record: Record) -> bool:
    """Whether the record's name, type or monument types name something of one of the classes."""
    text = " ".join([record.name, record.record_type or "", *(record.monument_types or [])]).lower()
    for value in feature_classes:
        pattern = _CLASS_PATTERNS.get(FeatureClass(value))
        if pattern is not None and pattern.search(text):
            return True
    return False


def load_finding(db: Session, public_id: str, viewer: User | None) -> Finding:
    """A finding by public id. A hidden one is only found by a moderator."""
    finding = db.scalars(select(Finding).where(Finding.public_id == public_id)).one_or_none()
    if finding is None:
        raise FindingNotFoundError()
    if finding.hidden_at is not None:
        active = viewer if viewer is not None and viewer.is_active else None
        if active is None or Role(active.role) not in MODERATOR_ROLES:
            raise FindingNotFoundError()
    return finding


def suggest_for_finding(
    db: Session, finding: Finding, viewer: User | None, *, limit: int = 10
) -> SuggestionList:
    """Records the finding might be, near the position `viewer` may see, best first.

    The search starts from `visible_location`, never from the exact position.
    Someone who may only see the 1 km square gets distances to the square
    itself, so everything inside it is 0 m away, and ties are broken by the
    distance from the square's centre. Both are public, so neither the
    distances nor the order can give the exact position away. The score weighs
    nearness against whether the record's type fits the finding's class or its
    community class.
    """
    assert 1 <= limit <= 50, "limit must be between 1 and 50"
    origin = sensitivity.visible_location(finding, viewer)
    area = gridref.parse_gridref(origin.square).polygon() if origin.square else None
    assert origin.obscured == (area is not None), "an obscured position always has its square"
    candidates = nearby(
        db, origin.lon, origin.lat, radius_m=SUGGEST_RADIUS_M, limit=SUGGEST_CANDIDATES, area=area
    )
    classes = [value for value in (finding.feature_class, finding.community_class) if value]
    scored = []
    for result in candidates:
        assert result.distance_m is not None, "nearby() always gives a distance"
        fits = type_fits(classes, result.record)
        score = DISTANCE_WEIGHT * (1 - min(result.distance_m / SUGGEST_RADIUS_M, 1.0)) + TYPE_WEIGHT * fits
        from_centre = _flat_distance(origin.lon, origin.lat, result.lon, result.lat)
        scored.append((Suggestion(result, fits, round(score, 4)), from_centre))
    scored.sort(
        key=lambda pair: (-pair[0].score, pair[0].result.distance_m, pair[1], pair[0].result.record.id)
    )
    return SuggestionList(origin, [suggestion for suggestion, _ in scored[:limit]])


def _flat_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Metres between two nearby points, near enough for breaking ties."""
    dx = (lon2 - lon1) * METRES_PER_DEGREE * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * METRES_PER_DEGREE
    return math.hypot(dx, dy)


__all__ = [
    "CLASS_TERMS",
    "FindingNotFoundError",
    "InvalidSearchError",
    "RecordNotFoundError",
    "RecordResult",
    "Suggestion",
    "SuggestionList",
    "clean_query",
    "get_record",
    "list_sources",
    "load_finding",
    "nearby",
    "prefix_tsquery",
    "query_words",
    "search",
    "suggest_for_finding",
    "type_fits",
    "use_name_similarity",
]
