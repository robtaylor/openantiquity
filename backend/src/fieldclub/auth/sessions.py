"""Browser sessions.

A session is an opaque random token. The browser holds the token in a cookie
and the database holds only its hash. Sessions slide: each use, at most once an
hour, pushes the expiry out again, so an account in regular use never signs
itself out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fieldclub.auth.tokens import hash_ip, hash_presented, hash_token, new_token
from fieldclub.config import get_settings
from fieldclub.models import User, UserSession

# How stale `last_used_at` may get before a request writes to the session row.
TOUCH_INTERVAL = timedelta(hours=1)

MAX_USER_AGENT_LENGTH = 400


@dataclass(frozen=True)
class ResolvedSession:
    user: User
    session: UserSession
    # True when this call extended the session. The cookie should be re-sent
    # so the browser's copy lives as long as the server's.
    refreshed: bool


def _now() -> datetime:
    return datetime.now(UTC)


def session_lifetime() -> timedelta:
    return timedelta(days=get_settings().session_days)


def create_session(
    db: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
    now: datetime | None = None,
) -> str:
    """Start a session for a user and return its token. The caller commits.

    The token is returned once and never stored. Put it in the cookie with
    `cookies.set_session_cookie`.
    """
    assert user.id is not None, "the user must be flushed before a session is created"
    assert not user.is_deleted, f"user {user.id} deleted their account and can't be signed in"
    now = now or _now()
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + session_lifetime(),
            last_used_at=now,
            user_agent=user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None,
            ip_hash=hash_ip(ip) if ip else None,
        )
    )
    user.last_seen_at = now
    db.flush()
    return token


def resolve_session(db: Session, token: str | None, *, now: datetime | None = None) -> ResolvedSession | None:
    """The session and user behind a token, or `None` if it is unknown or expired.

    A deleted account is signed out for good, so its sessions resolve to
    nothing. Banned users are still returned. Deciding what a banned user may
    do is the caller's job. When the session is extended the change is
    flushed, and the caller commits.
    """
    token_hash = hash_presented(token)
    if token_hash is None:
        return None
    now = now or _now()
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_hash)
    ).first()
    if row is None:
        return None
    session, user = row
    if session.expires_at <= now or user.is_deleted:
        return None
    refreshed = session.last_used_at is None or now - session.last_used_at >= TOUCH_INTERVAL
    if refreshed:
        session.last_used_at = now
        session.expires_at = now + session_lifetime()
        user.last_seen_at = now
        db.flush()
    return ResolvedSession(user=user, session=session, refreshed=refreshed)


def revoke_session(db: Session, token: str | None) -> bool:
    """End the session behind a token. Returns whether there was one. The caller commits."""
    token_hash = hash_presented(token)
    return token_hash is not None and revoke_session_by_hash(db, token_hash)


def revoke_session_by_hash(db: Session, token_hash: str) -> bool:
    """End the session whose token has this hash. Returns whether there was one. The caller commits."""
    result = db.execute(delete(UserSession).where(UserSession.token_hash == token_hash))
    return bool(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


def revoke_all_sessions(db: Session, user: User) -> int:
    """End every session a user has, for example when they are banned. The caller commits."""
    result = db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    return int(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


def purge_expired(db: Session, *, now: datetime | None = None) -> int:
    """Delete sessions past their expiry. The caller commits."""
    result = db.execute(delete(UserSession).where(UserSession.expires_at <= (now or _now())))
    return int(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue]
