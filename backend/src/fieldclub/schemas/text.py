"""Which characters, and how much nesting, text sent by people may have.

PostgreSQL can't store NUL in `text` or `jsonb`, and a lone surrogate can't be
encoded as UTF-8 at all. Either one, left unchecked, is a 500 from the database
driver. The other control characters have no place in anything a person
typed. Line breaks and tabs are allowed here, because notes and descriptions
have them. Single-line fields such as names apply stricter rules of their own
(see `fieldclub.auth.handles`).
"""

from __future__ import annotations

import re
from typing import Any

# C0 and C1 control characters except tab, line feed and carriage return, plus
# lone surrogates.
_UNSTORABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]")

# Deep enough for GeoJSON and any settings a client keeps. Far below the depth
# at which Pydantic refuses to serialise a value back out.
MAX_JSON_DEPTH = 32

# How much of a nested path an error message quotes.
_MAX_PATH_SHOWN = 60

_WALKED = (str, dict, list)


def has_unstorable_character(text: str) -> bool:
    """Whether `text` holds a control character or lone surrogate that must not be stored."""
    return _UNSTORABLE.search(text) is not None


# Where an item sits: its parent's link, whether the key is a list index, and the key.
_Link = tuple["_Link | None", bool, Any]


def _spell(link: _Link | None) -> str:
    """The path to an item, such as `outline.coordinates[0][3]`, from its chain of links."""
    parts: list[str] = []
    while link is not None:
        link, is_index, key = link
        parts.append(f"[{key}]" if is_index else f".{key}")
    path = "".join(reversed(parts))
    return path[1:] if path.startswith(".") else path


def find_problem(value: Any, *, max_depth: int = MAX_JSON_DEPTH, name: str = "The request") -> str | None:
    """Why a JSON value can't be accepted, in a sentence, or None when it can.

    Looks at every string and every object key, however deeply nested, and
    refuses nesting deeper than `max_depth`. A value that isn't a dict, list
    or string is left to the caller's own validation.
    """
    assert max_depth >= 1, "max_depth must be at least 1"

    def where(link: _Link | None) -> str:
        # Only spelled out for an error, so a clean body builds no path strings.
        path = _spell(link)
        return (path if len(path) <= _MAX_PATH_SHOWN else f"{path[:_MAX_PATH_SHOWN]}...") or name

    # A stack, not recursion, so a hostile body can't exhaust the interpreter's.
    pending: list[tuple[Any, int, _Link | None]] = [(value, 0, None)] if isinstance(value, _WALKED) else []
    while pending:
        item, depth, link = pending.pop()
        if isinstance(item, str):
            if has_unstorable_character(item):
                return f"{where(link)} contains a control character, which can't be stored."
            continue
        if depth >= max_depth:
            return f"{where(link)} is nested more than {max_depth} levels deep."
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str) and has_unstorable_character(key):
                    return f"{where(link)} has a key containing a control character, which can't be stored."
                if isinstance(child, _WALKED):
                    pending.append((child, depth + 1, (link, False, key)))
        else:
            assert isinstance(item, list), f"only strings, dicts and lists are walked, not {type(item)}"
            # Numbers, booleans and nulls need no look, which keeps long
            # coordinate lists cheap.
            pending.extend(
                (child, depth + 1, (link, True, index))
                for index, child in enumerate(item)
                if isinstance(child, _WALKED)
            )
    return None
