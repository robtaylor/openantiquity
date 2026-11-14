"""Keeping a marking: handing it on, what happens when its keeper's account goes, and an admin's removal.

A finding's finder is its credit, and never changes. Its keeper is who may
change it (`findings.check_keeper`), and is what passes from one member to
another. `findings.keeper_id` is null while the finder keeps it, so a
version that doesn't know the column goes on working, and
`findings.keeper_of` reads it.

Handing on is an offer and an acceptance (`offer`, `take`). One offer
stands at a time, in `keeping_offered_to` and `keeping_offered_at`. The
keeper may offer, and an admin may offer an orphaned marking. Anyone with
no account under the handle, a deleted account and a banned one are
refused alike with `user_not_found`, so an offer can't tell a member who is
banned. The person offered is told once (`keeping_offered`), and an offer
made again to them while theirs stands tells them nothing new. The
notification names no actor, so an admin's offer reads as a keeper's does.

A marking is orphaned when its keeper's account is deleted or banned.
Deleting an account keeps the keeping with it (`forget_keeping`), clears
the offers made on what it kept and to it, withdraws its pending
suggestions, and tells each admin once how many markings it left without a
keeper (`keeper_gone`). A ban keeps the keeping with the person too, and
clears every offer made to them (`moderation.ban`), so to the keeper it
reads as a refusal, and nothing comes back with the ban lifted to say it
was a ban. Lifting a ban clears the offers made meanwhile on what the
person keeps (`moderation.unban`). Nothing a non-admin is sent says a marking is orphaned,
since that would say its keeper is banned: every refusal a member can meet
here is one that holds whatever the keeper's standing.

An admin finds orphaned markings in a list of their own
(`orphaned_markings`), reads each earlier shape (`shape_history`, the one
route that sends `path_before`), and may take the marking back to one of
them or remove it (`remove_marking`). The finding, its tier, its answers
and its evidence stay. The moderation log records the revisions and never
a shape, because `moderation.log_action` writes its data to the host's log.

Services flush and never commit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.orm import Session, aliased, undefer

from fieldclub.errors import ConflictError, ForbiddenError, UserNotFoundError, ValidationFailedError
from fieldclub.models import Finding, FindingShapeChange, Notification, ShapeSuggestion, User
from fieldclub.schemas.common import int_from_cursor, paginate
from fieldclub.services import activity, findings, moderation, sensitivity, shape_edits, shapes
from fieldclub.vocab import (
    ActivityKind,
    ModerationActionKind,
    ReportTarget,
    Role,
    ShapeChangeKind,
    SuggestionState,
)

logger = logging.getLogger(__name__)

# How many earlier shapes one page of `shape_history` holds.
SHAPES_PAGE = 50


class NotOfferedError(ForbiddenError):
    code = "not_offered"
    message = "This marking hasn't been offered to you."


class AlreadyKeeperError(ValidationFailedError):
    code = "already_keeper"
    message = "They keep this marking already."


class FindingHiddenError(ConflictError):
    code = "finding_hidden"
    message = "A moderator has hidden this finding, so it can't be handed on until it is shown again."


class NoSuchRevisionError(ValidationFailedError):
    code = "no_such_revision"
    message = "There's no earlier shape of this finding with that revision to put back."


class NotOrphanedError(ConflictError):
    code = "not_orphaned"
    message = "This marking's keeper is still a member. A moderator hides it, or bans its keeper, first."


# --------------------------------------------------------------------------
# Who keeps it
# --------------------------------------------------------------------------


def keeper(db: Session, finding: Finding) -> User:
    """The account that keeps the marking, whatever its standing."""
    found = db.get(User, findings.keeper_of(finding))
    assert found is not None, f"finding {finding.public_id} has no keeper"
    return found


def is_orphaned(kept_by: User) -> bool:
    """Whether a marking kept by `kept_by` is orphaned: its keeper is deleted or banned."""
    return kept_by.is_deleted or kept_by.is_banned


def _keeper_column() -> ColumnElement[int]:
    return func.coalesce(Finding.keeper_id, Finding.author_id)


def check_may_offer(finding: Finding, kept_by: User, user: User) -> None:
    """Refuse an offer, or taking one back, from anyone but the keeper or an admin on an orphaned marking.

    A member who isn't the keeper is refused with `not_keeper` whether or not
    the marking is orphaned, so the refusal says nothing of the keeper.
    """
    assert kept_by.has_id(findings.keeper_of(finding)), "the keeper passed is the finding's"
    if user.has_id(kept_by.id):
        return
    if moderation.is_admin(user) and is_orphaned(kept_by):
        return
    raise findings.NotKeeperError()


def offer_stands(finding: Finding, offered_to: User | None) -> bool:
    """Whether the finding's offer stands: one is made, to an account that is neither deleted nor banned.

    Deleting an account and banning one clear the offers made to it, so this
    is for the moment one of those crossed an offer.
    """
    if finding.keeping_offered_to is None:
        return False
    assert offered_to is not None, "the person offered is loaded with the finding"
    assert offered_to.has_id(finding.keeping_offered_to), "the person passed is the one offered"
    return offered_to.is_active


def sees_offer(finding: Finding, kept_by: User, viewer: User | None, offered_to: User | None) -> bool:
    """Whether `viewer` is told of the standing offer: the keeper, the person offered and moderators."""
    active = sensitivity.active_viewer(viewer)
    if active is None or not offer_stands(finding, offered_to):
        return False
    offered = finding.keeping_offered_to
    return (
        active.has_id(kept_by.id)
        or (offered is not None and active.has_id(offered))
        or moderation.is_moderator(active)
    )


def check_not_hidden(finding: Finding) -> None:
    """Refuse to hand on a hidden finding. Only its finder and moderators get this far."""
    if finding.hidden_at is not None:
        raise FindingHiddenError()


def check_offered(finding: Finding, user: User) -> None:
    if finding.keeping_offered_to is None or not user.has_id(finding.keeping_offered_to):
        raise NotOfferedError()


def _member_by_handle(db: Session, handle: str) -> User:
    """An active account by handle. Unknown, deleted and banned are one answer, with one body."""
    found = db.scalar(select(User).where(User.handle == handle))
    if found is None or not found.is_active:
        raise UserNotFoundError()
    return found


# --------------------------------------------------------------------------
# Handing on
# --------------------------------------------------------------------------


def offer(db: Session, finding: Finding, user: User, handle: str, *, now: datetime | None = None) -> None:
    """Offer the keeping of `finding` to the member with `handle`, replacing any offer. Hold the lock.

    The person offered is notified only when the offer is new to them, and
    not while they have an unread notification of an offer of it.
    """
    kept_by = keeper(db, finding)
    check_may_offer(finding, kept_by, user)
    check_not_hidden(finding)
    offered = _member_by_handle(db, handle)
    if offered.has_id(kept_by.id):
        raise AlreadyKeeperError()
    if finding.keeping_offered_to == offered.id:
        return
    finding.keeping_offered_to = offered.id
    finding.keeping_offered_at = now or datetime.now(UTC)
    # Taking an offer back and making it again doesn't tell them again while they haven't read it.
    if not activity.has_unread(db, offered, ActivityKind.KEEPING_OFFERED, finding):
        db.add(
            Notification(user_id=offered.id, kind=ActivityKind.KEEPING_OFFERED.value, finding_id=finding.id)
        )
    db.flush()


def withdraw_offer(db: Session, finding: Finding, user: User) -> None:
    """Take back the standing offer: the keeper, an admin on an orphaned marking, or the person offered."""
    if finding.keeping_offered_to is not None and user.has_id(finding.keeping_offered_to):
        # "No thanks": they have answered it, so a later offer is news to them.
        activity.mark_read_about(db, user, ActivityKind.KEEPING_OFFERED, finding)
        _clear_offer(finding)
        db.flush()
        return
    try:
        check_may_offer(finding, keeper(db, finding), user)
    except findings.NotKeeperError:
        raise NotOfferedError() from None
    _clear_offer(finding)
    db.flush()


def _clear_offer(finding: Finding) -> None:
    finding.keeping_offered_to = None
    finding.keeping_offered_at = None


def take(db: Session, finding: Finding, user: User) -> None:
    """The person offered takes the keeping on. Hold the lock.

    Refused on a withdrawn finding (`finding_withdrawn`), and on a hidden
    one (`finding_hidden`) to those who see it, everyone else having had
    `finding_not_found`. They become the keeper, or the finder keeps it
    again when it is them, the offer clears, their own pending suggestion on
    it is withdrawn, they follow the finding, and its followers are told
    (`keeper_changed`), which names them and nothing of the shape.
    """
    check_offered(finding, user)
    findings.check_open(finding)
    check_not_hidden(finding)
    finding.keeper_id = None if user.has_id(finding.author_id) else user.id
    activity.mark_read_about(db, user, ActivityKind.KEEPING_OFFERED, finding)
    _clear_offer(finding)
    # A keeper changes the shape themselves, so their own suggestion goes.
    db.execute(
        update(ShapeSuggestion)
        .where(
            ShapeSuggestion.finding_id == finding.id,
            ShapeSuggestion.user_id == user.id,
            ShapeSuggestion.state == SuggestionState.PENDING.value,
        )
        .values(state=SuggestionState.WITHDRAWN.value, decided_at=datetime.now(UTC))
        .execution_options(synchronize_session="fetch")
    )
    db.flush()
    findings.follow(db, user, finding)
    activity.record(db, ActivityKind.KEEPER_CHANGED, user, finding)


# --------------------------------------------------------------------------
# When an account goes
# --------------------------------------------------------------------------


def forget_keeping(db: Session, user: User, *, now: datetime | None = None) -> int:
    """What deleting `user`'s account does to keeping. Returns how many markings it left without a keeper.

    The keeping stays with the account, so each marking it kept is orphaned,
    whether or not its finder is still a member. Offers on those markings
    and offers to the account are cleared, and its pending suggestions are
    withdrawn. Each active admin but the person is told once, with the count
    and nothing else, when there is any.
    """
    assert user.id is not None, "the user must be saved"
    now = now or datetime.now(UTC)
    kept = _keeper_column() == user.id
    findings.clear_offers_kept_by(db, user)
    findings.clear_offers_to(db, user)
    db.execute(
        update(ShapeSuggestion)
        .where(ShapeSuggestion.user_id == user.id, ShapeSuggestion.state == SuggestionState.PENDING.value)
        .values(state=SuggestionState.WITHDRAWN.value, decided_at=now)
        .execution_options(synchronize_session="fetch")
    )
    markings = db.scalar(select(func.count()).select_from(Finding).where(kept)) or 0
    if markings:
        admins = db.scalars(
            select(User.id).where(
                User.role == Role.ADMIN.value,
                User.deleted_at.is_(None),
                User.banned_at.is_(None),
                User.id != user.id,
            )
        ).all()
        db.add_all(
            Notification(user_id=admin, kind=ActivityKind.KEEPER_GONE.value, data={"markings": markings})
            for admin in admins
        )
    db.flush()
    return markings


# --------------------------------------------------------------------------
# What admins do with an orphaned marking
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OrphanedMarking:
    finding: Finding
    author: User
    keeper: User


def orphaned_markings(
    db: Session, *, limit: int, cursor: str | None = None
) -> tuple[list[OrphanedMarking], str | None]:
    """Findings whose keeper is deleted or banned, newest first, hidden and withdrawn ones included.

    For admins alone, who see every finding exactly and every hidden one.
    """
    kept_by = aliased(User, name="kept_by")
    query = (
        select(Finding, kept_by)
        .join(kept_by, kept_by.id == _keeper_column())
        .where(or_(kept_by.deleted_at.is_not(None), kept_by.banned_at.is_not(None)))
        .order_by(Finding.id.desc())
    )
    if cursor is not None:
        query = query.where(Finding.id < int_from_cursor(cursor))
    rows = db.execute(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda row: [row[0].id])
    authors = findings.users_by_id(db, (row[0].author_id for row in page))
    return [OrphanedMarking(row[0], authors[row[0].author_id], row[1]) for row in page], next_cursor


def check_orphaned(kept_by: User) -> None:
    if not is_orphaned(kept_by):
        raise NotOrphanedError()


@dataclass(frozen=True)
class EarlierShape:
    """One change to a finding's shape, and the shape before it, which `remove_marking` can put back."""

    change: FindingShapeChange
    by: User
    # The path at `change.revision - 1`. None when there was no shape, or an old outline no path reads.
    path_before: shapes.Path | None
    # Whether `remove_marking` can put that shape back.
    restorable: bool


