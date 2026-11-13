"""Investigations: the shared notebook, who belongs to one, and what it holds.

There is no private channel between members (Decision 0009), so a private
investigation has exactly one member: its owner. Adding a collaborator needs
the investigation to be public or unlisted first, and an investigation with
collaborators can't be made private.

The owner always holds an `owner` row in `investigation_members`, written by
`create_investigation`. The rule is checked here, so callers get a clear
error, and again by triggers from `models/extras.sql`, so a write that skips
this module still can't break it.

Who may do what:

| Visibility | Read                   | Edit and add items | Members, visibility, delete |
|------------|------------------------|--------------------|-----------------------------|
| public     | anyone                 | owner, editor      | owner                       |
| unlisted   | anyone with the link   | owner, editor      | owner                       |
| private    | the owner              | the owner          | the owner                   |

A banned or deleted account counts as signed out. Anyone a page doesn't let
read an investigation gets `investigation_not_found`, so an id says nothing
about a private one. A member can leave; only the owner removes others.

Nobody is made a member without saying yes. The owner invites a contributor
by handle, which writes their row with `accepted_at` null. Until they accept
they have no role, the investigation isn't in their `mine` list, and they
can decline by leaving. Someone who hasn't finished the welcome step can't
be invited.

A moderator can hide an investigation (`services.moderation.set_hidden`).
A hidden one is found only by its members and moderators: it leaves the
public list, feeds and invitations, and everyone else gets
`investigation_not_found`.

Only a public investigation is in the public list or a feed. Making one
public records `investigation_published`; making it unlisted or private again
removes that row, so no feed built from `activity` can show it afterwards.
Moderators can list every unlisted investigation (`Scope.UNLISTED`), so
collaborators never have a channel moderators can't find (Decision 0009,
rule 5).

When an account is deleted (`forget_account`) its private investigations go
with it, since nobody else could ever read them. A shared one passes to its
longest-standing editor, or stays, readable and unmanaged, when it has none.

Every change takes the investigation's row lock first (`load(..., lock=True)`).
That serialises membership against visibility, and every change to the
order of items, so two edits at once can't lose an item or give two items
the same place. `investigation_items` holds a deferred unique constraint on
the place as well.

Items that point at a finding or a record are resolved for each viewer by
`item_views`. A finding the viewer may not see because it is hidden, a
withdrawn finding, and a record that has left the index come back as an
`Unavailable` line with nothing of the target in it. A position is never
read here: responses take it from `services.sensitivity`.

Services flush and never commit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import case, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub.auth import onboarding
from fieldclub.config import get_settings
from fieldclub.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidCursorError,
    NotFoundError,
    UnauthorisedError,
    ValidationFailedError,
)
from fieldclub.errors import InvestigationNotFoundError as InvestigationNotFoundError
from fieldclub.errors import UserNotFoundError as UserNotFoundError
from fieldclub.models import (
    Activity,
    Finding,
    Investigation,
    InvestigationHeldFinding,
    InvestigationItem,
    InvestigationMember,
    Record,
    Source,
    User,
)
from fieldclub.models.common import to_db_geometry
from fieldclub.schemas.common import cursor_int, decode_cursor, offset_from_cursor, offset_page, paginate
from fieldclub.schemas.text import has_unstorable_character
from fieldclub.services import activity, findings, geo, ids, records, sensitivity
from fieldclub.services.records import RecordResult
from fieldclub.vocab import ActivityKind, FindingState, InvestigationItemKind, InvestigationRole, Visibility

PUBLIC_ID_CONSTRAINT = "uq_investigations_public_id"

# The most items one investigation holds, and the most members.
MAX_ITEMS = 500
MAX_MEMBERS = 50

# The kinds whose content lives in `investigation_items.data`.
DATA_KINDS = frozenset(
    {InvestigationItemKind.VIEW, InvestigationItemKind.REFERENCE, InvestigationItemKind.PROFILE}
)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class PrivateInvestigationError(ConflictError):
    # The same text the database trigger raises, so either reads the same in a log.
    code = "private_investigation_has_one_member"
    message = "A private investigation can't have collaborators. Make it public or unlisted first."


class InvestigationForbiddenError(ForbiddenError):
    code = "investigation_forbidden"
    message = "Only the investigation's owner or an editor can do that."


class OwnerOnlyError(ForbiddenError):
    code = "investigation_owner_only"
    message = "Only the investigation's owner can do that."


class MemberNotFoundError(NotFoundError):
    code = "member_not_found"
    message = "There's no member with that handle."


class InvitationNotFoundError(NotFoundError):
    code = "invitation_not_found"
    message = "You have no invitation to this investigation waiting."


class ModeratorOnlyError(ForbiddenError):
    code = "investigation_moderator_only"
    message = "Only moderators can list unlisted investigations."


class OwnerMembershipError(ConflictError):
    code = "owner_is_always_a_member"
    message = "The owner is always a member, with the owner role."


class TooManyMembersError(ConflictError):
    code = "too_many_members"
    message = f"An investigation can have at most {MAX_MEMBERS} members."


class ItemNotFoundError(NotFoundError):
    code = "item_not_found"
    message = "That investigation has no such item."


class TooManyItemsError(ConflictError):
    code = "too_many_items"
    message = f"An investigation can hold at most {MAX_ITEMS} items."


class ItemUnavailableError(ConflictError):
    code = "item_unavailable"
    message = "This item's finding isn't shown, so its title and note can't be changed."


class InvalidItemError(ValidationFailedError):
    code = "invalid_item"
    message = "That item is missing what its kind needs."


# --------------------------------------------------------------------------
# Creating, and the membership rule
# --------------------------------------------------------------------------


def _record_published(db: Session, investigation: Investigation, actor: User) -> None:
    activity.record(db, ActivityKind.INVESTIGATION_PUBLISHED, actor, investigation=investigation)


def _forget_published(db: Session, investigation: Investigation) -> None:
    """Remove the published event of an investigation that is no longer public."""
    db.execute(
        delete(Activity).where(
            Activity.investigation_id == investigation.id,
            Activity.kind == ActivityKind.INVESTIGATION_PUBLISHED.value,
        )
    )


def _area_columns(area: BaseGeometry | None) -> dict[str, Any]:
    """The area and its grid squares, which are always set together."""
    if area is None:
        return {"area": None, "area_squares": None}
    squares = sensitivity.square_cover(area)
    assert squares is not None, "an area is checked to be on the grids before it is saved"
    return {"area": to_db_geometry(area), "area_squares": to_db_geometry(squares)}


def create_investigation(
    db: Session,
    owner: User,
    *,
    title: str,
    visibility: Visibility | str = Visibility.PRIVATE,
    summary: str | None = None,
    notes: str | None = None,
    area: Any = None,
) -> Investigation:
    """A new investigation with its owner as the one member. The caller commits.

    `area` is a shapely geometry or None. A public one is published at once.
    """
    visibility = Visibility(visibility)
    investigation = ids.insert_with_public_id(
        db,
        lambda public_id: Investigation(
            public_id=public_id,
            owner_id=owner.id,
            title=title,
            summary=summary,
            notes=notes,
            **_area_columns(area),
            visibility=visibility.value,
        ),
        PUBLIC_ID_CONSTRAINT,
    )
    db.add(
        InvestigationMember(
            investigation_id=investigation.id,
            user_id=owner.id,
            role=InvestigationRole.OWNER.value,
            accepted_at=func.now(),
        )
    )
    db.flush()
    if visibility is Visibility.PUBLIC:
        _record_published(db, investigation, owner)
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
    db: Session,
    investigation: Investigation,
    user: User,
    role: InvestigationRole | str,
    *,
    accepted: bool = True,
) -> InvestigationMember | None:
    """Add a collaborator, or raise `PrivateInvestigationError` if it is private.

    With `accepted` false the row is an invitation the person has yet to
    accept. Adding the owner changes nothing and returns None. The caller commits.
    """
    role = InvestigationRole(role)
    if role is InvestigationRole.OWNER:
        raise ValueError("An investigation has one owner, set by investigations.owner_id.")
    if user.id == investigation.owner_id:
        return None
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        raise PrivateInvestigationError()
    member = InvestigationMember(
        investigation_id=investigation.id,
        user_id=user.id,
        role=role.value,
        accepted_at=func.now() if accepted else None,
    )
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


def change_visibility(
    db: Session, investigation: Investigation, actor: User, visibility: Visibility | str
) -> Investigation:
    """`set_visibility`, then the published event: recorded on the way to public, removed on the way back."""
    before, after = Visibility(investigation.visibility), Visibility(visibility)
    set_visibility(db, investigation, after)
    if before is not Visibility.PUBLIC and after is Visibility.PUBLIC:
        _record_published(db, investigation, actor)
    elif before is Visibility.PUBLIC and after is not Visibility.PUBLIC:
        _forget_published(db, investigation)
    return investigation


def check_members(db: Session, investigation: Investigation) -> None:
    """Assert the membership rule holds for one investigation."""
    rows = db.execute(
        select(InvestigationMember.user_id, InvestigationMember.role, InvestigationMember.accepted_at).where(
            InvestigationMember.investigation_id == investigation.id
        )
    ).all()
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        assert len(rows) == 1, (
            f"private investigation {investigation.public_id} must have exactly one member, has {len(rows)}"
        )
    owners = [
        (user_id, accepted) for user_id, role, accepted in rows if role == InvestigationRole.OWNER.value
    ]
    assert [user_id for user_id, _ in owners] == [investigation.owner_id], (
        f"investigation {investigation.public_id} must have its owner as an owner member, found {owners}"
    )
    assert owners[0][1] is not None, f"the owner of {investigation.public_id} must have accepted"


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


class Need(StrEnum):
    READ = "read"
    EDIT = "edit"
    OWN = "own"


@dataclass(frozen=True)
class Access:
    """An investigation and the viewer's role in it, None for someone who isn't a member.

    `invited` is the role a pending invitation offers the viewer, if there is one.
    """

    investigation: Investigation
    role: InvestigationRole | None
    invited: InvestigationRole | None = None

    @property
    def may_edit(self) -> bool:
        return self.role in (InvestigationRole.OWNER, InvestigationRole.EDITOR)

    @property
    def is_owner(self) -> bool:
        return self.role is InvestigationRole.OWNER


def membership(db: Session, investigation: Investigation, viewer: User | None) -> InvestigationMember | None:
    """The viewer's row, accepted or not. A banned or deleted account has none."""
    active = sensitivity.active_viewer(viewer)
    if active is None:
        return None
    return db.get(InvestigationMember, (investigation.id, active.id))


