"""Investigations and who belongs to one.

There is no private channel between members (Decision 0009), so a private
investigation has exactly one member: its owner. Adding a collaborator needs
the investigation to be public or unlisted first, and an investigation with
collaborators can't be made private.

The owner always holds an `owner` row in `investigation_members`, written by
`create_investigation`. The rule is checked here, so callers get a clear
error, and again by triggers from `models/extras.sql`, so a write that skips
this module still can't break it.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.errors import ConflictError
from fieldclub.models import Investigation, InvestigationMember, User
from fieldclub.services import ids
from fieldclub.vocab import InvestigationRole, Visibility


class PrivateInvestigationError(ConflictError):
    # The same text the database trigger raises, so either reads the same in a log.
    code = "private_investigation_has_one_member"
    message = "A private investigation can't have collaborators. Make it public or unlisted first."


def create_investigation(
    db: Session,
    owner: User,
    *,
    title: str,
    visibility: Visibility | str = Visibility.PRIVATE,
    summary: str | None = None,
) -> Investigation:
    """A new investigation with its owner as the one member. The caller commits."""
    investigation = Investigation(
        public_id=ids.new_public_id(db, Investigation),
        owner_id=owner.id,
        title=title,
        summary=summary,
        visibility=Visibility(visibility).value,
    )
    db.add(investigation)
    db.flush()
    db.add(
        InvestigationMember(
            investigation_id=investigation.id, user_id=owner.id, role=InvestigationRole.OWNER.value
        )
    )
    db.flush()
    return investigation


def _others(db: Session, investigation: Investigation) -> int:
    """How many members the investigation has besides its owner."""
    count = db.scalar(
        select(func.count())
        .select_from(InvestigationMember)
        .where(
            InvestigationMember.investigation_id == investigation.id,
            InvestigationMember.user_id != investigation.owner_id,
        )
    )
    assert count is not None
    return count


def add_member(
    db: Session, investigation: Investigation, user: User, role: InvestigationRole | str
) -> InvestigationMember | None:
    """Add a collaborator, or raise `PrivateInvestigationError` if it is private.

    Adding the owner changes nothing and returns None. The caller commits.
    """
    role = InvestigationRole(role)
    if role is InvestigationRole.OWNER:
        raise ValueError("An investigation has one owner, set by investigations.owner_id.")
    if user.id == investigation.owner_id:
        return None
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        raise PrivateInvestigationError()
    member = InvestigationMember(investigation_id=investigation.id, user_id=user.id, role=role.value)
    db.add(member)
    db.flush()
    return member


def set_visibility(db: Session, investigation: Investigation, visibility: Visibility | str) -> Investigation:
    """Change who can see an investigation. Private is refused while it has collaborators."""
    visibility = Visibility(visibility)
    if visibility is Visibility.PRIVATE and _others(db, investigation):
        raise PrivateInvestigationError()
    investigation.visibility = visibility.value
    db.flush()
    return investigation


def check_members(db: Session, investigation: Investigation) -> None:
    """Assert the membership rule holds for one investigation."""
    rows = db.execute(
        select(InvestigationMember.user_id, InvestigationMember.role).where(
            InvestigationMember.investigation_id == investigation.id
        )
    ).all()
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        assert len(rows) == 1, (
            f"private investigation {investigation.public_id} must have exactly one member, has {len(rows)}"
        )
    owners = [user_id for user_id, role in rows if role == InvestigationRole.OWNER.value]
    assert owners == [investigation.owner_id], (
        f"investigation {investigation.public_id} must have its owner as an owner member, found {owners}"
    )
