"""The emailed one-time sign-in link, over HTTP and as a service."""

from __future__ import annotations

import logging
import re
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth import email_link
from fieldclub.auth.failures import EmailMismatchError, LinkConfirmationRequiredError, LinkInvalidError
from fieldclub.auth.mailer import LogMailer, MailNotSentError, Message, SmtpMailer, get_mailer
from fieldclub.auth.tokens import hash_token
from fieldclub.config import SESSION_COOKIE, get_settings
from fieldclub.errors import ConfigError
from fieldclub.main import create_app
from fieldclub.models import MagicLink, User, UserSession
from fieldclub.schemas.auth import EmailStarted
from tests.auth.fakes import PUBLIC_URL
from tests.helpers import ClientFor, MakeUser, count, envelope, error_code, settings

START = "/api/v1/auth/email/start"
VERIFY = "/api/v1/auth/email/verify"
VERIFIED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def mail_on(env: Callable[..., None]) -> None:
    env(MAIL_BACKEND="log", PUBLIC_URL=PUBLIC_URL)


@pytest.fixture
def browser(app: FastAPI, client_for: ClientFor, mail_on: None) -> TestClient:
    return client_for(app)


def token_from(message: Message) -> str:
    match = re.search(r"#token=([A-Za-z0-9_-]+)", message.body)
    assert match, message.body
    return match.group(1)


def caller_at(app: FastAPI, client_for: ClientFor, ip: str) -> TestClient:
    """A signed-out client calling from `ip`, for the rate-limit tests."""
    caller = client_for(app)
    caller.headers["X-Forwarded-For"] = ip
    return caller


def request_link(browser: TestClient, email: str, **body: Any) -> str:
    response = browser.post(START, json={"email": email, **body})
    assert response.status_code == 202, response.text
    return token_from(LogMailer.outbox[-1])


# --------------------------------------------------------------------------
# Asking for a link
# --------------------------------------------------------------------------


def test_a_link_is_emailed_and_only_its_hash_is_stored(browser: TestClient, db: Session) -> None:
    response = browser.post(START, json={"email": "ann@example.org", "next": "/f/7K3QXM"})
    assert response.status_code == 202
    (message,) = LogMailer.outbox
    assert message.to == "ann@example.org"
    token = token_from(message)
    assert f"{PUBLIC_URL}/signin/email?next=%2Ff%2F7K3QXM#token={token}" in message.body
    link = db.scalars(select(MagicLink)).one()
    assert link.token_hash == hash_token(token)
    assert token not in (link.token_hash, link.email)
    assert link.used_at is None
    assert timedelta(minutes=14) < link.expires_at - datetime.now(UTC) <= timedelta(minutes=15)


def test_an_unsafe_next_is_dropped_from_the_link(browser: TestClient) -> None:
    request_link(browser, "ann@example.org", next="//evil.example")
    assert "evil" not in LogMailer.outbox[-1].body
    assert "/signin/email#token=" in LogMailer.outbox[-1].body


def _comparable(response) -> tuple[int, str, dict[str, str]]:
    # Each request has its own id, in its header and in an error's body.
    request_id = response.headers["x-request-id"]
    headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in ("date", "content-length", "x-request-id")
    }
    # Each answer binds its own browser, so only the cookie's value may differ.
    if "set-cookie" in headers:
        headers["set-cookie"] = re.sub(r"=[^;]+;", "=<value>;", headers["set-cookie"], count=1)
    return response.status_code, response.text.replace(request_id, "<id>"), headers


