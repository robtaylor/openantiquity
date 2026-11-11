"""How well a name answers what was typed in the search box, and how much the thing named matters.

The search box ranks places and records together, by three numbers each:

1. **Fit** (`name_fit`), best first:
   - 4: the name is the query, or its first part is: "Stonehenge, the Avenue,
     and three barrows" and "Silbury Hill: a monumental Neolithic mound" both
     open with the thing searched for, and go on to say more;
   - 3: the name starts with the query as whole words ("Sutton Hoo Woodbridge");
   - 2: it starts with the query part-way through a word, as while typing
     ("Sutton Hook Wood", "Avebury" for "ave");
   - 1: it holds the query as whole words ("... ship burial) at Sutton Hoo");
   - 0: a loose match by spelling.
2. **Weight** (`PLACE`, `record_weight`), lower first: places and
   designations of national importance (scheduled monuments, World Heritage
   Sites, registered parks, gardens and battlefields, protected wrecks),
   then other records, then the minor names: the 380,000 listed buildings,
   many of them houses named after a monument or a village, and the reports
   and dated samples that are about a site rather than the site.
3. **Band** (`band`), which puts them together: first every name that fits
   (fit 1 to 4) and isn't minor, by fit and then weight; then the minor names
   that fit, by fit; then the loose matches, by how alike they are, then
   weight. So the 73 radiocarbon dates and the listed building called
   "Stonehenge" come after the scheduled monument and the World Heritage
   Site whose names open with it, and the reports titled "Sutton Hoo, ..."
   after the scheduled monument "... at Sutton Hoo".

Ties keep each list's own order, places before records.

`records.search(by_name=True)` orders its matches by the same numbers in SQL
(`fit_sql`, `weight_sql`, `band_sql`), so the few records the search box asks
for are the best by this measure. `tests/records/test_name_rank.py` holds the
two to each other.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, case, func, literal, or_

from fieldclub.vocab import RecordCategory

FIT_EXACT = 4
FIT_STARTS = 3
FIT_STARTS_PART_WORD = 2
FIT_HOLDS = 1
FIT_LOOSE = 0

# Weights. Places and national designations share the first, so a place keeps its lead.
NATIONAL = 0
PLACE = 0
OTHER = 1
MINOR = 2

# Bands.
FITS = 0
MINOR_FITS = 1
LOOSE = 2

# Designations of national importance, by the source that holds them.
NATIONAL_SOURCES = frozenset(
    {
        "he-nhle-scheduled-monuments",
        "he-nhle-world-heritage-sites",
        "he-nhle-registered-parks-and-gardens",
        "he-nhle-registered-battlefields",
        "he-nhle-protected-wreck-sites",
    }
)
# Listed buildings: hundreds of thousands of names, many of them houses named after something else.
MINOR_SOURCES = frozenset({"he-nhle-listed-buildings-points", "he-nhle-listed-buildings-polygons"})
# Records about a site rather than of it: reports and dated samples.
MINOR_CATEGORIES = frozenset({RecordCategory.DOCUMENT.value, RecordCategory.EVENT.value})

# Where a name's first part ends.
_FIRST_PART = re.compile(r"[,:;(]")
_FIRST_PART_SQL = "[,:;(]"
_NOT_A_WORD_SQL = "[^[:alnum:]]+"


def name_fit(phrase: str, words: list[str], first_words: list[str]) -> int:
    """The fit of a name to the query `phrase` (its words joined by single spaces).

    `words` are the name's words and `first_words` those of its first part,
    both as `records.name_words` makes them.
    """
    assert phrase, "a query has words"
    name = " ".join(words)
    if name == phrase or " ".join(first_words) == phrase:
        return FIT_EXACT
    if name.startswith(phrase + " "):
        return FIT_STARTS
    if name.startswith(phrase):
        return FIT_STARTS_PART_WORD
    if f" {phrase} " in f" {name} ":
        return FIT_HOLDS
    return FIT_LOOSE


def first_part(name: str) -> str:
    """A name up to its first comma, colon, semicolon or bracket."""
    return _FIRST_PART.split(name, maxsplit=1)[0]


def record_weight(source_key: str, category: str) -> int:
    if source_key in NATIONAL_SOURCES:
        return NATIONAL
    if source_key in MINOR_SOURCES or category in MINOR_CATEGORIES:
        return MINOR
    return OTHER


def band(fit: int, weight: int) -> int:
    if fit == FIT_LOOSE:
        return LOOSE
    return MINOR_FITS if weight == MINOR else FITS


def _words_sql(text: SQLColumnExpression[Any]) -> ColumnElement[str]:
    """Lower case, every run of characters that aren't letters or digits one space, trimmed."""
    return func.btrim(func.regexp_replace(func.lower(text), _NOT_A_WORD_SQL, " ", "g"))


def fit_sql(name: SQLColumnExpression[str], phrase: str) -> ColumnElement[int]:
    """`name_fit` in SQL, for a column of names."""
    # The phrase is letters, digits and single spaces, so it holds no LIKE wildcard.
    assert re.fullmatch(r"[^\W_]+( [^\W_]+)*", phrase), "the phrase must be words and spaces"
    words = _words_sql(name)
    first = _words_sql(func.split_part(func.regexp_replace(name, _FIRST_PART_SQL, ",", "g"), ",", 1))
    return case(
        (or_(words == literal(phrase), first == literal(phrase)), FIT_EXACT),
        (words.like(literal(phrase + " %")), FIT_STARTS),
        (words.like(literal(phrase + "%")), FIT_STARTS_PART_WORD),
        ((literal(" ") + words + literal(" ")).like(literal(f"% {phrase} %")), FIT_HOLDS),
        else_=FIT_LOOSE,
    )


def weight_sql(
    source_key: SQLColumnExpression[str], category: SQLColumnExpression[str]
) -> ColumnElement[int]:
    """`record_weight` in SQL."""
    return case(
        (source_key.in_(sorted(NATIONAL_SOURCES)), NATIONAL),
        (or_(source_key.in_(sorted(MINOR_SOURCES)), category.in_(sorted(MINOR_CATEGORIES))), MINOR),
        else_=OTHER,
    )


def band_sql(fit: ColumnElement[int], weight: ColumnElement[int]) -> ColumnElement[int]:
    """`band` in SQL."""
    return case((fit == FIT_LOOSE, LOOSE), (weight == MINOR, MINOR_FITS), else_=FITS)
