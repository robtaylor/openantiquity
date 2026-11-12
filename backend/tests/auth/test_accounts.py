"""Accounts: created at first sign-in, found for the development login, and deleted."""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.auth import accounts, sessions
from fieldclub.auth.accounts import (
    HandleGenerationError,
    create_user,
    delete_account,
    dev_user,
    suggest_handle,
)
from fieldclub.auth.handles import (
    HANDLE_CONSTRAINT,
    HANDLE_PATTERN,
    InvalidDisplayNameError,
    InvalidHandleError,
)
from fieldclub.db import is_unique_violation
from fieldclub.models import AuthIdentity, Follow, MagicLink, Notification, User, UserSession
from fieldclub.services import activity
from tests.helpers import MakeFinding, MakeUser, count

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# create_user
# --------------------------------------------------------------------------


def test_a_new_account_is_a_member_with_a_generated_handle(db: Session) -> None:
    user = create_user(db)
    db.commit()
    assert re.fullmatch(r"[A-Z][a-z]+[A-Z][a-z]+\d{2}", user.handle)
    assert user.display_name == user.handle
    assert user.role == "member"
    assert (user.email, user.email_verified_at, user.avatar_url, user.deleted_at) == (None, None, None, None)
    assert user.id is not None


def test_a_new_account_takes_what_the_provider_said(db: Session) -> None:
    user = create_user(
        db,
        display_name="  Rob   Taylor ",
        email="Rob@Example.org",
        email_verified_at=NOW,
    )
    db.commit()
    db.refresh(user)
    assert user.display_name == "Rob Taylor"
    assert (user.email, user.email_verified_at) == ("Rob@Example.org", NOW)
    assert user.avatar_url is None
    assert user.role == "member"
    assert user.handle != user.display_name


@pytest.mark.parametrize(
    "name", ["", "   ", "Moderator", "x" * 61, "line\nbreak", "\u202egnp.exe", "a\u200bb"]
)
def test_a_provider_name_that_breaks_the_rules_falls_back_to_the_handle(db: Session, name: str) -> None:
    user = create_user(db, display_name=name)
    assert user.display_name == user.handle


def test_there_is_no_guest_role(db: Session) -> None:
    with pytest.raises(ValueError, match="guest"):
        create_user(db, role="guest")


def test_a_taken_handle_is_retried(db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch) -> None:
    make_user(handle="QuietBarrow42")
    offered = iter(["QuietBarrow42", "quietbarrow42", "MossyCairn17"])
    monkeypatch.setattr(accounts, "generate_handle", lambda rng, digits: next(offered))
    before = make_user()

    user = create_user(db)
    db.commit()
    assert user.handle == "MossyCairn17"
    assert count(db, User) == 3
    # The collisions did not disturb anything else in the session.
    db.refresh(before)
    assert before.handle


def test_a_collision_does_not_roll_back_the_callers_work(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="QuietBarrow42")
    offered = iter(["QuietBarrow42", "WindyHenge88"])
    monkeypatch.setattr(accounts, "generate_handle", lambda rng, digits: next(offered))

    pending = User(handle="PendingUser", display_name="Pending")
    db.add(pending)
    db.flush()
    create_user(db)
    db.commit()
    assert set(db.scalars(select(User.handle))) == {"QuietBarrow42", "PendingUser", "WindyHenge88"}


def test_later_attempts_use_longer_numbers(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="Taken")
    asked: list[int] = []

    def fake(rng: random.Random | None, digits: int) -> str:
        asked.append(digits)
        return "Taken" if len(asked) <= accounts.SHORT_ATTEMPTS else "FlintyTrowel1234"

    monkeypatch.setattr(accounts, "generate_handle", fake)
    user = create_user(db)
    assert user.handle == "FlintyTrowel1234"
    assert asked == [2, 2, 2, 2, 4]


def test_gives_up_with_a_clear_error_when_every_handle_is_taken(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="Taken")
    monkeypatch.setattr(accounts, "generate_handle", lambda rng, digits: "Taken")
    with pytest.raises(HandleGenerationError) as caught:
        create_user(db)
    assert caught.value.code == "handle_generation_failed"
    db.rollback()
    assert count(db, User) == 1


def test_seeded_generation_is_repeatable(db: Session) -> None:
    first = create_user(db, rng=random.Random(11)).handle
    db.rollback()
    assert create_user(db, rng=random.Random(11)).handle == first


def test_many_accounts_all_get_distinct_handles(db: Session) -> None:
    handles = [create_user(db).handle for _ in range(300)]
    db.commit()
    assert len({handle.lower() for handle in handles}) == 300


