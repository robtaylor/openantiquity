"""Accounts: creating one at first sign-in, the development login, and deleting one.

Every account belongs to someone who signed in. There are no guest accounts.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fieldclub.auth import sessions
from fieldclub.auth.handles import (
    FORMER_HANDLE_PREFIX,
    FORMER_MEMBER,
    InvalidDisplayNameError,
    claim_handle,
    generate_handle,
    validate_display_name,
    validate_handle,
)
from fieldclub.errors import AppError
from fieldclub.models import AuthIdentity, Follow, MagicLink, Notification, User
from fieldclub.services import ids, investigations, media
from fieldclub.vocab import Role

logger = logging.getLogger(__name__)

# The first tries use two digits, like QuietBarrow42. If the short names are
# running out, later tries use four.
SHORT_ATTEMPTS = 4
MAX_ATTEMPTS = 10


class HandleGenerationError(AppError):
    code = "handle_generation_failed"
    message = "We couldn't find a free name. Please try again."


def _digits_for(attempt: int) -> int:
    return 2 if attempt < SHORT_ATTEMPTS else 4


def _usable_display_name(name: str | None) -> str | None:
    """A provider's name for someone, if it passes our rules. Otherwise None."""
    if not name:
        return None
    try:
        return validate_display_name(name)
    except InvalidDisplayNameError:
        return None


def create_user(
    db: Session,
    *,
    display_name: str | None = None,
    email: str | None = None,
    email_verified_at: datetime | None = None,
    avatar_url: str | None = None,
    role: Role | str = Role.MEMBER,
    rng: random.Random | None = None,
) -> User:
    """Create an account with a generated handle such as `QuietBarrow42`. The caller commits.

    This is what a first sign-in calls. `display_name` is the name the
    provider gave. When there is none, or it breaks the display-name rules,
    the handle is used. The welcome sheet lets the person change both.

    A handle that is already taken is retried inside a savepoint, so a
    collision never disturbs the caller's transaction. Any other integrity
    error, such as an email address already in use, is the caller's to handle.
    """
    role = Role(role)
    shown = _usable_display_name(display_name)
    for attempt in range(MAX_ATTEMPTS):
        handle = generate_handle(rng, digits=_digits_for(attempt))
        user = User(
            handle=handle,
            display_name=shown or handle,
            email=email,
            email_verified_at=email_verified_at,
            avatar_url=avatar_url,
            role=role.value,
        )
        if claim_handle(db, user):
            return user
        logger.info("Generated handle %s is taken, trying another", handle)
    raise HandleGenerationError()


def suggest_handle(db: Session, *, rng: random.Random | None = None) -> str:
    """A generated handle that nobody has right now, for the welcome sheet to offer.

    Only a suggestion. Someone else may take it before it is saved, and the
    unique constraint settles that when it is.
    """
    for attempt in range(MAX_ATTEMPTS):
        handle = generate_handle(rng, digits=_digits_for(attempt))
        if db.scalar(select(User.id).where(User.handle == handle)) is None:
            return handle
    raise HandleGenerationError()


def dev_user(
    db: Session, handle: str, *, role: Role | str | None = None, display_name: str | None = None
) -> User:
    """The test user called `handle`, created if need be. The caller commits.

    For `POST /auth/dev-login` only. When `role` is given the user ends up
    with it, whether they existed or not. Left out, a new user is a member
    and an existing one keeps the role they have.
    """
    handle = validate_handle(handle)
    wanted = Role(role) if role is not None else None
    shown = validate_display_name(display_name) if display_name is not None else None

    def find() -> User | None:
        return db.scalars(select(User).where(User.handle == handle)).one_or_none()

    user = find()
    if user is None:
        new_user = User(handle=handle, display_name=shown or handle, role=(wanted or Role.MEMBER).value)
        if claim_handle(db, new_user):
            user = new_user
        else:
            # Another request created the same user a moment ago.
            user = find()
            assert user is not None, f"{handle} broke the unique constraint but can't be found"
    assert not user.is_deleted, "validate_handle refuses the handles deleted accounts are given"
    if wanted is not None and user.role != wanted.value:
        user.role = wanted.value
    if shown is not None and user.display_name != shown:
        user.display_name = shown
    db.flush()
    return user


def delete_account(db: Session, user: User, *, now: datetime | None = None) -> None:
    """Delete an account at its owner's request. The caller commits.

    Personal data goes: the email address, the provider identities, the
    sessions and any unused sign-in links, the bio, settings and picture,
    the person's follows and notifications, which were only ever for them to
    read, and every photo they uploaded, file and row. Their private
    investigations go too, and their memberships and invitations elsewhere
    (`investigations.forget_account`).

    The public record of their contributions stays, because it was published
    under an open licence and other people's work builds on it (Decisions
    0002 and 0009): findings, second looks, evidence, votes, comments,
    mentions, square surveys and the items they added to investigations. So
    does the record moderation keeps: reports they made or that are about
    them, and the moderation log. The row stays, marked deleted and stripped
    of everything personal, so all of these keep an author, credited to
    "Former member" from now on, and the old handle no longer leads to them.

    Role, reputation and its itemised events are kept, because they set the
    weight of what the person contributed. Nobody else can read the events.
    """
    assert user.id is not None, "the user must be flushed before it can be deleted"
    assert not user.is_deleted, f"user {user.id} is already deleted"
    now = now or datetime.now(UTC)

    db.execute(delete(AuthIdentity).where(AuthIdentity.user_id == user.id))
    sessions.revoke_all_sessions(db, user)
    links = MagicLink.user_id == user.id
    if user.email is not None:
        links = links | (MagicLink.email == user.email)
    db.execute(delete(MagicLink).where(links))
    # Without the follows, events would go on writing notifications nobody can read.
    db.execute(delete(Follow).where(Follow.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    # Private investigations go; shared ones pass to an editor (see `forget_account`).
    investigations.forget_account(db, user)
    # A photo is personal data: its file and row go, and the evidence it was on stays without it.
    media.forget_account(db, user)

    user.email = None
    user.email_verified_at = None
    user.avatar_url = None
    user.bio = None
    user.settings = None
    user.display_name = FORMER_MEMBER
    user.deleted_at = now
    _anonymise_handle(db, user)
    db.flush()


def _anonymise_handle(db: Session, user: User) -> None:
    """Swap the handle for one that says nothing about who it was."""
    for _ in range(MAX_ATTEMPTS):
        candidate = f"{FORMER_HANDLE_PREFIX}{ids.generate()}{ids.generate()[:2]}"
        if claim_handle(db, user, candidate):
            return
    raise HandleGenerationError()
