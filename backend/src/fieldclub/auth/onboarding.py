"""The welcome step: who may contribute (Decision 0009).

A first sign-in creates an account with no age band and no accepted terms.
Until the person completes the welcome sheet, every write route refuses them
with `onboarding_required`. The account routes (`/auth/me`, logout, the
welcome step itself) stay open, so they can finish it, change their mind or
delete the account.

Contributors must be `FIELDCLUB_MIN_AGE` or over. The welcome sheet offers the
bands whose youngest age is at least that. An account in the 16 to 17 band
keeps neither the name nor the picture its sign-in provider gave, and is shown
to other people by handle only (`User.shows_handle_only`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fieldclub.auth import profile
from fieldclub.config import Settings
from fieldclub.errors import ConflictError, ForbiddenError, ValidationFailedError
from fieldclub.models import User
from fieldclub.vocab import AGE_BAND_YOUNGEST, AgeBand


class OnboardingRequiredError(ForbiddenError):
    code = "onboarding_required"
    message = "Choose your age band and accept the contributor terms before you contribute."


class BelowMinimumAgeError(ForbiddenError):
    code = "below_minimum_age"

    def __init__(self, min_age: int) -> None:
        super().__init__(f"Contributors must be {min_age} or over.")


class TermsNotAcceptedError(ValidationFailedError):
    code = "terms_not_accepted"
    message = "You need to accept the contributor terms to contribute."


class AlreadyWelcomedError(ConflictError):
    code = "already_welcomed"
    message = "You've already finished the welcome step."


def allowed_age_bands(settings: Settings) -> tuple[AgeBand, ...]:
    """The bands the welcome sheet may accept, youngest first."""
    return tuple(band for band in AgeBand if AGE_BAND_YOUNGEST[band] >= settings.min_age)


def has_welcomed(user: User) -> bool:
    return user.age_band is not None and user.terms_accepted_at is not None


def check_contributor(user: User, settings: Settings) -> None:
    """Raise unless `user` may contribute: welcomed, and in a band the minimum age allows."""
    if not has_welcomed(user):
        raise OnboardingRequiredError()
    if AgeBand(user.age_band) not in allowed_age_bands(settings):
        raise BelowMinimumAgeError(settings.min_age)


def complete_welcome(
    db: Session,
    user: User,
    *,
    age_band: AgeBand | str,
    accept_terms: bool,
    settings: Settings,
    handle: str = profile.UNSET,
    display_name: str = profile.UNSET,
    now: datetime | None = None,
) -> User:
    """Record the welcome sheet. The caller commits.

    Everything is checked before anything changes, so a refusal leaves the
    account as it was.
    """
    if has_welcomed(user):
        raise AlreadyWelcomedError()
    if accept_terms is not True:
        raise TermsNotAcceptedError()
    band = AgeBand(age_band)
    if band not in allowed_age_bands(settings):
        raise BelowMinimumAgeError(settings.min_age)

    changes: dict[str, Any] = {}
    if handle is not profile.UNSET:
        changes["handle"] = handle
    if display_name is not profile.UNSET:
        changes["display_name"] = display_name
    elif band is AgeBand.AGE_16_17:
        # Never keep the provider's name for a 16 or 17 year old.
        changes["display_name"] = handle if handle is not profile.UNSET else user.handle
    # Raises before anything is stored if the handle is taken or a name is bad.
    profile.update_profile(db, user, **changes)

    if band is AgeBand.AGE_16_17:
        user.avatar_url = None
    user.age_band = band.value
    user.terms_accepted_at = now or datetime.now(UTC)
    db.flush()
    return user