def access_for(db: Session, investigation: Investigation, viewer: User | None) -> Access:
    """The viewer's role, or the role an invitation they haven't accepted offers them."""
    member = membership(db, investigation, viewer)
    if member is None:
        return Access(investigation, None)
    if member.accepted_at is None:
        return Access(investigation, None, invited=InvestigationRole(member.role))
    return Access(investigation, InvestigationRole(member.role))


def role_of(db: Session, investigation: Investigation, viewer: User | None) -> InvestigationRole | None:
    """The viewer's role in the investigation. An invitation not yet accepted gives none."""
    return access_for(db, investigation, viewer).role


def may_read(
    investigation: Investigation, role: InvestigationRole | None, viewer: User | None = None
) -> bool:
    """Public and unlisted ones are open to anyone who has the id. A private one only to its owner.

    One a moderator has hidden is open only to its members and moderators.
    """
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        return role is InvestigationRole.OWNER
    if investigation.hidden_at is not None:
        return role is not None or findings.is_moderator(viewer)
    return True


def load(
    db: Session, public_id: str, viewer: User | None, need: Need = Need.READ, *, lock: bool = False
) -> Access:
    """The investigation with this id and the viewer's role, or the error that `need` calls for.

    With `lock`, the row lock is taken before anything is checked, so the
    checks hold until the caller commits.
    """
    normalised = ids.normalise(public_id)
    if normalised is None:
        raise InvestigationNotFoundError()
    query = select(Investigation).where(Investigation.public_id == normalised)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    investigation = db.scalar(query)
    if investigation is None:
        raise InvestigationNotFoundError()
    access = access_for(db, investigation, viewer)
    if not may_read(investigation, access.role, viewer):
        raise InvestigationNotFoundError()
    if need is Need.EDIT and not access.may_edit:
        raise InvestigationForbiddenError()
    if need is Need.OWN and not access.is_owner:
        raise OwnerOnlyError()
    return access


