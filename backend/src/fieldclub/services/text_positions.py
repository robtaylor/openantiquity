"""Positions written in words: grid references, coordinates and three-word addresses in free text.

A finding's title, description and notes, its comments, evidence and
mentions are free text, and a person can type a position into any of them.
For a protected finding that would undo Decision 0005, so
`services.sensitivity.visible_text` replaces every position found here with
`PLACEHOLDER` for a viewer who doesn't see the exact position, and
`services.findings` refuses a title or description that holds one when the
finding isn't open.

What counts as a position finer than a 1 km square:

- A grid reference of six figures or more on the British or Irish grid, in
  any case, with or without spaces: `SU 123 456`, `su123456`,
  `SU 12345 67890`, `J 338 740`. The figure groups may also be split by a
  hyphen, dot, comma or slash (`SU 123-456`, `SU.123.456`, `SU 123,456`),
  and the letters from the figures by a hyphen or dot (`SU-123456`). The
  letters must name a real square and stand on their own, so `NHLE 1012345`
  isn't one. Four figures name a 1 km square and are left alone. The figures
  must split evenly: six, eight or ten together, or two equal groups. An odd
  run such as `SU 1234567` is left alone, as `parse_gridref` refuses it.
- A latitude and longitude pair in the British Isles (latitude 49 to 61.5,
  longitude -14 to 2.5), in either order: decimal degrees with at least two
  decimal places on each, with a decimal point or a decimal comma
  (`51.4286, -1.8542`, `51.43N 1.85W`, `@51.4286,-1.8542`, `51.4286/-1.8542`,
  `51,4286 -1,8542`), perhaps labelled (`lat 51.4286 lon -1.8542`,
  `Lat: 51.4286, Long: -1.8542`, `lat=51.4286&lon=-1.8542`), or degrees and
  minutes with seconds or decimal minutes (`51°25'43"N 1°51'15"W`,
  `51° 25.7' N, 1° 51.2' W`, `51d25m43s N 1d51m15s W`). Degrees and minutes
  written with spaces alone count when both carry a hemisphere
  (`N51 25.716 W1 51.250`, `51 25 43N 1 51 15W`). Two decimal places are
  1.1 km of latitude but 0.7 km of longitude, and whole minutes 1.9 by
  1.2 km, so the first is a position and the second isn't.
- A British National Grid easting and northing in metres, labelled
  (`E 410250 N 169960`, `410250E 169960N`, `easting 410250, northing 169960`)
  or as a pair of six figures and six or seven separated by a comma, a slash
  or a space (`410250, 169960`, `410250/169960`, `410250 169960`), inside
  the grid and unless both are whole kilometres.
- A three-word address: three words joined by dots, after `///` or a
  what3words link, or on their own when none of the words is part of a web
  or file address (`www`, `com`, `uk`, `pdf` and the like) and each has at
  least three letters.

Map links say where a place is in their own ways, and count the same:
coordinates labelled with a prefix (`mlat=51.4286&mlon=-1.8542` from
OpenStreetMap), split by a tilde (`cp=51.4286~-1.8542` from Bing) or by a
query parameter (`51.4286&lng=-1.8542`), both axes named in a query with
other parameters between them (`lat=51.4286&zoom=17&lng=-1.8542`), Google's
`!3d51.4286!4d-1.8542`,
and an easting and northing as `x=410250&y=169960`. A word or address with
`%` escapes in it (`51%C2%B025%2743%22N`) is read decoded as well, and when
the decoded form holds a position the whole word is hidden.

An Open Location Code ("plus code") counts too, in full (`9C3WC4HW+F8`) or
short (`C4HW+F8 Avebury`, as Google shares it), and so does any link to a map
site, such as a short link (`maps.app.goo.gl/...`), an OpenStreetMap object
or tile, a geohash or a plus code, because such a link opens at a place
whether or not figures show in it.

Text is read as a person sees it: compatibility forms such as full-width
letters and figures are read as the plain ones (NFKC), invisible format
characters are skipped, and a run of spaces counts as one, so every pattern
takes time in proportion to the text. Spans still point into the text as
written, so `redact` keeps everything around a position exactly.

Some text only looks like a position, and is left alone: postcodes
(`SO17 1BJ`), dates (`2024-11-11`), telephone numbers (`01234 567890`), list
entry numbers (`1012345`), a single number, and prices. Some ordinary text
is caught, and is accepted as the cost of not missing a position: a word of
one or two letters that names a grid square followed by six figures (`no
123456`, `A 123 456`, `No. 123.456`), two six-figure numbers side by side,
two numbers with a decimal comma that could be a latitude and a longitude
(`52,000 1,250`), three dotted words such as `fish.and.chips`, a sum of
four figures and two (`3456+78`, which is also a plus code), and any link
into a map site, even one that doesn't open at a place.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import unquote

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

# The figure groups may be split by spaces or by one hyphen, dot, comma or
# slash, and the letters from the figures by spaces or a hyphen or dot.
_GROUPS = rf"(?:{_SEP}*[-.,/]{_SEP}*|{_SEP}+)"
_GRID = re.compile(
    rf"(?<![A-Za-z0-9])(?P<letters>[A-Za-z]{{1,2}}){_SEP}*[-.]?{_SEP}*"
    rf"(?:(?P<east>\d{{3,5}}){_GROUPS}(?P<north>\d{{3,5}})|(?P<compact>\d{{6,10}}))(?![.,]?\d)"
)

# A signed decimal number of degrees, with a decimal point or a decimal comma.
_NUMBER = r"[-+\u2212]?\d{1,3}[.,]\d+"
_HEMISPHERE = r"[NSEWnsew]"
_DEGREE = r"[\u00b0\u00ba\u02dad]"
_MINUTE = r"['\u2032\u2019m]"
_SECOND = r"(?:\"|\u2033|\u201d|''|s)"
# A tilde is Bing's, and a query parameter (`&lng=`) a map link's.
_BETWEEN = rf"(?:{_SEP}*[,;/|~]{_SEP}*|&[A-Za-z_]{{1,16}}=|{_SEP}+)"
_BETWEEN_OR_NONE = rf"{_SEP}*[,;/|~]?{_SEP}*"
# A word naming the axis, as in `lat 51.43` or `lon=-1.85`, perhaps with a
# short prefix, as in OpenStreetMap's `mlat=` and `mlon=`.
_AXIS_LABEL = r"(?i:[a-z]{0,3}?(?:latitude|lat|longitude|long|lon|lng))"


def _label(i: int) -> str:
    return rf"(?P<l{i}>{_AXIS_LABEL}){_SEP}*[:=]?{_SEP}*"


def _decimal(i: int, *, leading: bool) -> str:
    """One decimal number of degrees, with its hemisphere before it or, perhaps, after it."""
    number = rf"(?P<v{i}>{_NUMBER}){_SEP}*{_DEGREE}?"
    if leading:
        return rf"(?P<h{i}>{_HEMISPHERE}){_SEP}*{number}"
    return rf"{number}{_SEP}*(?P<h{i}>{_HEMISPHERE})?"


def _dms(i: int, *, leading: bool) -> str:
    """Degrees and minutes, perhaps with seconds, with the hemisphere before it or, perhaps, after it.

    The marks may be symbols, the letters `d`, `m` and `s`, or spaces. A
    value without a degree mark (`51 25 43N`) only counts when both values
    carry a hemisphere, which `_dms_pair` checks.
    """
    value = (
        rf"(?P<d{i}>\d{{1,3}})(?:{_SEP}*(?P<k{i}>{_DEGREE}){_SEP}*|{_SEP}+)(?P<m{i}>\d{{1,2}}(?:\.\d+)?)"
        rf"(?:(?:{_SEP}*{_MINUTE}{_SEP}*|{_SEP}+)(?P<s{i}>\d{{1,2}}(?:\.\d+)?)(?:{_SEP}*{_SECOND})?"
        rf"|{_SEP}*{_MINUTE})?"
    )
    if leading:
        return rf"(?P<h{i}>{_HEMISPHERE}){_SEP}*{value}"
    return rf"{value}{_SEP}*(?P<h{i}>{_HEMISPHERE})?"


# Not after a word, a currency sign or a decimal point, and not running on
# into more figures or a word. Each pair is written with the hemispheres
# before the numbers (`N 51.43 W 1.85`) or after them, or without them, and a
# pattern is tried for each, because a letter between two numbers could
# belong to either. A decimal pair may name its axes (`lat 51.43 lon -1.85`).
_DECIMAL_PAIRS = tuple(
    re.compile(
        rf"(?<![\w.\u00a3$\u20ac])(?:{_label(1)})?{_decimal(1, leading=leading)}"
        rf"(?:{_BETWEEN}|{_SEP}*[,;/|&]?{_SEP}*{_label(2)}){_decimal(2, leading=leading)}"
        r"(?!\.?\d)(?![^\W\d_])"
    )
    for leading in (True, False)
)
_DMS_PAIRS = tuple(
    re.compile(rf"(?<![\w.]){_dms(1, leading=leading)}{_BETWEEN_OR_NONE}{_dms(2, leading=leading)}(?!\w)")
    for leading in (True, False)
)

_EAST_NORTH_LABELLED = re.compile(
    rf"(?i)(?<![\w.])(?:e|easting|x){_SEP}*[:=]?{_SEP}*(?P<e>\d{{6}})(?!\d)[,;&]?{_SEP}*"
    rf"(?:n|northing|y){_SEP}*[:=]?{_SEP}*(?P<n>\d{{6,7}})(?!\.?\d)(?!\w)"
    rf"|(?<![\w.])(?P<e2>\d{{6}}){_SEP}*(?:e|east){_SEP}*[,;]?{_SEP}*(?P<n2>\d{{6,7}}){_SEP}*(?:n|north)(?![\w])"
)
_EAST_NORTH_PAIR = re.compile(
    rf"(?<![\w.,/])(?P<e>\d{{6}})(?:{_SEP}*[,/]{_SEP}*|{_SEP}+)(?P<n>\d{{6,7}})(?![.,/]?\d)(?!\w)"
)

# Google's place links: `!3d<latitude>!4d<longitude>`.
_GOOGLE_DATA = re.compile(rf"!3d(?P<v1>{_NUMBER})!4d(?P<v2>{_NUMBER})")
# A query string naming both axes, with other parameters between them:
# `lat=51.4286&zoom=17&lng=-1.8542`.
_QUERY_PAIR = re.compile(
    rf"(?<![\w.])(?P<l1>{_AXIS_LABEL})=(?P<v1>{_NUMBER})(?:&[^&\s=#]{{1,20}}=[^&\s#]{{0,40}}){{1,8}}"
    rf"&(?P<l2>{_AXIS_LABEL})=(?P<v2>{_NUMBER})(?![.\d])"
)

# Open Location Codes: an even number of characters from their alphabet, a
# `+`, and two or three more. Four or more before the `+` name a place to
# within metres, given a nearby town for a short one.
_OLC = "23456789CFGHJMPQRVWXcfghjmpqrvwx"
_PLUS_CODE = re.compile(rf"(?<![0-9A-Za-z+])(?P<code>[{_OLC}]{{4,8}})\+[{_OLC}]{{2,3}}(?![0-9A-Za-z+])")

# Links into map sites: each opens at a place, whatever its address shows.
_MAP_SITES = (
    r"maps\.app\.goo\.gl/",
    r"goo\.gl/maps/",
    r"g\.co/kgs/",
    r"maps\.google\.[a-z]{2,3}(?:\.[a-z]{2})?[/?#]",
    r"google\.[a-z]{2,3}(?:\.[a-z]{2})?/maps[/?@#]",
    r"openstreetmap\.org[/?#]",
    r"osm\.org/",
    r"bing\.com/maps[/?#]",
    r"maps\.apple\.com[/?#]",
    r"(?:wego\.)?here\.com/[a-z]{1,2}/",
    r"what3words\.com/",
    r"w3w\.co/",
    r"plus\.codes/",
    r"geohash\.org/",
    r"gridreferencefinder\.com[/?#]",
    r"streetmap\.co\.uk/",
    r"wikimapia\.org[/?#]",
    r"waze\.com/(?:[a-z-]+/)?(?:ul|live-map)",
)
_MAP_LINK = re.compile(
    rf"(?i)(?<![\w.@/-])(?:https?://)?(?:[a-z0-9-]{{1,63}}\.){{0,4}}(?:{'|'.join(_MAP_SITES)})"
    r"[^\s<>\"'\[\]{}|\\^`]+"
)

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
    PLUS_CODE = "plus_code"
    MAP_LINK = "map_link"


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
    number = float(value.replace("\u2212", "-").replace(",", "."))
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


def _axis(match: re.Match[str], i: int) -> str | None:
    """The axis a value names by its label, or else by its hemisphere."""
    label = match.groupdict().get(f"l{i}")
    if label is not None:
        return "lat" if "lat" in label.lower() else "lon"
    hemisphere = match[f"h{i}"]
    if hemisphere is None:
        return None
    return "lat" if hemisphere.upper() in "NS" else "lon"


def _decimal_pair(match: re.Match[str]) -> bool:
    if min(len(re.split("[.,]", match[f"v{i}"])[1]) for i in (1, 2)) < 2:
        return False
    return _pair(_signed(match["v1"], match["h1"]), _signed(match["v2"], match["h2"]), match)


def _labelled_values(match: re.Match[str], axes: tuple[str | None, str | None]) -> bool:
    """Two decimal values whose axes are known, from a map link's own fields."""
    if min(len(re.split("[.,]", match[f"v{i}"])[1]) for i in (1, 2)) < 2:
        return False
    if axes[0] is not None and axes[0] == axes[1]:
        return False
    return _lat_lon(_signed(match["v1"], None), _signed(match["v2"], None), axes)


