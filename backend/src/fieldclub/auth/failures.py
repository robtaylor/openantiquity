"""Why a sign-in failed, as stable short codes.

A provider callback is a browser navigation, so its failures leave as a
redirect to the app with `?signin_error=<code>`, never as a page of detail.
The emailed link is an API call, so its failures are the usual JSON error.
"""

from __future__ import annotations

from fieldclub.errors import AppError, BadRequestError, ForbiddenError, NotFoundError, UpstreamError


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


class SignInFailedError(AppError):
    status_code = 500
    code = "signin_failed"
    message = "Sign-in failed. Please try again."
