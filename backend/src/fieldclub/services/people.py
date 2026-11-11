"""People's public pages: who they are, what they found, and what they helped with.

Deleted and banned accounts answer as not found (`get_person`), whatever
their handle was.

What a page shows of someone in the 16 to 17 band, or who hasn't chosen a
band, follows Decision 0009 through `PublicUser`: the handle and no picture.
Their bio is left out too, because free text on a profile is where contact
details would go.

Blind second looks (Decisions 0008 and 0010). A profile counts and lists the
findings a person took a second look at only to that person. Everyone else
gets no count and an empty list: someone polling a profile would see when an
answer arrived, and the unnamed tier change at that moment would show which
way it went, across every finding the person answers at once. The person sees
them on their own, without a date and in the findings' order. The reputation
anyone else sees leaves out the points an answer earns
(`reputation.ANSWER_REASONS`), which are paid only when it matched how the
finding turned out. The itemised points, and the full total, are for the
person themselves.

Lists leave out findings that are withdrawn, or hidden from the viewer, and
anything deleted. Positions come from `sensitivity.visible_location` for the
viewer, in the schemas.

Services flush and never commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, func, literal, select, tuple_, union_all
from sqlalchemy.orm import Session

from fieldclub.errors import ForbiddenError, InvalidCursorError, NotFoundError
from fieldclub.models import Comment, Evidence, Finding, Mention, Observation, ReputationEvent, User
from fieldclub.schemas.common import cursor_int, decode_cursor, int_from_cursor, paginate
from fieldclub.services import feed, findings, reputation, sensitivity
from fieldclub.services.findings import FindingFilters


class UserNotFoundError(NotFoundError):
    code = "user_not_found"
    message = "There's nobody here with that name."


class PointsArePrivateError(ForbiddenError):
    code = "points_are_private"
    message = "Only the person themselves can see where their points came from."


def get_person(db: Session, handle: str) -> User:
    """The active account with this handle, or `UserNotFoundError`. Handles match without regard to case."""
    user = db.scalar(select(User).where(User.handle == handle.strip()))
    if user is None or not user.is_active:
        raise UserNotFoundError()
    return user


def is_self(person: User, viewer: User | None) -> bool:
    active = sensitivity.active_viewer(viewer)
    return active is not None and active.has_id(person.id)


# --------------------------------------------------------------------------
# The profile
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Counts:
    findings: int
    # For the person themselves. None for everyone else: see the module docstring.
    second_looks: int | None
    evidence: int
    comments: int
    mentions: int


@dataclass(frozen=True)
class Profile:
    person: User
    counts: Counts
    # What anyone may see: the total without the points answers earned.
    reputation: float
    # The full total, for the person themselves. None for everyone else.
    reputation_total: float | None
    is_self: bool


def _count(db: Session, query: Select[*tuple[Any, ...]]) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def _findings_of(person: User, viewer: User | None) -> Select[Finding]:
    return findings.findings_query(viewer, FindingFilters(author=person.handle))


def _on_listed_findings[*Row](query: Select[*Row], finding_id: Any, viewer: User | None) -> Select[*Row]:
    return query.join(Finding, Finding.id == finding_id).where(feed.finding_listed_clause(viewer))


def _second_looks(person: User, viewer: User | None) -> Select[int, int]:
    query = select(Observation.id, Finding.id.label("finding_id")).where(
        Observation.user_id == person.id, Observation.withdrawn_at.is_(None)
    )
    return _on_listed_findings(query, Observation.finding_id, viewer)


def _evidence(person: User, viewer: User | None) -> Select[str, int, int, datetime]:
    query = select(
        literal(ContributionKind.EVIDENCE.value).label("kind"),
        Evidence.id.label("id"),
        Evidence.finding_id.label("finding_id"),
        Evidence.created_at.label("created_at"),
    ).where(Evidence.user_id == person.id, Evidence.deleted_at.is_(None))
    return _on_listed_findings(query, Evidence.finding_id, viewer)


def _comments(person: User, viewer: User | None) -> Select[str, int, int, datetime]:
    query = select(
        literal(ContributionKind.COMMENT.value).label("kind"),
        Comment.id.label("id"),
        Comment.finding_id.label("finding_id"),
        Comment.created_at.label("created_at"),
    ).where(Comment.user_id == person.id, Comment.deleted_at.is_(None))
    return _on_listed_findings(query, Comment.finding_id, viewer)


def _mentions(person: User, viewer: User | None) -> Select[str, int, int, datetime]:
    query = select(
        literal(ContributionKind.MENTION.value).label("kind"),
        Mention.id.label("id"),
        Mention.finding_id.label("finding_id"),
        Mention.created_at.label("created_at"),
    ).where(Mention.user_id == person.id)
    return _on_listed_findings(query, Mention.finding_id, viewer)


def public_reputation(db: Session, person: User) -> float:
    """The person's points without those their answers earned. See the module docstring."""
    answered = db.scalar(
        select(func.coalesce(func.sum(ReputationEvent.delta), 0.0)).where(
            ReputationEvent.user_id == person.id, ReputationEvent.reason.in_(reputation.ANSWER_REASONS)
        )
    )
    # Points are whole or half numbers, so rounding only clears float noise.
    return round(max(0.0, person.reputation - float(answered or 0.0)), 2)