def _google_data(match: re.Match[str]) -> bool:
    return _labelled_values(match, ("lat", "lon"))


def _query_pair(match: re.Match[str]) -> bool:
    def axis(label: str) -> str:
        return "lat" if "lat" in label.lower() else "lon"

    return _labelled_values(match, (axis(match["l1"]), axis(match["l2"])))


def _dms_pair(match: re.Match[str]) -> bool:
    if not any(match[f"s{i}"] is not None or "." in match[f"m{i}"] for i in (1, 2)):
        return False
    if any(float(match[f"m{i}"]) >= 60 or float(match[f"s{i}"] or 0) >= 60 for i in (1, 2)):
        return False
    if not all(match[f"k{i}"] is not None or match[f"h{i}"] is not None for i in (1, 2)):
        return False

    def degrees(i: int) -> float:
        value = int(match[f"d{i}"]) + float(match[f"m{i}"]) / 60 + float(match[f"s{i}"] or 0) / 3600
        return _signed(str(value), match[f"h{i}"])

    return _pair(degrees(1), degrees(2), match)


def _pair(first: float, second: float, match: re.Match[str]) -> bool:
    axes = (_axis(match, 1), _axis(match, 2))
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


def _plus_code(match: re.Match[str]) -> bool:
    return len(match["code"]) % 2 == 0