def test_an_email_already_in_use_is_the_callers_to_handle(db: Session, make_user: MakeUser) -> None:
    make_user(email="taken@example.org")
    with pytest.raises(IntegrityError) as caught:
        create_user(db, email="TAKEN@example.org")
    db.rollback()
    assert not is_unique_violation(caught.value, HANDLE_CONSTRAINT)
    assert is_unique_violation(caught.value, "uq_users_email")
    assert count(db, User) == 1


# --------------------------------------------------------------------------
# suggest_handle
# --------------------------------------------------------------------------


def test_a_suggested_handle_is_valid_and_creates_nothing(db: Session) -> None:
    handle = suggest_handle(db)
    assert HANDLE_PATTERN.fullmatch(handle)
    assert re.fullmatch(r"[A-Z][a-z]+[A-Z][a-z]+\d{2}", handle)
    assert count(db, User) == 0


def test_a_suggestion_skips_handles_that_are_taken(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="QuietBarrow42")
    offered = iter(["quietbarrow42", "MossyCairn17"])
    monkeypatch.setattr(accounts, "generate_handle", lambda rng, digits: next(offered))
    assert suggest_handle(db) == "MossyCairn17"

    monkeypatch.setattr(accounts, "generate_handle", lambda rng, digits: "QuietBarrow42")
    with pytest.raises(HandleGenerationError):
        suggest_handle(db)


# --------------------------------------------------------------------------
# dev_user
# --------------------------------------------------------------------------


def test_dev_user_creates_a_named_member(db: Session) -> None:
    user = dev_user(db, "TestRob")
    db.commit()
    assert (user.handle, user.display_name, user.role) == ("TestRob", "TestRob", "member")
    assert count(db, User) == 1


def test_dev_user_finds_an_existing_user_whatever_the_case(db: Session, make_user: MakeUser) -> None:
    existing = make_user("expert", handle="DrTrowel", display_name="Dr Trowel")
    found = dev_user(db, "drtrowel")
    assert found.id == existing.id
    assert (found.role, found.display_name) == ("expert", "Dr Trowel"), "nothing changes unless asked"
    assert count(db, User) == 1


def test_dev_user_applies_a_role_and_display_name_when_given(db: Session, make_user: MakeUser) -> None:
    created = dev_user(db, "TestMod", role="moderator", display_name="Test Mod")
    assert (created.role, created.display_name) == ("moderator", "Test Mod")
    existing = make_user(handle="Climber")
    promoted = dev_user(db, "Climber", role="trusted")
    assert promoted.id == existing.id
    assert promoted.role == "trusted"


