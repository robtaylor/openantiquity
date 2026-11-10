"""The `fieldclub_session` cookie: HttpOnly, SameSite=Lax, and Secure outside development."""

from __future__ import annotations

from starlette.responses import Response

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