def _restorable(change: FindingShapeChange) -> bool:
    """Whether the shape before `change` can be put back: a path, or no shape at all.

    A change from no shape is `drawn`. Any other change with no path before
    it was made to an old outline of several parts or with holes, which no
    path can hold.
    """
    return change.path_before is not None or change.kind == ShapeChangeKind.DRAWN.value


def shape_history(
    db: Session, finding: Finding, *, limit: int = SHAPES_PAGE, cursor: str | None = None
) -> tuple[list[EarlierShape], str | None]:
    """Every change to the finding's shape with the shape before it, newest first.

    For admins alone: the one reader of `path_before`.
    """
    query = (
        select(FindingShapeChange)
        .options(undefer(FindingShapeChange.path_before))
        .where(FindingShapeChange.finding_id == finding.id)
        .order_by(FindingShapeChange.revision.desc())
    )
    if cursor is not None:
        query = query.where(FindingShapeChange.revision < int_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda change: [change.revision])
    people = findings.users_by_id(db, (change.user_id for change in page))
    return [
        EarlierShape(
            change=change,
            by=people[change.user_id],
            path_before=shapes.read_path(change.path_before) if change.path_before is not None else None,
            restorable=_restorable(change),
        )
        for change in page
    ], next_cursor


def _shape_at(db: Session, finding: Finding, revision: int) -> shapes.Path | None:
    """The finding's path at an earlier `revision`, None for no shape, or `NoSuchRevisionError`.

    The shape at revision n is the path before the change that made n + 1.
    """
    if not 0 <= revision < finding.shape_revision:
        raise NoSuchRevisionError()
    change = db.scalar(
        select(FindingShapeChange)
        .options(undefer(FindingShapeChange.path_before))
        .where(FindingShapeChange.finding_id == finding.id, FindingShapeChange.revision == revision + 1)
    )
    if change is None or not _restorable(change):
        raise NoSuchRevisionError()
    return shapes.read_path(change.path_before) if change.path_before is not None else None