@pytest.mark.parametrize(
    "account",
    [
        pytest.param({"email_verified_at": VERIFIED_AT}, id="verified"),
        pytest.param({}, id="unverified"),
        pytest.param({"email_verified_at": VERIFIED_AT, "banned_at": VERIFIED_AT}, id="banned"),
    ],
)
def test_the_answer_is_the_same_for_known_and_unknown_addresses(
    account: dict[str, Any], browser: TestClient, make_user: MakeUser, db: Session
) -> None:
    make_user(email="known@example.org", **account)
    known = browser.post(START, json={"email": "known@example.org"})
    unknown = browser.post(START, json={"email": "nobody@example.org"})
    assert _comparable(known) == _comparable(unknown)
    assert known.status_code == 202
    assert known.headers["set-cookie"].startswith(f"{email_link.LINK_COOKIE}=")
    # Both did the same work: one stored link and one email each.
    assert count(db, MagicLink) == 2
    assert [m.to for m in LogMailer.outbox] == ["known@example.org", "nobody@example.org"]
    links = db.scalars(select(MagicLink)).all()
    assert all(link.user_id is None for link in links)


def test_a_malformed_address_is_refused_the_same_way_for_everyone(browser: TestClient) -> None:
    for email in ("not-an-address", "", "a@", "@b.c", "a" * 400 + "@example.org"):
        response = browser.post(START, json={"email": email})
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
    assert not LogMailer.outbox


def test_email_start_needs_a_mailer(app: FastAPI, client_for: ClientFor) -> None:
    response = client_for(app).post(START, json={"email": "ann@example.org"})
    assert response.status_code == 404
    assert error_code(response) == "provider_unavailable"


def test_email_start_needs_the_client_header(app: FastAPI, client_for: ClientFor, mail_on: None) -> None:
    response = client_for(app, with_header=False).post(START, json={"email": "ann@example.org"})
    assert response.status_code == 403
    assert not LogMailer.outbox


# --------------------------------------------------------------------------
# Following the link
# --------------------------------------------------------------------------


def test_a_link_signs_in_a_new_person_who_then_needs_the_welcome_step(
    browser: TestClient, db: Session
) -> None:
    token = request_link(browser, "new@example.org")
    response = browser.post(VERIFY, json={"token": token})
    assert response.status_code == 200
    me = response.json()
    assert me["email"] == "new@example.org"
    assert me["email_verified"] is True
    assert me["needs_welcome"] is True
    assert browser.get("/api/v1/auth/me").json()["handle"] == me["handle"]
    link = db.scalars(select(MagicLink)).one()
    assert link.used_at is not None
    assert link.user_id is not None


def test_a_link_signs_in_the_account_that_has_the_address(
    browser: TestClient, make_user: MakeUser, db: Session
) -> None:
    ann = make_user(handle="AnnExisting", email="ann@example.org", email_verified_at=VERIFIED_AT)
    token = request_link(browser, "ANN@example.org")
    assert browser.post(VERIFY, json={"token": token}).json()["handle"] == "AnnExisting"
    assert count(db, User) == 1
    db.refresh(ann)
    assert ann.email_verified_at == VERIFIED_AT


def test_a_link_works_once(browser: TestClient, app: FastAPI, client_for: ClientFor, db: Session) -> None:
    token = request_link(browser, "ann@example.org")
    assert browser.post(VERIFY, json={"token": token}).status_code == 200
    again = client_for(app).post(VERIFY, json={"token": token})
    assert again.status_code == 400
    assert error_code(again) == "link_invalid"
    assert "set-cookie" not in again.headers
    assert count(db, UserSession) == 1


def test_a_link_expires_after_fifteen_minutes(browser: TestClient, db: Session) -> None:
    token = request_link(browser, "ann@example.org")
    with time_machine.travel(datetime.now(UTC) + timedelta(minutes=15, seconds=1), tick=False):
        response = browser.post(VERIFY, json={"token": token})
    assert error_code(response) == "link_invalid"
    assert count(db, User) == 0


def test_the_start_message_states_the_link_lifetime() -> None:
    assert email_link.LINK_LIFETIME.total_seconds() == 15 * 60
    assert "fifteen minutes" in EmailStarted().message


def test_a_link_still_works_just_before_it_expires(browser: TestClient) -> None:
    token = request_link(browser, "ann@example.org")
    with time_machine.travel(datetime.now(UTC) + timedelta(minutes=14, seconds=50), tick=False):
        assert browser.post(VERIFY, json={"token": token}).status_code == 200


