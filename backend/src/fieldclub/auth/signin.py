"""Finding or creating the person behind a sign-in, and starting their session.

Every way of signing in ends here. For a provider:

1. An identity already known by provider and subject signs in its account.
2. Otherwise, if the provider asserts a verified email, and an account has
   that same address verified, the new identity is linked to that account.
   An unverified address never links, and Facebook's never counts as
   verified (`EMAIL_TRUSTED_FROM`).
3. Otherwise a new account is made with a generated handle and the
   provider's name and picture. It has no age band or accepted terms, so the
   welcome step still applies. The address goes on the account only when it is
   verified and nobody else has it, so that nobody can claim an address they
   haven't proved and later receive its sign-in links.

Deleted and banned accounts can't sign in, by provider or by link.

Addresses are stored as CITEXT, so the database matches them with Postgres
`lower()`, which under the server's collation folds a few non-ASCII capitals
to ASCII letters: `İvan@` matches `ivan@`. Those are different mailboxes, so
an address found that way counts as the same address only when the two differ
in nothing but the case of ASCII letters (`same_address`). Otherwise the link
is refused, or the provider identity gets an account of its own.

Services flush and never commit. The router commits.
"""

from __future__ import annotations

import logging
import string
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.auth import accounts, sessions
from fieldclub.auth.failures import AccountDeletedError, EmailUnavailableError
from fieldclub.auth.handles import constraint_name, is_unique_violation
from fieldclub.auth.oauth import ProviderIdentity
from fieldclub.errors import BannedError
from fieldclub.models import AuthIdentity, User
from fieldclub.vocab import SignInProvider

logger = logging.getLogger(__name__)

# Providers whose "this address is verified" is believed. Facebook asserts no
# such thing. Microsoft's adapter only reports an address verified when the
# token carries the domain-owner flag.
EMAIL_TRUSTED_FROM = frozenset(
    {SignInProvider.GOOGLE, SignInProvider.APPLE, SignInProvider.MICROSOFT, SignInProvider.OSM}
)

IDENTITY_CONSTRAINT = "uq_auth_identities_provider_subject"
EMAIL_CONSTRAINT = "uq_users_email"
# Tries at the identity insert. A second try only happens when another request
# signed the same person in, or took the same new address, at the same moment.
_ATTEMPTS = 2

_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def check_can_sign_in(user: User) -> None:
    if user.is_deleted:
        raise AccountDeletedError()
    if user.is_banned:
        raise BannedError()


def same_address(first: str, second: str) -> bool:
    """Whether two addresses are one mailbox: equal but for the case of ASCII letters."""
    return first.translate(_ASCII_LOWER) == second.translate(_ASCII_LOWER)


def _verified_email(identity: ProviderIdentity) -> str | None:
    if identity.email and identity.email_verified and identity.provider in EMAIL_TRUSTED_FROM:
        return identity.email
    return None


def _find_by_identity(db: Session, identity: ProviderIdentity) -> tuple[AuthIdentity, User] | None:
    row = db.execute(
        select(AuthIdentity, User)
        .join(User, User.id == AuthIdentity.user_id)
        .where(AuthIdentity.provider == identity.provider.value, AuthIdentity.subject == identity.subject)
    ).first()
    return None if row is None else (row[0], row[1])


def _find_by_email(db: Session, email: str) -> User | None:
    """The account whose address the database matches with `email`. Check it with `same_address`."""
    return db.scalars(select(User).where(User.email == email)).one_or_none()


def _holds(user: User, email: str) -> bool:
    assert user.email is not None, f"user {user.id} was found by an address it doesn't have"
    return same_address(user.email, email)


def _is_retryable(exc: IntegrityError) -> bool:
    """Another request made the same identity, or took the same address, a moment ago."""
    return is_unique_violation(exc, IDENTITY_CONSTRAINT) or is_unique_violation(exc, EMAIL_CONSTRAINT)


def user_for_identity(db: Session, identity: ProviderIdentity, *, now: datetime | None = None) -> User:
    """The account this provider identity signs in to, made if need be. The caller commits."""
    now = now or datetime.now(UTC)
    for attempt in range(_ATTEMPTS):
        found = _find_by_identity(db, identity)
        if found is not None:
            known, user = found
            check_can_sign_in(user)
            known.email = identity.email
            db.flush()
            return user
        try:
            with db.begin_nested():
                return _link_or_create(db, identity, now)
        except IntegrityError as exc:
            if attempt + 1 == _ATTEMPTS or not _is_retryable(exc):
                raise
            logger.info(
                "A %s sign-in met %s from another request; looking again",
                identity.provider.value,
                constraint_name(exc),
            )
    raise AssertionError("unreachable: the last attempt returns or raises")


def _link_or_create(db: Session, identity: ProviderIdentity, now: datetime) -> User:
    verified = _verified_email(identity)
    holder = _find_by_email(db, verified) if verified else None
    if verified and holder is not None and holder.email_verified_at is not None and _holds(holder, verified):
        check_can_sign_in(holder)
        user = holder
        logger.info("Linking a %s identity to user %s by verified email", identity.provider.value, user.id)
    else:
        # An address someone else holds, verified or not, stays theirs, and so
        # does one the database would confuse with theirs.
        email = verified if verified and holder is None else None
        user = accounts.create_user(
            db,
            display_name=identity.display_name,
            email=email,
            email_verified_at=now if email else None,
            avatar_url=identity.avatar_url,
        )
    db.add(
        AuthIdentity(
            user_id=user.id, provider=identity.provider.value, subject=identity.subject, email=identity.email
        )
    )
    db.flush()
    return user


def user_for_email(db: Session, email: str, *, now: datetime | None = None) -> User:
    """The account a proven address signs in to, made if need be. The caller commits.

    Following the link proves the address, so an account that held it
    unverified has it verified now. An account the database matches but that
    holds a different mailbox (`same_address`) is refused, and none is made.
    """
    now = now or datetime.now(UTC)
    user = _find_by_email(db, email)
    if user is None:
        try:
            with db.begin_nested():
                return accounts.create_user(db, email=email, email_verified_at=now)
        except IntegrityError as exc:
            # Another link for the same new address was followed at the same moment.
            user = _find_by_email(db, email) if is_unique_violation(exc, EMAIL_CONSTRAINT) else None
            if user is None:
                raise
            # The constraint's name only: the database's message holds the address.
            logger.info("Account for an emailed link was created by another request (%s)", EMAIL_CONSTRAINT)
    if not _holds(user, email):
        raise EmailUnavailableError()
    check_can_sign_in(user)
    if user.email_verified_at is None:
        user.email_verified_at = now
        db.flush()
    return user


def begin_session(
    db: Session,
    user: User,
    *,
    previous_token: str | None,
    user_agent: str | None,
    ip: str | None,
    previous_hash: str | None = None,
) -> str:
    """A new session for `user`, ending whatever session the browser presented. The caller commits.

    A session token that existed before sign-in is never carried over, so a
    token planted in someone's browser can't become a signed-in one.
    `previous_hash` is the hash of a session the browser presented earlier in
    the same sign-in, for a callback that arrives without the session cookie.
    """
    check_can_sign_in(user)
    sessions.revoke_session(db, previous_token)
    if previous_hash:
        sessions.revoke_session_by_hash(db, previous_hash)
    return sessions.create_session(db, user, user_agent=user_agent, ip=ip)
