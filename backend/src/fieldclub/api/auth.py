"""Signing in, the current session, and the signed-in person's own account.

Provider sign-in is a pair of browser navigations: `/auth/oauth/{provider}/start`
redirects to the provider, and the provider returns to `/callback`, by GET or,
for Apple, by a cross-site POST. Both always answer with a redirect to the
app, carrying `?signin_error=<code>` when something went wrong. The emailed
link is two JSON calls, `/auth/email/start` and `/auth/email/verify`. The
logic is in `fieldclub.auth.oauth`, `signin` and `email_link`.

`dev_router` holds `POST /auth/dev-login` and `GET /auth/dev-outbox`.
`create_app()` mounts it only when `FIELDCLUB_DEV_LOGIN` is on and the
environment is dev or test.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from fieldclub import ratelimit
from fieldclub.api.deps import AppSettings, CurrentUser, Db, OptionalUser, rate_limit
from fieldclub.auth import (
    accounts,
    cookies,
    email_link,
    oauth,
    onboarding,
    profile,
    providers,
    sessions,
    signin,
)
from fieldclub.auth.deps import client_ip
from fieldclub.auth.failures import FlowStateError, ProviderUnavailableError, SignInFailedError
from fieldclub.auth.flow import FLOW_COOKIE, new_flow, seal, state_matches, unseal
from fieldclub.auth.mailer import LogMailer, get_mailer
from fieldclub.auth.redirects import DEFAULT_NEXT, app_url, safe_next
from fieldclub.auth.tokens import hash_token, new_token
from fieldclub.config import SESSION_COOKIE, Settings
from fieldclub.errors import AppError, NotFoundError
from fieldclub.models import User
from fieldclub.schemas.auth import (
    DevEmail,
    DevLogin,
    DevOutbox,
    EmailStart,
    EmailStarted,
    EmailVerify,
    HandleSuggestion,
    Me,
    MeUpdate,
    Welcome,
)
from fieldclub.vocab import SignInProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
dev_router = APIRouter(prefix="/auth", tags=["auth"])

# Each emailed link goes to an inbox someone else may own, so an address has a
# budget of its own as well as the caller's.
_LINKS_PER_ADDRESS = ratelimit.get_limiter("auth_email_address", 5, per_seconds=3600)

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


@router.get("/session", response_model=Me | None)
def get_session(user: OptionalUser) -> Me | None:
    """The signed-in user, or null when nobody is, so a signed-out page load is no error.

    A stale cookie and a banned account answer null too. `GET /auth/me` keeps its 401 and 403.
    """
    return Me.from_user(user) if user is not None else None


@router.patch(
    "/me",
    response_model=Me,
    dependencies=[Depends(rate_limit("auth_me_update", 120, per_seconds=3600))],
)
def update_me(body: MeUpdate, request: Request, user: CurrentUser, db: Db, settings: AppSettings) -> Me:
    """Change your handle, display name, bio or settings, or remove your provider's picture.

    A bio is free text on a public profile, so it is a contribution: writing
    one needs a finished welcome step, like any other. Clearing it doesn't,
    nor does removing the picture (`avatar_url: null`).
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


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("auth_delete", 10, per_seconds=3600))],
)
def delete_me(response: Response, user: CurrentUser, db: Db) -> None:
    """Delete your account and sign out everywhere.

    Your email address, sign-in identities and sessions are removed. What you
    contributed stays, credited to "Former member".
    """
    accounts.delete_account(db, user)
    db.commit()
    cookies.clear_session_cookie(response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("auth_logout", 60, per_seconds=3600))],
)
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


# --------------------------------------------------------------------------
# Sign-in by provider
# --------------------------------------------------------------------------