def profile(db: Session, person: User, viewer: User | None) -> Profile:
    mine = is_self(person, viewer)
    counts = Counts(
        findings=_count(db, _findings_of(person, viewer)),
        second_looks=_count(db, _second_looks(person, viewer)) if mine else None,
        evidence=_count(db, _evidence(person, viewer)),
        comments=_count(db, _comments(person, viewer)),
        mentions=_count(db, _mentions(person, viewer)),
    )
    return Profile(
        person=person,
        counts=counts,
        reputation=public_reputation(db, person),
        reputation_total=round(person.reputation, 2) if mine else None,
        is_self=mine,
    )


def list_person_findings(
    db: Session, person: User, viewer: User | None, *, limit: int, cursor: str | None = None
) -> findings.FindingPage:
    """The person's findings, newest first, as `GET /findings?author=` lists them for this viewer."""
    return findings.list_findings(
        db, viewer, FindingFilters(author=person.handle), limit=limit, cursor=cursor
    )


# --------------------------------------------------------------------------
# Contributions
# --------------------------------------------------------------------------


class ContributionKind(StrEnum):
    EVIDENCE = "evidence"
    COMMENT = "comment"
    MENTION = "mention"
    SECOND_LOOK = "second_look"


@dataclass(frozen=True)
class Contribution:
    kind: ContributionKind
    # The row's id: the evidence, comment or mention. None for a second look.
    id: int | None
    # None for a second look. See the module docstring.
    created_at: datetime | None
    finding: Finding
    # The evidence's kind, or the mention's.
    subkind: str | None = None


@dataclass(frozen=True)
class ContributionPage:
    items: list[Contribution]
    next_cursor: str | None


def list_contributions(
    db: Session,
    person: User,
    viewer: User | None,
    *,
    kind: ContributionKind | None = None,
    limit: int,
    cursor: str | None = None,
) -> ContributionPage:
    """What the person helped with on findings this viewer may see.

    Without `kind`: evidence, comments and mentions together, newest first.
    `kind=second_look` lists the findings they took a second look at, newest
    finding first, with no dates, to the person alone. For anyone else it is
    empty, whatever they have answered (see the module docstring).
    """
    if kind is ContributionKind.SECOND_LOOK:
        if not is_self(person, viewer):
            return ContributionPage([], None)
        return _list_second_looks(db, person, viewer, limit=limit, cursor=cursor)
    parts = {
        ContributionKind.EVIDENCE: _evidence,
        ContributionKind.COMMENT: _comments,
        ContributionKind.MENTION: _mentions,
    }
    chosen = [build(person, viewer) for wanted, build in parts.items() if kind is None or kind is wanted]
    rows_of = union_all(*chosen).subquery() if len(chosen) > 1 else chosen[0].subquery()
    key = tuple_(rows_of.c.created_at, rows_of.c.kind, rows_of.c.id)
    query = select(rows_of).order_by(rows_of.c.created_at.desc(), rows_of.c.kind.desc(), rows_of.c.id.desc())
    if cursor is not None:
        query = query.where(key < _contribution_cursor(cursor))
    rows: Sequence[Any] = db.execute(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda row: [row.created_at.isoformat(), row.kind, row.id])
    found = findings_by_id(db, {row.finding_id for row in page})
    subkinds = _subkinds(db, page)
    return ContributionPage(
        [
            Contribution(
                kind=ContributionKind(row.kind),
                id=row.id,
                created_at=row.created_at,
                finding=found[row.finding_id],
                subkind=subkinds.get((row.kind, row.id)),
            )
            for row in page
        ],
        next_cursor,
    )


