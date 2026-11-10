"""The emailed one-time sign-in link, for people who use none of the providers.

`POST /auth/email/start` makes a link for any well-formed address and sends
it. It never looks the address up, so it does the same work and gives the
same answer whether or not an account has that address: nobody can use it to
learn who is a member. Following the link proves the address, and
`POST /auth/email/verify` then signs in to the account that has it, or makes
one.

Only the SHA-256 of the token is stored. A link lasts fifteen minutes and
works once: it is spent by one conditional `UPDATE`, so two clicks at the
same moment can't both sign in. Unknown, spent and expired links all fail
with the same `link_invalid`.

The token travels in the link's fragment (`#token=`), which browsers never
send to a server, so it stays out of access logs and `Referer` headers. The
app reads it and posts it to `/auth/email/verify`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update
from sqlalchemy.orm import Session

from fieldclub.auth import signin
from fieldclub.auth.failures import LinkInvalidError
from fieldclub.auth.mailer import Message
from fieldclub.auth.providers import register_provider
from fieldclub.auth.tokens import MAX_TOKEN_LENGTH, hash_token, new_token
from fieldclub.config import Settings
from fieldclub.models import MagicLink, User
from fieldclub.vocab import SignInProvider

LINK_LIFETIME = timedelta(minutes=15)
# The app's page that reads the token from the fragment and posts it.
LINK_PAGE = "/signin/email"

register_provider(SignInProvider.EMAIL, lambda settings: settings.mail_backend is not None)


def create_link(db: Session, email: str, *, now: datetime | None = None) -> str:
    """Store a new link for `email` and return its token. The caller commits, then sends."""
    now = now or datetime.now(UTC)
    token = new_token()
    db.add(MagicLink(email=email, token_hash=hash_token(token), expires_at=now + LINK_LIFETIME))
    db.flush()
    return token


def link_message(settings: Settings, email: str, token: str, next_path: str) -> Message:
    query = f"?{urlencode({'next': next_path})}" if next_path != "/" else ""
    url = f"{settings.public_url.rstrip('/')}{LINK_PAGE}{query}#token={token}"
    minutes = int(LINK_LIFETIME.total_seconds() // 60)
    body = (
        "Here is your link to sign in to Field Club:\n\n"
        f"{url}\n\n"
        f"It works once, for the next {minutes} minutes. If you didn't ask for it, ignore this email "
        "and nothing will happen.\n"
    )
    return Message(to=email, subject="Your Field Club sign-in link", body=body)


def redeem(db: Session, token: str | None, *, now: datetime | None = None) -> User:
    """Spend a link and return the account it signs in to. The caller commits."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise LinkInvalidError()
    now = now or datetime.now(UTC)
    spent = db.execute(
        update(MagicLink)
        .where(
            MagicLink.token_hash == hash_token(token),
            MagicLink.used_at.is_(None),
            MagicLink.expires_at > now,
        )
        .values(used_at=now)
        .returning(MagicLink.id, MagicLink.email)
    ).first()
    if spent is None:
        raise LinkInvalidError()
    user = signin.user_for_email(db, spent.email, now=now)
    db.execute(update(MagicLink).where(MagicLink.id == spent.id).values(user_id=user.id))
    return user