def _always(match: re.Match[str]) -> bool:
    return True


# Each pattern, what it finds, and the test a match must pass.
_FINDERS: tuple[tuple[re.Pattern[str], PositionKind, Callable[[re.Match[str]], bool]], ...] = (
    (_GRID, PositionKind.GRID_REFERENCE, _grid),
    *((pattern, PositionKind.COORDINATES, _decimal_pair) for pattern in _DECIMAL_PAIRS),
    *((pattern, PositionKind.COORDINATES, _dms_pair) for pattern in _DMS_PAIRS),
    (_GOOGLE_DATA, PositionKind.COORDINATES, _google_data),
    (_QUERY_PAIR, PositionKind.COORDINATES, _query_pair),
    (_EAST_NORTH_LABELLED, PositionKind.EASTING_NORTHING, _labelled_east_north),
    (_EAST_NORTH_PAIR, PositionKind.EASTING_NORTHING, _paired_east_north),
    (_WORDS, PositionKind.THREE_WORDS, _three_words),
    (_PLUS_CODE, PositionKind.PLUS_CODE, _plus_code),
    (_MAP_LINK, PositionKind.MAP_LINK, _always),
)


# A run of text with no space in it, such as a link. Those with a `%` escape are decoded.
_WORD_RUN = re.compile(r"\S+")
_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
# Escapes inside escapes are read this many times over.
_DECODE_ROUNDS = 3
# Longer words are not decoded: no address is that long.
_ESCAPED_WORD_MAX = 8000