def remove_marking(
    db: Session,
    finding: Finding,
    admin: User,
    *,
    to_revision: int | None,
    shape_revision: int,
    reason: str,
) -> bool:
    """An admin puts an orphaned marking back to an earlier shape, or removes its shape. Hold the lock.

    Refusals come in this order: `admins_only`, `not_orphaned`,
    `shape_changed`, `no_such_revision`. An earlier shape is never refused
    as too far from the point: within `shapes.SHAPE_MAX_GAP_M` of a point
    the finder placed, the point stays, and otherwise the server places it
    by the restored shape, as for a point nobody placed, and the finding's
    events and its default title follow. The change goes through
    `findings.apply_shape_change` with the admin as its maker, so the anchor
    follows `place_anchor`, the finding's events follow its square, and it
    is reassessed when what lies beyond `looked_at` changed. It isn't held
    to `looked_at`, since an earlier shape may lie outside ground looked at
    since, and `looked_at` is kept. The finding, its tier, its answers and
    its evidence stay. The log row's data is the two revisions and no shape.
    Returns whether the shape changed: putting back the shape it has
    changes nothing and logs nothing.
    """
    moderation.check_admin(admin)
    check_orphaned(keeper(db, finding))
    shape_edits.check_revision(finding, shape_revision)
    path = _shape_at(db, finding, to_revision) if to_revision is not None else None
    from_revision = finding.shape_revision
    if path is not None and not finding.location_derived:
        restored = shapes.shape_of(path)
        if shapes.distance_m(restored.geometry, shape_edits.current_anchor(finding)) > shapes.SHAPE_MAX_GAP_M:
            # A point placed by hand far from the shape being put back, as a keeper who dragged both
            # away leaves it, would make every put-back `outline_too_far`. The server places the
            # point by the restored shape instead, as for a marking whose point nobody placed.
            finding.location_derived = True
    kind = findings.apply_shape_change(
        db, finding, admin, path=path, revision=from_revision, held_to_looked_at=False, unannounced=True
    )
    if kind is None:
        return False
    moderation.log_action(
        db,
        admin,
        ModerationActionKind.REMOVE_MARKING,
        ReportTarget.FINDING,
        finding.id,
        reason,
        {"from_revision": from_revision, "to_revision": to_revision},
    )
    return True
