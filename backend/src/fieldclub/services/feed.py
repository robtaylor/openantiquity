"""The activity feed and each person's notifications: what may be listed, and for whom.

Both read rows that `services.activity.record` wrote, and both list a row
only while what it is about can still be seen:

- an event on a finding that is hidden from this viewer (`findings.not_hidden_clause`)
  or withdrawn is left out,
- an event on an investigation that isn't public is left out, so a private or
  unlisted one never appears, and so is one on an investigation a moderator
  has hidden, but for moderators and its owner,
- an event whose actor is banned is left out, and a deleted actor is shown as
  no one, because the account's name has gone,
- `comment_added`, `evidence_added`, `followup_logged` and `mention_added`
  are left out once the comment, evidence or mention they name in `data`
  (`comment_id`, `evidence_id`, `mention_id`) has been deleted, or hidden from
  this viewer by the rules its own lists follow: a hidden comment or mention
  is still listed for moderators and its author, and hidden evidence for
  nobody.

A notification of an invitation to an investigation (`investigation_id`)
is listed while the person is still invited to it or belongs to it, and
not once a moderator hides it, unless they are a member or a moderator.

`public_event` applies the same rule for a signed-out visitor, and the
event stream uses it to decide what it may announce.

Positions (Decision 0005). `activity.location` is the centre of the
finding's 1 km square for every finding, whatever its level, so filtering by
a box over it can tell nobody more than the square, which everyone may see.
A shrinking box can't narrow a protected finding down to its spot. Responses
never carry that column: a finding's position comes from
`sensitivity.visible_location` for the viewer, at the time of reading.

Blind second looks (Decision 0008). An event a second look caused has no
actor and no data, so it never matches a person filter and names nobody.
Notifications copy the event's actor and data, so the same holds there.

Feeds are newest first by id, with the last id as the cursor.

Services flush and never commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, not_, or_, select, update
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from fieldclub.errors import InvestigationNotFoundError as InvestigationNotFoundError
from fieldclub.models import (
    Activity,
    Comment,
    Evidence,
    Finding,
    Investigation,
    InvestigationMember,
    Mention,
    Notification,
    User,
)
from fieldclub.schemas.common import BBox, int_from_cursor, is_bbox, paginate
from fieldclub.services import findings, geo, ids, mentions
from fieldclub.vocab import ActivityKind, FindingState, Visibility

# The user who did something, as distinct from the viewer.
Actor = aliased(User, name="actor")

# The kinds this version has a name for. A newer version serving beside this
# one during a deploy, or one this version was gone back from, can have stored
# a kind it added. Such a row is never listed, so nothing here has to read it
# (Decision 0033).
_KNOWN_KINDS = tuple(kind.value for kind in ActivityKind)

# The kinds whose row names the thing they were about in `data`, and what it is.
_COMMENT_KINDS = (ActivityKind.COMMENT_ADDED.value,)
_EVIDENCE_KINDS = (ActivityKind.EVIDENCE_ADDED.value, ActivityKind.FOLLOWUP_LOGGED.value)
_MENTION_KINDS = (ActivityKind.MENTION_ADDED.value,)


# --------------------------------------------------------------------------
# What may be listed
# --------------------------------------------------------------------------


def finding_listed_clause(viewer: User | None) -> ColumnElement[bool]:
    """Findings this viewer may see in a list: not hidden from them, and not withdrawn."""
    return and_(findings.not_hidden_clause(viewer), Finding.state != FindingState.WITHDRAWN.value)


def _ref(data: Any, key: str) -> ColumnElement[Any]:
    return data[key].as_integer()


def _content_gone(kind: InstrumentedAttribute[str], data: Any, viewer: User | None) -> ColumnElement[bool]:
    """Rows about a comment, evidence or mention that has been deleted, or hidden from this viewer.

    A hidden comment or mention is still listed for moderators and its
    author, as its finding's page shows it to them. Hidden evidence, and
    evidence by a banned account, leaves pages for everyone, and so leaves
    these lists too (`findings.standing_evidence_clause`).
    """
    comment_shown = exists().where(
        Comment.id == _ref(data, "comment_id"),
        Comment.deleted_at.is_(None),
        findings.shown_clause(Comment.hidden_at, Comment.user_id, viewer),
    )
    evidence_shown = exists().where(
        Evidence.id == _ref(data, "evidence_id"), findings.standing_evidence_clause()
    )
    mention_shown = exists().where(Mention.id == _ref(data, "mention_id"), mentions.shown_clause(viewer))
    return or_(
        and_(kind.in_(_COMMENT_KINDS), not_(comment_shown)),
        and_(kind.in_(_EVIDENCE_KINDS), not_(evidence_shown)),
        # A mention found by the channel scan may name none, so only one that is named is checked.
        and_(kind.in_(_MENTION_KINDS), data.has_key("mention_id"), not_(mention_shown)),
    )


def investigation_listed_clause(viewer: User | None) -> ColumnElement[bool]:
    """Investigations whose events this viewer may see: public, and not hidden from them."""
    return and_(
        Investigation.visibility == Visibility.PUBLIC.value,
        findings.shown_clause(Investigation.hidden_at, Investigation.owner_id, viewer),
    )


def _listed[*Row](
    query: Select[*Row],
    viewer: User | None,
    *,
    kind: InstrumentedAttribute[str],
    data: Any,
    actor_id: InstrumentedAttribute[int | None],
    finding_id: InstrumentedAttribute[int | None],
    investigation: ColumnElement[bool] | None = None,
    investigation_id: InstrumentedAttribute[int | None] | None = None,
) -> Select[*Row]:
    """Join a query over activity or notifications to what its rows are about, and keep what may be listed.

    The query must select from the table the columns belong to. Finding and
    the `Actor` alias are outer-joined, and Investigation too when the table
    has an investigation column, so callers can select them. `investigation`
    says which investigations a row may be about.
    """
    query = query.outerjoin(Finding, Finding.id == finding_id).outerjoin(Actor, Actor.id == actor_id)
    conditions: list[ColumnElement[bool]] = [
        kind.in_(_KNOWN_KINDS),
        or_(finding_id.is_(None), finding_listed_clause(viewer)),
        or_(actor_id.is_(None), Actor.banned_at.is_(None)),
        not_(_content_gone(kind, data, viewer)),
    ]
    if investigation_id is not None:
        assert investigation is not None, "say which investigations may be listed"
        query = query.outerjoin(Investigation, Investigation.id == investigation_id)
        conditions.append(or_(investigation_id.is_(None), investigation))
    return query.where(*conditions)


def _listed_activity[*Row](query: Select[*Row], viewer: User | None) -> Select[*Row]:
    return _listed(
        query,
        viewer,
        kind=Activity.kind,
        data=Activity.data,
        actor_id=Activity.actor_id,
        finding_id=Activity.finding_id,
        investigation=investigation_listed_clause(viewer),
        investigation_id=Activity.investigation_id,
    )


def _shown_actor(actor: User | None) -> User | None:
    """The actor to credit: nobody for a deleted account, which is credited to no one by name."""
    if actor is None or actor.is_deleted:
        return None
    assert not actor.is_banned, "rows by banned actors are filtered out before this"
    return actor


# --------------------------------------------------------------------------
# The feed
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedFilters:
    """Filters for `GET /activity`, already resolved to rows the viewer may see."""

    bbox: BBox | None = None
    kinds: tuple[ActivityKind, ...] = ()
    finding_id: int | None = None
    investigation_id: int | None = None
    actor_id: int | None = None

    def __post_init__(self) -> None:
        assert self.bbox is None or is_bbox(self.bbox), "bbox runs west to east and south to north"


@dataclass(frozen=True)
class FeedItem:
    activity: Activity
    # None when nobody is credited: a second look, the system, or a deleted account.
    actor: User | None
    finding: Finding | None
    investigation: Investigation | None


@dataclass(frozen=True)
class FeedPage:
    items: list[FeedItem]
    next_cursor: str | None


def feed_query(viewer: User | None, filters: FeedFilters) -> Select[Activity, Finding, Investigation, User]:
    """The events this viewer may see, newest first, as (Activity, Finding, Investigation, Actor) rows."""
    query = _listed_activity(select(Activity, Finding, Investigation, Actor), viewer)
    if filters.bbox is not None:
        # The square's centre, never the spot: see the module docstring.
        query = query.where(func.ST_Intersects(Activity.location, geo.envelope(filters.bbox)))
    if filters.kinds:
        query = query.where(Activity.kind.in_([kind.value for kind in filters.kinds]))
    if filters.finding_id is not None:
        query = query.where(Activity.finding_id == filters.finding_id)
    if filters.investigation_id is not None:
        query = query.where(Activity.investigation_id == filters.investigation_id)
    if filters.actor_id is not None:
        query = query.where(Activity.actor_id == filters.actor_id)
    return query.order_by(Activity.id.desc())


def list_feed(
    db: Session, viewer: User | None, filters: FeedFilters, *, limit: int, cursor: str | None = None
) -> FeedPage:
    query = feed_query(viewer, filters)
    if cursor is not None:
        query = query.where(Activity.id < int_from_cursor(cursor))
    rows: Sequence[Any] = db.execute(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda row: [row[0].id])
    return FeedPage(
        [FeedItem(row[0], _shown_actor(row[3]), row[1], row[2]) for row in page],
        next_cursor,
    )


def public_investigation(db: Session, public_id: str, viewer: User | None) -> Investigation:
    """A public investigation not hidden from this viewer, by its public id, or not found."""
    normalised = ids.normalise(public_id)
    if normalised is None:
        raise InvestigationNotFoundError()
    investigation = db.scalar(
        select(Investigation).where(
            Investigation.public_id == normalised, investigation_listed_clause(viewer)
        )
    )
    if investigation is None:
        raise InvestigationNotFoundError()
    return investigation


def public_event(db: Session, activity_id: int) -> Activity | None:
    """The event, if a signed-out visitor's feed lists it, or None.

    For the event stream, which announces only what the public feed lists.
    """
    return db.scalar(_listed_activity(select(Activity), None).where(Activity.id == activity_id))


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NotificationItem:
    notification: Notification
    actor: User | None
    finding: Finding | None
    # The investigation an invitation is to.
    investigation: Investigation | None = None


@dataclass(frozen=True)
class NotificationPage:
    items: list[NotificationItem]
    next_cursor: str | None
    unread_count: int


def _invitation_listed(user: User) -> ColumnElement[bool]:
    """An investigation a notification may name: one the person is still invited to or belongs to.

    An invitation the owner took back, or the person declined, leaves the
    list, and so does one to an investigation a moderator has hidden from them.
    """
    member = exists().where(
        InvestigationMember.investigation_id == Investigation.id, InvestigationMember.user_id == user.id
    )
    if findings.is_moderator(user):
        return member
    joined = exists().where(
        InvestigationMember.investigation_id == Investigation.id,
        InvestigationMember.user_id == user.id,
        InvestigationMember.accepted_at.is_not(None),
    )
    return and_(member, or_(Investigation.hidden_at.is_(None), joined))


def _my_notifications[*Row](query: Select[*Row], user: User) -> Select[*Row]:
    assert user.id is not None, "only a saved user has notifications"
    listed = _listed(
        query,
        user,
        kind=Notification.kind,
        data=Notification.data,
        actor_id=Notification.actor_id,
        finding_id=Notification.finding_id,
        investigation=_invitation_listed(user),
        investigation_id=Notification.investigation_id,
    )
    return listed.where(Notification.user_id == user.id)


def unread_count(db: Session, user: User) -> int:
    """How many of the person's listed notifications are unread."""
    query = _my_notifications(select(func.count()).select_from(Notification), user)
    return db.scalar(query.where(Notification.read_at.is_(None))) or 0