# The separators `_SEP` names, which `_normalised` folds to one space a run.
_SEPARATOR = re.compile(_SEP)
# Degree, minute and second marks the patterns read as written. NFKC would
# turn some into letters (`º` into `o`) or into two marks.
_MARKS = frozenset("\u00b0\u00ba\u02da\u2032\u2033\u2019\u201d")
# What needs no folding: plain ASCII text without a run of two separators.
_FOLD_NEEDED = re.compile(r"[^\x00-\x7f]|[ \t]{2}")


@dataclass(frozen=True)
class _Folded:
    """Text as the patterns read it, and where each of its characters came from in the original."""

    text: str
    # `origin[i]` is the index in the original of folded character `i`, and
    # `origin[len(text)]` is the original's length. None when nothing was folded.
    origin: list[int] | None

    def span(self, start: int, end: int) -> tuple[int, int]:
        if self.origin is None:
            return start, end
        return self.origin[start], self.origin[end - 1] + 1


def _normalised(text: str) -> _Folded:
    """`text` in NFKC form a character at a time, less format characters, each run of separators one space."""
    if not _FOLD_NEEDED.search(text):
        return _Folded(text, None)
    folded: list[str] = []
    origin: list[int] = []
    after_separator = False
    for index, character in enumerate(text):
        if unicodedata.category(character) == "Cf":
            continue
        plain = character.isascii() or character in _MARKS
        for part in character if plain else unicodedata.normalize("NFKC", character):
            separator = _SEPARATOR.fullmatch(part) is not None
            if separator and after_separator:
                continue
            after_separator = separator
            folded.append(" " if separator else part)
            origin.append(index)
    origin.append(len(text))
    return _Folded("".join(folded), origin)


