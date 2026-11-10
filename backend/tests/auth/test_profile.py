"""Changing your own details."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from fieldclub.auth.handles import InvalidDisplayNameError, InvalidHandleError
from fieldclub.auth.profile import MAX_SETTINGS_DEPTH, HandleTakenError, update_profile
from fieldclub.errors import ValidationFailedError
from tests.helpers import MakeUser, nested


def test_nothing_passed_changes_nothing(db: Session, make_user: MakeUser) -> None:
    user = make_user(handle="QuietBarrow42", bio="Hello")
    update_profile(db, user)
    assert (user.handle, user.display_name, user.bio) == ("QuietBarrow42", "QuietBarrow42", "Hello")


def test_display_name_and_bio(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    update_profile(db, user, display_name="  Rob T  ", bio="  Walks the Ridgeway.  ")
    db.commit()
    assert (user.display_name, user.bio) == ("Rob T", "Walks the Ridgeway.")
    update_profile(db, user, bio="")
    assert user.bio is None
    update_profile(db, user, bio=None)
    assert user.bio is None


@pytest.mark.parametrize("fields", [{"display_name": "   "}, {"display_name": "x" * 61}, {"bio": "x" * 1001}])
def test_limits(db: Session, make_user: MakeUser, fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        update_profile(db, make_user(), **fields)


def test_changing_handle_carries_an_untouched_display_name_along(db: Session, make_user: MakeUser) -> None:
    fresh = make_user(handle="QuietBarrow42")
    update_profile(db, fresh, handle="RidgewayRob")
    db.commit()
    assert (fresh.handle, fresh.display_name) == ("RidgewayRob", "RidgewayRob")

    named = make_user(handle="MossyCairn7", display_name="Dr Mossy")
    update_profile(db, named, handle="MossyCairn8")
    assert (named.handle, named.display_name) == ("MossyCairn8", "Dr Mossy")


def test_handle_must_be_valid(db: Session, make_user: MakeUser) -> None:
    user = make_user(handle="QuietBarrow42")
    with pytest.raises(InvalidHandleError):
        update_profile(db, user, handle="no spaces allowed")
    with pytest.raises(InvalidHandleError):
        update_profile(db, user, handle="admin")
    assert user.handle == "QuietBarrow42"


def test_a_taken_handle_is_a_conflict_and_leaves_the_user_alone(db: Session, make_user: MakeUser) -> None:
    make_user(handle="RidgewayRob")
    user = make_user(handle="QuietBarrow42")
    with pytest.raises(HandleTakenError) as caught:
        update_profile(db, user, handle="ridgewayrob", bio="New bio")
    assert caught.value.status_code == 409
    assert caught.value.code == "handle_taken"
    db.commit()
    db.refresh(user)
    assert user.handle == "QuietBarrow42"
    assert user.bio is None, "a refused update changes nothing"


def test_changing_only_the_case_of_your_own_handle_is_allowed(db: Session, make_user: MakeUser) -> None:
    user = make_user(handle="quietbarrow42")
    update_profile(db, user, handle="QuietBarrow42")
    db.commit()
    db.refresh(user)
    assert user.handle == "QuietBarrow42"


def test_settings_merge_one_key_at_a_time(db: Session, make_user: MakeUser) -> None:
    user = make_user(settings={"units": "metric", "layer": "composite"})
    update_profile(db, user, settings={"layer": "slope", "sun": {"azimuth": 315}})
    db.commit()
    db.refresh(user)
    assert user.settings == {"units": "metric", "layer": "slope", "sun": {"azimuth": 315}}
    update_profile(db, user, settings={"units": None})
    db.commit()
    db.refresh(user)
    assert user.settings == {"layer": "slope", "sun": {"azimuth": 315}}


def test_settings_have_a_size_limit(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(ValidationFailedError, match="too large"):
        update_profile(db, make_user(), settings={"blob": "x" * 9000})


@pytest.mark.parametrize(
    "name", ["Moderator", "\u202egnp.exe", "a\u200bb", "line\nbreak", "nul\x00byte", "Former member"]
)
def test_display_names_follow_the_display_name_rules(db: Session, make_user: MakeUser, name: str) -> None:
    user = make_user(handle="QuietBarrow42")
    with pytest.raises(InvalidDisplayNameError):
        update_profile(db, user, display_name=name, bio="Not stored either")
    assert (user.display_name, user.bio) == ("QuietBarrow42", None)


def test_a_bio_may_have_line_breaks_but_no_control_characters(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    update_profile(db, user, bio="First line.\n\tSecond line.")
    db.commit()
    assert user.bio == "First line.\n\tSecond line."
    for bad in ("nul\x00byte", "bell\x07", "escape\x1b[31m"):
        with pytest.raises(ValidationFailedError, match="control characters"):
            update_profile(db, user, bio=bad)
    assert user.bio == "First line.\n\tSecond line."


def test_settings_may_nest_only_so_far(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    # The settings object is the first level, so a value may be one level shallower.
    update_profile(db, user, settings={"ok": nested(MAX_SETTINGS_DEPTH - 1)})
    db.commit()
    for depth in (MAX_SETTINGS_DEPTH, 300, 5000):
        with pytest.raises(ValidationFailedError, match="nested more than"):
            update_profile(db, user, settings={"deep": nested(depth)})
    db.refresh(user)
    assert list(user.settings or {}) == ["ok"], "a refused update stores nothing"


@pytest.mark.parametrize(
    "settings",
    [
        {"note": "nul\x00byte"},
        {"nul\x00key": 1},
        {"list": ["fine", {"inner": "bell\x07"}]},
        {"surrogate": "\ud800"},
    ],
)
def test_settings_refuse_text_the_database_cannot_store(
    db: Session, make_user: MakeUser, settings: dict[str, Any]
) -> None:
    with pytest.raises(ValidationFailedError, match="control character"):
        update_profile(db, make_user(), settings=settings)


def test_settings_must_be_plain_json(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(ValidationFailedError, match="plain JSON"):
        update_profile(db, make_user(), settings={"opacity": float("nan")})
    with pytest.raises(ValidationFailedError, match="plain JSON"):
        update_profile(db, make_user(), settings={"when": object()})