def notifications_query(user: User) -> Select[Notification, Finding, User, Investigation]:
    """The person's listed notifications, newest first, with their finding, actor and investigation."""
    query = select(Notification, Finding, Actor, Investigation)
    return _my_notifications(query, user).order_by(Notification.id.desc())


def list_notifications(db: Session, user: User, *, limit: int, cursor: str | None = None) -> NotificationPage:
    """The person's own notifications, newest first, and how many are unread."""
    query = notifications_query(user)
    if cursor is not None:
        query = query.where(Notification.id < int_from_cursor(cursor))
    rows: Sequence[Any] = db.execute(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda row: [row[0].id])
    return NotificationPage(
        [NotificationItem(row[0], _shown_actor(row[2]), row[1], row[3]) for row in page],
        next_cursor,
        unread_count(db, user),
    )


def mark_read(db: Session, user: User, *, ids: Sequence[int] | None = None, up_to: int | None = None) -> int:
    """Mark the person's notifications read: those in `ids`, or every one up to `up_to`, or all.

    Ids that aren't the person's own are skipped without a word, so the answer
    says nothing about anyone else's. Returns how many changed.
    """
    assert user.id is not None, "only a saved user has notifications"
    assert ids is None or up_to is None, "give ids or up_to, not both"
    statement = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids is not None:
        if not ids:
            return 0
        statement = statement.where(Notification.id.in_(list(ids)))
    if up_to is not None:
        statement = statement.where(Notification.id <= up_to)
    result = db.execute(statement.values(read_at=datetime.now(UTC)))
    db.flush()
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue]
