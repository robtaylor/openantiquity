"""Positions written in free text, found and hidden (Decision 0005).

The module docstring of `services/text_positions.py` says what counts and
what is left alone. These cases hold it to that.
"""

from __future__ import annotations

import pytest

from fieldclub import gridref
from fieldclub.services.text_positions import (
    PLACEHOLDER,
    PositionKind,
    find_positions,
    holds_position,
    redact,
    restore,
)
from tests.helpers import AVEBURY

# Avebury's henge, written every way people write it.
GRID_REFERENCES = [
    "SU 102 699",
    "SU102699",
    "su 102 699",
    "Su102 699",
    "SU 1025 6996",
    "SU10256996",
    "su 10256 69961",
    "SU\u00a01025\u00a06996",
    "SU 1025\u20096996",
    "SU 102\u200b699",
    # The Irish grid: one letter.
    "J 338 740",
    "j338740",
    "O 1590 3440",
    # Shetland and the far south-west.
    "HU 4741 4112",
    "SV 9050 1025",
    # Figure groups split by a hyphen, a dot, a comma or a slash.
    "SU 102-699",
    "SU-102-699",
    "SU.102.699",
    "SU 102,699",
    "SU 102/699",
    "SU-102699",
]

COORDINATES = [
    "51.4286, -1.8542",
    "51.4286,-1.8542",
    "51.4286 -1.8542",
    "51.43, -1.85",
    "-1.8542, 51.4286",
    "51.4286N 1.8542W",
    "51.4286 N, 1.8542 W",
    "N 51.4286 W 1.8542",
    "N51.4286, W1.8542",
    "51.4286\u00b0N 1.8542\u00b0W",
    "51.4286\u00b0 -1.8542\u00b0",
    "@51.4286,-1.8542,17z",
    "#map=17/51.4286/-1.8542",
    "geo:51.4286,-1.8542",
    "51.4286 \u22121.8542",
    "51\u00b025'43\"N 1\u00b051'15\"W",
    "51\u00b0 25' 43\" N, 1\u00b0 51' 15\" W",
    "51\u00b025\u203243\u2033N 1\u00b051\u203215\u2033W",
    "51\u00b0 25.716\u2032 N, 1\u00b0 51.252\u2032 W",
    "N 51\u00b025.7' W 1\u00b051.2'",
    # Dublin and Lerwick, on the edges of what is looked for.
    "53.3498, -6.2603",
    "60.1546, -1.1494",
    # Labelled latitude and longitude.
    "lat 51.4286 lon -1.8542",
    "Lat: 51.4286, Long: -1.8542",
    "latitude 51.4286 longitude -1.8542",
    "lat=51.4286&lon=-1.8542",
    "lng -1.8542, lat 51.4286",
    # Degrees and decimal minutes without symbols, the hemisphere first.
    "N51 25.716 W1 51.250",
    "N 51 25.716, W 1 51.252",
    # Degrees, minutes and seconds without symbols, or with letters.
    "51 25 43N 1 51 15W",
    "51 25 43 N, 1 51 15 W",
    "51d25m43s N 1d51m15s W",
    "51d 25m 43s N, 1d 51m 15s W",
    # Decimal commas.
    "51,4286 -1,8542",
    "51,4286; -1,8542",
]

EASTINGS_AND_NORTHINGS = [
    "E 410250 N 169960",
    "E:410250 N:169960",
    "410250E 169960N",
    "easting 410250, northing 169960",
    "Easting: 410250 Northing: 169960",
    "410250, 169960",
    "410250,169960",
    "447410, 1141250",
    # Separated by a space or a slash.
    "410250 169960",
    "410250/169960",
]

THREE_WORDS = [
    "///filled.count.soap",
    "/// filled.count.soap",
    "https://what3words.com/filled.count.soap",
    "w3w.co/filled.count.soap",
    "filled.count.soap",
    "Filled.Count.Soap",
]