def _begin_session(db: Db, user: User, request: Request, *, previous_hash: str | None = None) -> str:
    """A new session for whoever just signed in, ending the one this browser presented."""
    return signin.begin_session(
        db,
        user,
        previous_token=request.cookies.get(SESSION_COOKIE),
        previous_hash=previous_hash,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


def _failure(settings: Settings, target: str, code: str) -> RedirectResponse:
    """Back to the app with a short error code, and nothing else about what went wrong."""
    return RedirectResponse(app_url(settings, target, signin_error=code), status.HTTP_303_SEE_OTHER)


@router.get(
    "/oauth/{provider}/start",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    dependencies=[Depends(rate_limit("auth_oauth_start", 30, per_seconds=600))],
)
def oauth_start(
    provider: str,
    request: Request,
    settings: AppSettings,
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    """Send the browser to the provider. `next` is where to land afterwards: a path on this site.

    The start is a same-site navigation, so the session cookie is here even
    for Apple, whose callback won't carry it. The flow remembers its hash so
    that the callback can end it.
    """
    target = safe_next(next_path)
    try:
        chosen = oauth.get_provider(provider, settings)
        flow = new_flow(chosen.id.value, target, presented_session=request.cookies.get(SESSION_COOKIE))
        url = chosen.authorization_url(settings, flow)
    except AppError as exc:
        logger.info("Sign-in with %.40r couldn't start: %s", provider, exc.code)
        return _failure(settings, target, exc.code)
    response = RedirectResponse(url, status.HTTP_302_FOUND)
    cookies.set_flow_cookie(response, seal(flow), chosen)
    return response


def _finish_oauth(
    provider: str, callback: oauth.Callback, request: Request, db: Db, settings: Settings
) -> RedirectResponse:
    """Check the state, verify the person, sign them in and send them on. Every outcome is a redirect."""
    flow = unseal(request.cookies.get(FLOW_COOKIE))
    # The flow must be for the provider this callback is for.
    if flow is not None and flow.provider != provider:
        flow = None
    target = flow.next if flow is not None else DEFAULT_NEXT
    chosen: oauth.OAuthProvider | None = None
    try:
        chosen = oauth.get_provider(provider, settings)
        if flow is None or not state_matches(flow, callback.state):
            raise FlowStateError()
        identity = chosen.complete(settings, flow, callback)
        user = signin.user_for_identity(db, identity)
        token = _begin_session(db, user, request, previous_hash=flow.presented_session)
        db.commit()
    except AppError as exc:
        db.rollback()
        logger.info("Sign-in with %.40r failed: %s", provider, exc.code)
        response = _failure(settings, target, exc.code)
    except Exception:
        db.rollback()
        logger.exception("Sign-in with %.40r failed unexpectedly", provider)
        response = _failure(settings, target, SignInFailedError.code)
    else:
        response = RedirectResponse(app_url(settings, target), status.HTTP_303_SEE_OTHER)
        cookies.set_session_cookie(response, token)
    if chosen is not None:
        # One flow, one callback, whatever the outcome.
        cookies.clear_flow_cookie(response, chosen)
    return response


_CALLBACK_LIMIT = Depends(rate_limit("auth_oauth_callback", 30, per_seconds=600))


@router.get(
    "/oauth/{provider}/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    dependencies=[_CALLBACK_LIMIT],
)
def oauth_callback(
    provider: str,
    request: Request,
    db: Db,
    settings: AppSettings,
    code: Annotated[str | None, Query(max_length=4096)] = None,
    state: Annotated[str | None, Query(max_length=512)] = None,
    error: Annotated[str | None, Query(max_length=512)] = None,
) -> RedirectResponse:
    """Where the provider sends the browser back, by GET."""
    return _finish_oauth(provider, oauth.Callback(code=code, state=state, error=error), request, db, settings)


@router.post(
    "/oauth/{provider}/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    dependencies=[_CALLBACK_LIMIT],
)
def oauth_callback_post(
    provider: str,
    request: Request,
    db: Db,
    settings: AppSettings,
    code: Annotated[str | None, Form(max_length=4096)] = None,
    state: Annotated[str | None, Form(max_length=512)] = None,
    error: Annotated[str | None, Form(max_length=512)] = None,
    user: Annotated[str | None, Form(max_length=oauth.MAX_APPLE_USER_FIELD)] = None,
) -> RedirectResponse:
    """Where Apple posts back from another site. It can't send the client header, so `state` guards it."""
    callback = oauth.Callback(code=code, state=state, error=error, user=user)
    return _finish_oauth(provider, callback, request, db, settings)


# --------------------------------------------------------------------------
# Sign-in by emailed link
# --------------------------------------------------------------------------


def _require_email_link(settings: Settings) -> None:
    """Refuse unless the emailed link is switched on, by the same rule `/meta` reports."""
    if not providers.is_enabled(SignInProvider.EMAIL, settings):
        raise ProviderUnavailableError()


@router.post(
    "/email/start",
    response_model=EmailStarted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("auth_email_start", 10, per_seconds=3600))],
)
def email_start(body: EmailStart, response: Response, db: Db, settings: AppSettings) -> EmailStarted:
    """Email a one-time sign-in link, bound to this browser by a cookie.

    The answer is the same whether or not the address has an account.
    """
    _require_email_link(settings)
    mailer = get_mailer(settings)
    assert mailer is not None, "the emailed link is enabled only with a mail backend"
    ratelimit.enforce_key(_LINKS_PER_ADDRESS, f"email:{hash_token(email_link.rate_key(body.email))}")
    browser = new_token()
    token = email_link.create_link(db, body.email, browser=browser)
    db.commit()
    mailer.send(email_link.link_message(settings, body.email, token, safe_next(body.next)))
    cookies.set_link_cookie(response, browser)
    return EmailStarted()


@router.post(
    "/email/verify",
    response_model=Me,
    dependencies=[Depends(rate_limit("auth_email_verify", 30, per_seconds=3600))],
)
def email_verify(
    body: EmailVerify, request: Request, response: Response, db: Db, settings: AppSettings
) -> Me:
    """Spend an emailed link and sign in. Unknown, used and expired links all fail with `link_invalid`.

    In a browser other than the one that asked for the link, this answers
    `confirmation_required` with the masked address until posted with `confirm`.
    """
    _require_email_link(settings)
    user = email_link.redeem(
        db, body.token, browser=request.cookies.get(email_link.LINK_COOKIE), confirmed=body.confirm
    )
    token = _begin_session(db, user, request)
    db.commit()
    cookies.set_session_cookie(response, token)
    cookies.clear_link_cookie(response)
    return Me.from_user(user)


@dev_router.post(
    "/dev-login",
    response_model=Me,
    dependencies=[Depends(rate_limit("auth_dev_login", 600, per_seconds=3600))],
)
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
    token = _begin_session(db, user, request)
    db.commit()
    cookies.set_session_cookie(response, token)
    return Me.from_user(user)


@dev_router.get("/dev-outbox", response_model=DevOutbox)
def dev_outbox(
    settings: AppSettings, to: Annotated[str, Query(min_length=3, max_length=oauth.MAX_EMAIL)]
) -> DevOutbox:
    """The sign-in emails the log mailer sent to `to`, newest first. Development and test only.

    The full-stack browser tests read emailed links here instead of from the
    server's log. Like the development sign-in it gives a session to whoever
    asks, so it exists only where that does.
    """
    if not settings.dev_login_enabled:
        raise NotFoundError()
    return DevOutbox(
        items=[
            DevEmail(to=message.to, subject=message.subject, body=message.body, link=message.link)
            for message in LogMailer.sent_to(to)
        ]
    )
