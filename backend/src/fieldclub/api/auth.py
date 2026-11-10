"""The current session and the signed-in person's own account.

Sign-in by provider (`/auth/oauth/*`) and by emailed link (`/auth/email/*`)
belong in this module too and are not built yet. `fieldclub.auth` describes how
to add them.

`dev_router` holds `POST /auth/dev-login`. `create_app()` mounts it only when
`FIELDCLUB_DEV_LOGIN` is on and the environment is dev or test.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from fieldclub import ratelimit
from fieldclub.api.deps import AppSettings, CurrentUser, Db, rate_limit
from fieldclub.auth import accounts, cookies, onboarding, profile, sessions
from fieldclub.auth.deps import client_ip
from fieldclub.config import SESSION_COOKIE
from fieldclub.errors import NotFoundError
from fieldclub.models import User
from fieldclub.schemas.auth import DevLogin, HandleSuggestion, Me, MeUpdate, Welcome

router = APIRouter(prefix="/auth", tags=["auth"])
dev_router = APIRouter(prefix="/auth", tags=["auth"])

# Settings are saved as people use the map, so the limit on the route is
# generous. Changing handle is rare, and each change frees a name for someone
# else to take, so it has a much smaller budget of its own.
_HANDLE_CHANGES = ratelimit.get_limiter("auth_handle_change", 5, per_seconds=24 * 3600)


def _without_nulls(changes: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """`changes` less any of `fields` sent as null, which means "leave it"."""
    return {name: value for name, value in changes.items() if not (name in fields and value is None)}


def _count_handle_change(request: Request, user: User, before: str) -> None:
    """Spend from the handle-change budget if the handle changed.

    Counted once the change is known to be good, so a mistyped or taken name
    costs nothing. Refused here, nothing has been committed.
    """
    if user.handle != before:
        ratelimit.enforce(_HANDLE_CHANGES, request, user)


@router.get("/me", response_model=Me)
def get_me(user: CurrentUser) -> Me:
    """The signed-in user. 401 when nobody is signed in."""
    return Me.from_user(user)


@router.patch(
    "/me",
    response_model=Me,
    dependencies=[Depends(rate_limit("auth_me_update", 120, per_seconds=3600))],
)
def update_me(body: MeUpdate, request: Request, user: CurrentUser, db: Db, settings: AppSettings) -> Me:
    """Change your handle, display name, bio or settings.

    A bio is free text on a public profile, so it is a contribution: writing
    one needs a finished welcome step, like any other. Clearing it doesn't.
    """
    changes = body.model_dump(exclude_unset=True)
    if changes.get("bio"):
        onboarding.check_contributor(user, settings)
    # Only the bio can be cleared.
    changes = _without_nulls(changes, ("handle", "display_name", "settings"))
    handle_before = user.handle
    profile.update_profile(db, user, **changes)
    _count_handle_change(request, user, handle_before)
    db.commit()
    return Me.from_user(user)


@router.post(
    "/welcome",
    response_model=Me,
    dependencies=[Depends(rate_limit("auth_welcome", 30, per_seconds=3600))],
)
def welcome(body: Welcome, request: Request, user: CurrentUser, db: Db, settings: AppSettings) -> Me:
    """Finish the welcome sheet: age band, contributor terms, and optionally handle and name.

    Until this is done every route that stores a contribution refuses with
    `onboarding_required`. It can be done once. An account in the 16 to 17
    band keeps neither the name nor the picture its sign-in provider gave.
    """
    changes = body.model_dump(exclude_unset=True, exclude={"age_band", "accept_terms"})
    changes = _without_nulls(changes, ("handle", "display_name"))
    handle_before = user.handle
    onboarding.complete_welcome(
        db, user, age_band=body.age_band, accept_terms=body.accept_terms, settings=settings, **changes
    )
    _count_handle_change(request, user, handle_before)
    db.commit()
    return Me.from_user(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(response: Response, user: CurrentUser, db: Db) -> None:
    """Delete your account and sign out everywhere.

    Your email address, sign-in identities and sessions are removed. What you
    contributed stays, credited to "Former member".
    """
    accounts.delete_account(db, user)
    db.commit()
    cookies.clear_session_cookie(response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Db) -> None:
    """End this session. Safe to call when not signed in."""
    sessions.revoke_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    cookies.clear_session_cookie(response)


@router.get(
    "/handle-suggestion",
    response_model=HandleSuggestion,
    dependencies=[Depends(rate_limit("auth_handle_suggestion", 120, per_seconds=3600))],
)
def handle_suggestion(db: Db) -> HandleSuggestion:
    """A generated handle that nobody has, for the welcome sheet to offer."""
    return HandleSuggestion(handle=accounts.suggest_handle(db))


@dev_router.post("/dev-login", response_model=Me)
def dev_login(body: DevLogin, request: Request, response: Response, db: Db, settings: AppSettings) -> Me:
    """Sign in as a named test user, creating it if need be. Development and test only.

    This is how local development and end-to-end tests get a session. It does
    not exist in production.
    """
    # The router is only mounted when this is true. Checked again here so that
    # mounting it by mistake still signs nobody in.
    if not settings.dev_login_enabled:
        raise NotFoundError()
    user = accounts.dev_user(db, body.handle, role=body.role, display_name=body.display_name)
    token = sessions.create_session(
        db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
    )
    db.commit()
    cookies.set_session_cookie(response, token)
    return Me.from_user(user)
