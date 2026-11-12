"""Names: the generated handle an account starts with, and the rules for choosing your own.

A handle is the unique name in `/u/<handle>`. A display name is free text shown
beside contributions. Both are checked here so that every way of setting one
(the welcome sheet, a provider's profile, the development login) applies the
same rules.

Nobody may pass for the project, its staff or a deleted account. Both kinds
of name are compared by their `skeleton`: case, width, spaces, hyphens and
underscores folded away, letters from other alphabets that look like Latin
ones (a Cyrillic a, a Greek o) and digits that pass for letters (`0`, `1`)
read as the Latin letter. A name whose skeleton holds either of the
project's names is refused (`Open-Antiquity`, `OpenAntiquityTeam`), and so is
one that is a staff word with nothing but a generic word or a number beside
it (`Admin-Team`, `Staff_Account`, `Moderator2`), while names that merely
contain one (`Badminton`, `Staffordshire`) are fine.

A handle someone gives up, by changing it or deleting their account, is
held back from everyone else for `HANDLE_COOLING_OFF` (`released_handles`),
so old `@mentions` of it and links to `/u/<handle>` don't pass to a stranger
at once. Whoever gave it up may take it back.
"""

from __future__ import annotations

import random
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.db import is_unique_violation
from fieldclub.errors import ConflictError, ValidationFailedError
from fieldclub.models import ReleasedHandle

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
# Compared by skeleton, so "A d m i n", "MODERATOR." and "Admin" written with
# a Cyrillic A are caught too. "me" and "eligible" only matter as routes, so
# they are fine here.
RESERVED_DISPLAY_NAMES = (RESERVED - {"me", "eligible"}) | {"formermember"}

# The project's names: refused anywhere in a name.
PROJECT_NAMES = ("openantiquity", "fieldclub")
# Words that read as staff, and what may stand beside one in a name that still
# reads as staff. Other words beside them make an ordinary name.
STAFF_WORDS = ("administrator", "admin", "moderator", "mod", "staff", "system", "root", "official")
STAFF_AFFIXES = frozenset(
    {"", "s", "team", "account", "official", "support", "help", "desk", "the", "real", "uk", "main", "head",
     "chief", "office", "openantiquity", "fieldclub"}
)  # fmt: skip

# How long a handle someone gave up is held back from everyone else.
HANDLE_COOLING_OFF = timedelta(days=365)

# Letters from other alphabets that are drawn like Latin ones, and digits used
# as letters, each read as the Latin letter it passes for. Lower case only:
# `skeleton` casefolds first.
_LOOKALIKES = str.maketrans(
    {
        # Cyrillic
        "\u0430": "a", "\u0432": "b", "\u0435": "e", "\u0451": "e", "\u043a": "k", "\u043c": "m",
        "\u043d": "h", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0442": "t", "\u0443": "y",
        "\u0445": "x", "\u0455": "s", "\u0456": "i", "\u0457": "i", "\u0458": "j", "\u0501": "d",
        "\u04cf": "i", "\u051b": "q", "\u051d": "w", "\u0491": "r",
        # Greek
        "\u03b1": "a", "\u03b2": "b", "\u03b5": "e", "\u03b7": "n", "\u03b9": "i", "\u03ba": "k",
        "\u03bd": "v", "\u03bf": "o", "\u03c1": "p", "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
        "\u03b6": "z", "\u03bc": "u",
        # Latin letters drawn like others, and digits as letters
        "\u0131": "i", "l": "i", "1": "i", "|": "i", "0": "o", "3": "e", "4": "a", "5": "s", "7": "t",
        "\u0251": "a", "\u0269": "i", "\u0261": "g",
    }
)  # fmt: skip

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


def skeleton(name: str) -> str:
    """What a name looks like, for comparing it with the reserved names. See the module docstring.

    Marks over letters are dropped (`é` reads as `e`), and `rn` reads as `m`
    and `vv` as `w`, as they do at a glance.
    """
    compatible = unicodedata.normalize("NFKC", name).casefold().translate(_LOOKALIKES)
    bare = "".join(
        char for char in unicodedata.normalize("NFKD", compatible) if not unicodedata.combining(char)
    )
    letters = "".join(char for char in bare if char.isalnum())
    return letters.replace("rn", "m").replace("vv", "w")


_RESERVED_SKELETONS = frozenset(skeleton(word) for word in RESERVED)
_PROJECT_SKELETONS = tuple(skeleton(word) for word in PROJECT_NAMES)
_STAFF_SKELETONS = tuple(skeleton(word) for word in STAFF_WORDS)
_AFFIX_SKELETONS = frozenset(skeleton(word) for word in STAFF_AFFIXES)
_RESERVED_DISPLAY_SKELETONS = frozenset(skeleton(word) for word in RESERVED_DISPLAY_NAMES)


def _reads_as_staff(shape: str) -> bool:
    for word in _STAFF_SKELETONS:
        for rest in (shape.removeprefix(word), shape.removesuffix(word)):
            if rest != shape and rest in _AFFIX_SKELETONS:
                return True
    return False


def passes_for_the_project(name: str) -> bool:
    """Whether a handle or display name would pass for the project or its staff.

    A number at the end is set aside first, so `Admin1` is `Admin`, not `Admini`.
    """
    shapes = {skeleton(name), skeleton(name.rstrip("0123456789 _-."))}
    return any(
        any(project in shape for project in _PROJECT_SKELETONS) or _reads_as_staff(shape) for shape in shapes
    )


def validate_handle(handle: str) -> str:
    """Check a handle someone chose. Returns it stripped of surrounding space."""
    handle = handle.strip()
    if not HANDLE_PATTERN.fullmatch(handle):
        raise InvalidHandleError()
    shape = skeleton(handle)
    former = handle.lower().startswith(FORMER_HANDLE_PREFIX.lower()) or shape == skeleton(FORMER_MEMBER)
    if former or shape in _RESERVED_SKELETONS or passes_for_the_project(handle):
        raise InvalidHandleError("That name is reserved. Please choose another.")
    return handle


class HandleHeldBackError(ConflictError):
    code = "handle_held_back"
    message = "Someone gave up that name recently, so it isn't free yet. Please choose another."


def held_back(db: Session, handle: str, user: User | None, *, now: datetime | None = None) -> bool:
    """Whether `handle` was given up by someone other than `user` within `HANDLE_COOLING_OFF`."""
    since = (now or datetime.now(UTC)) - HANDLE_COOLING_OFF
    owner = db.execute(
        select(ReleasedHandle.user_id).where(
            ReleasedHandle.handle == handle, ReleasedHandle.released_at > since
        )
    ).first()
    return owner is not None and (user is None or user.id is None or owner.user_id != user.id)


def check_not_held_back(db: Session, handle: str, user: User | None) -> None:
    if held_back(db, handle, user):
        raise HandleHeldBackError()


def release_handle(db: Session, handle: str, user: User | None, *, now: datetime | None = None) -> None:
    """Hold back a handle `user` gave up. None for a deleted account's, which nobody takes back."""
    released_at = now or datetime.now(UTC)
    owner = user.id if user is not None else None
    db.execute(
        insert(ReleasedHandle)
        .values(handle=handle, released_at=released_at, user_id=owner)
        .on_conflict_do_update(
            index_elements=[ReleasedHandle.handle], set_={"released_at": released_at, "user_id": owner}
        )
    )


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
    shape = skeleton(name)
    if shape in _RESERVED_DISPLAY_SKELETONS or passes_for_the_project(name):
        raise InvalidDisplayNameError("That name is reserved. Please choose another.")
    return name
