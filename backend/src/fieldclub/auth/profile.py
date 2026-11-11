"""Changing your own details."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from fieldclub.auth.handles import claim_handle, validate_display_name, validate_handle
from fieldclub.errors import ConflictError, ValidationFailedError
from fieldclub.models import User
from fieldclub.schemas import text

MAX_BIO = 1000
MAX_SETTINGS_BYTES = 8192
# Settings are a few flat groups of preferences. Anything deeper is not ours.
MAX_SETTINGS_DEPTH = 6

# Marks an argument that was left out, as opposed to one set to None.
UNSET: Any = object()


class HandleTakenError(ConflictError):
    code = "handle_taken"
    message = "Someone already has that name."


def update_profile(
    db: Session,
    user: User,
    *,
    handle: str = UNSET,
    display_name: str = UNSET,
    bio: str | None = UNSET,
    settings: dict[str, Any] = UNSET,
    avatar_url: None = UNSET,
) -> User:
    """Change the fields that were passed. The caller commits.

    `avatar_url` can only be cleared: passing None removes the picture a
    sign-in provider gave.

    `settings` is merged into what is stored, one top-level key at a time. A
    key set to `None` is removed.

    Everything is checked before anything is changed, so a refused update
    leaves the user exactly as they were.
    """
    changes: dict[str, Any] = {}
    if avatar_url is not UNSET:
        assert avatar_url is None, "a picture can only be cleared"
        changes["avatar_url"] = None
    if display_name is not UNSET:
        changes["display_name"] = validate_display_name(display_name or "")
    if bio is not UNSET:
        bio = (bio or "").strip() or None
        if bio and len(bio) > MAX_BIO:
            raise ValidationFailedError(f"A bio is at most {MAX_BIO} characters.")
        if bio and text.has_unstorable_character(bio):
            raise ValidationFailedError("A bio can't contain control characters.")
        changes["bio"] = bio
    if settings is not UNSET:
        merged = dict(user.settings or {})
        for key, value in (settings or {}).items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        # Checked before anything is stored. Settings nested too deeply would
        # be accepted by the database and then fail to serialise on every
        # later read of the account.
        problem = text.find_problem(merged, max_depth=MAX_SETTINGS_DEPTH, name="settings")
        if problem is not None:
            raise ValidationFailedError(problem)
        try:
            size = len(json.dumps(merged, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError):
            raise ValidationFailedError("Settings must be plain JSON.") from None
        if size > MAX_SETTINGS_BYTES:
            raise ValidationFailedError("Those settings are too large to store.")
        changes["settings"] = merged
    if handle is not UNSET:
        handle = validate_handle(handle)
        if handle != user.handle:
            # A new account's display name may still be its generated handle.
            # Keep the two in step until the person chooses a display name.
            if "display_name" not in changes and user.display_name == user.handle:
                changes["display_name"] = handle
            _change_handle(db, user, handle)

    for name, value in changes.items():
        setattr(user, name, value)
    db.flush()
    return user


def _change_handle(db: Session, user: User, handle: str) -> None:
    """Take a new handle, or raise `HandleTakenError` and leave the old one in place."""
    if not claim_handle(db, user, handle):
        raise HandleTakenError()
