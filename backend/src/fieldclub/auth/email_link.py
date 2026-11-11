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

Asking for a link spends every earlier unspent link for the same address, so
only the newest one works.

A link is bound to the browser that asked for it. `/auth/email/start` sets the
`openantiquity_email_link` cookie, a random value whose hash is stored on the link,
and `/auth/email/verify` signs in straight away only when that cookie comes
back. Anywhere else, for example on another device, verify answers
`confirmation_required` with the address masked, spends nothing, and signs in
only when posted again with `confirm`. Without this, someone could ask for a
link to their own address, send it to a victim, and have the victim's browser
signed in to the attacker's account, where the victim's drafts would then be
saved (login CSRF). The app must show the masked address and let the person
choose; it must never confirm on their behalf.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from fieldclub.auth import signin
from fieldclub.auth.failures import LinkConfirmationRequiredError, LinkInvalidError
from fieldclub.auth.mailer import Message
from fieldclub.auth.providers import register_provider
from fieldclub.auth.tokens import hash_presented, hash_token, new_token
from fieldclub.config import Settings
from fieldclub.models import MagicLink, User
from fieldclub.vocab import SignInProvider

LINK_LIFETIME = timedelta(minutes=15)
# The app's page that reads the token from the fragment and posts it.
LINK_PAGE = "/signin/email"
# The cookie that binds a link to the browser that asked for it, sent only to verify.
LINK_COOKIE = "openantiquity_email_link"
VERIFY_PATH = "/api/v1/auth/email/verify"

register_provider(SignInProvider.EMAIL, lambda settings: settings.mail_backend is not None)


def rate_key(email: str) -> str:
    """The mailbox an address delivers to, for its rate limit: casefolded, without any `+tag`."""
    local, _, domain = email.rpartition("@")
    return f"{local.split('+', 1)[0]}@{domain}".casefold()


def masked(email: str) -> str:
    """An address shown to whoever holds a link: its first letter and its domain."""
    local, _, domain = email.rpartition("@")
    # No address in the messages: they could reach a log.
    assert local, "a stored link always has a local part"
    assert domain, "a stored link always has a domain"
    return f"{local[0]}***@{domain}"


def create_link(db: Session, email: str, *, browser: str | None = None, now: datetime | None = None) -> str:
    """Store a new link for `email` and return its token. The caller commits, then sends.

    Earlier unspent links for the address are spent. `browser` is the value of
    the asking browser's link cookie.
    """
    now = now or datetime.now(UTC)
    db.execute(
        update(MagicLink).where(MagicLink.email == email, MagicLink.used_at.is_(None)).values(used_at=now)
    )
    token = new_token()
    db.add(
        MagicLink(
            email=email,
            token_hash=hash_token(token),
            browser_hash=hash_presented(browser),
            expires_at=now + LINK_LIFETIME,
        )
    )
    db.flush()
    return token


def link_message(settings: Settings, email: str, token: str, next_path: str) -> Message:
    query = f"?{urlencode({'next': next_path})}" if next_path != "/" else ""
    url = f"{settings.public_url.rstrip('/')}{LINK_PAGE}{query}#token={token}"
    minutes = int(LINK_LIFETIME.total_seconds() // 60)
    body = (
        "Here is your link to sign in to Open Antiquity:\n\n"
        f"{url}\n\n"
        f"It works once, for the next {minutes} minutes. If you didn't ask for it, ignore this email "
        "and nothing will happen.\n"
    )
    return Message(to=email, subject="Your Open Antiquity sign-in link", body=body, link=url)


def _from_this_browser(link: MagicLink, browser: str | None) -> bool:
    return link.browser_hash is not None and link.browser_hash == hash_presented(browser)


def redeem(
    db: Session,
    token: str | None,
    *,
    browser: str | None = None,
    confirmed: bool = False,
    now: datetime | None = None,
) -> User:
    """Spend a link and return the account it signs in to. The caller commits.

    `browser` is the link cookie the request carried. A link from another
    browser is spent only when `confirmed`, and otherwise raises
    `LinkConfirmationRequiredError` with the masked address.
    """
    token_hash = hash_presented(token)
    if token_hash is None:
        raise LinkInvalidError()
    now = now or datetime.now(UTC)
    live = (
        MagicLink.token_hash == token_hash,
        MagicLink.used_at.is_(None),
        MagicLink.expires_at > now,
    )
    link = db.scalars(select(MagicLink).where(*live)).one_or_none()
    if link is None:
        raise LinkInvalidError()
    if not confirmed and not _from_this_browser(link, browser):
        raise LinkConfirmationRequiredError(details={"email": masked(link.email)})
    # Conditional, so two clicks at the same moment can't both sign in.
    spent = db.execute(
        update(MagicLink).where(MagicLink.id == link.id, *live).values(used_at=now).returning(MagicLink.id)
    ).first()
    if spent is None:
        raise LinkInvalidError()
    user = signin.user_for_email(db, link.email, now=now)
    link.user_id = user.id
    db.flush()
    return user
