"""Finding, linking or creating the account behind a sign-in, without HTTP."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth import sessions, signin
from fieldclub.auth.failures import AccountDeletedError, EmailUnavailableError
from fieldclub.auth.oauth import ProviderIdentity
from fieldclub.errors import BannedError
from fieldclub.models import AuthIdentity, User
from fieldclub.vocab import SignInProvider
from tests.helpers import MakeUser, count

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def miss_once(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make `signin.<name>` find nothing the first time, as if another request hadn't committed yet."""
    real = getattr(signin, name)
    calls = 0

    def find_missing_once(*args: Any) -> Any:
        nonlocal calls
        calls += 1
        return None if calls == 1 else real(*args)

    monkeypatch.setattr(signin, name, find_missing_once)


def google(subject: str = "g-1", email: str | None = "ann@example.org", *, verified: bool = True, **extra):
    return ProviderIdentity(SignInProvider.GOOGLE, subject, email=email, email_verified=verified, **extra)


def test_a_new_identity_makes_a_new_account_that_has_not_been_welcomed(db: Session) -> None:
    user = signin.user_for_identity(
        db, google(display_name="Ann Barrow", avatar_url="https://x/a.png"), now=NOW
    )
    db.commit()
    assert user.display_name == "Ann Barrow"
    assert user.avatar_url == "https://x/a.png"
    assert user.email == "ann@example.org"
    assert user.email_verified_at == NOW
    assert user.age_band is None
    assert user.terms_accepted_at is None
    identity = db.scalars(select(AuthIdentity)).one()
    assert (identity.user_id, identity.provider, identity.subject) == (user.id, "google", "g-1")


def test_a_bad_display_name_falls_back_to_the_handle(db: Session) -> None:
    user = signin.user_for_identity(db, google(display_name="Admin"), now=NOW)
    assert user.display_name == user.handle


def test_a_known_identity_signs_in_its_account_and_records_the_latest_address(db: Session) -> None:
    first = signin.user_for_identity(db, google(), now=NOW)
    db.commit()
    again = signin.user_for_identity(db, google(email="ann@new.example"), now=NOW)
    assert again.id == first.id
    assert db.scalars(select(AuthIdentity)).one().email == "ann@new.example"
    # The account's own address doesn't follow the provider's.
    assert again.email == "ann@example.org"


def test_a_verified_address_links_to_the_account_with_it_verified(db: Session, make_user: MakeUser) -> None:
    ann = make_user(email="ann@example.org", email_verified_at=VERIFIED_AT)
    user = signin.user_for_identity(db, google(email="ANN@example.org"), now=NOW)
    assert user.id == ann.id
    assert count(db, User) == 1


@pytest.mark.parametrize(
    "identity",
    [
        pytest.param(google(verified=False), id="unverified"),
        pytest.param(
            ProviderIdentity(SignInProvider.FACEBOOK, "f", email="ann@example.org", email_verified=True),
            id="facebook-claims-verified",
        ),
    ],
)
def test_an_address_that_is_not_trusted_never_links(
    identity: ProviderIdentity, db: Session, make_user: MakeUser
) -> None:
    ann = make_user(email="ann@example.org", email_verified_at=VERIFIED_AT)
    user = signin.user_for_identity(db, identity, now=NOW)
    assert user.id != ann.id
    assert user.email is None
    assert user.email_verified_at is None


def test_an_unverified_address_is_not_put_on_a_new_account(db: Session) -> None:
    user = signin.user_for_identity(db, google(verified=False), now=NOW)
    assert user.email is None
    # It is still remembered on the identity, as the provider gave it.
    assert db.scalars(select(AuthIdentity)).one().email == "ann@example.org"


def test_a_banned_account_is_refused_by_identity_and_by_linked_address(
    db: Session, make_user: MakeUser
) -> None:
    banned = make_user(email="ann@example.org", email_verified_at=VERIFIED_AT, banned_at=VERIFIED_AT)
    with pytest.raises(BannedError):
        signin.user_for_identity(db, google(), now=NOW)
    db.rollback()
    db.add(AuthIdentity(user_id=banned.id, provider="osm", subject="o-1"))
    db.commit()
    with pytest.raises(BannedError):
        signin.user_for_identity(db, ProviderIdentity(SignInProvider.OSM, "o-1"), now=NOW)


def test_a_deleted_account_is_refused(db: Session, make_user: MakeUser) -> None:
    gone = make_user(deleted_at=VERIFIED_AT)
    db.add(AuthIdentity(user_id=gone.id, provider="osm", subject="o-1"))
    db.commit()
    with pytest.raises(AccountDeletedError):
        signin.user_for_identity(db, ProviderIdentity(SignInProvider.OSM, "o-1"), now=NOW)


