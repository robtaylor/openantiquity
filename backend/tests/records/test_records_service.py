from __future__ import annotations

import pytest
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.models import Source
from fieldclub.services import records
from fieldclub.services.records import InvalidSearchError, RecordNotFoundError, SearchTimeoutError
from tests.records.support import OVERTON, SILBURY, add_record, add_source

HOSTILE = [
    "'",
    '"',
    "silbury'; DROP TABLE records; --",
    "barrow & | ! <-> :* ( ) \\",
    "!!!",
    "barrow:*",
    "(silbury | !hill) <2> mound",
    "\x00silbury\x00",
    "silbury‮​\x07\x1b[31m",
    "%_%",
    "\ud800",
    "s" * 10_000,
    "silbury " * 500,
    "",
    "   ",
    "église",
    # Lower-casing these changes the characters they're made of.
    "İstanbul",
    "İ",
    "ﬁeld ½ Ŀl ǅ क़",
]


@pytest.fixture
def index(db: Session) -> dict[str, int]:
    """A few monuments around Avebury from two sources, one disabled."""
    designations = add_source(db)
    finds = add_source(db, "test-finds", name="Test finds", category="find", reuse="non_commercial")
    hidden = add_source(db, "test-hidden", name="Hidden source", enabled=False)
    made = {
        "silbury": add_record(
            db,
            designations,
            "Silbury Hill: a monumental Neolithic mound",
            geom=Point(*SILBURY).buffer(0.001),
            record_type="Scheduled monument",
        ),
        "bowl": add_record(db, designations, "Bowl barrow on Overton Hill", *OVERTON),
        "long": add_record(db, designations, "West Kennet long barrow", -1.8507, 51.4085),
        "henge": add_record(
            db, designations, "Avebury henge and stone circles", -1.8542, 51.4286, monument_types=["HENGE"]
        ),
        "coin": add_record(
            db, finds, "Roman coin", -1.8570, 51.4150, summary="A worn coin found near Silbury"
        ),
        "secret": add_record(db, hidden, "Silbury hidden record", *SILBURY),
        # Spelt like a misspelling of Silbury, for the ranking test.
        "ropery": add_record(db, designations, "The West Ropery (site of), South Yard", -4.18, 50.37),
    }
    db.commit()
    return {name: record.id for name, record in made.items()}


def names(results: list[records.RecordResult]) -> list[str]:
    return [result.record.name for result in results]


# --------------------------------------------------------------------------
# Text search
# --------------------------------------------------------------------------


def test_a_name_that_starts_with_the_query_comes_first(db: Session, index: dict[str, int]) -> None:
    found, _ = records.search(db, "silbury")
    assert names(found)[0].startswith("Silbury Hill")
    # The coin mentions Silbury in its summary, so it matches too, lower down.
    assert "Roman coin" in names(found)


def test_a_half_typed_word_matches(db: Session, index: dict[str, int]) -> None:
    found, _ = records.search(db, "silb")
    assert names(found)[0].startswith("Silbury Hill")


def test_a_misspelt_name_matches_by_trigram(db: Session, index: dict[str, int]) -> None:
    found, _ = records.search(db, "silbery")
    assert names(found)[0].startswith("Silbury Hill")
    # The Ropery shares as many trigrams with "silbery", and ranks below.
    assert names(found).index("The West Ropery (site of), South Yard") > 0


def test_type_words_match(db: Session, index: dict[str, int]) -> None:
    assert set(names(records.search(db, "barrow")[0])) == {
        "Bowl barrow on Overton Hill",
        "West Kennet long barrow",
    }
    assert names(records.search(db, "henge")[0]) == ["Avebury henge and stone circles"]


def test_a_disabled_source_is_never_searched(db: Session, index: dict[str, int]) -> None:
    assert "Silbury hidden record" not in names(records.search(db, "silbury")[0])
    assert "Silbury hidden record" not in names(records.search(db)[0])


