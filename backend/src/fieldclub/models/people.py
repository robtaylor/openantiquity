"""People: users, how they sign in, their sessions and their reputation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from fieldclub.db import Base
from fieldclub.models.common import CreatedAt, IdPk, JsonDict, TimestampTz, enum_check, fk, json_column
from fieldclub.vocab import AgeBand, Role


class User(Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", Role), enum_check("age_band", AgeBand))

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    handle: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # Both are empty until the person completes the welcome sheet, and every
    # write route refuses them until then (Decision 0009). See
    # `auth.onboarding`.
    age_band: Mapped[str | None] = mapped_column(Text)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    role: Mapped[str] = mapped_column(Text, default=Role.MEMBER.value, server_default=Role.MEMBER.value)
    reputation: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    bio: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[JsonDict | None] = json_column()
    last_seen_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    banned_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    # Set when the person deleted their account. The row stays, stripped of
    # everything personal, so their contributions keep an author.
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampTz)

    @property
    def is_banned(self) -> bool:
        return self.banned_at is not None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active(self) -> bool:
        """False for a banned or deleted account, which counts as signed out wherever access is decided."""
        return not (self.is_banned or self.is_deleted)

    def has_id(self, user_id: int | None) -> bool:
        """Whether this is the user with `user_id`, such as a row's author.

        Two objects that have not been saved yet both have an id of None. That
        must never read as a match.
        """
        return self.id is not None and user_id is not None and self.id == user_id

    @property
    def shows_handle_only(self) -> bool:
        """Whether others see only the handle: true in the 16 to 17 band, and until a band is set."""
        return self.age_band != AgeBand.AGE_18_PLUS.value

    def __repr__(self) -> str:
        return f"<User {self.handle} ({self.role})>"


class AuthIdentity(Base):
    """A sign-in from an outside provider (Google, OpenStreetMap) tied to a user.

    `email` is the address the provider asserted, whether or not it verified
    it. Only a verified address may link an identity to an existing user.
    """

    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE", index=True)
    provider: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)


class UserSession(Base):
    """A browser session. Only the hash of the cookie's token is stored."""

    __tablename__ = "sessions"

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE", index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TimestampTz)
    last_used_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)


class MagicLink(Base):
    """A one-time sign-in link sent by email. Only the hash of its token is stored."""

    __tablename__ = "magic_links"

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    email: Mapped[str] = mapped_column(CITEXT, index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[int | None] = fk("users.id", ondelete="CASCADE")
    expires_at: Mapped[datetime] = mapped_column(TimestampTz)
    used_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    # The hash of the random value in the cookie of the browser that asked for the link.
    browser_hash: Mapped[str | None] = mapped_column(Text)


class ReputationEvent(Base):
    """One itemised award of points, so a person can see where each one came from."""

    __tablename__ = "reputation_events"

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE", index=True)
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    finding_id: Mapped[int | None] = fk("findings.id", ondelete="SET NULL", index=True)


__all__ = ["AuthIdentity", "MagicLink", "ReputationEvent", "User", "UserSession"]
