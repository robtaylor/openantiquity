"""Names: the generated handle an account starts with, and the rules for choosing your own.

A handle is the unique name in `/u/<handle>`. A display name is free text shown
beside contributions. Both are checked here so that every way of setting one
(the welcome sheet, a provider's profile, the development login) applies the
same rules.
"""

from __future__ import annotations

import random
import re
import secrets
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.db import is_unique_violation
from fieldclub.errors import ValidationFailedError

if TYPE_CHECKING:
    from fieldclub.models import User

ADJECTIVES = tuple(
    """
    Amber Ancient Bold Bracken Chalky Curious Dappled Dusty Early Flinty Frosty Gentle Golden Grassy
    Heathery Hidden Hollow Keen Lofty Lonely Lost Lowland Merry Misty Mossy Ochre Patient Peaty Quiet
    Rolling Russet Silent Silver Steady Sunken Upland Wandering Weathered Winding Windy
    """.split()
)

NOUNS = tuple(
    """
    Antler Ard Bailey Barrow Beaker Broch Brooch Cairn Causeway Cist Crannog Cursus Ditch Dolmen Drove
    Dyke Earthwork Flint Fogou Furrow Handaxe Henge Hillfort Holloway Kiln Lynchet Menhir Midden Moat
    Monolith Motte Mound Palisade Posthole Quern Rampart Ridge Roundhouse Sherd Souterrain Spindle
    Terrace Torc Trackway Trowel Tumulus Tump Urn
    """.split()
)

HANDLE_MIN_LENGTH = 3
HANDLE_MAX_LENGTH = 30
HANDLE_PATTERN = re.compile(rf"[A-Za-z][A-Za-z0-9_-]{{{HANDLE_MIN_LENGTH - 1},{HANDLE_MAX_LENGTH - 1}}}")

# The unique constraint on `users.handle`. It, not a query, decides who gets a name.
HANDLE_CONSTRAINT = "uq_users_handle"

MAX_DISPLAY_NAME = 60

# What a deleted account is shown as, and how its handle starts. The handle
# becomes the prefix plus a random code, such as `Former-7K3QXM9A`, and nobody
# may choose a handle that starts the same way.
FORMER_MEMBER = "Former member"
FORMER_HANDLE_PREFIX = "Former-"

# Names that would read as official, or that clash with routes. The project's
# name is reserved in both forms it has had (Decision 0017).
RESERVED = frozenset(
    {
        "admin",
        "administrator",
        "anonymous",
        # GET /mod/users/eligible is the list, so it can't be a person's page.
        "eligible",
        "guest",
        "fieldclub",
        "me",
        "mod",
        "moderator",
        "openantiquity",
        "root",
        "staff",
        "system",
    }
)

# Display names that would read as official, or as an account that has gone.
# Compared with case, width, spaces and punctuation folded away, so "A d m i n"
# and "MODERATOR." are caught too. "me" and "eligible" only matter as routes, so
# they are fine here.
RESERVED_DISPLAY_NAMES = (RESERVED - {"me", "eligible"}) | {"formermember"}

# Unicode categories with no place in a name on one line: controls (line
# breaks and tabs among them), format characters (the bidirectional overrides
# and the zero-width characters), surrogates, private use, unassigned, and the
# line and paragraph separators.
_NAME_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class InvalidHandleError(ValidationFailedError):
    code = "invalid_handle"
    message = (
        f"A name is {HANDLE_MIN_LENGTH} to {HANDLE_MAX_LENGTH} characters, starts with a letter, "
        "and uses only letters, numbers, hyphens and underscores."
    )


class InvalidDisplayNameError(ValidationFailedError):
    code = "invalid_display_name"
    message = (
        f"A display name is 1 to {MAX_DISPLAY_NAME} characters on one line, with no invisible characters."
    )


def claim_handle(db: Session, user: User, handle: str | None = None) -> bool:
    """Save `user`, with `handle` if given, inside a savepoint. False if the handle is taken.

    The unique constraint decides who gets a name. Asking first and writing
    second would let two people take the same one at the same moment. A new
    user is added, and a new handle assigned, inside the savepoint:
    begin_nested() flushes what is already pending before the savepoint
    exists, and a failure there would take the caller's whole transaction with
    it. Any other integrity error is raised.
    """
    try:
        with db.begin_nested():
            if handle is not None:
                user.handle = handle
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        if not is_unique_violation(exc, HANDLE_CONSTRAINT):
            raise
        return False
    return True


def generate_handle(rng: random.Random | None = None, *, digits: int = 2) -> str:
    """A name such as `QuietBarrow42`."""
    assert 1 <= digits <= 6, "a handle carries between one and six digits"
    rng = rng or secrets.SystemRandom()
    number = rng.randrange(10 ** (digits - 1), 10**digits)
    return f"{rng.choice(ADJECTIVES)}{rng.choice(NOUNS)}{number}"


def validate_handle(handle: str) -> str:
    """Check a handle someone chose. Returns it stripped of surrounding space."""
    handle = handle.strip()
    if not HANDLE_PATTERN.fullmatch(handle):
        raise InvalidHandleError()
    if handle.lower() in RESERVED or handle.lower().startswith(FORMER_HANDLE_PREFIX.lower()):
        raise InvalidHandleError("That name is reserved. Please choose another.")
    return handle


def _folded(name: str) -> str:
    """A name reduced to its letters and digits, for comparing with the reserved list."""
    compatible = unicodedata.normalize("NFKC", name).casefold()
    return "".join(char for char in compatible if char.isalnum())


def validate_display_name(name: str) -> str:
    """Check a display name. Returns it trimmed, with runs of spaces closed up.

    Refused: anything empty or over the limit, line breaks and other control
    characters, the invisible format characters that can reorder or hide text
    (bidirectional overrides, zero-width joiners and spaces), and names that
    would pass for staff or for a deleted account.
    """
    if any(unicodedata.category(char) in _NAME_FORBIDDEN_CATEGORIES for char in name):
        raise InvalidDisplayNameError()
    name = unicodedata.normalize("NFC", " ".join(name.split()))
    if not 1 <= len(name) <= MAX_DISPLAY_NAME:
        raise InvalidDisplayNameError()
    if _folded(name) in RESERVED_DISPLAY_NAMES:
        raise InvalidDisplayNameError("That name is reserved. Please choose another.")
    return name