def test_filters_by_source_category_and_box(db: Session, index: dict[str, int]) -> None:
    assert names(records.search(db, sources=["test-finds"])[0]) == ["Roman coin"]
    assert names(records.search(db, categories=["find"])[0]) == ["Roman coin"]
    near_overton = records.search(db, bbox=(-1.83, 51.405, -1.82, 51.415))[0]
    assert names(near_overton) == ["Bowl barrow on Overton Hill"]
    with pytest.raises(InvalidSearchError, match="Unknown record categories: bogus"):
        records.search(db, categories=["bogus"])
    with pytest.raises(InvalidSearchError, match="west < east"):
        records.search(db, bbox=(1, 51, 0, 52))


def test_without_text_records_come_in_name_order_and_page(db: Session, index: dict[str, int]) -> None:
    first, cursor = records.search(db, limit=2)
    assert names(first) == ["Avebury henge and stone circles", "Bowl barrow on Overton Hill"]
    assert cursor is not None
    second, cursor = records.search(db, limit=2, cursor=cursor)
    assert names(second) == ["Roman coin", "Silbury Hill: a monumental Neolithic mound"]
    third, cursor = records.search(db, limit=2, cursor=cursor)
    assert names(third) == ["The West Ropery (site of), South Yard", "West Kennet long barrow"]
    assert cursor is None


def test_every_result_carries_its_source(db: Session, index: dict[str, int]) -> None:
    for result in records.search(db)[0]:
        assert result.source.key == result.record.source_key
        assert result.source.licence
        assert result.source.attribution
        assert result.source.reuse in ("open", "non_commercial")


@pytest.mark.parametrize("query", HOSTILE)
def test_hostile_text_never_breaks_the_search(db: Session, index: dict[str, int], query: str) -> None:
    found, _ = records.search(db, query)
    assert all(result.record.name != "Silbury hidden record" for result in found)
    # The session is still usable afterwards: nothing was left half-done.
    assert records.search(db, "henge")[0]


def test_hostile_text_is_reduced_to_letters_and_digits() -> None:
    assert records.query_words("barrow & | ! <-> :* ( ) \\") == ["barrow"]
    assert records.query_words("silbury'; DROP TABLE records; --") == ["silbury", "drop", "table", "records"]
    assert records.prefix_tsquery(["silbury", "hill"]) == "silbury:* & hill:*"
    assert records.prefix_tsquery(["st", "mary"]) == "st & mary:*"
    assert records.clean_query("\x00silbury‮  hill\x07") == "silbury hill"
    assert len(records.clean_query("s" * 10_000)) == records.MAX_QUERY_CHARS
    assert len(records.query_words("a " * 100)) == records.MAX_QUERY_WORDS


def test_folding_happens_before_the_words_are_picked_out() -> None:
    assert records.query_words("İstanbul") == ["istanbul"]
    assert records.query_words("ﬁeld") == ["field"]
    assert records.query_words("½") == ["1", "2"]


def test_every_character_gives_words_the_tsquery_accepts() -> None:
    # Each code point alone, doubled and inside a word, as a pasted name might hold it.
    for code in range(0x30000):
        char = chr(code)
        for text in (char, char * 2, f"a{char}b"):
            records.prefix_tsquery(records.query_words(text))


def test_quoted_words_still_match(db: Session, index: dict[str, int]) -> None:
    assert names(records.search(db, '"silbury hill"')[0])[0].startswith("Silbury Hill")


def test_a_cursor_out_of_range_is_refused(db: Session, index: dict[str, int]) -> None:
    from fieldclub.schemas.common import encode_cursor

    with pytest.raises(InvalidSearchError, match="out of range"):
        records.search(db, cursor=encode_cursor([records.MAX_OFFSET + 1]))


# --------------------------------------------------------------------------
# Near a point
# --------------------------------------------------------------------------


def test_nearby_is_nearest_first_with_distances(db: Session, index: dict[str, int]) -> None:
    found = records.nearby(db, *SILBURY, radius_m=1500)
    assert names(found)[0].startswith("Silbury Hill")
    # Inside the mound's area, so no distance at all.
    assert found[0].distance_m == 0
    distances = [result.distance_m or 0.0 for result in found]
    assert distances == sorted(distances)
    assert "Bowl barrow on Overton Hill" not in names(found)  # 2.3 km away
    assert "Silbury hidden record" not in names(found)


