"""Sending the emailed sign-in link.

`get_mailer(settings)` picks one of two implementations by
`FIELDCLUB_MAIL_BACKEND`:

- `log` writes the message, link included, to the log and keeps the last few
  in `LogMailer.outbox`. For development and tests. Settings refuse it in
  production, because a link in a log is a session for whoever reads it.
- `smtp` sends through `FIELDCLUB_SMTP_HOST`.

Unset, there is no mailer and the emailed link isn't offered.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage
from typing import ClassVar, Protocol

from fieldclub.config import Settings
from fieldclub.errors import UpstreamError

logger = logging.getLogger(__name__)


class MailNotSentError(UpstreamError):
    code = "mail_not_sent"
    message = "We couldn't send the email just now. Please try again in a few minutes."


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, message: Message) -> None: ...


class LogMailer:
    """Writes each message to the log. Never used in production."""

    # Shared by every instance, so a test can read what the app sent.
    outbox: ClassVar[deque[Message]] = deque(maxlen=50)

    def send(self, message: Message) -> None:
        LogMailer.outbox.append(message)
        logger.info("Email to %s: %s\n%s", message.to, message.subject, message.body)


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        assert settings.smtp_host, "settings refuse smtp without a host"
        assert settings.mail_from, "settings refuse smtp without a sender"
        self.settings = settings

    def send(self, message: Message) -> None:
        settings = self.settings
        assert settings.smtp_host
        assert settings.mail_from
        email = EmailMessage()
        email["From"] = settings.mail_from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.body)
        timeout = settings.http_timeout_s
        context = ssl.create_default_context()
        try:
            if settings.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
                )
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
            with server:
                if settings.smtp_security == "starttls":
                    server.starttls(context=context)
                if settings.smtp_username and settings.smtp_password is not None:
                    server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                server.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            # The exception's text can quote the recipient, so only its kind is logged.
            logger.error(
                "Sending through %s failed: %s %s",
                settings.smtp_host,
                type(exc).__name__,
                getattr(exc, "smtp_code", ""),
            )
            raise MailNotSentError() from exc
        logger.info("Sent sign-in email through %s", settings.smtp_host)


def get_mailer(settings: Settings) -> Mailer | None:
    """The configured mailer, or None when the emailed link is switched off."""
    if settings.mail_backend == "log":
        return LogMailer()
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings)
    return None
