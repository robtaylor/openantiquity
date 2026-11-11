"""Generated handles, and the rules for chosen handles and display names."""

from __future__ import annotations

import random
import re

import pytest

from fieldclub.auth.handles import (
    ADJECTIVES,
    HANDLE_PATTERN,
    NOUNS,
    InvalidDisplayNameError,
    InvalidHandleError,
    generate_handle,
    validate_display_name,
    validate_handle,
)


def test_generated_handles_look_like_quietbarrow42() -> None:
    rng = random.Random(1)
    for _ in range(500):
        handle = generate_handle(rng)
        match = re.fullmatch(r"([A-Z][a-z]+)([A-Z][a-z]+)(\d{2})", handle)
        assert match, handle
        assert match.group(1) in ADJECTIVES
        assert match.group(2) in NOUNS
        assert 10 <= int(match.group(3)) <= 99
        assert validate_handle(handle) == handle


def test_generation_is_repeatable_with_a_seeded_generator() -> None:
    assert generate_handle(random.Random(7)) == generate_handle(random.Random(7))
    assert len({generate_handle() for _ in range(50)}) > 40


def test_digits_can_be_widened() -> None:
    assert re.fullmatch(r"[A-Za-z]+\d{4}", generate_handle(random.Random(3), digits=4))


def test_word_lists_are_clean() -> None:
    for words in (ADJECTIVES, NOUNS):
        assert len(set(words)) == len(words)
        assert all(re.fullmatch(r"[A-Z][a-z]+", word) for word in words)
    assert len(ADJECTIVES) * len(NOUNS) * 90 > 150_000
    longest = max(map(len, ADJECTIVES)) + max(map(len, NOUNS)) + 4
    assert longest <= 30, "every generated handle must fit the handle rules"
    assert "Barrow" in NOUNS
    assert "Quiet" in ADJECTIVES


@pytest.mark.parametrize("handle", ["Rob", "QuietBarrow42", "mossy-cairn_7", "a" * 30, "  Padded  "])
def test_valid_handles(handle: str) -> None:
    assert validate_handle(handle) == handle.strip()
    assert HANDLE_PATTERN.fullmatch(handle.strip())


@pytest.mark.parametrize(
    "handle",
    [
        "",
        "ab",
        "a" * 31,
        "9lives",
        "-dash",
        "has space",
        "dot.name",
        "émile",
        "a/b",
        "admin",
        "Moderator",
        "ME",
        "line\nbreak",
        "nul\x00byte",
        # Deleted accounts are given handles that start like this.
        "Former-7K3QXM9A",
        "former-member",
    ],
)
def test_invalid_handles(handle: str) -> None:
    with pytest.raises(InvalidHandleError) as caught:
        validate_handle(handle)
    assert caught.value.status_code == 422
    assert caught.value.code == "invalid_handle"


def test_the_handle_pattern_does_not_let_a_trailing_newline_through() -> None:
    assert HANDLE_PATTERN.fullmatch("QuietBarrow42")
    assert not HANDLE_PATTERN.fullmatch("QuietBarrow42\n")


# --------------------------------------------------------------------------
# Display names
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("Rob", "Rob"),
        ("  Rob   Taylor  ", "Rob Taylor"),
        ("Dr Mossy O'Cairn-Smith", "Dr Mossy O'Cairn-Smith"),
        ("Siân Ní Bhraonáin", "Siân Ní Bhraonáin"),
        ("王小明", "王小明"),
        ("Digger 🌿", "Digger 🌿"),
        ("Rob\u00a0Taylor", "Rob Taylor"),
        # Decomposed e + combining acute is stored composed.
        ("Ame\u0301lie", "Am\u00e9lie"),
        ("x" * 60, "x" * 60),
        ("The Moderator's Friend", "The Moderator's Friend"),
        ("Me", "Me"),
    ],
)
def test_valid_display_names(given: str, stored: str) -> None:
    assert validate_display_name(given) == stored


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "x" * 61,
        "line\nbreak",
        "tab\there",
        "nul\x00byte",
        # Right-to-left override: shows as "exe.png" reversed.
        "\u202egnp.exe",
        "left\u2066isolate",
        # Zero-width space, joiner and no-break space.
        "a\u200bb",
        "a\u200db",
        "a\ufeffb",
        "soft\u00adhyphen",
        "line\u2028separator",
        "private\ue000use",
        "lone\ud800surrogate",
    ],
)
def test_display_names_refuse_invisible_and_control_characters(name: str) -> None:
    with pytest.raises(InvalidDisplayNameError) as caught:
        validate_display_name(name)
    assert caught.value.status_code == 422
    assert caught.value.code == "invalid_display_name"


@pytest.mark.parametrize(
    "name",
    [
        "Moderator",
        "moderator",
        "ADMIN",
        "A d m i n",
        "Admin.",
        "-= Staff =-",
        "System",
        "Root",
        "Mod",
        # Full-width letters fold to the plain ones.
        "\uff21\uff44\uff4d\uff49\uff4e",
        "Former member",
        "former-member",
        "Open Antiquity",
        "open-antiquity",
        "Field Club",
    ],
)
def test_display_names_cannot_pass_for_staff_or_a_deleted_account(name: str) -> None:
    with pytest.raises(InvalidDisplayNameError, match="reserved"):
        validate_display_name(name)
