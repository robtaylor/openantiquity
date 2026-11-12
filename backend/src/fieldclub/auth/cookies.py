"""The `__Host-openantiquity_session` cookie (HttpOnly, SameSite=Lax, Secure; `openantiquity_session`
in local development over http), the sign-in flow cookie, and the emailed link's browser cookies."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from fieldclub.auth.email_link import (
    KNOWN_COOKIE,
    KNOWN_LIFETIME,
    LINK_COOKIE,
    LINK_COOKIE_PATH,
    LINK_LIFETIME,
)
from fieldclub.auth.flow import FLOW_COOKIE, FLOW_LIFETIME_S
from fieldclub.auth.oauth import OAuthProvider, callback_path
from fieldclub.auth.sessions import session_lifetime
from fieldclub.config import get_settings


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(session_lifetime().total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def session_token(request: Request) -> str | None:
    """The session token the request carries, if any."""
    return request.cookies.get(get_settings().session_cookie_name)


def _flow_cookie_attributes(provider: OAuthProvider) -> dict[str, Any]:
    """Scoped to the provider's callback. A provider that returns with a cross-site
    POST (Apple) needs SameSite=None for the browser to send the cookie, and
    browsers take that only with Secure."""
    return {
        "path": callback_path(provider.id),
        "httponly": True,
        "samesite": "none" if provider.form_post else "lax",
        "secure": True if provider.form_post else get_settings().session_cookie_secure,
    }


def set_flow_cookie(response: Response, value: str, provider: OAuthProvider) -> None:
    """The signed `openantiquity_oauth` cookie for one sign-in flow, sent only to its callback."""
    response.set_cookie(FLOW_COOKIE, value, max_age=FLOW_LIFETIME_S, **_flow_cookie_attributes(provider))


def clear_flow_cookie(response: Response, provider: OAuthProvider) -> None:
    response.delete_cookie(FLOW_COOKIE, **_flow_cookie_attributes(provider))


def _link_cookie_attributes() -> dict[str, Any]:
    return {
        "path": LINK_COOKIE_PATH,
        "httponly": True,
        "samesite": "lax",
        "secure": get_settings().session_cookie_secure,
    }


def set_link_cookie(response: Response, value: str) -> None:
    """The `openantiquity_email_link` cookie that binds an emailed link to this browser."""
    response.set_cookie(
        LINK_COOKIE, value, max_age=int(LINK_LIFETIME.total_seconds()), **_link_cookie_attributes()
    )


def clear_link_cookie(response: Response) -> None:
    response.delete_cookie(LINK_COOKIE, **_link_cookie_attributes())


def set_known_cookie(response: Response, value: str) -> None:
    """The `openantiquity_email_known` cookie: the mailboxes this browser signed in to by link."""
    response.set_cookie(
        KNOWN_COOKIE, value, max_age=int(KNOWN_LIFETIME.total_seconds()), **_link_cookie_attributes()
    )