def test_an_identity_made_by_a_concurrent_sign_in_is_found_not_duplicated(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two callbacks for the same new person at once: the second finds the first's identity."""
    winner = signin.user_for_identity(db, google(), now=NOW)
    db.commit()
    miss_once(monkeypatch, "_find_by_identity")
    user = signin.user_for_identity(db, google(), now=NOW)
    assert user.id == winner.id
    assert count(db, AuthIdentity) == 1


def test_an_emailed_address_finds_or_makes_the_account(db: Session, make_user: MakeUser) -> None:
    holder = make_user(email="held@example.org")
    assert holder.email_verified_at is None
    found = signin.user_for_email(db, "HELD@example.org", now=NOW)
    assert found.id == holder.id
    # Following the link proved the address.
    assert found.email_verified_at == NOW
    made = signin.user_for_email(db, "new@example.org", now=NOW)
    assert made.email == "new@example.org"
    assert made.email_verified_at == NOW
    assert made.age_band is None


def test_an_emailed_address_of_a_banned_or_deleted_account_is_refused(
    db: Session, make_user: MakeUser
) -> None:
    make_user(email="banned@example.org", banned_at=VERIFIED_AT)
    with pytest.raises(BannedError):
        signin.user_for_email(db, "banned@example.org", now=NOW)


# --------------------------------------------------------------------------
# Addresses that the database's case-insensitive match would confuse
# --------------------------------------------------------------------------

# U+0130 LATIN CAPITAL LETTER I WITH DOT ABOVE and U+212A KELVIN SIGN, which
# Postgres lower() folds to ASCII "i" and "k".
DOTTED_I = "\u0130van@example.org"
KELVIN = "\u212aate@example.org"


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("ann@example.org", "ann@example.org", True),
        ("Ann@Example.ORG", "ann@example.org", True),
        (DOTTED_I, "ivan@example.org", False),
        (KELVIN, "kate@example.org", False),
        ("\u00c4sa@example.org", "\u00e4sa@example.org", False),
        ("\u00e4sa@example.org", "\u00e4sa@example.org", True),
    ],
)
def test_two_addresses_are_the_same_only_when_they_differ_in_ascii_case(
    first: str, second: str, same: bool
) -> None:
    assert signin.same_address(first, second) is same
    assert signin.same_address(second, first) is same


@pytest.mark.parametrize(
    ("held", "proved"),
    [
        pytest.param("ivan@example.org", DOTTED_I, id="dotted-i-to-ascii"),
        pytest.param(DOTTED_I, "ivan@example.org", id="ascii-to-dotted-i"),
    ],
)
def test_an_emailed_address_never_signs_in_to_an_account_it_only_folds_to(
    held: str, proved: str, db: Session, make_user: MakeUser
) -> None:
    make_user(email=held, email_verified_at=VERIFIED_AT)
    with pytest.raises(EmailUnavailableError):
        signin.user_for_email(db, proved, now=NOW)
    assert count(db, User) == 1


@pytest.mark.parametrize("asserted", [DOTTED_I, KELVIN])
def test_a_provider_address_never_links_to_an_account_it_only_folds_to(
    asserted: str, db: Session, make_user: MakeUser
) -> None:
    victim = make_user(
        email=asserted.replace("\u0130", "i").replace("\u212a", "k"), email_verified_at=VERIFIED_AT
    )
    user = signin.user_for_identity(db, google(email=asserted), now=NOW)
    assert user.id != victim.id
    # The database would call the address taken, so the new account has none.
    assert user.email is None


def test_an_address_taken_by_a_concurrent_sign_in_links_instead_of_failing(
    db: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Two providers make an account for the same new verified address at once."""
    winner = signin.user_for_identity(db, google(), now=NOW)
    db.commit()
    miss_once(monkeypatch, "_find_by_email")
    apple = ProviderIdentity(SignInProvider.APPLE, "a-1", email="ann@example.org", email_verified=True)
    with caplog.at_level(logging.INFO, logger="fieldclub"):
        user = signin.user_for_identity(db, apple, now=NOW)
    assert user.id == winner.id
    assert count(db, User) == 1
    assert count(db, AuthIdentity) == 2
    assert "ann@example.org" not in caplog.text


def test_an_account_made_by_a_concurrent_link_is_found_and_no_address_is_logged(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    holder = make_user(email="ann@example.org", email_verified_at=VERIFIED_AT)
    miss_once(monkeypatch, "_find_by_email")
    with caplog.at_level(logging.INFO, logger="fieldclub"):
        user = signin.user_for_email(db, "ann@example.org", now=NOW)
    assert user.id == holder.id
    assert "created by another request" in caplog.text
    assert "ann@example.org" not in caplog.text


def test_begin_session_ends_the_presented_session(db: Session, make_user: MakeUser) -> None:
    old_user, new_user = make_user(), make_user()
    old = sessions.create_session(db, old_user)
    db.commit()
    token = signin.begin_session(db, new_user, previous_token=old, user_agent="ua", ip="203.0.113.5")
    db.commit()
    assert token != old
    assert sessions.resolve_session(db, old) is None
    resolved = sessions.resolve_session(db, token)
    assert resolved is not None
    assert resolved.user.id == new_user.id


def test_begin_session_refuses_a_banned_account(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(BannedError):
        signin.begin_session(
            db, make_user(banned_at=VERIFIED_AT), previous_token=None, user_agent=None, ip=None
        )
