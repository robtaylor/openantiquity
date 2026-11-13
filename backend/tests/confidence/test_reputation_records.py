"""Writing reputation awards: each is paid once, and members become eligible for trusted at fifty points."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import ReputationEvent, User
from fieldclub.services.reputation import TRUSTED_AT, Award, record_awards
from fieldclub.vocab import Role
from tests.helpers import MakeFinding, MakeUser, count


def reload(db: Session, user: User) -> User:
    db.expire_all()
    fresh = db.get(User, user.id)
    assert fresh is not None
    return fresh


def test_awards_are_itemised_and_added_up(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder, helper = make_user(), make_user()
    finding = make_finding(finder)
    recorded = record_awards(
        db,
        finding.id,
        [
            Award(finder.id, 2, "tier_seen"),
            Award(finder.id, 5, "tier_corroborated"),
            Award(helper.id, 1, "x"),
        ],
    )
    db.commit()
    assert len(recorded.awards) == 3
    assert (reload(db, finder).reputation, reload(db, helper).reputation) == (7.0, 1.0)
    reasons = db.scalars(select(ReputationEvent.reason).where(ReputationEvent.user_id == finder.id)).all()
    assert sorted(reasons) == ["tier_corroborated", "tier_seen"]


def test_an_award_already_held_is_skipped(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder = make_user()
    finding = make_finding(finder)
    record_awards(db, finding.id, [Award(finder.id, 2, "tier_seen")])
    again = record_awards(
        db, finding.id, [Award(finder.id, 2, "tier_seen"), Award(finder.id, 5, "tier_corroborated")]
    )
    db.commit()
    assert [award.reason for award in again.awards] == ["tier_corroborated"]
    assert reload(db, finder).reputation == 7.0
    assert count(db, ReputationEvent) == 2


def test_the_same_reason_on_another_finding_is_paid(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder = make_user()
    for finding in (make_finding(finder), make_finding(finder)):
        record_awards(db, finding.id, [Award(finder.id, 2, "tier_seen")])
    db.commit()
    assert reload(db, finder).reputation == 4.0


@pytest.mark.parametrize(("points", "eligible"), [(TRUSTED_AT - 1, False), (TRUSTED_AT, True)])
def test_a_member_becomes_eligible_at_fifty_points_but_is_not_promoted(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, points: float, eligible: bool
) -> None:
    member = make_user(reputation=points - 20)
    finding = make_finding(member)
    recorded = record_awards(db, finding.id, [Award(member.id, 20, "tier_ground_checked")])
    db.commit()
    # Trusted users download protected positions, so promotion is a moderator's call.
    assert reload(db, member).role == Role.MEMBER.value
    assert recorded.eligible == ((member.id,) if eligible else ())


def test_a_member_already_over_fifty_is_not_reported_again(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    member = make_user(reputation=TRUSTED_AT + 5)
    recorded = record_awards(db, make_finding(member).id, [Award(member.id, 2, "tier_seen")])
    assert (recorded.eligible, reload(db, member).role) == ((), Role.MEMBER.value)


@pytest.mark.parametrize("role", [Role.EXPERT, Role.MODERATOR, Role.ADMIN, Role.TRUSTED])
def test_other_roles_are_left_alone(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, role: Role
) -> None:
    user = make_user(role, reputation=45.0)
    finding = make_finding(user)
    recorded = record_awards(db, finding.id, [Award(user.id, 30, "tier_confirmed")])
    db.commit()
    assert (reload(db, user).role, recorded.eligible) == (role.value, ())


def test_a_banned_member_is_not_eligible(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> None:
    member = make_user(reputation=45.0, banned_at=datetime(2026, 11, 1, tzinfo=UTC))
    recorded = record_awards(db, make_finding().id, [Award(member.id, 10, "tier_probable")])
    db.commit()
    assert (reload(db, member).role, reload(db, member).reputation, recorded.eligible) == ("member", 55.0, ())


def test_nothing_to_record(db: Session, make_finding: MakeFinding) -> None:
    recorded = record_awards(db, make_finding().id, [])
    assert (recorded.awards, recorded.eligible) == ((), ())


def test_a_repeated_award_in_one_call_is_a_bug(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    user = make_user()
    with pytest.raises(AssertionError):
        record_awards(db, make_finding().id, [Award(user.id, 1, "x"), Award(user.id, 1, "x")])
