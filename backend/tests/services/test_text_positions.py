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
]

# Ordinary text that is caught, as the module docstring accepts.
CAUGHT_ALL_THE_SAME = ["no 123456", "A 123 456", "fish.and.chips", "52.10 0.25"]


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
