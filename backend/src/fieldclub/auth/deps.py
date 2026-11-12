"""FastAPI dependencies for knowing who is asking.

    @router.post("/things")
    def create_thing(user: CurrentUser, db: Db) -> ...

- `OptionalUser` is the signed-in user or `None`.
- `CurrentUser` is the signed-in user, or a 401.
- `Contributor` is the signed-in user once they have finished the welcome
  step, or a 403 with code `onboarding_required` (or `below_minimum_age`).
  Every route that stores a contribution takes this, not `CurrentUser`.
- `require_role(Role.MODERATOR, Role.ADMIN)` is the user if they hold one of
  those roles, or a 403.

A banned user is treated as signed out by `OptionalUser` and gets a 403 with
code `banned` from `CurrentUser`. Someone who deleted their account is signed
out everywhere.

Requests that change data must also carry `X-OpenAntiquity-Client: web`. That is
checked for every path by `fieldclub.auth.csrf.ClientHeaderMiddleware`, so routes
don't ask for it.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from fieldclub.auth import cookies, onboarding, sessions
from fieldclub.config import get_settings
from fieldclub.db import get_db
from fieldclub.errors import BannedError, ForbiddenError, UnauthorisedError
from fieldclub.models import User
from fieldclub.vocab import Role

Db = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    """The caller's IP address.

    Behind a proxy the socket address is the proxy's. `FIELDCLUB_TRUSTED_PROXY_HOPS`
    says how many proxies we run behind, and so which entry of
    `X-Forwarded-For`, counted from the right, was written by one we trust.
    Entries further left are whatever the client chose to send.

    A proxy may add its entry as a header line of its own instead of
    appending to the line it received. The lines are one list in the order
    they arrive, so they are joined before counting. Reading only the first
    line would believe the client's.

    `FIELDCLUB_CLIENT_IP_HEADER` names a header the proxy sets to the
    visitor's address, overwriting any the visitor sent (`Fly-Client-IP`).
    When it is set, that header alone is read. A request without exactly one
    valid address in it didn't come through the proxy, and is the socket's.
    """
    settings = get_settings()
    if settings.client_ip_header:
        given = request.headers.getlist(settings.client_ip_header)
        if len(given) == 1 and _is_address(given[0].strip()):
            return given[0].strip()
        return request.client.host if request.client else None
    hops = settings.trusted_proxy_hops
    if hops > 0:
        lines = request.headers.getlist("x-forwarded-for")
        forwarded = [part.strip() for line in lines for part in line.split(",") if part.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else None


def _is_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def current_user_optional(request: Request, response: Response, db: Db) -> User | None:
    """The signed-in user, or `None`. Never raises for a missing or stale cookie."""
    token = cookies.session_token(request)
    resolved = sessions.resolve_session(db, token)
    if resolved is None:
        return None
    if resolved.refreshed:
        assert token is not None, "a session resolved from a token"
        db.commit()
        cookies.set_session_cookie(response, token)
    if resolved.user.is_banned:
        request.state.fieldclub_banned = True
        return None
    return resolved.user


OptionalUser = Annotated[User | None, Depends(current_user_optional)]


def current_user(request: Request, user: OptionalUser) -> User:
    """The signed-in user. 401 when there is none, 403 when they are banned."""
    if user is None:
        if getattr(request.state, "fieldclub_banned", False):
            raise BannedError()
        raise UnauthorisedError()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_contributor(user: CurrentUser) -> User:
    """The signed-in user, if they may contribute. See `fieldclub.auth.onboarding`."""
    onboarding.check_contributor(user, get_settings())
    return user


Contributor = Annotated[User, Depends(current_contributor)]


def require_role(*roles: Role) -> Callable[..., User]:
    """A dependency that passes the user through only if they hold one of `roles`.

    @router.get("/mod/reports")
    def reports(user: Annotated[User, Depends(require_role(Role.MODERATOR, Role.ADMIN))]) -> ...
    """
    assert roles, "require_role needs at least one role"
    allowed = frozenset(Role(role) for role in roles)

    def dependency(user: CurrentUser) -> User:
        if Role(user.role) not in allowed:
            raise ForbiddenError()
        return user

    return dependency