def _touch(investigation: Investigation) -> None:
    investigation.updated_at = func.now()


# --------------------------------------------------------------------------
# Editing and deleting
# --------------------------------------------------------------------------

EDITABLE = frozenset({"title", "summary", "notes", "area", "visibility"})


def update_investigation(db: Session, access: Access, actor: User, changes: dict[str, Any]) -> Investigation:
    """Apply the fields given. Visibility is the owner's; the rest is the owner's or an editor's.

    `area` is a shapely geometry or None. The caller holds the lock and commits.
    """
    assert set(changes) <= EDITABLE, f"not editable: {set(changes) - EDITABLE}"
    investigation = access.investigation
    if not access.may_edit:
        raise InvestigationForbiddenError()
    if "visibility" in changes and changes["visibility"] != investigation.visibility and not access.is_owner:
        raise OwnerOnlyError()
    for name in ("title", "summary", "notes"):
        if name in changes:
            setattr(investigation, name, changes[name])
    if "area" in changes:
        for name, value in _area_columns(changes["area"]).items():
            setattr(investigation, name, value)
    if "visibility" in changes:
        change_visibility(db, investigation, actor, changes["visibility"])
    _touch(investigation)
    db.flush()
    return investigation


def delete_investigation(db: Session, access: Access) -> None:
    """Delete it with its items, members and events. The owner's call."""
    if not access.is_owner:
        raise OwnerOnlyError()
    db.delete(access.investigation)
    db.flush()


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------


class Scope(StrEnum):
    # Public investigations, for everyone.
    PUBLIC = "public"
    # Every investigation the viewer belongs to, whatever its visibility.
    MINE = "mine"
    # The ones the viewer has been invited to and hasn't yet accepted.
    INVITED = "invited"
    # Every unlisted investigation, for moderators only.
    UNLISTED = "unlisted"


@dataclass(frozen=True)
class Listed:
    investigation: Investigation
    owner: User
    item_count: int
    # What the viewer may see of its text and area, given the findings it holds.
    guard: sensitivity.PositionGuard


