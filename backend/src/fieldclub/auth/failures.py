"""Why a sign-in failed, as stable short codes.

A provider callback is a browser navigation, so its failures leave as a
redirect to the app with `?signin_error=<code>`, never as a page of detail.
The emailed link is an API call, so its failures are the usual JSON error.
"""

from __future__ import annotations

from fieldclub.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UpstreamError,
)


class ProviderUnavailableError(NotFoundError):
    code = "provider_unavailable"
    message = "That way of signing in isn't available."


class FlowStateError(BadRequestError):
    """The callback's `state` is missing, forged, expired or from another browser."""

    code = "state_mismatch"
    message = "That sign-in didn't start here, or took too long. Please try again."


class SignInCancelledError(BadRequestError):
    code = "cancelled"
    message = "Sign-in was cancelled."


class ProviderError(UpstreamError):
    """The provider refused the code, or answered in a shape we don't accept."""

    code = "provider_error"
    message = "The sign-in provider didn't confirm who you are. Please try again."


class InvalidIdentityError(AppError):
    """The identity token failed verification: signature, issuer, audience, expiry or nonce."""

    status_code = 400
    code = "invalid_token"
    message = "The sign-in provider's answer couldn't be verified."


class AccountDeletedError(ForbiddenError):
    code = "account_deleted"
    message = "This account has been deleted."


class LinkInvalidError(BadRequestError):
    """An emailed link that is unknown, used or expired. One code for all three, on purpose."""

    code = "link_invalid"
    message = "This sign-in link has expired or has already been used. Ask for a new one."


class LinkConfirmationRequiredError(ConflictError):
    """A live link opened in a browser that didn't ask for it.

    Nothing is spent. The app asks the person to type their address and posts
    again with it as `email`, and never fills it in on their behalf: someone
    can ask for a link to their own address and send it to somebody else.
    """

    code = "confirmation_required"
    message = "This link was asked for in another browser. Type your email address to sign in."


class EmailMismatchError(ConflictError):
    """A link opened in another browser, confirmed with an address it wasn't sent to. Nothing is spent."""

    code = "email_mismatch"
    message = (
        "This link was sent to a different address. If someone else sent it to you, it would sign "
        "you in to their account, so ask for your own link."
    )


class EmailUnavailableError(ConflictError):
    """A proven address that the database would confuse with another account's.

    Addresses are matched case-insensitively, and Postgres folds a few
    non-ASCII capitals to ASCII letters (`İ` to `i`). Two such addresses are
    different mailboxes, so neither may sign in to the other's account.
    """

    code = "email_unavailable"
    message = "This address can't be used to sign in. Please use another address or a sign-in provider."


class SignInFailedError(AppError):
    status_code = 500
    code = "signin_failed"
    message = "Sign-in failed. Please try again."
