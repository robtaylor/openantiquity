"""The record index: search, records near a point, one record, sources, and suggestions for a finding.

Every function returns records paired with their `Source`, so the caller can
always show the licence and attribution. Records of a disabled source are
never returned.

Text search uses three indexes. A btree on `lower(name)` finds names that
start with the query. The generated `records.search` tsvector finds records
by the words of their name, types and summary, with every word of three or
more letters treated as a prefix so a half-typed word still matches. The
trigram index on `records.name` finds names that are spelt differently from
the query, leaving out short words and stop words, which share trigrams with
much of the index. Each index gives at most `SEARCH_CANDIDATES` matches, and
only those are ranked, so a common word stays quick on a large index. Only
letters and digits from the query reach any of them, so quotes, tsquery
operators and control characters can't break the query or change its meaning.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from psycopg.errors import QueryCanceled
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import (
    ColumnElement,
    Integer,
    Select,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    true,
    union,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import AppError, BadRequestError, NotFoundError
from fieldclub.models import Evidence, Finding, Record, Source, User
from fieldclub.models.common import SRID
from fieldclub.schemas.common import (
    MAX_OFFSET,
    check_bbox,
    int_from_cursor,
    offset_from_cursor,
    offset_page,
    paginate,
)
from fieldclub.services import findings, geo, name_rank, record_tiles, sensitivity
from fieldclub.vocab import COVERAGE_RECORD_TYPES, FeatureClass, FindingState

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
# How many matches each index may give before they are ranked: enough to page
# to `MAX_OFFSET`. Ranking every match of a common word took a second at 500,000 records.
SEARCH_CANDIDATES = MAX_OFFSET + 200
# Shorter words share trigrams with too much of the index to be worth a spelling match.
MIN_TRIGRAM_WORD = 3
# A search slower than this is cancelled. The search box asks again as people type.
SEARCH_TIMEOUT_MS = 2000

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


class InvalidSearchError(BadRequestError):
    code = "invalid_search"


class SearchTimeoutError(AppError):
    status_code = 503
    code = "search_timeout"
    message = "That search took too long. Add another word, or search a smaller area."


@dataclass(frozen=True)
class RecordResult:
    record: Record
    source: Source
    lon: float
    lat: float
    # Metres from the point asked about, for a search near a point.
    distance_m: float | None = None

    @property
    def url(self) -> str | None:
        """Where the record is seen at its source: its own page, or the viewer of the source's material."""
        if self.record.url is not None:
            return self.record.url
        # Imported here: `context` checks its points with this module.
        from fieldclub.services import context

        return context.material_url(self.record.source_key, self.lon, self.lat)


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


def fold(text: str) -> str:
    """The text in lower case and NFKC form, with a Turkish dotted capital I read as a plain i.

    Lower-casing can change the characters a word is made of: "İ" becomes
    "i" and a combining dot, and NFKC turns "½" into 1, a fraction slash and 2. So the words are
    picked out after folding, never before.
    """
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).lower())
    return folded.replace("i̇", "i")


def name_words(text: str) -> list[str]:
    """Every word of a name, as `query_words` reads a query's but with no limit on their number or length."""
    return _WORD.findall(fold(text))


def query_words(text: str) -> list[str]:
    """The words of a query that reach the database: letters and digits only, lower case."""
    return [word[:MAX_WORD_CHARS] for word in _WORD.findall(fold(text))][:MAX_QUERY_WORDS]


def prefix_tsquery(words: list[str]) -> str:
    """`to_tsquery` text matching every word as a prefix, such as `silbury:* & hil:* & st`.

    Safe because each word is letters and digits only. A word shorter than
    `MIN_TRIGRAM_WORD` is matched whole, because a one- or two-letter prefix
    matches thousands of lexemes. Stop words like "the" drop out in
    PostgreSQL rather than matching nothing.
    """
    assert all(_WORD.fullmatch(word) for word in words), "words must be letters and digits only"
    return " & ".join(word if len(word) < MIN_TRIGRAM_WORD else f"{word}:*" for word in words)


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


def _filters(
    statement: AnySelect,
    *,
    sources: list[str] | None,
    categories: list[str] | None,
    bbox: tuple[float, float, float, float] | None,
) -> AnySelect:
    if sources:
        statement = statement.where(Record.source_key.in_(sources))
    categories = record_tiles.check_categories(categories, InvalidSearchError)
    if categories:
        statement = statement.where(Record.category.in_(categories))
    if bbox is not None:
        statement = statement.where(func.ST_Intersects(Record.geom, geo.envelope(check_bbox(bbox))))
    return statement


def _results(rows: Any, distance: bool = False) -> list[RecordResult]:
    return [RecordResult(row[0], row[1], row[2], row[3], float(row[4]) if distance else None) for row in rows]


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


def _name_similarity() -> ColumnElement[Any]:
    """A column that makes `%>` match at `NAME_SIMILARITY` for the rest of the transaction."""
    return func.set_config("pg_trgm.word_similarity_threshold", str(NAME_SIMILARITY), true())