def held_findings(db: Session, investigation_ids: Iterable[int]) -> dict[int, list[Finding]]:
    """The findings each investigation holds or has held, whether or not the viewer may see them.

    A finding taken off the page still lies where the notes and views put
    it, so `investigation_held_findings` keeps every finding ever added.
    The items are read too, for one added before that table was kept.
    """
    wanted = set(investigation_ids)
    held: dict[int, dict[int, Finding]] = {investigation_id: {} for investigation_id in wanted}
    if wanted:
        current = (
            select(InvestigationItem.investigation_id, Finding)
            .join(Finding, Finding.id == InvestigationItem.finding_id)
            .where(InvestigationItem.investigation_id.in_(wanted))
        )
        earlier = (
            select(InvestigationHeldFinding.investigation_id, Finding)
            .join(Finding, Finding.id == InvestigationHeldFinding.finding_id)
            .where(InvestigationHeldFinding.investigation_id.in_(wanted))
        )
        for query in (current, earlier):
            for investigation_id, finding in db.execute(query):
                held[investigation_id][finding.id] = finding
    return {investigation_id: list(found.values()) for investigation_id, found in held.items()}


def item_shape(kind: InvestigationItemKind | str, data: dict[str, Any] | None) -> BaseGeometry | None:
    """Where a saved view or a height profile is, or None for an item that isn't drawn."""
    if data is None:
        return None
    kind = InvestigationItemKind(kind)
    if kind is InvestigationItemKind.VIEW:
        return Point(data["centre"])
    if kind is InvestigationItemKind.PROFILE:
        return LineString(data["line"]["coordinates"])
    return None


def _drawn(db: Session, investigations: Sequence[Investigation]) -> dict[int, list[BaseGeometry]]:
    """What was drawn in each investigation: its area, and its saved views and height profiles."""
    drawn: dict[int, list[BaseGeometry]] = {
        investigation.id: [to_shape(investigation.area)] if investigation.area is not None else []
        for investigation in investigations
    }
    if drawn:
        rows = db.execute(
            select(InvestigationItem.investigation_id, InvestigationItem.kind, InvestigationItem.data).where(
                InvestigationItem.investigation_id.in_(drawn),
                InvestigationItem.kind.in_(
                    [InvestigationItemKind.VIEW.value, InvestigationItemKind.PROFILE.value]
                ),
            )
        )
        for investigation_id, kind, data in rows:
            shape = item_shape(kind, data)
            if shape is not None:
                drawn[investigation_id].append(shape)
    return drawn


def position_guards(
    db: Session, investigations: Sequence[Investigation], viewer: User | None, *, download: bool = False
) -> dict[int, sensitivity.PositionGuard]:
    """What `viewer` may see of what was written and drawn in each investigation, by id.

    The findings each holds or has held decide, hidden and withdrawn ones
    included, and so does every finding near what was drawn in it, whatever
    holds it (`sensitivity.PositionGuard`, Decision 0023). A finding a
    moderator has hidden counts only where it is or was held: near anything
    else it is left out (`sensitivity.hidden_near`, Decision 0032).
    """
    held = held_findings(db, (investigation.id for investigation in investigations))
    drawn = _drawn(db, investigations)
    near = sensitivity.hidden_near(
        db, viewer, (shape for shapes in drawn.values() for shape in shapes), download=download
    )
    return {
        investigation.id: sensitivity.position_guard(
            held[investigation.id], viewer, download=download, near=near, shapes=drawn[investigation.id]
        )
        for investigation in investigations
    }


def position_guard(
    db: Session, investigation: Investigation, viewer: User | None, *, download: bool = False
) -> sensitivity.PositionGuard:
    """`position_guards` for one investigation."""
    return position_guards(db, [investigation], viewer, download=download)[investigation.id]


def _item_count() -> Any:
    return (
        select(func.count())
        .select_from(InvestigationItem)
        .where(InvestigationItem.investigation_id == Investigation.id)
        .scalar_subquery()
    )


def list_investigations(
    db: Session,
    viewer: User | None,
    scope: Scope,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Listed], str | None]:
    """A page of investigations, most recently changed first.

    `bbox` matches the area the investigation's editors drew, as this viewer
    may see it: an area near a finding the viewer sees only as a square is
    matched by the whole grid squares it covers, as it is shown
    (`sensitivity.PositionGuard.area`), so narrowing the box can't find it out.
    A private investigation is only ever listed for its owner, and an unlisted
    one for its members, the people invited to it, and moderators.
    """
    query = select(Investigation, User, _item_count()).join(User, User.id == Investigation.owner_id)
    if scope is Scope.PUBLIC:
        query = query.where(
            Investigation.visibility == Visibility.PUBLIC.value,
            findings.shown_clause(Investigation.hidden_at, Investigation.owner_id, viewer),
        )
    else:
        active = sensitivity.active_viewer(viewer)
        if active is None:
            raise UnauthorisedError()
        if scope is Scope.UNLISTED:
            if not findings.is_moderator(active):
                raise ModeratorOnlyError()
            query = query.where(Investigation.visibility == Visibility.UNLISTED.value)
        else:
            accepted = InvestigationMember.accepted_at.is_not(None)
            query = query.join(
                InvestigationMember,
                (InvestigationMember.investigation_id == Investigation.id)
                & (InvestigationMember.user_id == active.id)
                & (accepted if scope is Scope.MINE else ~accepted),
            )
            if scope is Scope.INVITED and not findings.is_moderator(active):
                # Someone only invited isn't a member yet, so a hidden one is gone for them.
                query = query.where(Investigation.hidden_at.is_(None))
    if bbox is not None:
        near = sensitivity.near_hidden_clause(viewer, Investigation.area)
        shown = case((near, Investigation.area_squares), else_=Investigation.area)
        query = query.where(func.ST_Intersects(shown, geo.envelope(bbox)))
    if cursor is not None:
        value, last_id = decode_cursor(cursor, 2)
        last_id = cursor_int(last_id)
        if not isinstance(value, str):
            raise InvalidCursorError()
        try:
            after = datetime.fromisoformat(value)
        except ValueError:
            raise InvalidCursorError() from None
        query = query.where(tuple_(Investigation.updated_at, Investigation.id) < (after, last_id))
    query = query.order_by(Investigation.updated_at.desc(), Investigation.id.desc()).limit(limit + 1)
    found = list(db.execute(query))
    guards = position_guards(db, [investigation for investigation, _, _ in found], viewer)
    rows = [
        Listed(investigation, owner, count, guards[investigation.id]) for investigation, owner, count in found
    ]
    return paginate(rows, limit, lambda row: [row.investigation.updated_at.isoformat(), row.investigation.id])


