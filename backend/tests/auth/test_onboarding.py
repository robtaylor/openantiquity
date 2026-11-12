"""The welcome step: age band and contributor terms before any contribution (Decision 0009)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from fieldclub.auth.deps import Contributor
from fieldclub.auth.onboarding import (
    AlreadyWelcomedError,
    BelowMinimumAgeError,
    OnboardingRequiredError,
    TermsNotAcceptedError,
    allowed_age_bands,
    check_contributor,
    complete_welcome,
)
from fieldclub.auth.profile import HandleTakenError
from fieldclub.config import get_settings
from fieldclub.errors import install_error_handlers
from fieldclub.models import User
from fieldclub.vocab import AgeBand
from tests.helpers import ClientAs, ClientFor, MakeUser, error_code, settings

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ADULT, TEEN = AgeBand.AGE_18_PLUS, AgeBand.AGE_16_17


# --------------------------------------------------------------------------
# Age bands and the minimum age
# --------------------------------------------------------------------------


def test_the_minimum_age_defaults_to_16_and_allows_both_bands() -> None:
    assert get_settings().min_age == 16
    assert allowed_age_bands(settings()) == (TEEN, ADULT)


@pytest.mark.parametrize(("min_age", "bands"), [(16, (TEEN, ADULT)), (17, (ADULT,)), (18, (ADULT,))])
def test_a_band_is_offered_only_when_all_of_it_is_old_enough(
    min_age: int, bands: tuple[AgeBand, ...]
) -> None:
    # At 17 the 16 to 17 band would let 16 year olds in, so it is refused.
    assert allowed_age_bands(settings(min_age=min_age)) == bands


@pytest.mark.parametrize("min_age", [13, 15, 19])
def test_the_minimum_age_must_be_one_the_bands_can_express(min_age: int) -> None:
    with pytest.raises(ValueError, match="min_age"):
        settings(min_age=min_age)


# --------------------------------------------------------------------------
# Completing the welcome step
# --------------------------------------------------------------------------


def test_an_adult_completes_the_welcome_step(db: Session, newcomer: User) -> None:
    with pytest.raises(OnboardingRequiredError):
        check_contributor(newcomer, settings())
    complete_welcome(
        db,
        newcomer,
        age_band=ADULT,
        accept_terms=True,
        handle="RidgewayRob",
        display_name="Rob",
        settings=settings(),
        now=NOW,
    )
    db.commit()
    db.refresh(newcomer)
    assert (newcomer.handle, newcomer.display_name) == ("RidgewayRob", "Rob")
    assert (newcomer.age_band, newcomer.terms_accepted_at) == ("18_plus", NOW)
    check_contributor(newcomer, settings())


def test_handle_and_display_name_are_optional(db: Session, newcomer: User) -> None:
    complete_welcome(db, newcomer, age_band=ADULT, accept_terms=True, settings=settings(), now=NOW)
    assert (newcomer.handle, newcomer.display_name) == ("QuietBarrow42", "Robert Provider")


def test_a_16_or_17_year_old_keeps_nothing_from_the_provider(db: Session, newcomer: User) -> None:
    complete_welcome(db, newcomer, age_band=TEEN, accept_terms=True, settings=settings(), now=NOW)
    db.commit()
    db.refresh(newcomer)
    assert newcomer.age_band == "16_17"
    # The provider's name and picture are not kept, so they can't be shown.
    assert (newcomer.display_name, newcomer.avatar_url) == ("QuietBarrow42", None)
    check_contributor(newcomer, settings())


def test_a_16_or_17_year_old_may_choose_a_display_name_but_it_stays_private_in_public(
    db: Session, newcomer: User
) -> None:
    complete_welcome(
        db, newcomer, age_band=TEEN, accept_terms=True, display_name="Robbie", settings=settings(), now=NOW
    )
    assert (newcomer.display_name, newcomer.avatar_url) == ("Robbie", None)
    assert newcomer.shows_handle_only is True


def test_terms_must_be_accepted(db: Session, newcomer: User) -> None:
    with pytest.raises(TermsNotAcceptedError) as caught:
        complete_welcome(db, newcomer, age_band=ADULT, accept_terms=False, settings=settings(), now=NOW)
    assert (caught.value.code, caught.value.status_code) == ("terms_not_accepted", 422)
    assert (newcomer.age_band, newcomer.terms_accepted_at) == (None, None)


def test_a_band_below_the_minimum_age_is_refused(db: Session, newcomer: User) -> None:
    with pytest.raises(BelowMinimumAgeError) as caught:
        complete_welcome(
            db, newcomer, age_band=TEEN, accept_terms=True, settings=settings(min_age=18), now=NOW
        )
    assert (caught.value.code, caught.value.status_code) == ("below_minimum_age", 403)
    assert "18" in caught.value.message
    assert (newcomer.age_band, newcomer.terms_accepted_at) == (None, None)


def test_the_welcome_step_happens_once(db: Session, newcomer: User) -> None:
    complete_welcome(db, newcomer, age_band=TEEN, accept_terms=True, settings=settings(), now=NOW)
    with pytest.raises(AlreadyWelcomedError) as caught:
        complete_welcome(db, newcomer, age_band=ADULT, accept_terms=True, settings=settings(), now=NOW)
    assert (caught.value.code, caught.value.status_code) == ("already_welcomed", 409)
    assert newcomer.age_band == "16_17"


def test_a_taken_handle_leaves_the_account_as_it_was(
    db: Session, newcomer: User, make_user: MakeUser
) -> None:
    make_user(handle="TakenName")
    with pytest.raises(HandleTakenError):
        complete_welcome(
            db, newcomer, age_band=ADULT, accept_terms=True, handle="TakenName", settings=settings(), now=NOW
        )
    db.commit()
    db.refresh(newcomer)
    assert (newcomer.handle, newcomer.age_band, newcomer.terms_accepted_at) == ("QuietBarrow42", None, None)


@pytest.mark.parametrize(
    ("columns", "code"),
    [
        ({"age_band": None, "terms_accepted_at": None}, "onboarding_required"),
        ({"age_band": "18_plus", "terms_accepted_at": None}, "onboarding_required"),
        ({"age_band": None, "terms_accepted_at": NOW}, "onboarding_required"),
    ],
)
def test_check_contributor_needs_both(make_user: MakeUser, columns: dict, code: str) -> None:
    with pytest.raises(OnboardingRequiredError) as caught:
        check_contributor(make_user(**columns), settings())
    assert (caught.value.code, caught.value.status_code) == (code, 403)


def test_raising_the_minimum_age_stops_existing_accounts_below_it(make_user: MakeUser) -> None:
    teen = make_user(age_band="16_17", terms_accepted_at=NOW)
    check_contributor(teen, settings())
    with pytest.raises(BelowMinimumAgeError):
        check_contributor(teen, settings(min_age=18))


# --------------------------------------------------------------------------
# The dependency every write route uses
# --------------------------------------------------------------------------


@pytest.fixture
def write_app(db: Session) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/things")
    def create_thing(user: Contributor) -> dict[str, str]:
        return {"handle": user.handle}

    return app


@pytest.fixture
def sign_in(write_app: FastAPI, client_for: ClientFor) -> ClientAs:
    return lambda user: client_for(write_app, user)


def test_a_write_route_refuses_anyone_who_has_not_finished_the_welcome_step(
    sign_in: ClientAs, newcomer: User
) -> None:
    response = sign_in(newcomer).post("/things")
    assert response.status_code == 403
    assert error_code(response) == "onboarding_required"


def test_a_write_route_lets_a_contributor_through(sign_in: ClientAs, make_user: MakeUser) -> None:
    user = make_user(handle="Ready", age_band="16_17", terms_accepted_at=NOW)
    response = sign_in(user).post("/things")
    assert (response.status_code, response.json()) == (200, {"handle": "Ready"})


def test_a_write_route_still_needs_a_session(write_app: FastAPI, client_for: ClientFor) -> None:
    response = client_for(write_app, with_header=False).post("/things")
    assert response.status_code == 401
    assert error_code(response) == "unauthorised"


def test_a_write_route_follows_the_minimum_age_setting(
    sign_in: ClientAs, make_user: MakeUser, env: Callable[..., None]
) -> None:
    client = sign_in(make_user(age_band="16_17", terms_accepted_at=NOW))
    env(MIN_AGE="18")
    response = client.post("/things")
    assert response.status_code == 403
    assert error_code(response) == "below_minimum_age"