def _contribution_cursor(cursor: str) -> tuple[datetime, str, int]:
    when, kind, last_id = decode_cursor(cursor, 3)
    if kind not in ContributionKind:
        raise InvalidCursorError()
    last_id = cursor_int(last_id)
    try:
        return datetime.fromisoformat(when), kind, last_id
    except (TypeError, ValueError):
        raise InvalidCursorError() from None


def _subkinds(db: Session, rows: Sequence[Any]) -> dict[tuple[str, int], str]:
    """The kind of each piece of evidence and each mention on the page."""
    wanted: dict[str, list[int]] = {}
    for row in rows:
        wanted.setdefault(row.kind, []).append(row.id)
    found: dict[tuple[str, int], str] = {}
    for kind, model in ((ContributionKind.EVIDENCE, Evidence), (ContributionKind.MENTION, Mention)):
        ids = wanted.get(kind.value)
        if ids:
            for row_id, subkind in db.execute(select(model.id, model.kind).where(model.id.in_(ids))):
                found[(kind.value, row_id)] = subkind
    return found


def _list_second_looks(
    db: Session, person: User, viewer: User | None, *, limit: int, cursor: str | None
) -> ContributionPage:
    query = (
        select(Finding)
        .join(Observation, Observation.finding_id == Finding.id)
        .where(
            Observation.user_id == person.id,
            Observation.withdrawn_at.is_(None),
            feed.finding_listed_clause(viewer),
        )
        .order_by(Finding.id.desc())
    )
    if cursor is not None:
        query = query.where(Finding.id < int_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda finding: [finding.id])
    return ContributionPage(
        [Contribution(ContributionKind.SECOND_LOOK, None, None, finding) for finding in page], next_cursor
    )


def findings_by_id(db: Session, finding_ids: set[int]) -> dict[int, Finding]:
    if not finding_ids:
        return {}
    return {finding.id: finding for finding in db.scalars(select(Finding).where(Finding.id.in_(finding_ids)))}


# --------------------------------------------------------------------------
# Points
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PointsPage:
    events: list[ReputationEvent]
    # The findings the points were for, where the person may still see them.
    findings: dict[int, Finding]
    next_cursor: str | None

    def finding_of(self, event: ReputationEvent) -> Finding | None:
        return self.findings.get(event.finding_id) if event.finding_id is not None else None


def list_points(
    db: Session, person: User, viewer: User | None, *, limit: int, cursor: str | None = None
) -> PointsPage:
    """Where each of the person's points came from, newest first. For the person alone."""
    if not is_self(person, viewer):
        raise PointsArePrivateError()
    query = (
        select(ReputationEvent)
        .where(ReputationEvent.user_id == person.id)
        .order_by(ReputationEvent.id.desc())
    )
    if cursor is not None:
        query = query.where(ReputationEvent.id < int_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    page, next_cursor = paginate(rows, limit, lambda event: [event.id])
    finding_ids = {event.finding_id for event in page if event.finding_id is not None}
    listed: ColumnElement[bool] = feed.finding_listed_clause(person)
    shown = (
        {f.id: f for f in db.scalars(select(Finding).where(Finding.id.in_(finding_ids), listed))}
        if finding_ids
        else {}
    )
    return PointsPage(list(page), shown, next_cursor)