@pytest.mark.parametrize("guess", ["x", "a" * 43, "A" * 128, "../../etc", "' OR 1=1 --"])
def test_a_guessed_link_fails_like_a_spent_one(guess: str, browser: TestClient, db: Session) -> None:
    request_link(browser, "ann@example.org")
    response = browser.post(VERIFY, json={"token": guess})
    assert response.status_code == 400
    assert error_code(response) == "link_invalid"
    assert count(db, User) == 0


def test_an_overlong_or_empty_token_is_refused_before_lookup(browser: TestClient) -> None:
    assert browser.post(VERIFY, json={"token": "a" * 129}).status_code == 422
    assert browser.post(VERIFY, json={"token": ""}).status_code == 422


def test_a_banned_account_cannot_sign_in_by_link(
    browser: TestClient, make_user: MakeUser, db: Session
) -> None:
    make_user(email="banned@example.org", email_verified_at=VERIFIED_AT, banned_at=VERIFIED_AT)
    token = request_link(browser, "banned@example.org")
    response = browser.post(VERIFY, json={"token": token})
    assert response.status_code == 403
    assert error_code(response) == "banned"
    assert count(db, UserSession) == 0


def test_a_deleted_accounts_address_starts_a_new_account(
    browser: TestClient, make_user: MakeUser, db: Session
) -> None:
    from fieldclub.auth import accounts

    gone = make_user(handle="Gone", email="gone@example.org", email_verified_at=VERIFIED_AT)
    accounts.delete_account(db, gone)
    db.commit()
    token = request_link(browser, "gone@example.org")
    me = browser.post(VERIFY, json={"token": token}).json()
    assert me["handle"] != "Gone"
    assert me["needs_welcome"] is True


def test_the_link_ends_any_session_the_browser_had(
    app: FastAPI, client_for: ClientFor, make_user: MakeUser, mail_on: None, db: Session
) -> None:
    browser = client_for(app, make_user())
    before = browser.cookies[SESSION_COOKIE]
    token = request_link(browser, "ann@example.org")
    response = browser.post(VERIFY, json={"token": token})
    issued = response.cookies.get(SESSION_COOKIE)
    assert issued
    assert issued != before
    assert db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(before))).first() is None


def test_asking_again_spends_the_earlier_links_this_browser_asked_for(
    browser: TestClient, db: Session
) -> None:
    first = request_link(browser, "new@example.org")
    other = request_link(browser, "other@example.org")
    second = request_link(browser, "NEW@example.org")
    assert error_code(browser.post(VERIFY, json={"token": first})) == "link_invalid"
    assert browser.post(VERIFY, json={"token": second}).status_code == 200
    assert count(db, User) == 1
    # Another address's link is untouched (this browser's cookie now names the newest link only).
    assert browser.post(VERIFY, json={"token": other, "email": "other@example.org"}).status_code == 200


def test_a_stranger_asking_for_your_address_leaves_your_link_working(
    browser: TestClient, app: FastAPI, client_for: ClientFor
) -> None:
    mine = request_link(browser, "ann@example.org")
    stranger = client_for(app)
    request_link(stranger, "ann@example.org")
    request_link(stranger, "Ann@example.org")
    signed_in = browser.post(VERIFY, json={"token": mine})
    assert signed_in.status_code == 200
    assert signed_in.json()["asked_here"] is True


def test_a_dotted_capital_i_link_never_signs_in_to_the_ascii_account(
    browser: TestClient, make_user: MakeUser, db: Session
) -> None:
    """U+0130 folds to ASCII "i" in Postgres lower(), so CITEXT matches the two addresses."""
    make_user(handle="Victim", email="ivan@example.org", email_verified_at=VERIFIED_AT)
    token = request_link(browser, "\u0130van@example.org")
    assert LogMailer.outbox[-1].to == "\u0130van@example.org"
    response = browser.post(VERIFY, json={"token": token})
    assert response.status_code == 409
    assert error_code(response) == "email_unavailable"
    assert SESSION_COOKIE not in response.cookies
    assert count(db, UserSession) == 0
    assert count(db, User) == 1


# --------------------------------------------------------------------------
# A link opened in a browser that didn't ask for it
# --------------------------------------------------------------------------