def test_nearby_distances_are_in_metres(db: Session, index: dict[str, int]) -> None:
    [bowl] = records.nearby(db, OVERTON[0] + 0.01, OVERTON[1], radius_m=1000)
    # 0.01 degrees of longitude at 51.41 degrees north is about 694 m.
    assert bowl.distance_m == pytest.approx(694, rel=0.01)


def test_nearby_filters(db: Session, index: dict[str, int]) -> None:
    assert names(records.nearby(db, *SILBURY, radius_m=1500, categories=["find"])) == ["Roman coin"]
    with pytest.raises(InvalidSearchError):
        records.nearby(db, 200, 51)


# --------------------------------------------------------------------------
# One record, and the sources
# --------------------------------------------------------------------------


def test_one_record_with_its_source(db: Session, index: dict[str, int]) -> None:
    result = records.get_record(db, index["coin"])
    assert result.record.name == "Roman coin"
    assert result.source.reuse == "non_commercial"
    with pytest.raises(RecordNotFoundError):
        records.get_record(db, index["secret"])
    with pytest.raises(RecordNotFoundError):
        records.get_record(db, 999_999)


def test_sources_are_listed_with_their_counts(db: Session, index: dict[str, int]) -> None:
    db.query(Source).filter(Source.key == "test-designations").update({"record_count": 4})
    db.commit()
    listed = {source.key: source.record_count for source in records.list_sources(db)}
    assert listed == {"test-designations": 4, "test-finds": None}


@pytest.mark.parametrize("column", ["licence", "attribution"])
def test_the_database_refuses_a_source_without_licence_or_attribution(db: Session, column: str) -> None:
    with pytest.raises(IntegrityError, match="ck_sources_licence_and_attribution_given"):
        add_source(db, "blank", **{column: "  "})


# --------------------------------------------------------------------------
# What keeps a search quick on a big index
# --------------------------------------------------------------------------


def test_short_and_stop_words_stay_out_of_the_trigram_match(db: Session) -> None:
    terms = records._terms(db, ["the", "st", "bowl", "a", "barrow"])
    assert terms.trigram == "bowl barrow"
    assert terms.phrase == "the st bowl a barrow"
    # Short words are matched whole, longer ones as prefixes.
    assert terms.tsquery == "the:* & st & bowl:* & a & barrow:*"
    only_stop_words = records._terms(db, ["the", "a"])
    assert only_stop_words.tsquery is None
    assert only_stop_words.trigram is None


def test_a_name_that_starts_with_stop_words_is_still_found(db: Session, index: dict[str, int]) -> None:
    assert names(records.search(db, "the")[0]) == ["The West Ropery (site of), South Yard"]
    assert names(records.search(db, "the west r")[0])[0] == "The West Ropery (site of), South Yard"


def test_each_index_gives_a_capped_number_of_candidates(
    db: Session, index: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three records match "barrow" or "hill"; with one candidate an index, at most three come back.
    monkeypatch.setattr(records, "SEARCH_CANDIDATES", 1)
    found, _ = records.search(db, "barrow")
    assert 1 <= len(found) <= 3


def test_a_slow_statement_is_cancelled_and_the_session_survives(db: Session) -> None:
    before = db.scalar(select(func.current_setting("statement_timeout")))
    with pytest.raises(SearchTimeoutError), records.time_limit(db, 50):
        db.execute(select(func.pg_sleep(1)))
    # The savepoint took the cancelled statement and the limit with it.
    assert db.scalar(select(func.current_setting("statement_timeout"))) == before
    with records.time_limit(db, 5000):
        db.execute(select(func.pg_sleep(0)))
    assert db.scalar(select(func.current_setting("statement_timeout"))) == before
    assert db.scalar(select(func.count()).select_from(Source)) == 0