# Text that only looks like a position, and is left alone.
LOOKALIKES = [
    # Postcodes.
    "SO17 1BJ",
    "SN8 1RF",
    "SW1A 1AA",
    # Dates and times.
    "2024-11-11",
    "11/11/2024",
    "11.11.2024",
    "at 12.30, 13.45",
    # Telephone numbers.
    "01672 539250",
    "+44 1672 539250",
    "Tel 01672 539250",
    "T 01672 539250",
    # List entry numbers, a monument number and an NMR number.
    "List entry 1012345",
    "NHLE 1012345",
    "Scheduled Monument 1008527",
    "MWI12345",
    "SU 16 NW 12",
    # A 1 km square, or coarser.
    "SU 10 69",
    "SU1069",
    "SU 1 6",
    # Fewer decimal places than a kilometre needs, or whole minutes.
    "51.4, -1.8",
    "51.43, -1.8",
    "51\u00b025'N 1\u00b051'W",
    # Whole kilometres.
    "410000, 169000",
    # Numbers out of the British Isles, and prices.
    "40.7128, -74.0060",
    "\u00a351.20, \u00a31.50",
    "12.30 13.45",
    # Web and file addresses.
    "www.bbc.co.uk",
    "historicengland.org.uk",
    "report.final.pdf",
    "e.g. the bank",
    # An odd run of figures, which isn't a grid reference.
    "SU 1234567",
    # Two hemispheres of one kind.
    "51.4286N 1.8542N",
    # Numbers with hemisphere letters that aren't a position.
    "51 25 43N",
    "N51 25 W1 51",
    "51 75 43N 1 51 15W",
    # Words between two numbers that aren't labels.
    "51.4286 metres from -1.8542",
    # A telephone number and a date, both with spaces.
    "07700 900123",
    "20241111 120000",
]

# Ordinary text that is caught, as the module docstring accepts.
CAUGHT_ALL_THE_SAME = [
    "no 123456",
    "A 123 456",
    "No. 123.456",
    "fish.and.chips",
    "52.10 0.25",
    "52,000 1,250",
    "123456 654321",
]


@pytest.mark.parametrize("text", GRID_REFERENCES)
def test_grid_references_are_found_in_every_spacing_and_case(text: str) -> None:
    (found,) = find_positions(f"The bank at {text} runs north.")
    assert found.kind is PositionKind.GRID_REFERENCE
    assert redact(f"The bank at {text} runs north.") == f"The bank at {PLACEHOLDER} runs north."


def test_the_grid_references_are_real_ones() -> None:
    ref = gridref.parse_gridref(GRID_REFERENCES[0])
    lon, lat = ref.centre()
    assert gridref.to_gridref(*AVEBURY, 6) == "SU 102 699"
    assert abs(lon - AVEBURY[0]) < 0.01
    assert abs(lat - AVEBURY[1]) < 0.01


@pytest.mark.parametrize("text", COORDINATES)
def test_latitude_and_longitude_are_found_in_several_notations(text: str) -> None:
    found = find_positions(f"Look at {text} on the map")
    assert [item.kind for item in found] == [PositionKind.COORDINATES], text
    hidden = redact(f"Look at {text}")
    assert PLACEHOLDER in hidden
    assert "4286" not in hidden
    assert "8542" not in hidden


@pytest.mark.parametrize("text", EASTINGS_AND_NORTHINGS)
def test_eastings_and_northings_are_found(text: str) -> None:
    assert [item.kind for item in find_positions(f"Centred on {text}.")] == [PositionKind.EASTING_NORTHING]


@pytest.mark.parametrize("text", THREE_WORDS)
def test_three_word_addresses_are_found(text: str) -> None:
    assert [item.kind for item in find_positions(f"Meet at {text} please")] == [PositionKind.THREE_WORDS]
    assert redact(f"Meet at {text} please") == f"Meet at {PLACEHOLDER} please"


@pytest.mark.parametrize("text", LOOKALIKES)
def test_text_that_only_looks_like_a_position_is_left_alone(text: str) -> None:
    assert find_positions(text) == [], text
    assert redact(f"See {text}.") == f"See {text}."


@pytest.mark.parametrize("text", CAUGHT_ALL_THE_SAME)
def test_some_ordinary_text_is_caught_all_the_same(text: str) -> None:
    assert holds_position(text)