@dataclass(frozen=True)
class Counts:
    items: int
    members: int


def counts(db: Session, investigation: Investigation) -> Counts:
    items = db.scalar(
        select(func.count())
        .select_from(InvestigationItem)
        .where(InvestigationItem.investigation_id == investigation.id)
    )
    members = db.scalar(
        select(func.count())
        .select_from(InvestigationMember)
        .where(
            InvestigationMember.investigation_id == investigation.id,
            InvestigationMember.accepted_at.is_not(None),
        )
    )
    assert items is not None
    assert members is not None
    return Counts(items, members)


# --------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberView:
    user: User
    role: InvestigationRole
    # When they were invited, or added as the owner.
    joined_at: datetime
    # False while the invitation waits for an answer.
    accepted: bool = True


def list_members(
    db: Session, investigation: Investigation, *, limit: int, cursor: str | None = None
) -> tuple[list[MemberView], str | None]:
    """The owner first, then everyone else in the order they were invited, invitations included."""
    offset = offset_from_cursor(cursor)
    rows = db.execute(
        select(
            User, InvestigationMember.role, InvestigationMember.created_at, InvestigationMember.accepted_at
        )
        .join(InvestigationMember, InvestigationMember.user_id == User.id)
        .where(InvestigationMember.investigation_id == investigation.id)
        .order_by(
            (InvestigationMember.role != InvestigationRole.OWNER.value).asc(),
            InvestigationMember.created_at.asc(),
            InvestigationMember.user_id.asc(),
        )
        .offset(offset)
        .limit(limit + 1)
    ).all()
    views = [
        MemberView(user, InvestigationRole(role), joined, accepted is not None)
        for user, role, joined, accepted in rows
    ]
    return offset_page(views, offset, limit, max_offset=MAX_MEMBERS)


def find_user(db: Session, handle: str) -> User:
    """The contributor with this handle, or `UserNotFoundError`.

    Someone banned, deleted, or who hasn't finished the welcome step and so
    has no age band (Decision 0009, rule 2) can't be invited, and is not found.
    """
    if has_unstorable_character(handle):
        raise UserNotFoundError()
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None or not user.is_active:
        raise UserNotFoundError()
    try:
        onboarding.check_contributor(user, get_settings())
    except AppError:
        raise UserNotFoundError() from None
    return user


def find_member(db: Session, investigation: Investigation, handle: str) -> User:
    """The member, or invited person, with this handle, whatever state their account is in."""
    if has_unstorable_character(handle):
        raise MemberNotFoundError()
    user = db.scalar(
        select(User)
        .join(InvestigationMember, InvestigationMember.user_id == User.id)
        .where(InvestigationMember.investigation_id == investigation.id, User.handle == handle)
    )
    if user is None:
        raise MemberNotFoundError()
    return user


def put_member(
    db: Session, access: Access, user: User, role: InvestigationRole | str
) -> tuple[InvestigationMember, bool]:
    """Invite `user` with `role`, or change the role they have or were offered. True when invited.

    The owner's call, under the lock. A private investigation takes nobody.
    The person is a member once they accept (`accept_invitation`). A new
    invitation sends them a notification (`activity.notify_invitation`).
    """
    role = InvestigationRole(role)
    investigation = access.investigation
    if not access.is_owner:
        raise OwnerOnlyError()
    if role is InvestigationRole.OWNER or user.id == investigation.owner_id:
        raise OwnerMembershipError()
    existing = db.get(InvestigationMember, (investigation.id, user.id))
    if existing is not None:
        existing.role = role.value
        db.flush()
        return existing, False
    if _others(db, investigation) + 1 >= MAX_MEMBERS:
        raise TooManyMembersError()
    member = add_member(db, investigation, user, role, accepted=False)
    assert member is not None, "the owner was handled above"
    owner = db.get(User, investigation.owner_id)
    assert owner is not None, "an investigation's owner always has a row"
    # The invited person is told, with nothing but who asked and which investigation.
    activity.notify_invitation(db, user, owner, investigation)
    return member, True