def test_a_link_from_another_browser_needs_the_address_typed_and_is_not_spent(
    browser: TestClient, app: FastAPI, client_for: ClientFor, db: Session
) -> None:
    """Someone asks for a link to their own address and sends it to a victim (login CSRF).

    The attacker picks an address that masks the same as the victim's, so the
    masked address can't be what stops it: the victim has to type theirs.
    """
    token = request_link(browser, "a9z@gmail.example")
    victim = client_for(app)
    response = victim.post(VERIFY, json={"token": token})
    assert response.status_code == 409
    assert error_code(response) == "confirmation_required"
    assert response.json()["error"]["details"] == {"email": "a***@gmail.example"}
    assert email_link.masked("alice.victim@gmail.example") == "a***@gmail.example"
    for typed in ("alice.victim@gmail.example", "a***@gmail.example", "a9z@gmail.exampl"):
        refused = victim.post(VERIFY, json={"token": token, "email": typed})
        assert refused.status_code == 409, typed
        assert error_code(refused) == "email_mismatch"
        assert SESSION_COOKIE not in refused.cookies
    assert SESSION_COOKIE not in response.cookies
    assert db.scalars(select(MagicLink)).one().used_at is None
    assert count(db, User) == 0
    # Someone who opened their own link on another device types their own address.
    confirmed = victim.post(VERIFY, json={"token": token, "email": " A9Z@gmail.example "})
    assert confirmed.status_code == 200
    assert confirmed.json()["email"] == "a9z@gmail.example"
    # So the interface knows not to save drafts left in this browser without asking.
    assert confirmed.json()["asked_here"] is False


def test_the_browser_that_asked_signs_in_without_confirming_and_its_cookie_is_cleared(
    browser: TestClient, db: Session
) -> None:
    token = request_link(browser, "ann@example.org")
    assert browser.cookies.get(email_link.LINK_COOKIE)
    link = db.scalars(select(MagicLink)).one()
    assert link.browser_hash == hash_token(browser.cookies[email_link.LINK_COOKIE])
    response = browser.post(VERIFY, json={"token": token})
    assert response.status_code == 200
    assert response.json()["asked_here"] is True
    assert email_link.LINK_COOKIE not in browser.cookies


def test_the_link_cookie_is_scoped_to_start_and_verify_and_lasts_as_long_as_the_link(
    browser: TestClient,
) -> None:
    response = browser.post(START, json={"email": "ann@example.org"})
    cookie = response.headers["set-cookie"].lower()
    assert f"path={email_link.LINK_COOKIE_PATH}" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert f"max-age={int(email_link.LINK_LIFETIME.total_seconds())}" in cookie


def test_an_unknown_link_fails_the_same_whether_or_not_it_is_confirmed(
    app: FastAPI, client_for: ClientFor, mail_on: None
) -> None:
    for body in ({"token": "a" * 43}, {"token": "a" * 43, "email": "ann@example.org"}):
        assert error_code(client_for(app).post(VERIFY, json=body)) == "link_invalid"


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("ann@example.org", "a***@example.org"),
        ("a@example.org", "a***@example.org"),
        ("\u00e4sa@b\u00fccher.example", "\u00e4***@b\u00fccher.example"),
    ],
)
def test_an_address_is_masked_to_its_first_letter_and_domain(email: str, masked: str) -> None:
    assert email_link.masked(email) == masked


def test_the_verify_path_the_cookie_names_is_the_routed_one(browser: TestClient) -> None:
    assert (email_link.VERIFY_PATH, email_link.START_PATH) == (VERIFY, START)
    paths = browser.get("/api/openapi.json").json()["paths"]
    assert VERIFY in paths
    assert START in paths


