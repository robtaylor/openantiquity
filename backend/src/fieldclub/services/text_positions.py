"""Positions written in words: grid references, coordinates and three-word addresses in free text.

A finding's title, description and notes, its comments, evidence and
mentions are free text, and a person can type a position into any of them.
For a protected or restricted finding that would undo Decision 0005, so
`services.sensitivity.visible_text` replaces every position found here with
`PLACEHOLDER` for a viewer who doesn't see the exact position, and
`services.findings` refuses a title or description that holds one when the
finding isn't open.

What counts as a position finer than a 1 km square:

- A grid reference of six figures or more on the British or Irish grid, in
  any case, with or without spaces: `SU 123 456`, `su123456`,
  `SU 12345 67890`, `J 338 740`. The letters must name a real square and
  stand on their own, so `NHLE 1012345` isn't one. Four figures name a 1 km
  square and are left alone. The figures must split evenly: six, eight or
  ten together, or two equal groups. An odd run such as `SU 1234567` is left
  alone, as `parse_gridref` refuses it.
- A latitude and longitude pair in the British Isles (latitude 49 to 61.5,
  longitude -14 to 2.5), in either order: decimal degrees with at least two
  decimal places on each (`51.4286, -1.8542`, `51.43N 1.85W`, `@51.4286,-1.8542`,
  `51.4286/-1.8542`), or degrees and minutes with seconds or decimal minutes
  (`51°25'43"N 1°51'15"W`, `51° 25.7' N, 1° 51.2' W`). Two decimal places
  are 1.1 km of latitude but 0.7 km of longitude, and whole minutes 1.9 by
  1.2 km, so the first is a position and the second isn't.
- A British National Grid easting and northing in metres, labelled
  (`E 410250 N 169960`, `410250E 169960N`, `easting 410250, northing 169960`)
  or as a pair with a comma (`410250, 169960`), unless both are whole
  kilometres.
- A three-word address: three words joined by dots, after `///` or a
  what3words link, or on their own when none of the words is part of a web
  or file address (`www`, `com`, `uk`, `pdf` and the like) and each has at
  least three letters.

Some text only looks like a position, and is left alone: postcodes
(`SO17 1BJ`), dates (`2024-11-11`), telephone numbers (`01234 567890`), list
entry numbers (`1012345`), a single number, and prices. Some ordinary text
is caught, and is accepted as the cost of not missing a position: a word of
one or two letters that names a grid square followed by six figures (`no
123456`, `A 123 456`), two six-figure numbers with a comma between them, and
three dotted words such as `fish.and.chips`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from fieldclub import gridref

PLACEHOLDER = "[position hidden]"

# Spaces a person or a copied page might put between parts: ordinary and
# non-breaking spaces, the thin and narrow spaces, and the zero-width ones.
_SEP = r"[ \t\u00a0\u1680\u2000-\u200b\u202f\u205f\u2060\u3000\ufeff]"

# The lettered squares of both grids, as `parse_gridref` reads them.
_ALPHABET = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
_SQUARES = frozenset(
    letters
    for letters in [*_ALPHABET, *(a + b for a in _ALPHABET for b in _ALPHABET)]
    if gridref.try_parse_gridref(f"{letters}11") is not None
)
assert {"SU", "NO", "TQ", "HU", "J", "O"} <= _SQUARES, "the grid squares are known"
assert "AB" not in _SQUARES

_GRID = re.compile(
    rf"(?<![A-Za-z0-9])(?P<letters>[A-Za-z]{{1,2}}){_SEP}*"
    rf"(?:(?P<east>\d{{3,5}}){_SEP}+(?P<north>\d{{3,5}})|(?P<compact>\d{{6,10}}))(?!\d)"
)

# A signed decimal number of degrees.
_NUMBER = r"[-+\u2212]?\d{1,3}\.\d+"
_HEMISPHERE = r"[NSEWnsew]"
_DEGREE = r"[\u00b0\u00ba\u02da]"
_MINUTE = r"['\u2032\u2019]"
_SECOND = r"(?:\"|\u2033|\u201d|'')"
_BETWEEN = rf"(?:{_SEP}*[,;/|]{_SEP}*|{_SEP}+)"
_BETWEEN_OR_NONE = rf"{_SEP}*[,;/|]?{_SEP}*"


def _decimal(i: int, *, leading: bool) -> str:
    """One decimal number of degrees, with its hemisphere before it or, perhaps, after it."""
    number = rf"(?P<v{i}>{_NUMBER}){_SEP}*{_DEGREE}?"
    if leading:
        return rf"(?P<h{i}>{_HEMISPHERE}){_SEP}*{number}"
    return rf"{number}{_SEP}*(?P<h{i}>{_HEMISPHERE})?"


def _dms(i: int, *, leading: bool) -> str:
    """Degrees and minutes, perhaps with seconds, with the hemisphere before it or, perhaps, after it."""
    value = (
        rf"(?P<d{i}>\d{{1,3}}){_SEP}*{_DEGREE}{_SEP}*(?P<m{i}>\d{{1,2}}(?:\.\d+)?){_SEP}*{_MINUTE}"
        rf"(?:{_SEP}*(?P<s{i}>\d{{1,2}}(?:\.\d+)?){_SEP}*{_SECOND})?"
    )
    if leading:
        return rf"(?P<h{i}>{_HEMISPHERE}){_SEP}*{value}"
    return rf"{value}{_SEP}*(?P<h{i}>{_HEMISPHERE})?"


# Not after a word, a currency sign or a decimal point, and not running on
# into more figures or a word. Each pair is written with the hemispheres
# before the numbers (`N 51.43 W 1.85`) or after them, or without them, and a
# pattern is tried for each, because a letter between two numbers could
# belong to either.
_DECIMAL_PAIRS = tuple(
    re.compile(
        rf"(?<![\w.\u00a3$\u20ac]){_decimal(1, leading=leading)}{_BETWEEN}{_decimal(2, leading=leading)}"
        r"(?!\.?\d)(?![^\W\d_])"
    )
    for leading in (True, False)
)
_DMS_PAIRS = tuple(
    re.compile(rf"(?<![\w.]){_dms(1, leading=leading)}{_BETWEEN_OR_NONE}{_dms(2, leading=leading)}(?!\w)")
    for leading in (True, False)
)

_EAST_NORTH_LABELLED = re.compile(
    rf"(?i)(?<![\w.])(?:e|easting){_SEP}*[:=]?{_SEP}*(?P<e>\d{{6}})(?!\d)[,;]?{_SEP}*"
    rf"(?:n|northing){_SEP}*[:=]?{_SEP}*(?P<n>\d{{6,7}})(?!\.?\d)(?!\w)"
    rf"|(?<![\w.])(?P<e2>\d{{6}}){_SEP}*(?:e|east){_SEP}*[,;]?{_SEP}*(?P<n2>\d{{6,7}}){_SEP}*(?:n|north)(?![\w])"
)
_EAST_NORTH_PAIR = re.compile(rf"(?<![\w.,])(?P<e>\d{{6}}){_SEP}*,{_SEP}*(?P<n>\d{{6,7}})(?!\.?\d)(?!\w)")

_WORD = r"[^\W\d_]+"
_WORDS = re.compile(
    rf"(?<![\w.@/-])(?P<prefix>///{_SEP}*|(?:https?://)?(?:www\.)?(?:what3words\.com|w3w\.co)/)?"
    rf"(?P<words>{_WORD}\.{_WORD}\.{_WORD})(?![\w@-]|\.[^\W\d_])"
)
# Parts of web and file addresses, which a bare three-word address never has.
_NOT_WORDS = frozenset(
    {
        "www", "com", "org", "net", "gov", "edu", "int", "info", "biz", "ac", "co", "uk", "io", "eu",
        "ie", "scot", "wales", "nhs", "sch", "ltd", "plc", "html", "htm", "php", "asp", "aspx", "pdf",
        "doc", "docx", "xls", "xlsx", "csv", "txt", "jpg", "jpeg", "png", "gif", "webp", "tif", "tiff",
        "json", "xml", "kml", "kmz", "zip", "shp", "gpkg",
    }
)  # fmt: skip

# Where the British Isles are, generously.
_LAT = (49.0, 61.5)
_LON = (-14.0, 2.5)


class PositionKind(StrEnum):
    GRID_REFERENCE = "grid_reference"
    COORDINATES = "coordinates"
    EASTING_NORTHING = "easting_northing"
    THREE_WORDS = "three_words"


@dataclass(frozen=True)
class Found:
    kind: PositionKind
    start: int
    end: int


def _grid(match: re.Match[str]) -> bool:
    if match["letters"].upper() not in _SQUARES:
        return False
    if match["compact"] is not None:
        return len(match["compact"]) % 2 == 0
    return len(match["east"]) == len(match["north"])


def _signed(value: str, hemisphere: str | None) -> float:
    number = float(value.replace("\u2212", "-"))
    return -abs(number) if hemisphere is not None and hemisphere.upper() in "SW" else number


def _lat_lon(first: float, second: float, axes: tuple[str | None, str | None]) -> bool:
    """Whether two signed numbers make a position in the British Isles, in whichever order fits."""

    def inside(lat: float, lon: float) -> bool:
        return _LAT[0] <= lat <= _LAT[1] and _LON[0] <= lon <= _LON[1]

    a_axis, b_axis = axes
    if a_axis == "lat" or b_axis == "lon":
        return a_axis != "lon" and b_axis != "lat" and inside(first, second)
    if a_axis == "lon" or b_axis == "lat":
        return inside(second, first)
    return inside(first, second) or inside(second, first)


def _axis(hemisphere: str | None) -> str | None:
    if hemisphere is None:
        return None
    return "lat" if hemisphere.upper() in "NS" else "lon"


def _decimal_pair(match: re.Match[str]) -> bool:
    if min(len(match["v1"].split(".")[1]), len(match["v2"].split(".")[1])) < 2:
        return False
    return _pair(_signed(match["v1"], match["h1"]), _signed(match["v2"], match["h2"]), match)


def _dms_pair(match: re.Match[str]) -> bool:
    if not any(match[f"s{i}"] is not None or "." in match[f"m{i}"] for i in (1, 2)):
        return False

    def degrees(i: int) -> float:
        value = int(match[f"d{i}"]) + float(match[f"m{i}"]) / 60 + float(match[f"s{i}"] or 0) / 3600
        return _signed(str(value), match[f"h{i}"])

    return _pair(degrees(1), degrees(2), match)


def _pair(first: float, second: float, match: re.Match[str]) -> bool:
    axes = (_axis(match["h1"]), _axis(match["h2"]))
    if axes[0] is not None and axes[0] == axes[1]:
        return False
    return _lat_lon(first, second, axes)


def _east_north(easting: str, northing: str) -> bool:
    east, north = int(easting), int(northing)
    if not (0 <= east < 700_000 and 0 <= north < 1_300_000):
        return False
    return east % 1000 != 0 or north % 1000 != 0


def _three_words(match: re.Match[str]) -> bool:
    if match["prefix"]:
        return True
    words = match["words"].lower().split(".")
    return all(len(word) >= 3 and word not in _NOT_WORDS for word in words)


def _labelled_east_north(match: re.Match[str]) -> bool:
    return _east_north(match["e"] or match["e2"], match["n"] or match["n2"])


def _paired_east_north(match: re.Match[str]) -> bool:
    return _east_north(match["e"], match["n"])


# Each pattern, what it finds, and the test a match must pass.
_FINDERS: tuple[tuple[re.Pattern[str], PositionKind, Callable[[re.Match[str]], bool]], ...] = (
    (_GRID, PositionKind.GRID_REFERENCE, _grid),
    *((pattern, PositionKind.COORDINATES, _decimal_pair) for pattern in _DECIMAL_PAIRS),
    *((pattern, PositionKind.COORDINATES, _dms_pair) for pattern in _DMS_PAIRS),
    (_EAST_NORTH_LABELLED, PositionKind.EASTING_NORTHING, _labelled_east_north),
    (_EAST_NORTH_PAIR, PositionKind.EASTING_NORTHING, _paired_east_north),
    (_WORDS, PositionKind.THREE_WORDS, _three_words),
)


def find_positions(text: str) -> list[Found]:
    """Every position finer than a 1 km square in `text`, in order, overlapping ones merged."""
    found = sorted(
        (
            Found(kind, match.start(), match.end())
            for pattern, kind, holds in _FINDERS
            for match in pattern.finditer(text)
            if holds(match)
        ),
        key=lambda item: (item.start, -item.end),
    )
    merged: list[Found] = []
    for item in found:
        if merged and item.start < merged[-1].end:
            last = merged[-1]
            merged[-1] = Found(last.kind, last.start, max(last.end, item.end))
        else:
            merged.append(item)
    return merged


def holds_position(text: str | None) -> bool:
    return text is not None and bool(find_positions(text))


def redact(text: str) -> str:
    """`text` with every position replaced by `PLACEHOLDER`."""
    parts: list[str] = []
    end = 0
    for item in find_positions(text):
        parts.append(text[end : item.start])
        parts.append(PLACEHOLDER)
        end = item.end
    parts.append(text[end:])
    return "".join(parts)