def accept_invitation(db: Session, access: Access, user: User) -> InvestigationMember:
    """Make the invitation `user` holds a membership. The caller holds the lock and commits."""
    member = db.get(InvestigationMember, (access.investigation.id, user.id))
    if member is None or member.accepted_at is not None:
        raise InvitationNotFoundError()
    member.accepted_at = func.now()
    db.flush()
    return member


def remove_member(db: Session, access: Access, actor: User, handle: str) -> None:
    """Remove a member or an invitation by handle.

    The owner removes anyone else; anyone else can leave or decline.
    """
    investigation = access.investigation
    try:
        user = find_member(db, investigation, handle)
    except MemberNotFoundError:
        if not access.is_owner:
            raise OwnerOnlyError() from None
        raise
    if user.id == investigation.owner_id:
        raise OwnerMembershipError()
    if not (access.is_owner or actor.has_id(user.id)):
        raise OwnerOnlyError()
    member = db.get(InvestigationMember, (investigation.id, user.id))
    assert member is not None, "find_member found them through their row"
    db.delete(member)
    db.flush()


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NewItem:
    kind: InvestigationItemKind
    # A finding's public id, for a finding item.
    finding: str | None = None
    record_id: int | None = None
    title: str | None = None
    note: str | None = None
    # A view, reference or profile, already validated by its schema.
    data: dict[str, Any] | None = None


def _check_item(kind: InvestigationItemKind, *, title: str | None, note: str | None, data: object) -> None:
    if kind is InvestigationItemKind.NOTE and not note:
        raise InvalidItemError("A note needs its text.")
    if kind is InvestigationItemKind.REFERENCE and not title:
        raise InvalidItemError("A reference needs a title.")
    if (kind in DATA_KINDS) != (data is not None):
        raise InvalidItemError(f"A {kind} item {'needs' if kind in DATA_KINDS else 'takes no'} {kind} data.")


def _next_position(db: Session, investigation: Investigation) -> int:
    highest = db.scalar(
        select(func.max(InvestigationItem.position)).where(
            InvestigationItem.investigation_id == investigation.id
        )
    )
    return 0 if highest is None else highest + 1


def add_item(db: Session, access: Access, actor: User, new: NewItem) -> InvestigationItem:
    """Add an item at the end. The caller holds the lock and commits."""
    investigation = access.investigation
    if not access.may_edit:
        raise InvestigationForbiddenError()
    _check_item(new.kind, title=new.title, note=new.note, data=new.data)
    if counts(db, investigation).items >= MAX_ITEMS:
        raise TooManyItemsError()
    finding_id = record_id = None
    if new.kind is InvestigationItemKind.FINDING:
        if new.finding is None:
            raise InvalidItemError("A finding item names its finding.")
        finding = findings.get_finding(db, new.finding, actor)
        findings.check_open(finding)
        finding_id = finding.id
    elif new.finding is not None:
        raise InvalidItemError("Only a finding item names a finding.")
    if new.kind is InvestigationItemKind.RECORD:
        if new.record_id is None:
            raise InvalidItemError("A record item names its record.")
        record_id = records.get_record(db, new.record_id).record.id
    elif new.record_id is not None:
        raise InvalidItemError("Only a record item names a record.")
    item = InvestigationItem(
        investigation_id=investigation.id,
        kind=new.kind.value,
        finding_id=finding_id,
        record_id=record_id,
        title=new.title,
        note=new.note,
        data=new.data,
        position=_next_position(db, investigation),
        added_by=actor.id,
    )
    db.add(item)
    if finding_id is not None:
        db.execute(
            insert(InvestigationHeldFinding)
            .values(investigation_id=investigation.id, finding_id=finding_id)
            .on_conflict_do_nothing()
        )
    _touch(investigation)
    db.flush()
    return item


def get_item(db: Session, investigation: Investigation, item_id: int) -> InvestigationItem:
    item = db.scalar(
        select(InvestigationItem).where(
            InvestigationItem.id == item_id, InvestigationItem.investigation_id == investigation.id
        )
    )
    if item is None:
        raise ItemNotFoundError()
    return item


ITEM_EDITABLE = frozenset({"title", "note", "data"})


def update_item(
    db: Session,
    access: Access,
    actor: User,
    item_id: int,
    changes: dict[str, Any],
    content_kinds: Sequence[InvestigationItemKind] = (),
) -> InvestigationItem:
    """Change an item's title, note or data. Its kind and what it points at stay.

    `content_kinds` names the kinds of content the request sent, which must
    be the item's own kind and nothing else. The text of a finding item whose
    finding `actor` isn't shown can't be changed: they are shown it with every
    place hidden (`item_text`), and saving that back would write the
    placeholder over what was written.
    """
    assert set(changes) <= ITEM_EDITABLE, f"not editable: {set(changes) - ITEM_EDITABLE}"
    if not access.may_edit:
        raise InvestigationForbiddenError()
    item = get_item(db, access.investigation, item_id)
    kind = InvestigationItemKind(item.kind)
    if content_kinds and list(content_kinds) != [kind]:
        raise InvalidItemError(f"A {kind} item takes only its own content.")
    if kind is InvestigationItemKind.FINDING and changes.keys() & {"title", "note"}:
        (view,) = item_views(db, [item], actor)
        if view.unavailable is not None:
            raise ItemUnavailableError()
    merged = {"title": item.title, "note": item.note, "data": item.data} | changes
    _check_item(kind, title=merged["title"], note=merged["note"], data=merged["data"])
    for name, value in changes.items():
        setattr(item, name, value)
    _touch(access.investigation)
    db.flush()
    return item


