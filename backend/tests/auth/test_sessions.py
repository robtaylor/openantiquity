"""Sessions: created, resolved, extended with use, expired and revoked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import time_machine
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth import sessions
from fieldclub.auth.tokens import hash_token
from fieldclub.models import UserSession
from tests.helpers import MakeUser, count

START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def test_create_session_stores_only_the_hash(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    with time_machine.travel(START, tick=False):
        token = sessions.create_session(db, user, user_agent="Firefox", ip="203.0.113.5")
        db.commit()
    row = db.scalars(select(UserSession)).one()
    assert row.token_hash == hash_token(token)
    assert token not in (row.token_hash, row.user_agent, row.ip_hash)
    assert row.user_id == user.id
    assert row.expires_at == START + timedelta(days=365)
    assert row.last_used_at == START
    assert row.user_agent == "Firefox"
    assert row.ip_hash is not None
    assert "203.0.113.5" not in row.ip_hash
    assert user.last_seen_at == START


def test_long_user_agents_are_cut_short(db: Session, make_user: MakeUser) -> None:
    sessions.create_session(db, make_user(), user_agent="x" * 5000)
    db.commit()
    stored = db.scalars(select(UserSession.user_agent)).one()
    assert stored is not None
    assert len(stored) == sessions.MAX_USER_AGENT_LENGTH


def test_resolve_returns_the_user(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    token = sessions.create_session(db, user)
    db.commit()
    resolved = sessions.resolve_session(db, token)
    assert resolved is not None
    assert resolved.user.id == user.id
    assert resolved.refreshed is False


def test_unknown_missing_and_oversized_tokens_resolve_to_nothing(db: Session, make_user: MakeUser) -> None:
    sessions.create_session(db, make_user())
    db.commit()
    assert sessions.resolve_session(db, None) is None
    assert sessions.resolve_session(db, "") is None
    assert sessions.resolve_session(db, "not-a-real-token") is None
    assert sessions.resolve_session(db, "x" * 10_000) is None


def test_the_stored_hash_is_not_a_usable_token(db: Session, make_user: MakeUser) -> None:
    token = sessions.create_session(db, make_user())
    db.commit()
    assert sessions.resolve_session(db, hash_token(token)) is None


def test_sessions_expire(db: Session, make_user: MakeUser) -> None:
    with time_machine.travel(START, tick=False):
        token = sessions.create_session(db, make_user())
        db.commit()
    with time_machine.travel(START + timedelta(days=364, hours=23), tick=False):
        assert sessions.resolve_session(db, token) is not None
        db.rollback()
    with time_machine.travel(START + timedelta(days=365, seconds=1), tick=False):
        assert sessions.resolve_session(db, token) is None


def test_use_extends_a_session_at_most_once_an_hour(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    with time_machine.travel(START, tick=False):
        token = sessions.create_session(db, user)
        db.commit()

    with time_machine.travel(START + timedelta(minutes=59), tick=False):
        resolved = sessions.resolve_session(db, token)
        assert resolved is not None
        assert resolved.refreshed is False
        assert resolved.session.expires_at == START + timedelta(days=365)

    later = START + timedelta(days=200)
    with time_machine.travel(later, tick=False):
        resolved = sessions.resolve_session(db, token)
        assert resolved is not None
        assert resolved.refreshed is True
        db.commit()
    row = db.scalars(select(UserSession)).one()
    assert row.last_used_at == later
    assert row.expires_at == later + timedelta(days=365)
    db.refresh(user)
    assert user.last_seen_at == later

    # Still alive long after the original expiry, because it was used.
    with time_machine.travel(START + timedelta(days=500), tick=False):
        assert sessions.resolve_session(db, token) is not None


def test_revoke_ends_one_session(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    phone = sessions.create_session(db, user)
    laptop = sessions.create_session(db, user)
    db.commit()
    assert sessions.revoke_session(db, phone) is True
    db.commit()
    assert sessions.resolve_session(db, phone) is None
    assert sessions.resolve_session(db, laptop) is not None
    assert sessions.revoke_session(db, phone) is False
    assert sessions.revoke_session(db, None) is False
    assert sessions.revoke_session(db, "x" * 10_000) is False


def test_revoke_all_ends_every_session_of_one_user(db: Session, make_user: MakeUser) -> None:
    user, other = make_user(), make_user()
    sessions.create_session(db, user)
    sessions.create_session(db, user)
    kept = sessions.create_session(db, other)
    db.commit()
    assert sessions.revoke_all_sessions(db, user) == 2
    db.commit()
    assert count(db, UserSession) == 1
    assert sessions.resolve_session(db, kept) is not None


def test_purge_removes_only_expired_sessions(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    with time_machine.travel(START, tick=False):
        sessions.create_session(db, user)
    with time_machine.travel(START + timedelta(days=300), tick=False):
        fresh = sessions.create_session(db, user)
    db.commit()
    assert sessions.purge_expired(db, now=START + timedelta(days=400)) == 1
    db.commit()
    assert count(db, UserSession) == 1
    assert sessions.resolve_session(db, fresh, now=START + timedelta(days=400)) is not None


def test_a_deleted_account_is_signed_out_even_if_a_session_row_survives(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user()
    token = sessions.create_session(db, user)
    db.commit()
    assert sessions.resolve_session(db, token) is not None
    # Deleting an account removes its sessions. This is the case where one
    # slipped through, for instance a sign-in racing the deletion.
    user.deleted_at = START
    db.commit()
    assert sessions.resolve_session(db, token) is None
    assert count(db, UserSession) == 1


def test_banned_users_still_resolve_so_callers_can_tell_them_why(db: Session, make_user: MakeUser) -> None:
    user = make_user(banned_at=START)
    token = sessions.create_session(db, user)
    db.commit()
    resolved = sessions.resolve_session(db, token)
    assert resolved is not None
    assert resolved.user.is_banned