def test_redeem_spends_a_link_once_as_a_service(db: Session) -> None:
    token = email_link.create_link(db, "ann@example.org", browser="b" * 43)
    db.commit()
    for elsewhere in (None, "", "c" * 43, "x" * 200):
        with pytest.raises(LinkConfirmationRequiredError):
            email_link.redeem(db, token, browser=elsewhere)
    with pytest.raises(EmailMismatchError):
        email_link.redeem(db, token, typed_email="bob@example.org")
    redeemed = email_link.redeem(db, token, browser="b" * 43)
    db.commit()
    assert redeemed.user.email == "ann@example.org"
    assert redeemed.asked_here is True
    with pytest.raises(LinkInvalidError):
        email_link.redeem(db, token, typed_email="ann@example.org")
    for bad in (None, "", "x" * 200):
        with pytest.raises(LinkInvalidError):
            email_link.redeem(db, bad, typed_email="ann@example.org")


# --------------------------------------------------------------------------
# Rate limits
# --------------------------------------------------------------------------


def test_an_address_gets_twenty_links_an_hour_whoever_asks(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    for number in range(20):
        caller = caller_at(app, client_for, f"203.0.113.{number}")
        assert caller.post(START, json={"email": "ann@example.org"}).status_code == 202
    last = caller_at(app, client_for, "203.0.113.99")
    refused = last.post(START, json={"email": "Ann@Example.org"})
    assert refused.status_code == 429
    assert "retry-after" in refused.headers
    # Another address is unaffected.
    assert last.post(START, json={"email": "bob@example.org"}).status_code == 202
    assert len(LogMailer.outbox) == 21


def test_one_stranger_cannot_use_up_an_address_and_lock_its_owner_out(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    stranger = caller_at(app, client_for, "10.0.0.3")
    answers = [stranger.post(START, json={"email": f"alice+x{n}@example.org"}).status_code for n in range(5)]
    assert answers == [202, 202, 202, 429, 429]
    owner = caller_at(app, client_for, "10.0.0.4")
    assert owner.post(START, json={"email": "Alice@example.org"}).status_code == 202


def test_plus_tags_share_their_mailboxs_budget(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    for number in range(20):
        caller = caller_at(app, client_for, f"203.0.113.{number}")
        assert caller.post(START, json={"email": f"ann+{number}@example.org"}).status_code == 202
    last = caller_at(app, client_for, "203.0.113.99")
    assert last.post(START, json={"email": "Ann+other@example.org"}).status_code == 429
    assert last.post(START, json={"email": "ann@example.org"}).status_code == 429


@pytest.mark.parametrize(
    ("email", "key"),
    [
        ("ann@example.org", "ann@example.org"),
        ("Ann+Tag@Example.org", "ann@example.org"),
        ("ann+a+b@example.org", "ann@example.org"),
        ("+x@example.org", "@example.org"),
    ],
)
def test_the_rate_key_of_an_address_drops_its_plus_tag(email: str, key: str) -> None:
    assert email_link.rate_key(email) == key


def test_a_caller_gets_ten_links_an_hour_whatever_the_address(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    caller = caller_at(app, client_for, "203.0.113.7")
    for number in range(10):
        assert caller.post(START, json={"email": f"p{number}@example.org"}).status_code == 202
    assert caller.post(START, json={"email": "p11@example.org"}).status_code == 429
    other = caller_at(app, client_for, "198.51.100.1")
    assert other.post(START, json={"email": "p11@example.org"}).status_code == 202


def test_the_address_limit_answers_the_same_for_known_and_unknown_addresses(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None, make_user: MakeUser
) -> None:
    make_user(email="known@example.org", email_verified_at=VERIFIED_AT)
    answers = {}
    for email in ("known@example.org", "nobody@example.org"):
        last = None
        for number in range(21):
            last = caller_at(app, client_for, f"192.0.2.{number}").post(START, json={"email": email})
        assert last is not None
        answers[email] = (last.status_code, envelope(last))
    assert answers["known@example.org"] == answers["nobody@example.org"]
    assert answers["known@example.org"][0] == 429


# --------------------------------------------------------------------------
# Mailers and their settings
# --------------------------------------------------------------------------


def test_there_is_no_mailer_unless_one_is_chosen() -> None:
    assert get_mailer(settings()) is None
    assert isinstance(get_mailer(settings(mail_backend="log")), LogMailer)
    smtp = get_mailer(settings(mail_backend="smtp", smtp_host="smtp.example", mail_from="a@example.org"))
    assert isinstance(smtp, SmtpMailer)


def test_the_log_mailer_is_refused_in_production() -> None:
    with pytest.raises(ConfigError, match="MAIL_BACKEND=log"):
        settings(
            env="prod",
            secret_key="a-long-random-value-of-forty-characters!",
            trusted_proxy_hops=1,
            terms_url="/terms",
            dev_login=False,
            mail_backend="log",
        )


def test_smtp_needs_a_host_and_a_sender() -> None:
    with pytest.raises(ConfigError, match="SMTP_HOST"):
        settings(mail_backend="smtp", mail_from="a@example.org")
    with pytest.raises(ConfigError, match="MAIL_FROM"):
        settings(mail_backend="smtp", smtp_host="smtp.example")


class FakeSmtp:
    instances: ClassVar[list[FakeSmtp]] = []
    fail_with: ClassVar[Exception | None] = None

    def __init__(self, host: str, port: int, timeout: float, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[tuple[str, Any]] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append(("quit", None))

    def starttls(self, context: Any) -> None:
        self.calls.append(("starttls", None))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", (user, password)))

    def send_message(self, message: Any) -> None:
        if FakeSmtp.fail_with is not None:
            raise FakeSmtp.fail_with
        self.calls.append(("send", message))


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    FakeSmtp.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    return FakeSmtp


def test_smtp_sends_with_starttls_and_login(fake_smtp: type[FakeSmtp]) -> None:
    mailer = SmtpMailer(
        settings(
            mail_backend="smtp",
            smtp_host="smtp.example",
            smtp_username="user",
            smtp_password="pw",
            mail_from="OpenAntiquity <signin@example.org>",
        )
    )
    mailer.send(Message(to="ann@example.org", subject="Hi", body="Link"))
    (server,) = fake_smtp.instances
    assert (server.host, server.port) == ("smtp.example", 587)
    names = [name for name, _ in server.calls]
    assert names == ["starttls", "login", "send", "quit"]
    sent = server.calls[2][1]
    assert sent["To"] == "ann@example.org"
    assert sent["From"] == "OpenAntiquity <signin@example.org>"


def test_smtp_failure_is_an_upstream_error_and_logs_no_address(
    fake_smtp: type[FakeSmtp], caplog: pytest.LogCaptureFixture
) -> None:
    fake_smtp.fail_with = smtplib.SMTPRecipientsRefused(
        {"ann@example.org": (550, b"no mailbox ann@example.org")}
    )
    mailer = SmtpMailer(settings(mail_backend="smtp", smtp_host="smtp.example", mail_from="a@example.org"))
    with caplog.at_level(logging.INFO, logger="fieldclub"), pytest.raises(MailNotSentError):
        mailer.send(Message(to="ann@example.org", subject="Hi", body="Link"))
    assert "SMTPRecipientsRefused" in caplog.text
    assert "ann@example.org" not in caplog.text


def test_smtp_over_ssl_skips_starttls(fake_smtp: type[FakeSmtp]) -> None:
    mailer = SmtpMailer(
        settings(
            mail_backend="smtp",
            smtp_host="smtp.example",
            smtp_port=465,
            smtp_security="ssl",
            mail_from="a@b.org",
        )
    )
    mailer.send(Message(to="ann@example.org", subject="Hi", body="Link"))
    (server,) = fake_smtp.instances
    assert "context" in server.kwargs
    assert [name for name, _ in server.calls] == ["send", "quit"]


def test_the_email_start_route_sends_through_smtp(
    app: FastAPI, client_for: ClientFor, env: Callable[..., None], fake_smtp: type[FakeSmtp]
) -> None:
    env(MAIL_BACKEND="smtp", SMTP_HOST="smtp.example", MAIL_FROM="a@example.org", SMTP_SECURITY="none")
    response = client_for(app).post(START, json={"email": "ann@example.org"})
    assert response.status_code == 202
    (server,) = fake_smtp.instances
    assert [name for name, _ in server.calls] == ["send", "quit"]
    assert "#token=" in server.calls[0][1].get_content()


# --------------------------------------------------------------------------
# The development outbox, for the full-stack browser tests
# --------------------------------------------------------------------------

OUTBOX = "/api/v1/auth/dev-outbox"


def test_the_outbox_gives_the_links_sent_to_an_address_newest_first(browser: TestClient) -> None:
    first = request_link(browser, "walker@example.org")
    request_link(browser, "someone.else@example.org")
    second = request_link(browser, "walker@example.org", next="/f/ABC123")
    response = browser.get(OUTBOX, params={"to": "walker@example.org"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["to"] for item in items] == ["walker@example.org", "walker@example.org"]
    assert [token_from(Message(item["to"], item["subject"], item["body"])) for item in items] == [
        second,
        first,
    ]
    assert items[0]["link"].endswith(f"#token={second}")
    assert items[0]["link"] in items[0]["body"]
    assert "next=%2Ff%2FABC123" in items[0]["link"]


def test_the_outbox_matches_an_address_whatever_its_case(browser: TestClient) -> None:
    request_link(browser, "Walker@Example.org")
    items = browser.get(OUTBOX, params={"to": "walker@example.ORG"}).json()["items"]
    assert len(items) == 1


def test_the_outbox_needs_an_address(browser: TestClient) -> None:
    assert browser.get(OUTBOX).status_code == 422


def test_the_outbox_exists_only_where_the_development_sign_in_does(
    db: Session, env: Callable[..., None], client_for: ClientFor, mail_on: None
) -> None:
    off = get_settings().model_copy(update={"dev_login": False})
    browser = client_for(create_app(off))
    assert browser.get(OUTBOX, params={"to": "a@example.org"}).status_code == 404
    assert OUTBOX not in browser.get("/api/openapi.json").json()["paths"]
    # Mounted by mistake, it still says nothing.
    env(DEV_LOGIN="false")
    mounted = client_for(create_app(include_dev_routes=True))
    LogMailer.outbox.append(
        Message("a@example.org", "Your OpenAntiquity sign-in link", "https://x/#token=abc")
    )
    response = mounted.get(OUTBOX, params={"to": "a@example.org"})
    assert response.status_code == 404
    assert "abc" not in response.text


def test_a_browser_that_signed_in_by_link_keeps_its_own_budget_when_strangers_use_up_the_rest(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    """Strangers on enough addresses could use up the 20 an hour and leave the owner no way in."""
    owner = caller_at(app, client_for, "10.9.9.9")
    token = request_link(owner, "owner@example.org")
    signed_in = owner.post(VERIFY, json={"token": token})
    assert signed_in.status_code == 200, signed_in.text
    known = owner.cookies.get(email_link.KNOWN_COOKIE)
    assert known
    owner.post("/api/v1/auth/logout")
    for number in range(8):
        stranger = caller_at(app, client_for, f"2001:db8:{number}::1")
        for _ in range(3):
            stranger.post(START, json={"email": "owner@example.org"})
    late = caller_at(app, client_for, "10.8.8.8")
    assert late.post(START, json={"email": "owner@example.org"}).status_code == 429
    # A cookie made up, or one for another mailbox, buys nothing.
    late.cookies.set(email_link.KNOWN_COOKIE, "0" * 64, path=email_link.LINK_COOKIE_PATH)
    assert late.post(START, json={"email": "owner@example.org"}).status_code == 429
    # The owner's browser, from another address now, still gets its link.
    owner.headers["X-Forwarded-For"] = "10.7.7.7"
    assert owner.post(START, json={"email": "Owner@example.org"}).status_code == 202


def test_one_ipv6_site_counts_as_one_caller_for_an_address(
    app: FastAPI, client_for: ClientFor, mail_on: None, limits_on: None
) -> None:
    answers = [
        caller_at(app, client_for, f"2001:db8:1:{number}::1")
        .post(START, json={"email": "ann@example.org"})
        .status_code
        for number in range(5)
    ]
    assert answers == [202, 202, 202, 429, 429]
