"""How the search box ranks names: the fit, the weight and the band, in Python and in SQL alike."""

from __future__ import annotations

import pytest
from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.services import name_rank, records, search
from tests.helpers import add_record, add_source
from tests.records.test_geo_search import add_place

NAMES = [
    ("stonehenge", "Stonehenge", name_rank.FIT_EXACT),
    ("stonehenge", "STONEHENGE", name_rank.FIT_EXACT),
    ("stonehenge", "Stonehenge, the Avenue, and three barrows", name_rank.FIT_EXACT),
    ("silbury hill", "Silbury Hill: a monumental Neolithic mound", name_rank.FIT_EXACT),
    ("maiden castle", "Maiden Castle (Fort)", name_rank.FIT_EXACT),
    ("hadrian s wall", "Hadrian's Wall in wall mile 7", name_rank.FIT_STARTS),
    ("sutton hoo", "Sutton Hoo Woodbridge", name_rank.FIT_STARTS),
    ("sutton hoo", "Sutton Hook Wood", name_rank.FIT_STARTS_PART_WORD),
    ("ave", "Avebury", name_rank.FIT_STARTS_PART_WORD),
    (
        "sutton hoo",
        "Prehistoric settlement and group of barrows (including site of ship burial) at Sutton Hoo",
        name_rank.FIT_HOLDS,
    ),
    ("avebury", "Barrow on Avebury Down, S of track from Avebury", name_rank.FIT_HOLDS),
    ("avebury", "Avery Hill", name_rank.FIT_LOOSE),
    ("hoo", "Sutton Hook Wood", name_rank.FIT_LOOSE),
    ("silbury", "(site of) Silbury", name_rank.FIT_HOLDS),
]


@pytest.mark.parametrize(("phrase", "name", "fit"), NAMES)
def test_python_and_sql_agree_on_how_a_name_fits(db: Session, phrase: str, name: str, fit: int) -> None:
    words = records.name_words(name)
    first = records.name_words(name_rank.first_part(name))
    assert name_rank.name_fit(phrase, words, first) == fit
    assert db.scalar(select(name_rank.fit_sql(literal(name), phrase))) == fit


@pytest.mark.parametrize(
    ("source_key", "category", "weight"),
    [
        ("he-nhle-scheduled-monuments", "designation", name_rank.NATIONAL),
        ("he-nhle-world-heritage-sites", "designation", name_rank.NATIONAL),
        ("he-nhle-registered-parks-and-gardens", "designation", name_rank.NATIONAL),
        ("he-nhle-registered-battlefields", "designation", name_rank.NATIONAL),
        ("he-nhle-listed-buildings-points", "designation", name_rank.MINOR),
        ("he-research-spatial-reports", "document", name_rank.MINOR),
        ("bern-xronos-radiocarbon", "event", name_rank.MINOR),
        ("isaw-pleiades-places", "monument", name_rank.OTHER),
        ("he-conservation-areas", "designation", name_rank.OTHER),
    ],
)
def test_python_and_sql_agree_on_a_records_weight(
    db: Session, source_key: str, category: str, weight: int
) -> None:
    assert name_rank.record_weight(source_key, category) == weight
    assert db.scalar(select(name_rank.weight_sql(literal(source_key), literal(category)))) == weight


def test_every_weighted_source_is_a_real_source() -> None:
    keys = {connector.source.key for connector in registry.all_connectors()}
    assert keys >= name_rank.NATIONAL_SOURCES
    assert keys >= name_rank.MINOR_SOURCES


def labels(db: Session, query: str) -> list[str]:
    return [hit.label for hit in search.geo_search(db, query, None)]


@pytest.fixture
def monuments(db: Session) -> None:
    """A few of the names the development database holds for famous monuments."""
    scheduled = add_source(db, "he-nhle-scheduled-monuments")
    world = add_source(db, "he-nhle-world-heritage-sites")
    listed = add_source(db, "he-nhle-listed-buildings-points")
    reports = add_source(db, "he-research-spatial-reports", category="document")
    dates = add_source(db, "bern-xronos-radiocarbon", category="event")
    pleiades = add_source(db, "isaw-pleiades-places", category="monument")
    add_record(db, listed, "STONEHENGE", -0.6, 52.0, external_id="1")
    add_record(db, listed, "STONEHENGE", -2.6, 53.0, external_id="2")
    for number in range(8):
        add_record(db, dates, "Stonehenge", -1.8262, 51.1789, external_id=f"date-{number}")
    add_record(
        db, scheduled, "Stonehenge, the Avenue, and three barrows adjacent to the Avenue", -1.826, 51.179
    )
    add_record(db, world, "Stonehenge, Avebury and Associated Sites", -1.85, 51.3)
    add_record(db, pleiades, "Stonehenge", -1.8262, 51.1789)
    add_place(db, "Stonehenge Works", -0.62, 52.05, kind="Other Settlement", rank=480)
    add_record(db, scheduled, "Avebury henge and stone circles", -1.854, 51.428)
    add_record(db, listed, "AVEBURY MANOR", -1.856, 51.427)
    add_place(db, "Avebury", -1.854, 51.428, rank=750)
    add_place(db, "Avery Hill", 0.08, 51.44, rank=760)
    add_record(db, reports, "Sutton Hoo, Suffolk. Report On Geophysical Survey", 1.34, 52.09)
    add_record(db, dates, "Sutton Hoo Woodbridge", 1.34, 52.09)
    add_record(
        db,
        scheduled,
        "Prehistoric settlement and group of barrows (including site of ship burial) at Sutton Hoo",
        1.34,
        52.09,
    )
    db.commit()


@pytest.mark.usefixtures("monuments")
def test_a_famous_monument_opens_its_search_not_the_houses_named_after_it(db: Session) -> None:
    found = labels(db, "Stonehenge")
    assert set(found[:2]) == {
        "Stonehenge, the Avenue, and three barrows adjacent to the Avenue",
        "Stonehenge, Avebury and Associated Sites",
    }
    assert found[2] == "Stonehenge"
    assert found.index("Stonehenge Works") < found.index("STONEHENGE")
    # One source's repeated name is shown once: the two listed buildings, and the eight dates.
    assert found.count("STONEHENGE") == 1
    assert found.count("Stonehenge") == 2


@pytest.mark.usefixtures("monuments")
def test_a_record_that_starts_with_the_name_comes_before_a_loose_place(db: Session) -> None:
    found = labels(db, "Avebury")
    assert found[:2] == ["Avebury", "Avebury henge and stone circles"]
    assert found.index("AVEBURY MANOR") < found.index("Avery Hill")


@pytest.mark.usefixtures("monuments")
def test_a_monument_that_holds_the_name_comes_before_reports_that_start_with_it(db: Session) -> None:
    found = labels(db, "Sutton Hoo")
    assert found[0].startswith("Prehistoric settlement")