def _matches(text: str) -> list[Found]:
    """Positions in `text` as written, found in its folded form."""
    folded = _normalised(text)
    return [
        Found(kind, *folded.span(match.start(), match.end()))
        for pattern, kind, holds in _FINDERS
        for match in pattern.finditer(folded.text)
        if holds(match)
    ]


def _decodings(word: str) -> list[str]:
    """`word` with its `%` escapes undone, once and up to `_DECODE_ROUNDS` times, and with `+`
    read as a space, as a query string means it. A plus code's `+` is lost to that last reading,
    so each round is read as it is too."""
    readings: list[str] = []
    for _ in range(_DECODE_ROUNDS):
        decoded = unquote(word)
        if decoded == word:
            break
        readings.append(decoded)
        word = decoded
    readings.append(word.replace("+", " "))
    return readings


def _escaped(text: str) -> list[Found]:
    """Each word with `%` escapes whose decoded form holds a position, as one span."""
    found = []
    for match in _WORD_RUN.finditer(text):
        word = match.group(0)
        if len(word) > _ESCAPED_WORD_MAX or not _ESCAPE.search(word):
            continue
        for reading in _decodings(word):
            inside = _matches(reading)
            if inside:
                found.append(Found(inside[0].kind, match.start(), match.end()))
                break
    return found


def find_positions(text: str) -> list[Found]:
    """Every position finer than a 1 km square in `text`, in order, overlapping ones merged."""
    found = sorted([*_matches(text), *_escaped(text)], key=lambda item: (item.start, -item.end))
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
