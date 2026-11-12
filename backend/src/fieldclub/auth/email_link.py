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

Asking for a link again from the same browser spends the links that browser
asked for before for that address, so only its newest works. A link someone
else asked for, from another browser, is left alone: a stranger asking for
your address can't spend the link you are about to click.

A link is bound to the browser that asked for it. `/auth/email/start` sets the
`openantiquity_email_link` cookie, a random value whose hash is stored on the link,
and `/auth/email/verify` signs in straight away only when that cookie comes
back. Anywhere else, for example on another device, verify answers
`confirmation_required` with the address masked, spends nothing, and signs in
only when posted again with the address the person types, which must be the
one the link was sent to (`email_mismatch` otherwise). Without this, someone
could ask for a link to their own address, send it to a victim, and have the
victim's browser signed in to the attacker's account, where the victim's
drafts would then be saved (login CSRF). A masked address alone isn't enough:
anyone can pick an address with the victim's first letter at the same big
domain. The victim types their own address, which isn't the attacker's.

A browser that has signed in with a link for a mailbox is remembered for
it: verify sets `openantiquity_email_known`, holding a keyed hash of the
mailbox for each of the last `KNOWN_MAILBOXES_MAX` it signed in to. Asking
from such a browser spends a budget of its own rather than the one all
callers share, so strangers who use up that one from many addresses don't
leave the owner without a way in. Nobody can make the value without the
server's key and the mailbox.

The answer says whether this browser asked for the link (`asked_here`). When
it didn't, the app must not save drafts left in the browser without asking:
the person may be signed in to someone else's account however careful they were.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from fieldclub.auth import signin
from fieldclub.auth.failures import EmailMismatchError, LinkConfirmationRequiredError, LinkInvalidError
from fieldclub.auth.mailer import Message
from fieldclub.auth.providers import register_provider
from fieldclub.auth.tokens import hash_presented, hash_token, new_token
from fieldclub.config import Settings, get_settings
from fieldclub.models import MagicLink, User
from fieldclub.vocab import SignInProvider

LINK_LIFETIME = timedelta(minutes=15)
# The app's page that reads the token from the fragment and posts it.
LINK_PAGE = "/signin/email"
# The cookie that binds a link to the browser that asked for it, sent only to
# start, which spends the links this browser asked for before, and to verify.
LINK_COOKIE = "openantiquity_email_link"
LINK_COOKIE_PATH = "/api/v1/auth/email"
VERIFY_PATH = f"{LINK_COOKIE_PATH}/verify"
START_PATH = f"{LINK_COOKIE_PATH}/start"
# The cookie that says which mailboxes this browser has signed in to by link,
# sent to start and verify only.
KNOWN_COOKIE = "openantiquity_email_known"
KNOWN_LIFETIME = timedelta(days=365)
KNOWN_MAILBOXES_MAX = 4

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


def create_link(
    db: Session,
    email: str,
    *,
    browser: str | None = None,
    previous_browser: str | None = None,
    now: datetime | None = None,
) -> str:
    """Store a new link for `email` and return its token. The caller commits, then sends.

    `browser` is the value of the link cookie the asking browser is given.
    `previous_browser` is the one it presented, if any: the earlier unspent
    links it asked for for this address are spent. Nobody else's are.
    """
    now = now or datetime.now(UTC)
    previous = hash_presented(previous_browser)
    if previous is not None:
        db.execute(
            update(MagicLink)
            .where(MagicLink.email == email, MagicLink.browser_hash == previous, MagicLink.used_at.is_(None))
            .values(used_at=now)
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


def _same_address(link: MagicLink, typed: str) -> bool:
    return typed.strip().casefold() == link.email.casefold()


def _known_tag(email: str) -> str:
    """The keyed hash of `email`'s mailbox (`rate_key`) a browser that signed in to it keeps."""
    mailbox = rate_key(email).encode("utf-8")
    return hmac.new(get_settings().signing_key, b"email-known:" + mailbox, hashlib.sha256).hexdigest()


def known_here(cookie: str | None, email: str) -> bool:
    """Whether the `KNOWN_COOKIE` a browser sent says it has signed in to `email`'s mailbox by link."""
    if not cookie:
        return False
    tag = _known_tag(email)
    return any(hmac.compare_digest(tag, held) for held in cookie.split(".")[:KNOWN_MAILBOXES_MAX])


def remember_here(cookie: str | None, email: str) -> str:
    """The `KNOWN_COOKIE` value with `email`'s mailbox added, keeping the latest few."""
    tag = _known_tag(email)
    held = [value for value in (cookie or "").split(".") if len(value) == len(tag) and value != tag]
    return ".".join([tag, *held][:KNOWN_MAILBOXES_MAX])


@dataclass(frozen=True)
class Redeemed:
    user: User
    # True when the browser that asked for the link redeemed it.
    asked_here: bool
    # The address the link was sent to.
    email: str


def redeem(
    db: Session,
    token: str | None,
    *,
    browser: str | None = None,
    typed_email: str | None = None,
    now: datetime | None = None,
) -> Redeemed:
    """Spend a link and return the account it signs in to. The caller commits.

    `browser` is the link cookie the request carried. A link from another
    browser is spent only when `typed_email` is the address it was sent to.
    Without one it raises `LinkConfirmationRequiredError` with the masked
    address, and with another `EmailMismatchError`. Neither spends it.
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
    asked_here = _from_this_browser(link, browser)
    if not asked_here:
        if typed_email is None:
            raise LinkConfirmationRequiredError(details={"email": masked(link.email)})
        if not _same_address(link, typed_email):
            raise EmailMismatchError()
    # Conditional, so two clicks at the same moment can't both sign in.
    spent = db.execute(
        update(MagicLink).where(MagicLink.id == link.id, *live).values(used_at=now).returning(MagicLink.id)
    ).first()
    if spent is None:
        raise LinkInvalidError()
    user = signin.user_for_email(db, link.email, now=now)
    link.user_id = user.id
    db.flush()
    return Redeemed(user, asked_here, link.email)
