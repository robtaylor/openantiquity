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

Only a public investigation is ever in a list or a feed. Making one public
records `investigation_published`; making it unlisted or private again
removes that row, so no feed built from `activity` can show it afterwards.

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

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session

from fieldclub.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorisedError,
    ValidationFailedError,
)
from fieldclub.models import (
    Activity,
    Finding,
    Investigation,
    InvestigationItem,
    InvestigationMember,
    Record,
    Source,
    User,
)
from fieldclub.models.common import to_db_geometry
from fieldclub.schemas.common import InvalidCursorError, decode_cursor, int_from_cursor, offset_page, paginate
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


class InvestigationNotFoundError(NotFoundError):
    code = "investigation_not_found"
    message = "There's no investigation with that id."


class InvestigationForbiddenError(ForbiddenError):
    code = "investigation_forbidden"
    message = "Only the investigation's owner or an editor can do that."


class OwnerOnlyError(ForbiddenError):
    code = "investigation_owner_only"
    message = "Only the investigation's owner can do that."


class MemberNotFoundError(NotFoundError):
    code = "member_not_found"
    message = "There's no member with that handle."


class UserNotFoundError(NotFoundError):
    code = "user_not_found"
    message = "There's nobody with that handle."


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
            area=to_db_geometry(area) if area is not None else None,
            visibility=visibility.value,
        ),
        PUBLIC_ID_CONSTRAINT,
    )
    db.add(
        InvestigationMember(
            investigation_id=investigation.id, user_id=owner.id, role=InvestigationRole.OWNER.value
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


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


class Need(StrEnum):
    READ = "read"
    EDIT = "edit"
    OWN = "own"


@dataclass(frozen=True)
class Access:
    """An investigation and the viewer's role in it, None for someone who isn't a member."""

    investigation: Investigation
    role: InvestigationRole | None

    @property
    def may_edit(self) -> bool:
        return self.role in (InvestigationRole.OWNER, InvestigationRole.EDITOR)

    @property
    def is_owner(self) -> bool:
        return self.role is InvestigationRole.OWNER


def role_of(db: Session, investigation: Investigation, viewer: User | None) -> InvestigationRole | None:
    """The viewer's role in the investigation. A banned or deleted account has none."""
    active = sensitivity.active_viewer(viewer)
    if active is None:
        return None
    role = db.scalar(
        select(InvestigationMember.role).where(
            InvestigationMember.investigation_id == investigation.id, InvestigationMember.user_id == active.id
        )
    )
    return InvestigationRole(role) if role is not None else None


def may_read(investigation: Investigation, role: InvestigationRole | None) -> bool:
    """Public and unlisted ones are open to anyone who has the id. A private one only to its owner."""
    if Visibility(investigation.visibility) is Visibility.PRIVATE:
        return role is InvestigationRole.OWNER
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
    access = Access(investigation, role_of(db, investigation, viewer))
    if not may_read(investigation, access.role):
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
        investigation.area = to_db_geometry(changes["area"]) if changes["area"] is not None else None
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


@dataclass(frozen=True)
class Listed:
    investigation: Investigation
    owner: User
    item_count: int


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

    `bbox` matches the area the investigation's editors drew. Unlisted and
    private investigations are only ever listed for their own members.
    """
    query = select(Investigation, User, _item_count()).join(User, User.id == Investigation.owner_id)
    if scope is Scope.MINE:
        active = sensitivity.active_viewer(viewer)
        if active is None:
            raise UnauthorisedError()
        query = query.join(
            InvestigationMember,
            (InvestigationMember.investigation_id == Investigation.id)
            & (InvestigationMember.user_id == active.id),
        )
    else:
        query = query.where(Investigation.visibility == Visibility.PUBLIC.value)
    if bbox is not None:
        query = query.where(func.ST_Intersects(Investigation.area, geo.envelope(bbox)))
    if cursor is not None:
        value, last_id = decode_cursor(cursor, 2)
        if not isinstance(value, str) or not isinstance(last_id, int) or isinstance(last_id, bool):
            raise InvalidCursorError()
        try:
            after = datetime.fromisoformat(value)
        except ValueError:
            raise InvalidCursorError() from None
        query = query.where(tuple_(Investigation.updated_at, Investigation.id) < (after, last_id))
    query = query.order_by(Investigation.updated_at.desc(), Investigation.id.desc()).limit(limit + 1)
    rows = [Listed(investigation, owner, count) for investigation, owner, count in db.execute(query)]
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
        .where(InvestigationMember.investigation_id == investigation.id)
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
    joined_at: datetime


def list_members(
    db: Session, investigation: Investigation, *, limit: int, cursor: str | None = None
) -> tuple[list[MemberView], str | None]:
    """The owner first, then everyone else in the order they joined."""
    offset = 0 if cursor is None else int_from_cursor(cursor)
    rows = db.execute(
        select(User, InvestigationMember.role, InvestigationMember.created_at)
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
    views = [MemberView(user, InvestigationRole(role), joined) for user, role, joined in rows]
    return offset_page(views, offset, limit, max_offset=MAX_MEMBERS)


def find_user(db: Session, handle: str) -> User:
    """The active account with this handle, or `UserNotFoundError`."""
    if has_unstorable_character(handle):
        raise UserNotFoundError()
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None or not user.is_active:
        raise UserNotFoundError()
    return user


def put_member(
    db: Session, access: Access, user: User, role: InvestigationRole | str
) -> tuple[InvestigationMember, bool]:
    """Add `user` with `role`, or change the role they have. True when they were added.

    The owner's call, under the lock. A private investigation takes nobody.
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
    member = add_member(db, investigation, user, role)
    assert member is not None, "the owner was handled above"
    return member, True


def remove_member(db: Session, access: Access, actor: User, user: User) -> None:
    """Remove a member. The owner removes anyone else; anyone else can leave."""
    investigation = access.investigation
    if user.id == investigation.owner_id:
        raise OwnerMembershipError()
    if not (access.is_owner or actor.has_id(user.id)):
        raise OwnerOnlyError()
    member = db.get(InvestigationMember, (investigation.id, user.id))
    if member is None:
        raise MemberNotFoundError()
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
    item_id: int,
    changes: dict[str, Any],
    content_kinds: Sequence[InvestigationItemKind] = (),
) -> InvestigationItem:
    """Change an item's title, note or data. Its kind and what it points at stay.

    `content_kinds` names the kinds of content the request sent, which must
    be the item's own kind and nothing else.
    """
    assert set(changes) <= ITEM_EDITABLE, f"not editable: {set(changes) - ITEM_EDITABLE}"
    if not access.may_edit:
        raise InvestigationForbiddenError()
    item = get_item(db, access.investigation, item_id)
    kind = InvestigationItemKind(item.kind)
    if content_kinds and list(content_kinds) != [kind]:
        raise InvalidItemError(f"A {kind} item takes only its own content.")
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
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (position, last_id)):
            raise InvalidCursorError()
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