def use_name_similarity(db: Session) -> None:
    """Make `%>` match at `NAME_SIMILARITY` for the rest of this transaction."""
    db.execute(select(_name_similarity()))


@contextmanager
def time_limit(db: Session, milliseconds: int = SEARCH_TIMEOUT_MS) -> Iterator[None]:
    """Cancel any statement inside that runs longer than `milliseconds`, as `SearchTimeoutError`.

    The block runs in a savepoint, so a cancelled statement leaves the
    session's transaction usable, and the limit ends with the block.
    """
    assert milliseconds > 0, "a time limit must be positive"
    previous = db.scalar(select(func.current_setting("statement_timeout")))
    try:
        with db.begin_nested():
            db.execute(select(func.set_config("statement_timeout", str(milliseconds), true())))
            yield
            db.execute(select(func.set_config("statement_timeout", previous, true())))
    except OperationalError as exc:
        if isinstance(exc.orig, QueryCanceled):
            raise SearchTimeoutError() from None
        raise


@dataclass(frozen=True)
class _Terms:
    """What a query's words become in SQL."""

    # All the words, for the name-starts-with match and the ranking.
    phrase: str
    # The `to_tsquery` text, or None when PostgreSQL drops every word as a stop word.
    tsquery: str | None
    # The words worth a trigram match, or None when none are.
    trigram: str | None


def _terms(db: Session, words: list[str]) -> _Terms:
    """Ask PostgreSQL which words are stop words, then build each kind of match from the rest.

    The same statement sets the word similarity that the trigram match uses,
    as `use_name_similarity` does, so a search costs no extra round trip for it.

    A stop word or a word under `MIN_TRIGRAM_WORD` letters shares a trigram
    with a large part of the index, so it stays out of the trigram match. A
    word that short is matched whole in the full-text match, because a one-
    or two-letter prefix matches thousands of lexemes. The name-starts-with
    match still catches it as the start of a name.
    """
    tsquery = prefix_tsquery(words)
    # One row: the similarity setting, the node count of the whole tsquery,
    # then one count per word, 0 for a stop word.
    row = db.execute(
        select(
            _name_similarity(),
            func.numnode(_tsquery(tsquery)),
            *(func.numnode(func.plainto_tsquery("english", literal(word))) for word in words),
        )
    ).one()
    _, nodes, *word_nodes = tuple(row)
    kept = [
        word for word, count in zip(words, word_nodes, strict=True) if count and len(word) >= MIN_TRIGRAM_WORD
    ]
    return _Terms(phrase=" ".join(words), tsquery=tsquery if nodes else None, trigram=" ".join(kept) or None)


def _tsquery(text: str) -> ColumnElement[Any]:
    return func.to_tsquery("english", literal(text))


def _candidates(
    terms: _Terms,
    *,
    sources: list[str] | None,
    categories: list[str] | None,
    bbox: tuple[float, float, float, float] | None,
) -> Any:
    """The ids of at most `SEARCH_CANDIDATES` matches from each index, as one subquery.

    Each arm stops at that many, so a common word costs a few thousand rows
    rather than ranking a large part of the table. A word that matches more
    records than that gives an arbitrary few thousand of them to rank, in
    the order the index scan found them, so its best match may be missed.
    Another word, or a smaller area, brings it back.
    """

    def arm(condition: ColumnElement[bool]) -> AnySelect:
        statement = select(Record.id).join(Source, Source.key == Record.source_key).where(Source.enabled)
        statement = _filters(statement, sources=sources, categories=categories, bbox=bbox)
        return statement.where(condition).limit(SEARCH_CANDIDATES)

    # The phrase is letters, digits and single spaces, so it holds no LIKE wildcard.
    assert re.fullmatch(r"[^\W_]+( [^\W_]+)*", terms.phrase), "the phrase must be words and spaces"
    arms = [arm(func.lower(Record.name).like(literal(terms.phrase + "%")))]
    if terms.tsquery is not None:
        arms.append(arm(Record.search.op("@@")(_tsquery(terms.tsquery))))
    if terms.trigram is not None:
        arms.append(arm(Record.name.op("%>")(literal(terms.trigram))))
    return union(*(statement.subquery().select() for statement in arms)).subquery()


