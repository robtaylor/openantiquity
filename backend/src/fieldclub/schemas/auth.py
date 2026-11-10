"""Shapes for the auth endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from fieldclub.auth import onboarding
from fieldclub.auth.handles import HANDLE_MAX_LENGTH, HANDLE_MIN_LENGTH, MAX_DISPLAY_NAME
from fieldclub.auth.profile import MAX_BIO
from fieldclub.models import User
from fieldclub.schemas.common import ApiModel, RequestModel
from fieldclub.vocab import AgeBand, Role


class Me(ApiModel):
    """The signed-in user, as they see themselves.

    Unlike `PublicUser`, this shows the stored name and picture, because it
    only ever goes to the account's owner.
    """

    handle: str
    display_name: str
    role: str
    avatar_url: str | None = None
    email: str | None
    email_verified: bool
    reputation: float
    bio: str | None
    settings: dict[str, Any]
    created_at: datetime
    age_band: AgeBand | None
    terms_accepted_at: datetime | None
    # True until the welcome sheet has recorded an age band and the terms.
    needs_welcome: bool

    @classmethod
    def from_user(cls, user: User) -> Me:
        return cls(
            handle=user.handle,
            display_name=user.display_name,
            role=user.role,
            avatar_url=user.avatar_url,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            reputation=user.reputation,
            bio=user.bio,
            settings=user.settings or {},
            created_at=user.created_at,
            age_band=AgeBand(user.age_band) if user.age_band is not None else None,
            terms_accepted_at=user.terms_accepted_at,
            needs_welcome=not onboarding.has_welcomed(user),
        )


class MeUpdate(RequestModel):
    """Fields to change. Leave a field out to keep it as it is."""

    handle: str | None = Field(default=None, min_length=HANDLE_MIN_LENGTH, max_length=HANDLE_MAX_LENGTH)
    display_name: str | None = Field(default=None, min_length=1, max_length=MAX_DISPLAY_NAME)
    # An empty string clears the bio.
    bio: str | None = Field(default=None, max_length=MAX_BIO)
    # Merged into the stored settings one top-level key at a time. A key set
    # to null is removed.
    settings: dict[str, Any] | None = None


class Welcome(RequestModel):
    """The welcome sheet. Leave out handle or display name to keep the one you have."""

    handle: str | None = Field(default=None, min_length=HANDLE_MIN_LENGTH, max_length=HANDLE_MAX_LENGTH)
    display_name: str | None = Field(default=None, min_length=1, max_length=MAX_DISPLAY_NAME)
    age_band: AgeBand
    # Must be true. Anything else is refused with `terms_not_accepted`.
    accept_terms: bool


class HandleSuggestion(ApiModel):
    """A generated handle that is free at the moment, such as `QuietBarrow42`."""

    handle: str


class DevLogin(RequestModel):
    """Who to sign in as. Development and test only."""

    handle: str = Field(min_length=HANDLE_MIN_LENGTH, max_length=HANDLE_MAX_LENGTH)
    # Given, the user ends up with this role. Left out, a new user is a member
    # and an existing one keeps the role they have.
    role: Role | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=MAX_DISPLAY_NAME)