def remove_item(db: Session, access: Access, item_id: int) -> None:
    if not access.may_edit:
        raise InvestigationForbiddenError()
    db.delete(get_item(db, access.investigation, item_id))
    _touch(access.investigation)
    db.flush()


def _ordered(db: Session, investigation: Investigation) -> list[InvestigationItem]:
    return list(
        db.scalars(
            select(InvestigationItem)
            .where(InvestigationItem.investigation_id == investigation.id)
            .order_by(InvestigationItem.position, InvestigationItem.id)
        )
    )


def move_item(db: Session, access: Access, item_id: int, after: int | None) -> InvestigationItem:
    """Put an item straight after the item `after`, or first when `after` is None.

    The places are renumbered from 0. The caller holds the lock, so a move
    made at the same moment by someone else applies after this one, to the
    order this one left.
    """
    if not access.may_edit:
        raise InvestigationForbiddenError()
    ordered = _ordered(db, access.investigation)
    by_id = {item.id: item for item in ordered}
    moving = by_id.get(item_id)
    if moving is None or (after is not None and after not in by_id):
        raise ItemNotFoundError()
    if after == item_id:
        return moving
    rest = [item for item in ordered if item.id != item_id]
    index = 0 if after is None else next(i for i, item in enumerate(rest) if item.id == after) + 1
    rest.insert(index, moving)
    for position, item in enumerate(rest):
        if item.position != position:
            item.position = position
    assert len(rest) == len(ordered), "a move must keep every item"
    _touch(access.investigation)
    db.flush()
    return moving


def list_items(
    db: Session, investigation: Investigation, *, limit: int, cursor: str | None = None
) -> tuple[list[InvestigationItem], str | None]:
    """A page of items in their order."""
    query = select(InvestigationItem).where(InvestigationItem.investigation_id == investigation.id)
    if cursor is not None:
        position, last_id = decode_cursor(cursor, 2)
        position, last_id = cursor_int(position), cursor_int(last_id)
        query = query.where(tuple_(InvestigationItem.position, InvestigationItem.id) > (position, last_id))
    rows = db.scalars(query.order_by(InvestigationItem.position, InvestigationItem.id).limit(limit + 1)).all()
    return paginate(rows, limit, lambda item: [item.position, item.id])


def all_items(db: Session, investigation: Investigation) -> list[InvestigationItem]:
    """Every item in order, for an export. There are at most `MAX_ITEMS`."""
    return _ordered(db, investigation)


# --------------------------------------------------------------------------
# What a viewer sees of each item
# --------------------------------------------------------------------------


class Unavailable(StrEnum):
    # A finding hidden by a moderator, for anyone who may not see hidden findings.
    HIDDEN = "hidden"
    # A finding its finder has withdrawn.
    WITHDRAWN = "withdrawn"
    # A record that has left the index, or a finding that no longer exists.
    GONE = "gone"
    # A saved map view or a height profile near a finding the viewer sees only
    # as a 1 km square: where it is would say where the finding is
    # (`sensitivity.PositionGuard`).
    NEAR_PROTECTED = "near_protected"


@dataclass(frozen=True)
class ItemView:
    item: InvestigationItem
    added_by: User
    # Set only when the viewer may see it.
    finding: Finding | None = None
    finding_author: User | None = None
    record: RecordResult | None = None
    unavailable: Unavailable | None = None


def records_by_id(db: Session, record_ids: Iterable[int]) -> dict[int, RecordResult]:
    """Records from enabled sources, with a point on each, by id."""
    wanted = set(record_ids)
    if not wanted:
        return {}
    rows = db.execute(
        select(Record, Source, func.ST_X(Record.centroid), func.ST_Y(Record.centroid))
        .join(Source, Source.key == Record.source_key)
        .where(Source.enabled, Record.id.in_(wanted))
    )
    return {record.id: RecordResult(record, source, lon, lat) for record, source, lon, lat in rows}


def _finding_unavailable(finding: Finding | None, viewer: User | None) -> Unavailable | None:
    if finding is None:
        return Unavailable.GONE
    if finding.hidden_at is not None and not findings.may_see_hidden(finding, viewer):
        return Unavailable.HIDDEN
    if finding.state == FindingState.WITHDRAWN.value:
        return Unavailable.WITHDRAWN
    return None


