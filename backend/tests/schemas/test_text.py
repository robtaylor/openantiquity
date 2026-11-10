"""Text and JSON that the database could not store are caught before they reach it."""

from __future__ import annotations

import time
from typing import Any

import pytest

from fieldclub.schemas.text import MAX_JSON_DEPTH, find_problem, has_unstorable_character
from tests.helpers import nested


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Plain words.",
        "Two\nlines\r\nand a\ttab",
        "Siân, 王小明 and 🌿",
        "non-breaking\u00a0space",
        "\u202e",
    ],
)
def test_ordinary_text_is_storable(text: str) -> None:
    assert has_unstorable_character(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "nul\x00",
        "\x01start",
        "bell\x07",
        "vertical\x0btab",
        "form\x0cfeed",
        "escape\x1b",
        "del\x7f",
        "c1\x85",
    ],
)
def test_control_characters_are_not_storable(text: str) -> None:
    assert has_unstorable_character(text) is True


def test_a_lone_surrogate_is_not_storable() -> None:
    assert has_unstorable_character("\ud800") is True
    assert has_unstorable_character("fine \U0001f33f") is False


@pytest.mark.parametrize(
    "value",
    [
        None,
        7,
        1.5,
        True,
        "text",
        [],
        {},
        {"a": [1, 2, {"b": "c"}], "d": None},
        {
            "type": "Polygon",
            "coordinates": [[[-1.86, 51.42], [-1.85, 51.42], [-1.85, 51.43], [-1.86, 51.42]]],
        },
    ],
)
def test_ordinary_json_has_no_problem(value: Any) -> None:
    assert find_problem(value) is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("nul\x00", "The request contains a control character"),
        ({"bio": "nul\x00"}, "bio contains a control character"),
        ({"settings": {"a": ["ok", {"b": "bell\x07"}]}}, "settings.a[1].b contains a control character"),
        ({"settings": {"nul\x00key": 1}}, "settings has a key containing a control character"),
        ({"nul\x00key": 1}, "The request has a key containing a control character"),
        ([["fine"], ["\ud800"]], "[1][0] contains a control character"),
    ],
)
def test_problems_say_where_they_are(value: Any, message: str) -> None:
    problem = find_problem(value)
    assert problem is not None
    assert problem.startswith(message)
    assert "\x00" not in problem, "the message never repeats the character it refuses"


def test_nesting_is_limited() -> None:
    assert find_problem(nested(MAX_JSON_DEPTH)) is None
    problem = find_problem(nested(MAX_JSON_DEPTH + 1))
    assert problem is not None
    assert f"nested more than {MAX_JSON_DEPTH} levels deep" in problem
    assert find_problem(nested(3), max_depth=3) is None
    assert find_problem(nested(4), max_depth=3, name="settings") is not None
    assert find_problem([[[[]]]], max_depth=3) is not None


def test_very_deep_values_are_refused_without_recursing() -> None:
    # Built with a loop: a literal this deep could not even be compiled.
    problem = find_problem(nested(200_000))
    assert problem is not None
    assert "nested more than" in problem
    assert len(problem) < 200, "a long path is cut short in the message"


def test_a_long_coordinate_list_is_cheap() -> None:
    ring = [[-1.86 + index * 1e-6, 51.42] for index in range(200_000)]
    started = time.perf_counter()
    assert find_problem({"type": "Polygon", "coordinates": [ring]}) is None
    assert time.perf_counter() - started < 2.0


def test_max_depth_must_be_positive() -> None:
    with pytest.raises(AssertionError):
        find_problem({}, max_depth=0)
