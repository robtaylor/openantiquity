"""Public ids: the short codes that appear in URLs, such as `/f/7K3QXM`.

Six characters of Crockford base32. The alphabet has no I, L, O or U, so a
code can be read aloud or copied by hand without confusing 1 with I or 0 with
O. Six characters give about a billion codes.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session

from fieldclub.db import constraint_name
from fieldclub.errors import AppError

logger = logging.getLogger(__name__)

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


def insert_with_public_id[T: HasPublicId](db: Session, build: Callable[[str], T], constraint: str) -> T:
    """Add and flush the row `build(public_id)` makes, with a public id no other row has.

    The unique constraint named `constraint` decides. Each attempt inserts
    inside a savepoint, so a clash costs only that attempt and another id is
    tried. Asking first and inserting second would let two requests take the
    same id at the same moment. Any other integrity error is raised.
    """
    for _ in range(MAX_ATTEMPTS):
        row = build(generate())
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != constraint:
                raise
            logger.info("public id %s was taken, trying another", row.public_id)
            continue
        return row
    raise IdGenerationError()