def search(
    db: Session,
    q: str | None = None,
    *,
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 50,
    cursor: str | None = None,
    by_name: bool = False,
) -> tuple[list[RecordResult], str | None]:
    """Records matching the text, filters and box, best match first. Returns a page and the next cursor.

    A record matches when its name starts with the query, when its words
    match the query's as prefixes, or when its name is spelt like the query.
    Ranking puts a name that starts with the query first, then weighs the
    full-text rank (name words count most, then types, then the summary)
    with how closely the name is spelt like the query. Without text,
    records come in name order. A search that runs past `SEARCH_TIMEOUT_MS`
    raises `SearchTimeoutError`.

    `by_name` orders the matches as the search box does (`name_rank`): by
    band, then by how the name fits the query and how much the thing named
    matters, then by the rank above.
    """
    assert 1 <= limit <= 200, "limit must be between 1 and 200"
    offset = offset_from_cursor(cursor)
    text = clean_query(q)
    words = query_words(text)
    if text and not words:
        # Punctuation and nothing else: nothing can match.
        return [], None

    with time_limit(db):
        if words:
            terms = _terms(db, words)
            # Matching uses word similarity, which is what the index serves. Ranking
            # uses the strict form, which tells "Silbury" from "Ropery" for "silbery".
            rank = (
                func.strict_word_similarity(literal(terms.phrase), Record.name)
                + cast(func.starts_with(func.lower(Record.name), literal(terms.phrase)), Integer) * 2
            )
            if terms.tsquery is not None:
                rank = rank + func.ts_rank_cd(Record.search, _tsquery(terms.tsquery), 1) * 4
            # The candidates carry the filters already, so the outer query needs only their ids.
            candidates = _candidates(terms, sources=sources, categories=categories, bbox=bbox)
            statement = _base().where(Record.id.in_(select(candidates.c.id)))
            if by_name:
                fit = name_rank.fit_sql(Record.name, terms.phrase)
                weight = name_rank.weight_sql(Record.source_key, Record.category)
                band = name_rank.band_sql(fit, weight)
                # Loose matches go by the rank, which holds how alike they are, before the weight.
                fitting_weight = case((band == name_rank.LOOSE, name_rank.NATIONAL), else_=weight)
                statement = statement.order_by(
                    band, fit.desc(), fitting_weight, rank.desc(), weight, Record.id
                )
            else:
                statement = statement.order_by(rank.desc(), Record.id)
        else:
            statement = _filters(_base(), sources=sources, categories=categories, bbox=bbox)
            statement = statement.order_by(Record.name, Record.id)
        rows = db.execute(statement.offset(offset).limit(limit + 1)).all()

    page, next_cursor = offset_page(rows, offset, limit)
    return _results(page), next_cursor


# --------------------------------------------------------------------------
# Near a point
# --------------------------------------------------------------------------


def check_point(lon: float, lat: float) -> None:
    if not gridref.is_lon_lat(lon, lat):
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
    on the geography. Records of a coverage type (`vocab.COVERAGE_RECORD_TYPES`)
    are left out, because they say where a source has looked, not what it found.
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
        or_(Record.record_type.is_(None), Record.record_type.not_in(COVERAGE_RECORD_TYPES)),
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


@dataclass(frozen=True)
class LinkedFindingPage:
    findings: list[Finding]
    next_cursor: str | None


def linked_findings(
    db: Session, record_id: int, viewer: User | None, *, limit: int, cursor: str | None = None
) -> LinkedFindingPage:
    """The findings whose evidence links this record, as `viewer` may list them, oldest first.

    A link counts while its evidence stands (`findings.standing_evidence_clause`).
    Withdrawn findings are left out for everyone, and hidden ones for all but
    their finder and moderators. So is every finding whose exact position the
    viewer doesn't see: its page leaves out the record it links for them
    (`redacted` evidence), because naming the record would place the finding
    as closely as the record is placed. `RecordNotFoundError` when the record
    isn't in the index.
    """
    get_record(db, record_id)
    linked = select(Evidence.finding_id).where(
        Evidence.record_id == record_id, findings.standing_evidence_clause()
    )
    query = (
        select(Finding)
        .where(
            Finding.id.in_(linked),
            Finding.state != FindingState.WITHDRAWN.value,
            findings.not_hidden_clause(viewer),
            sensitivity.as_sql(sensitivity.sees_exact_clause(viewer)),
        )
        .order_by(Finding.id)
    )
    if cursor is not None:
        query = query.where(Finding.id > int_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda finding: [finding.id])
    assert all(sensitivity.sees_exact(finding, viewer) for finding in items), "the SQL rule is sees_exact"
    return LinkedFindingPage(items, next_cursor)


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


def suggest_for_finding(
    db: Session, finding: Finding, viewer: User | None, *, limit: int = 10
) -> SuggestionList:
    """Records the finding might be, near the position `viewer` may see, best first.

    The search starts from `visible_location`, never from the exact position.
    Someone who may only see the 1 km square gets distances to the square
    itself, so everything inside it is 0 m away, and ties are broken by the
    distance from the square's centre. Both are public, so neither the
    distances nor the order can give the exact position away. The score weighs
    nearness against whether the record's type fits the finding's class or,
    for someone who may see other people's answers, its community class. The
    community class comes from those answers, so for anyone else it plays no
    part, and neither `type_fit` nor the order can give it away (Decision 0008).
    """
    assert 1 <= limit <= 50, "limit must be between 1 and 50"
    origin = sensitivity.visible_location(finding, viewer)
    area = origin.square_polygon()
    assert origin.obscured == (area is not None), "an obscured position always has its square"
    candidates = nearby(
        db, origin.lon, origin.lat, radius_m=SUGGEST_RADIUS_M, limit=SUGGEST_CANDIDATES, area=area
    )
    classes = [finding.feature_class]
    mine = findings.my_observation(db, finding, viewer)
    if finding.community_class and findings.answers_visible(finding, viewer, mine):
        classes.append(finding.community_class)
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
