"""A private investigation has exactly one member, its owner (Decision 0009)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.models import Investigation, InvestigationMember
from fieldclub.services import investigations
from fieldclub.services.investigations import (
    PrivateInvestigationError,
    add_member,
    create_investigation,
    set_visibility,
)
from fieldclub.vocab import InvestigationRole, Visibility
from tests.helpers import MakeUser


def members(db: Session, investigation: Investigation) -> list[tuple[int, str]]:
    rows = db.execute(
        select(InvestigationMember.user_id, InvestigationMember.role)
        .where(InvestigationMember.investigation_id == investigation.id)
        .order_by(InvestigationMember.user_id)
    )
    return [(user_id, role) for user_id, role in rows]


def test_a_new_investigation_is_private_with_its_owner_as_the_one_member(
    db: Session, make_user: MakeUser
) -> None:
    owner = make_user()
    investigation = create_investigation(db, owner, title="Parish survey")
    db.commit()
    assert investigation.visibility == "private"
    assert investigation.public_id
    assert members(db, investigation) == [(owner.id, "owner")]
    investigations.check_members(db, investigation)


@pytest.mark.parametrize("role", [InvestigationRole.EDITOR, InvestigationRole.VIEWER])
def test_nobody_else_can_join_a_private_investigation(
    db: Session, make_user: MakeUser, role: InvestigationRole
) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Private")
    with pytest.raises(PrivateInvestigationError) as caught:
        add_member(db, investigation, helper, role)
    assert caught.value.code == "private_investigation_has_one_member"
    assert caught.value.status_code == 409
    assert members(db, investigation) == [(owner.id, "owner")]


@pytest.mark.parametrize("visibility", [Visibility.PUBLIC, Visibility.UNLISTED])
def test_public_and_unlisted_investigations_take_collaborators(
    db: Session, make_user: MakeUser, visibility: Visibility
) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Open", visibility=visibility)
    add_member(db, investigation, helper, InvestigationRole.EDITOR)
    db.commit()
    assert members(db, investigation) == sorted([(owner.id, "owner"), (helper.id, "editor")])
    investigations.check_members(db, investigation)


def test_an_investigation_with_collaborators_cannot_be_made_private(db: Session, make_user: MakeUser) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Shared", visibility=Visibility.PUBLIC)
    add_member(db, investigation, helper, InvestigationRole.VIEWER)
    with pytest.raises(PrivateInvestigationError):
        set_visibility(db, investigation, Visibility.PRIVATE)
    assert investigation.visibility == "public"
    set_visibility(db, investigation, Visibility.UNLISTED)
    db.commit()
    assert investigation.visibility == "unlisted"


def test_a_solo_investigation_can_go_private_again(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = create_investigation(db, owner, title="Solo", visibility=Visibility.PUBLIC)
    set_visibility(db, investigation, Visibility.PRIVATE)
    db.commit()
    assert investigation.visibility == "private"


def test_a_second_owner_row_is_refused(db: Session, make_user: MakeUser) -> None:
    owner, other = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Public", visibility=Visibility.PUBLIC)
    with pytest.raises(ValueError, match="owner"):
        add_member(db, investigation, other, InvestigationRole.OWNER)


def test_adding_the_owner_again_changes_nothing(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = create_investigation(db, owner, title="Private")
    add_member(db, investigation, owner, InvestigationRole.EDITOR)
    assert members(db, investigation) == [(owner.id, "owner")]


def test_check_members_spots_a_broken_private_investigation(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = Investigation(public_id="INVBAD", owner_id=owner.id, title="No owner row")
    db.add(investigation)
    db.flush()
    with pytest.raises(AssertionError, match="exactly one member"):
        investigations.check_members(db, investigation)


# --------------------------------------------------------------------------
# The database holds the rule too, for any write that skips the service
# --------------------------------------------------------------------------


def test_the_database_refuses_a_second_member_of_a_private_investigation(
    db: Session, make_user: MakeUser
) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Private")
    db.commit()
    with pytest.raises(IntegrityError, match="private_investigation_has_one_member"):
        db.execute(
            insert(InvestigationMember).values(
                investigation_id=investigation.id, user_id=helper.id, role="viewer"
            )
        )
    db.rollback()


def test_the_database_refuses_moving_a_member_into_a_private_investigation(
    db: Session, make_user: MakeUser
) -> None:
    owner, helper = make_user(), make_user()
    shared = create_investigation(db, owner, title="Shared", visibility=Visibility.PUBLIC)
    private = create_investigation(db, owner, title="Private")
    add_member(db, shared, helper, InvestigationRole.VIEWER)
    db.commit()
    with pytest.raises(IntegrityError, match="private_investigation_has_one_member"):
        db.execute(
            update(InvestigationMember)
            .where(InvestigationMember.user_id == helper.id)
            .values(investigation_id=private.id)
        )
    db.rollback()


def test_the_database_refuses_making_a_shared_investigation_private(db: Session, make_user: MakeUser) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Shared", visibility=Visibility.UNLISTED)
    add_member(db, investigation, helper, InvestigationRole.EDITOR)
    db.commit()
    with pytest.raises(IntegrityError, match="private_investigation_has_one_member"):
        db.execute(
            update(Investigation).where(Investigation.id == investigation.id).values(visibility="private")
        )
    db.rollback()


def test_the_database_refuses_handing_a_private_investigation_to_someone_else(
    db: Session, make_user: MakeUser
) -> None:
    # The old owner's row would then be a second member.
    owner, other = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Private")
    db.commit()
    with pytest.raises(IntegrityError, match="private_investigation_has_one_member"):
        db.execute(
            update(Investigation).where(Investigation.id == investigation.id).values(owner_id=other.id)
        )
    db.rollback()


def test_deleting_an_investigation_still_removes_its_members(db: Session, make_user: MakeUser) -> None:
    owner, helper = make_user(), make_user()
    investigation = create_investigation(db, owner, title="Shared", visibility=Visibility.PUBLIC)
    add_member(db, investigation, helper, InvestigationRole.EDITOR)
    db.commit()
    db.delete(investigation)
    db.commit()
    assert db.scalar(select(func.count()).select_from(InvestigationMember)) == 0