def test_dev_user_copes_when_two_requests_create_the_same_user_at_once(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other request's user exists, but this one looked a moment too early.
    existing = make_user(handle="TestRob")
    real_scalars = db.scalars
    looked: list[int] = []

    def scalars_that_miss_once(statement, *args, **kwargs):
        looked.append(1)
        if len(looked) == 1:
            return real_scalars(select(User).where(User.id == -1))
        return real_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalars", scalars_that_miss_once)
    pending = User(handle="PendingUser", display_name="Pending")
    db.add(pending)

    found = dev_user(db, "TestRob", role="trusted")
    db.commit()
    assert found.id == existing.id
    assert found.role == "trusted"
    assert len(looked) == 2
    monkeypatch.undo()
    assert set(db.scalars(select(User.handle))) == {"TestRob", "PendingUser"}, (
        "the clash cost the caller nothing"
    )


@pytest.mark.parametrize("handle", ["no spaces", "admin", "ab", "Former-7K3QXM9A"])
def test_dev_user_applies_the_handle_rules(db: Session, handle: str) -> None:
    with pytest.raises(InvalidHandleError):
        dev_user(db, handle)
    assert count(db, User) == 0


def test_dev_user_refuses_unknown_roles_and_bad_display_names(db: Session) -> None:
    with pytest.raises(ValueError, match="guest"):
        dev_user(db, "TestRob", role="guest")
    with pytest.raises(InvalidDisplayNameError):
        dev_user(db, "TestRob", display_name="Administrator")


# --------------------------------------------------------------------------
# delete_account
# --------------------------------------------------------------------------


def test_deleting_removes_what_identifies_the_person(db: Session, make_user: MakeUser) -> None:
    user = make_user(
        "trusted",
        handle="RidgewayRob",
        display_name="Rob Taylor",
        email="rob@example.org",
        email_verified_at=NOW,
        avatar_url="https://example.org/rob.png",
        bio="Walks the Ridgeway.",
        settings={"units": "metric"},
        reputation=62.5,
    )
    other = make_user(email="other@example.org")
    db.add_all(
        [
            AuthIdentity(user_id=user.id, provider="google", subject="123", email="rob@example.org"),
            AuthIdentity(user_id=user.id, provider="osm", subject="456"),
            AuthIdentity(user_id=other.id, provider="google", subject="789"),
            MagicLink(email="ROB@example.org", token_hash="a", expires_at=NOW),
            MagicLink(email="elsewhere@example.org", token_hash="b", user_id=user.id, expires_at=NOW),
            MagicLink(email="other@example.org", token_hash="c", user_id=other.id, expires_at=NOW),
        ]
    )
    phone = sessions.create_session(db, user)
    sessions.create_session(db, user)
    kept = sessions.create_session(db, other)
    db.commit()

    delete_account(db, user, now=NOW)
    db.commit()
    db.refresh(user)

    assert (user.email, user.email_verified_at, user.avatar_url, user.bio, user.settings) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert user.display_name == "Former member"
    assert re.fullmatch(r"Former-[0-9A-HJKMNP-TV-Z]{8}", user.handle)
    assert (user.deleted_at, user.is_deleted) == (NOW, True)
    assert (user.role, user.reputation) == ("trusted", 62.5), "these set the weight of what they contributed"

    assert db.scalars(select(AuthIdentity.user_id)).all() == [other.id]
    assert db.scalars(select(UserSession.user_id)).all() == [other.id]
    assert db.scalars(select(MagicLink.token_hash)).all() == ["c"]
    assert sessions.resolve_session(db, phone) is None
    assert sessions.resolve_session(db, kept) is not None


def test_contributions_stay_and_are_credited_to_former_member(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    user = make_user(handle="RidgewayRob")
    finding = make_finding(user)
    delete_account(db, user)
    db.commit()

    db.refresh(finding)
    author = db.get(User, finding.author_id)
    assert author is not None
    assert author.id == user.id
    assert author.display_name == "Former member"
    assert db.scalar(select(User.id).where(User.handle == "RidgewayRob")) is None, (
        "the old handle no longer leads to them"
    )


def test_a_deleted_account_follows_nothing_and_is_told_nothing(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    user, other = make_user(), make_user()
    finding = make_finding(other)
    db.add_all(
        [
            Follow(user_id=user.id, finding_id=finding.id),
            Follow(user_id=other.id, finding_id=finding.id),
            Notification(user_id=user.id, kind="tier_changed", finding_id=finding.id),
            Notification(user_id=other.id, kind="tier_changed", finding_id=finding.id),
        ]
    )
    db.commit()

    delete_account(db, user)
    db.commit()
    assert db.scalars(select(Follow.user_id)).all() == [other.id]
    assert db.scalars(select(Notification.user_id)).all() == [other.id]

    # Later events reach the people still following, and nobody else.
    activity.record(db, "comment_added", None, finding)
    db.commit()
    assert set(db.scalars(select(Notification.user_id))) == {other.id}


def test_the_email_and_the_handle_are_free_again(db: Session, make_user: MakeUser) -> None:
    user = make_user(handle="RidgewayRob", email="rob@example.org")
    delete_account(db, user)
    db.commit()
    again = make_user(handle="RidgewayRob", email="rob@example.org")
    assert again.id != user.id


def test_a_deleted_account_cannot_be_signed_in_or_deleted_twice(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    delete_account(db, user)
    db.commit()
    with pytest.raises(AssertionError, match="deleted their account"):
        sessions.create_session(db, user)
    with pytest.raises(AssertionError, match="already deleted"):
        delete_account(db, user)


def test_deleting_gives_up_cleanly_if_no_anonymous_handle_is_free(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="Former-AAAAAAAA")
    monkeypatch.setattr(accounts.ids, "generate", lambda: "AAAAAA")
    user = make_user(handle="RidgewayRob", email="rob@example.org")
    with pytest.raises(HandleGenerationError):
        delete_account(db, user)
    db.rollback()
    db.refresh(user)
    assert (user.handle, user.email, user.deleted_at) == ("RidgewayRob", "rob@example.org", None)


def test_a_clash_on_the_anonymous_handle_is_retried(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(handle="Former-AAAAAAAA")
    codes = iter(["AAAAAA", "AAxxxx", "BBBBBB", "BBxxxx"])
    monkeypatch.setattr(accounts.ids, "generate", lambda: next(codes))
    user = make_user(handle="RidgewayRob", email="rob@example.org")

    delete_account(db, user)
    db.commit()
    db.refresh(user)
    assert user.handle == "Former-BBBBBBBB"
    assert (user.email, user.display_name) == (None, "Former member"), "the retry lost nothing"