def item_views(db: Session, items: Sequence[InvestigationItem], viewer: User | None) -> list[ItemView]:
    """Each item as `viewer` may see it, with what it points at loaded in a few queries."""
    finding_ids = {item.finding_id for item in items if item.finding_id is not None}
    found = (
        {f.id: f for f in db.scalars(select(Finding).where(Finding.id.in_(finding_ids)))}
        if finding_ids
        else {}
    )
    users = findings.users_by_id(
        db, [item.added_by for item in items] + [finding.author_id for finding in found.values()]
    )
    loaded = records_by_id(db, (item.record_id for item in items if item.record_id is not None))
    views: list[ItemView] = []
    for item in items:
        kind = InvestigationItemKind(item.kind)
        added_by = users[item.added_by]
        if kind is InvestigationItemKind.FINDING:
            finding = found.get(item.finding_id) if item.finding_id is not None else None
            missing = _finding_unavailable(finding, viewer)
            if missing is not None:
                views.append(ItemView(item, added_by, unavailable=missing))
            else:
                assert finding is not None
                views.append(
                    ItemView(item, added_by, finding=finding, finding_author=users[finding.author_id])
                )
        elif kind is InvestigationItemKind.RECORD:
            result = loaded.get(item.record_id) if item.record_id is not None else None
            if result is None:
                views.append(ItemView(item, added_by, unavailable=Unavailable.GONE))
            else:
                views.append(ItemView(item, added_by, record=result))
        else:
            views.append(ItemView(item, added_by))
    return views


def item_text(
    view: ItemView, reader: User | None, guard: sensitivity.PositionGuard
) -> tuple[str | None, str | None]:
    """An item's title and note as `reader` may read them.

    What a member writes on a finding item is about that finding, so a
    position written in it is hidden as the finding's own text is
    (`sensitivity.visible_text`), and from everyone once the finding isn't
    shown. Every item's text goes through the investigation's `guard` too.
    """
    item = view.item
    title, note = item.title, item.note
    if InvestigationItemKind(item.kind) is InvestigationItemKind.FINDING:
        title = sensitivity.visible_text(view.finding, reader, title)
        note = sensitivity.visible_text(view.finding, reader, note)
    return guard.text(title), guard.text(note)


def _identifier_address(url: str) -> str | None:
    """A video's or a DOI's address made again from its identifier alone, or None for any other."""
    # Imported here: `unfurl` needs the rate limiter, which needs the sign-in code, which needs this module.
    from fieldclub.services import unfurl

    try:
        address = unfurl.canonical(url)
    except ValidationFailedError:
        return None
    return address.canonical_url if address.provider in unfurl.IDENTIFIER_PROVIDERS else None


def item_content(item: InvestigationItem, guard: sensitivity.PositionGuard) -> dict[str, Any] | None:
    """A view's, reference's or profile's stored content as the guard lets it be read.

    None for a view or profile held back because it lies near a finding the
    reader sees only as a square. A reference keeps its citation without the
    positions in it, and its link only as `sensitivity.visible_url` would
    give it: rebuilt from a video's or a DOI's identifier, or not at all.
    """
    data = dict(item.data or {})
    shape = item_shape(item.kind, data)
    if shape is not None and guard.near(shape):
        return None
    if InvestigationItemKind(item.kind) is InvestigationItemKind.REFERENCE:
        url = data.get("url")
        if url is not None:
            data["url"] = guard.url(url, rebuilt=_identifier_address(url) if guard.hidden else None)
        if data.get("citation") is not None:
            data["citation"] = guard.text(data["citation"])
        return {name: value for name, value in data.items() if value is not None}
    return data


# --------------------------------------------------------------------------
# Account deletion
# --------------------------------------------------------------------------


def forget_account(db: Session, user: User) -> None:
    """Deal with a person's investigations when their account is deleted. The caller commits.

    Their private investigations are deleted, since nobody else could ever
    read them again. Each shared one they own passes to its longest-standing
    editor. One with no editor keeps its owner and stays readable, but
    nobody can manage it any more. Their memberships and invitations elsewhere go.
    """
    owned = db.scalars(select(Investigation).where(Investigation.owner_id == user.id).with_for_update()).all()
    for investigation in owned:
        if Visibility(investigation.visibility) is Visibility.PRIVATE:
            db.delete(investigation)
            continue
        heir = db.scalar(
            select(InvestigationMember)
            .where(
                InvestigationMember.investigation_id == investigation.id,
                InvestigationMember.role == InvestigationRole.EDITOR.value,
                InvestigationMember.accepted_at.is_not(None),
            )
            .order_by(InvestigationMember.accepted_at, InvestigationMember.user_id)
            .limit(1)
        )
        if heir is None:
            continue
        db.execute(
            delete(InvestigationMember).where(
                InvestigationMember.investigation_id == investigation.id,
                InvestigationMember.user_id == user.id,
            )
        )
        heir.role = InvestigationRole.OWNER.value
        investigation.owner_id = heir.user_id
        db.flush()
        check_members(db, investigation)
    db.execute(
        delete(InvestigationMember).where(
            InvestigationMember.user_id == user.id,
            InvestigationMember.role != InvestigationRole.OWNER.value,
        )
    )
    db.flush()