def test_every_position_in_a_text_is_replaced_and_the_rest_kept() -> None:
    text = "Two banks: SU 1025 6996 and 51.4286, -1.8542. Gate at ///filled.count.soap, list entry 1012345."
    assert redact(text) == (
        f"Two banks: {PLACEHOLDER} and {PLACEHOLDER}. Gate at {PLACEHOLDER}, list entry 1012345."
    )
    assert holds_position(text)
    assert not holds_position(None)
    assert not holds_position("")
    assert redact("") == ""


# Avebury in the share links people paste from map sites.
MAP_LINKS = [
    "https://www.openstreetmap.org/?mlat=51.42863&mlon=-1.85417",
    "https://www.openstreetmap.org/?mlat=51.42863&mlon=-1.85417#map=18/51.42863/-1.85417",
    "https://www.openstreetmap.org/#map=18/51.42863/-1.85417",
    "https://www.bing.com/maps?cp=51.42863~-1.85417&lvl=18",
    "https://www.google.com/maps/@51.42863,-1.85417,18z",
    "https://www.google.com/maps/place/51%C2%B025%2743.1%22N+1%C2%B051%2715.0%22W",
    "https://www.google.com/maps/place/Avebury/data=!3m1!4b1!4m5!3m4!1s0x0:0x0!8m2!3d51.42863!4d-1.85417",
    "https://www.google.com/maps/search/?api=1&query=51.42863%2C-1.85417",
    "https://www.google.com/maps/search/?api=1&query=51.42863%252C-1.85417",
    "http://maps.apple.com/?ll=51.42863,-1.85417&z=18",
    "https://maps.example/viewer?lat=51.42863&zoom=17&layer=os&lng=-1.85417",
    "https://maps.example/viewer?x=410250&y=169960",
    "geo:51.42863,-1.85417",
    "https://gridreferencefinder.com/?gr=SU1025069960",
    "https://what3words.com/filled.count.soap",
]


@pytest.mark.parametrize("link", MAP_LINKS)
def test_map_links_are_positions_however_the_site_writes_them(link: str) -> None:
    assert holds_position(link), link
    hidden = redact(f"See {link} for it")
    for figures in ("51.4286", "1.8541", "410250"):
        assert figures not in hidden, hidden
    assert hidden.startswith("See ")
    assert hidden.endswith(" for it")
    assert PLACEHOLDER in hidden


@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://doi.org/10.5284/1040209",
        "https://historicengland.org.uk/listing/the-list/list-entry/1008391",
        "https://example.org/a%20page%20about%20barrows",
        "Visit 100%25 of the site",
    ],
)
def test_ordinary_links_and_escapes_are_left_alone(link: str) -> None:
    assert not holds_position(link)
    assert redact(link) == link


def test_reading_escaped_and_paired_values_is_quick_on_long_hostile_text() -> None:
    import time

    for text in ("a" * 50_000, "%41" * 16_000, "lat=51.42863&" + "z=3&" * 12_000, "51.42863~" * 5_000):
        started = time.monotonic()
        redact(text)
        assert time.monotonic() - started < 0.5, text[:20]


# Positions written in other characters, or in other systems than the grid and degrees.
DISGUISED = [
    # Full-width letters and figures, as a phone keyboard in another script gives them.
    "\uff33\uff35\uff11\uff10\uff12\uff13\uff16\uff19\uff19\uff16",
    "\uff33\uff35 \uff11\uff10\uff12\uff13 \uff16\uff19\uff19\uff16",
    "\uff15\uff11.\uff14\uff12\uff18\uff16, -\uff11.\uff18\uff15\uff14\uff12",
    # Mathematical and circled forms that read as the same figures.
    "SU \U0001d7cf\U0001d7ce\U0001d7d0\U0001d7d1 6996",
    # Invisible format characters inside the figures.
    "SU 10\u200d23 69\u200c96",
    "SU 1023\u2066 6996",
    "51.42\u00ad86, -1.8542",
    # Open Location Codes ("plus codes"), in full and short with a place, as Google shares them.
    "9C3WC4HW+F8",
    "9c3wc4hw+f8",
    "C4HW+F8 Avebury",
    "C4HW+F8R",
    "https://plus.codes/9C3WC4HW+F8",
    "https://www.google.com/maps/search/9C3WC4HW%2BF8",
    # Geohash links.
    "https://geohash.org/gcnstf3c",
    "geohash.org/gcnhrwf9",
]


