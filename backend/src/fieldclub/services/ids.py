"""Public ids: the short codes that appear in URLs, such as `/f/7K3QXM`.

Six characters of Crockford base32. The alphabet has no I, L, O or U, so a
code can be read aloud or copied by hand without confusing 1 with I or 0 with
O. Six characters give about a billion codes.
"""

from __future__ import annotations

import secrets
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Mapped, Session

from fieldclub.errors import AppError

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 6
MAX_ATTEMPTS = 12

# What people type when they misread a character.
_ALIASES = str.maketrans({"O": "0", "I": "1", "L": "1"})

assert len(ALPHABET) == 32, "Crockford base32 has 32 symbols"
assert len(set(ALPHABET)) == 32, "the alphabet repeats a symbol"


class IdGenerationError(AppError):
    code = "id_generation_failed"
    message = "Couldn't allocate a new id. Please try again."


class HasPublicId(Protocol):
    public_id: Mapped[str]


def generate() -> str:
    """A random public id. Not checked for uniqueness."""
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalise(text: str) -> str | None:
    """Tidy a public id someone typed, or `None` if it can't be one.

    Upper-cases it, drops spaces and hyphens, and reads O as 0 and I or L as 1.
    """
    candidate = text.strip().replace("-", "").replace(" ", "").upper().translate(_ALIASES)
    if len(candidate) != LENGTH or any(char not in ALPHABET for char in candidate):
        return None
    return candidate


def new_public_id(db: Session, model: type[HasPublicId]) -> str:
    """A public id that no row of `model` has yet.

    The unique constraint on `public_id` is the real guarantee. Checking first
    just makes a clash something this function absorbs, where otherwise the
    caller's insert would fail.
    """
    for _ in range(MAX_ATTEMPTS):
        candidate = generate()
        taken = db.scalar(select(model.public_id).where(model.public_id == candidate).limit(1))
        if taken is None:
            return candidate
    raise IdGenerationError()
