"""The `fieldclub_session` cookie (HttpOnly, SameSite=Lax, Secure outside dev) and the sign-in flow cookie."""

from __future__ import annotations

from typing import Any

from starlette.responses import Response

from fieldclub.auth.flow import FLOW_COOKIE, FLOW_LIFETIME_S
from fieldclub.auth.sessions import session_lifetime
from fieldclub.config import SESSION_COOKIE, get_settings


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(session_lifetime().total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
    )


def _flow_cookie_attributes(path: str, cross_site_post: bool) -> dict[str, Any]:
    """A provider that returns with a cross-site POST (Apple) needs SameSite=None
    for the browser to send the cookie, and browsers take that only with Secure."""
    return {
        "path": path,
        "httponly": True,
        "samesite": "none" if cross_site_post else "lax",
        "secure": True if cross_site_post else get_settings().session_cookie_secure,
    }


def set_flow_cookie(response: Response, value: str, *, path: str, cross_site_post: bool) -> None:
    """The signed `fieldclub_oauth` cookie for one sign-in flow, sent only to its callback."""
    response.set_cookie(
        FLOW_COOKIE, value, max_age=FLOW_LIFETIME_S, **_flow_cookie_attributes(path, cross_site_post)
    )


def clear_flow_cookie(response: Response, *, path: str, cross_site_post: bool) -> None:
    response.delete_cookie(FLOW_COOKIE, **_flow_cookie_attributes(path, cross_site_post))