@pytest.mark.parametrize("text", DISGUISED)
def test_positions_in_other_characters_and_systems_are_found(text: str) -> None:
    sentence = f"Look at {text} today."
    assert holds_position(sentence), text
    hidden = redact(sentence)
    assert hidden.startswith("Look at "), hidden
    assert hidden.endswith(" today."), hidden
    assert PLACEHOLDER in hidden
    for figures in ("6996", "\uff16\uff19\uff19\uff16", "4286", "C4HW", "c4hw", "gcn"):
        assert figures not in hidden, hidden


# Links to map sites say where a place is even when no figures show it.
MAP_SITE_LINKS = [
    "https://maps.app.goo.gl/AbCdEf123",
    "https://goo.gl/maps/AbCdEf123",
    "https://www.google.com/maps/place/Avebury+Henge",
    "https://www.google.co.uk/maps/@?api=1&map_action=pano&pano=abc",
    "https://maps.google.com/?cid=1234567890",
    "https://osm.org/go/euu4P0Ia-",
    "https://www.openstreetmap.org/way/4054513",
    "https://tile.openstreetmap.org/18/129718/87091.png",
    "https://www.bing.com/maps?osid=abc",
    "https://maps.apple.com/?auid=123456",
    "https://wego.here.com/p/s-abc",
    "https://www.streetmap.co.uk/map.srf?x=410250&y=169960",
]


@pytest.mark.parametrize("link", MAP_SITE_LINKS)
def test_links_to_map_sites_are_positions(link: str) -> None:
    assert holds_position(link), link
    assert redact(f"See {link} for it") == f"See {PLACEHOLDER} for it"


@pytest.mark.parametrize(
    "text",
    [
        "+44 1672 539250",
        "C++ and C# code",
        "2+2 is 4, 22+33 is 55",
        "Grades A+ and B+",
        "openstreetmap.org has the paths",
        "We used Google Maps and OpenStreetMap.",
        "https://wiki.openstreetmap.org.example/page",
        "\uff21\uff42\uff43 is full-width text",
    ],
)
def test_text_near_those_systems_is_left_alone(text: str) -> None:
    assert not holds_position(text), text
    assert redact(text) == text


def test_redaction_keeps_the_text_around_a_position_exactly_as_written() -> None:
    text = "Ring\u00a0\u00a0ditch \uff08see\uff09 at SU\u200b 1023  6996, then\u3000\u3000north."
    assert redact(text) == f"Ring\u00a0\u00a0ditch \uff08see\uff09 at {PLACEHOLDER}, then\u3000\u3000north."


@pytest.mark.parametrize("separator", [" ", "\u00a0", "\t", "\u3000", "\u200b", " \u200b"])
@pytest.mark.parametrize(
    "before",
    [
        "a",
        "SU",
        "SU 123",
        "51.4286",
        "51.4286\u00b0",
        "N",
        "N 51",
        "51 25",
        "410250",
        "E",
        "lat",
        "51\u00b025'",
    ],
)
def test_finding_positions_takes_linear_time_however_long_the_spaces(before: str, separator: str) -> None:
    """A run of spaces once took time growing with its square or cube, from a signed-out read."""
    import time

    text = before + separator * (50_000 // len(separator)) + "x 1"
    started = time.monotonic()
    find_positions(text)
    assert time.monotonic() - started < 0.5, repr(before)


def test_text_edited_around_its_placeholders_gets_back_what_they_hid() -> None:
    original = f"Bank at SU 1023 6996, ditch at 51.4286, -1.8542, and a literal {PLACEHOLDER} typed."
    shown = redact(original)
    assert shown.count(PLACEHOLDER) == 3
    edited = shown.replace("Bank", "Low bank").replace("typed", "kept")
    assert restore(edited, original) == (
        f"Low bank at SU 1023 6996, ditch at 51.4286, -1.8542, and a literal {PLACEHOLDER} kept."
    )
    assert restore(shown, original) == original
    # One placeholder fewer or more, and nothing can be put back.
    assert restore(shown.replace(PLACEHOLDER, "", 1), original) is None
    assert restore(shown + PLACEHOLDER, original) is None
    assert restore("No positions", "No positions") == "No positions"
