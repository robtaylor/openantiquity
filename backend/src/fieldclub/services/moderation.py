"""Reports, the moderation queue, hiding, roles, bans and the moderation log.

Targets
=======

A report, a hide and a log entry each name a target by kind and id: a
finding, a comment, a piece of evidence, a mention, a photo, a person or an
investigation (`ReportTarget`). The API names a finding or an investigation
by its public id, a person by their handle and everything else by its
numeric id. `load_target` turns that
reference into the row, and refuses with `target_not_found` anything the
person asking may not see, so a member can't report, or learn of, something
hidden from them.

Hiding
======

A moderator can hide a finding, a comment, a piece of evidence, a mention, a
photo or an investigation, and undo it. Hidden things disappear for everyone
else on the next request:

- a hidden finding is seen only by moderators and its finder, everywhere
  findings are listed or opened (`findings.may_see_hidden`, and
  `records.load_finding`, which allows moderators only);
- a hidden comment reads as removed, with no author and no body, to everyone
  but moderators and its author, and leaves `comment_count`;
- hidden evidence stops counting at once (the finding is reassessed) and
  leaves finding pages, credits and exports for everyone
  (`findings.standing_evidence_clause`);
- a hidden mention leaves `mention_count`, and every mention list, the
  recent feed and profiles for everyone but moderators and whoever added it,
  and holds its address on the finding, so nobody, the channel scan
  included, can add it again while it stays hidden (`services.mentions`);
- a hidden photo is served only to moderators and its uploader
  (`media.may_see_media`);
- a hidden investigation is found only by its members and moderators, and
  leaves the public list and feeds (`investigations.may_read`).

An event a moderator's action causes, such as a tier change after evidence
is hidden, has no actor, so moderators aren't named in feeds.

Bans
====

A ban ends the person's sessions at once, and from then on every request
they make is treated as signed out (`auth.deps`). Their second looks, votes,
evidence and verifications stop counting, and their evidence leaves finding
pages and exports, while the ban lasts: every finding they touched is
reassessed straight away, with no actor. Their square surveys stop counting
too (`squares.counted_clause`), and their events and notifications leave
every list (`services.feed`). Their findings and comments stay,
because other people's work sits on them; a moderator hides any that need
it. Lifting the ban restores everything and reassesses again. Points already
paid stay paid, because there are no penalties: the eligible list shows where
each person's points came from, so a moderator can see points that a ring of
accounts handed one another. Second looks are blind for moderators too
(Decision 0008): the list names the people who answered a finding, and says a
point came from an answer on it, only when the moderator reading it found or
answered that finding. Otherwise points earned by answering are added up in
one source with no finding, `second_looks`.

Roles
=====

A moderator makes a member trusted, puts a trusted member back, and marks an
archaeologist as expert or takes that away. Only an admin makes or unmakes a
moderator. Admins are made outside Field Club, nobody changes their own
role, a banned account's role doesn't change, and a member becomes trusted
only once they have fifty points (Decision 0005). A role changes the weight
of everything the person has done, so their findings are reassessed.

The log
=======

Every action here, and every photo approved or refused, writes one
`moderation_actions` row: who, what, which target, when and why. The log
can't be skipped: the routes members use refuse a moderator what only a
moderator could do there. Lowering a level through
`PUT /findings/{public_id}/sensitivity` is `lower_through_moderation`
(`sensitivity.raise_sensitivity`), and a moderator raising someone else's
level there is logged (`raise_sensitivity`). Only its author deletes a
comment, evidence or a mention (`findings.delete_comment`,
`findings.delete_evidence`, `mentions.remove`), so a moderator hides
someone else's instead.

Nobody moderates their own work. A moderator can't hide, show again or set
the level of what they posted (`own_content`), resolve a report they made or
one about them or their work (`own_report`), and doesn't see those reports
in the queue.

A reporter whose report was dismissed can't report the same thing again for
`REPORT_COOLING_OFF` (`recently_dismissed`), so a few accounts can't keep one
target at the top of the queue.

Reports carry a note only moderators read. Nothing here sends free text to
any one member (Decision 0009): a report's outcome and the moderator's
reason stay in the log.

Services flush and never commit.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.auth.sessions import revoke_all_sessions
from fieldclub.db import is_unique_violation
from fieldclub.errors import (
    ConflictError,
    ForbiddenError,
    MediaNotFoundError,
    NotFoundError,
    ValidationFailedError,
)
from fieldclub.errors import UserNotFoundError as UserNotFoundError
from fieldclub.models import (
    Comment,
    Evidence,
    EvidenceVote,
    Finding,
    Investigation,
    Media,
    Mention,
    ModerationAction,
    Observation,
    Report,
    ReputationEvent,
    User,
)
from fieldclub.schemas.common import PublicUser, int_from_cursor, paginate
from fieldclub.services import findings, ids, investigations, media, sensitivity
from fieldclub.services.reputation import OBSERVATION_CORROBORATED, OBSERVATION_RULED_OUT, TRUSTED_AT
from fieldclub.vocab import (
    MODERATOR_ROLES,
    REPORT_DUE_HOURS,
    ModerationActionKind,
    ReportReason,
    ReportStatus,
    ReportTarget,
    Role,
    Sensitivity,
)

logger = logging.getLogger(__name__)

OPEN_REPORT_CONSTRAINT = "uq_reports_open_per_reporter"
HIDEABLE = frozenset(
    {
        ReportTarget.FINDING,
        ReportTarget.COMMENT,
        ReportTarget.EVIDENCE,
        ReportTarget.MENTION,
        ReportTarget.PHOTO,
        ReportTarget.INVESTIGATION,
    }
)
# Roles a moderator may give or take away. An admin may also give and take `moderator`.
MODERATOR_MANAGED_ROLES = frozenset({Role.MEMBER, Role.TRUSTED, Role.EXPERT})

_NUMERIC_REF = re.compile(r"[1-9][0-9]{0,17}")

# How long after a dismissal the same person can't report the same target again.
REPORT_COOLING_OFF = timedelta(hours=24)
# Reputation reasons that say how the person answered a finding (Decision 0008).
ANSWER_REASONS = frozenset({OBSERVATION_CORROBORATED, OBSERVATION_RULED_OUT})
# The reason on the one source that adds up answer points from findings the reader can't see answers on.
SECOND_LOOKS = "second_looks"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class TargetNotFoundError(NotFoundError):
    code = "target_not_found"
    message = "There's nothing of that kind with that id, or you can't see it."


class AlreadyReportedError(ConflictError):
    code = "already_reported"
    message = "You've already reported this. A moderator will look at it."


class CannotReportSelfError(ValidationFailedError):
    code = "cannot_report_self"
    message = "You can't report your own account."


class ReportNotFoundError(NotFoundError):
    code = "report_not_found"
    message = "There's no report with that id."


class ReportResolvedError(ConflictError):
    code = "report_already_resolved"
    message = "This report has already been dealt with."


class OwnReportError(ForbiddenError):
    code = "own_report"
    message = "Another moderator has to deal with a report you made, or one about you or your work."


class RecentlyDismissedError(ConflictError):
    code = "recently_dismissed"
    message = "A moderator has just looked at your report on this. You can report it again tomorrow."


class OwnContentError(ForbiddenError):
    code = "own_content"
    message = "Another moderator has to deal with something you posted."


class NotHideableError(ValidationFailedError):
    code = "not_hideable"
    message = "A person is banned, not hidden."


class AlreadyHiddenError(ConflictError):
    code = "already_hidden"
    message = "That is already hidden."


class NotHiddenError(ConflictError):
    code = "not_hidden"
    message = "That isn't hidden."


class RoleChangeForbiddenError(ForbiddenError):
    code = "role_change_forbidden"
    message = "You can't make that change to this person's role."


class NotEligibleError(ConflictError):
    code = "not_eligible"
    message = f"A member can be made trusted once they have {TRUSTED_AT:.0f} points."


class UserBannedError(ConflictError):
    code = "user_banned"
    message = "This account is banned. Lift the ban first."


class BanForbiddenError(ForbiddenError):
    code = "ban_forbidden"
    message = "You can't ban or unban this person."


class AlreadyBannedError(ConflictError):
    code = "already_banned"
    message = "This account is already banned."


class NotBannedError(ConflictError):
    code = "not_banned"
    message = "This account isn't banned."


def _now() -> datetime:
    return datetime.now(UTC)


# One rule for who counts as a moderator, beside the rule for who sees a hidden finding.
is_moderator = findings.is_moderator


class ModeratorsOnlyError(ForbiddenError):
    code = "moderators_only"
    message = "Only moderators can do that."


def check_moderator(user: User) -> None:
    """Refuse anyone who isn't a moderator or an admin, as every `/mod` route does."""
    if Role(user.role) not in MODERATOR_ROLES:
        raise ModeratorsOnlyError()


def check_may_set_sensitivity(finding: Finding, moderator: User, level: Sensitivity) -> None:
    """Refuse what `set_sensitivity` refuses, once the route has let a moderator through."""
    if moderator.has_id(finding.author_id):
        raise OwnContentError()
    if not sensitivity.may_change_sensitivity(finding, moderator, level):
        raise sensitivity.SensitivityChangeForbiddenError()


def _require_moderator(user: User) -> User:
    assert is_moderator(user), f"{user.handle} is not an active moderator; the route should have refused"
    return user


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------

_MODELS: dict[ReportTarget, type[Any]] = {
    ReportTarget.FINDING: Finding,
    ReportTarget.COMMENT: Comment,
    ReportTarget.EVIDENCE: Evidence,
    ReportTarget.MENTION: Mention,
    ReportTarget.PHOTO: Media,
    ReportTarget.USER: User,
    ReportTarget.INVESTIGATION: Investigation,
}
assert set(_MODELS) == set(ReportTarget), "every target kind has a table"

TargetRow = Finding | Comment | Evidence | Mention | Media | User | Investigation

# Who posted each kind of target, as a column: see `owner_of`.
_OWNER_COLUMNS: dict[ReportTarget, Any] = {
    ReportTarget.FINDING: Finding.author_id,
    ReportTarget.COMMENT: Comment.user_id,
    ReportTarget.EVIDENCE: Evidence.user_id,
    ReportTarget.MENTION: Mention.user_id,
    ReportTarget.PHOTO: Media.user_id,
    ReportTarget.USER: User.id,
    ReportTarget.INVESTIGATION: Investigation.owner_id,
}
assert set(_OWNER_COLUMNS) == set(ReportTarget), "every target kind has an owner"


@dataclass(frozen=True)
class Target:
    kind: ReportTarget
    row: TargetRow
    # The finding a comment, evidence or mention belongs to. The finding itself for a finding.
    finding: Finding | None

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def owner_id(self) -> int | None:
        return owner_of(self.kind, self.row)


def owner_of(kind: ReportTarget, row: TargetRow) -> int | None:
    """Who posted the target: a finding's finder, a photo's uploader, the person themselves."""
    if isinstance(row, Finding):
        return row.author_id
    if isinstance(row, User):
        return row.id
    if isinstance(row, Investigation):
        return row.owner_id
    return row.user_id


def ref_of(kind: ReportTarget, row: TargetRow) -> str:
    """How the API names a target: a finding's or investigation's public id, a handle, or the id."""
    if isinstance(row, Finding | Investigation):
        return row.public_id
    if isinstance(row, User):
        return row.handle
    return str(row.id)


def _row_by_ref(db: Session, kind: ReportTarget, ref: str) -> TargetRow | None:
    if kind is ReportTarget.FINDING:
        public_id = ids.normalise(ref)
        return db.scalar(select(Finding).where(Finding.public_id == public_id)) if public_id else None
    if kind is ReportTarget.USER:
        return db.scalar(select(User).where(User.handle == ref, User.deleted_at.is_(None)))
    if kind is ReportTarget.INVESTIGATION:
        public_id = ids.normalise(ref)
        return (
            db.scalar(select(Investigation).where(Investigation.public_id == public_id))
            if public_id
            else None
        )
    if not _NUMERIC_REF.fullmatch(ref):
        return None
    return db.get(_MODELS[kind], int(ref))


def _finding_of(db: Session, row: TargetRow) -> Finding | None:
    if isinstance(row, Finding):
        return row
    if isinstance(row, Comment | Evidence | Mention):
        return db.get(Finding, row.finding_id)
    return None


def _sees_hidden(owner_id: int | None, viewer: User | None) -> bool:
    active = sensitivity.active_viewer(viewer)
    return active is not None and (active.has_id(owner_id) or is_moderator(active))


def _visible(db: Session, target: Target, viewer: User | None) -> bool:
    """Whether `viewer` may see the target at all. Moderators see everything that still exists."""
    row, finding = target.row, target.finding
    if isinstance(row, Media):
        return media.may_fetch_media(db, row, viewer)
    if isinstance(row, User):
        return not row.is_deleted
    if finding is not None and finding.hidden_at is not None and not findings.may_see_hidden(finding, viewer):
        return False
    if isinstance(row, Comment):
        return row.deleted_at is None and (row.hidden_at is None or _sees_hidden(row.user_id, viewer))
    if isinstance(row, Evidence):
        if row.deleted_at is not None:
            return False
        standing = db.scalar(select(findings.standing_evidence_clause()).where(Evidence.id == row.id))
        return bool(standing) or is_moderator(viewer)
    if isinstance(row, Mention):
        return row.deleted_at is None and (row.hidden_at is None or _sees_hidden(row.user_id, viewer))
    return True


def load_target(db: Session, kind: ReportTarget | str, ref: str, viewer: User | None) -> Target:
    """The target `ref` names, if `viewer` may see it, or `TargetNotFoundError`."""
    kind = ReportTarget(kind)
    row: TargetRow | None
    if kind is ReportTarget.FINDING:
        # The one finding lookup, so a hidden finding is found by exactly those who may see it.
        try:
            row = findings.get_finding(db, ref, viewer)
        except findings.FindingNotFoundError:
            raise TargetNotFoundError() from None
    elif kind is ReportTarget.INVESTIGATION:
        # The one investigation lookup, so a private or hidden one is found by exactly those who may read it.
        try:
            row = investigations.load(db, ref, viewer).investigation
        except investigations.InvestigationNotFoundError:
            raise TargetNotFoundError() from None
    else:
        row = _row_by_ref(db, kind, ref)
    if row is None:
        raise TargetNotFoundError()
    target = Target(kind, row, _finding_of(db, row))
    if not _visible(db, target, viewer):
        raise TargetNotFoundError()
    return target


@dataclass(frozen=True)
class TargetSummary:
    """Enough of a target for a moderator to decide, whatever state it is in now."""

    kind: ReportTarget
    id: int
    # How the API names it. None when it no longer exists.
    ref: str | None
    exists: bool
    hidden: bool
    # Deleted by its author, a photo refused, or a person who deleted their account.
    removed: bool
    finding: Finding | None = None
    owner: User | None = None
    title: str | None = None
    body: str | None = None
    url: str | None = None
    photo_id: int | None = None
    created_at: datetime | None = None


def _details(row: TargetRow) -> dict[str, Any]:
    """The parts of a target a moderator reads, by kind."""
    if isinstance(row, Finding):
        return {"hidden": row.hidden_at is not None, "title": row.title, "body": row.description}
    if isinstance(row, Comment):
        return {"hidden": row.hidden_at is not None, "removed": row.deleted_at is not None, "body": row.body}
    if isinstance(row, Evidence):
        return {
            "hidden": row.hidden_at is not None,
            "removed": row.deleted_at is not None,
            "title": row.title,
            "body": row.note,
            "url": row.url,
            "photo_id": row.media_id,
        }
    if isinstance(row, Mention):
        return {
            "hidden": row.hidden_at is not None,
            "removed": row.deleted_at is not None,
            "title": row.title,
            "body": row.note,
            "url": row.url,
        }
    if isinstance(row, Media):
        return {
            "hidden": row.hidden_at is not None,
            "removed": row.rejected_at is not None,
            "photo_id": row.id,
        }
    if isinstance(row, Investigation):
        text = "\n\n".join(part for part in (row.summary, row.notes) if part)
        return {"hidden": row.hidden_at is not None, "title": row.title, "body": text or None}
    # A 16 or 17 year old's provider name is shown to nobody, moderators included (Decision 0009):
    # the one public face of a person is `PublicUser`. The bio is what a report may be about.
    return {"removed": row.is_deleted, "title": PublicUser.from_user(row).display_name, "body": row.bio}


def _summary(
    kind: ReportTarget, target_id: int, row: TargetRow | None, finding: Finding | None, owner: User | None
) -> TargetSummary:
    if row is None:
        return TargetSummary(kind, target_id, None, exists=False, hidden=False, removed=True)
    fields: dict[str, Any] = {"hidden": False, "removed": False} | _details(row)
    return TargetSummary(
        kind,
        row.id,
        ref_of(kind, row),
        exists=True,
        finding=finding,
        owner=owner,
        created_at=row.created_at,
        **fields,
    )


def summarise(
    db: Session, pairs: Iterable[tuple[ReportTarget, int]]
) -> dict[tuple[ReportTarget, int], TargetSummary]:
    """A summary of each target, loading each table once."""
    wanted: dict[ReportTarget, set[int]] = defaultdict(set)
    for kind, target_id in pairs:
        wanted[ReportTarget(kind)].add(target_id)
    rows: dict[tuple[ReportTarget, int], TargetRow] = {}
    for kind, target_ids in wanted.items():
        model = _MODELS[kind]
        for row in db.scalars(select(model).where(model.id.in_(target_ids))):
            rows[(kind, row.id)] = row
    finding_ids = {row.finding_id for row in rows.values() if isinstance(row, Comment | Evidence | Mention)}
    loaded = (
        {f.id: f for f in db.scalars(select(Finding).where(Finding.id.in_(finding_ids)))}
        if finding_ids
        else {}
    )
    loaded.update({row.id: row for row in rows.values() if isinstance(row, Finding)})
    owners = findings.users_by_id(
        db, {owner for (kind, _), row in rows.items() if (owner := owner_of(kind, row)) is not None}
    )
    summaries = {}
    for kind, target_ids in wanted.items():
        for target_id in target_ids:
            row = rows.get((kind, target_id))
            finding = None
            if isinstance(row, Finding):
                finding = row
            elif isinstance(row, Comment | Evidence | Mention):
                finding = loaded.get(row.finding_id)
            owner_id = owner_of(kind, row) if row is not None else None
            owner = owners.get(owner_id) if owner_id is not None else None
            summaries[(kind, target_id)] = _summary(kind, target_id, row, finding, owner)
    return summaries


# --------------------------------------------------------------------------
# The log
# --------------------------------------------------------------------------


def log_action(
    db: Session,
    actor: User,
    action: ModerationActionKind,
    kind: ReportTarget,
    target_id: int,
    reason: str | None,
    data: dict[str, Any] | None = None,
) -> ModerationAction:
    entry = ModerationAction(
        actor_id=actor.id,
        action=ModerationActionKind(action).value,
        target_kind=ReportTarget(kind).value,
        target_id=target_id,
        reason=reason,
        data=data,
    )
    db.add(entry)
    db.flush()
    logger.info("%s: %s %s %s %s", actor.handle, action, kind, target_id, data or "")
    return entry


@dataclass(frozen=True)
class LoggedAction:
    entry: ModerationAction
    actor: User
    target: TargetSummary


def list_actions(
    db: Session,
    *,
    kind: ReportTarget | None = None,
    ref: str | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[LoggedAction], str | None]:
    """The moderation log, newest first, optionally for one target."""
    query = select(ModerationAction).order_by(ModerationAction.id.desc())
    if kind is not None:
        query = query.where(ModerationAction.target_kind == kind.value)
        if ref is not None:
            row = _row_by_ref(db, kind, ref)
            if row is None:
                return [], None
            query = query.where(ModerationAction.target_id == row.id)
    if cursor is not None:
        query = query.where(ModerationAction.id < int_from_cursor(cursor))
    entries, next_cursor = paginate(db.scalars(query.limit(limit + 1)).all(), limit, lambda entry: [entry.id])
    actors = findings.users_by_id(db, (entry.actor_id for entry in entries))
    targets = summarise(db, ((ReportTarget(e.target_kind), e.target_id) for e in entries))
    return [
        LoggedAction(e, actors[e.actor_id], targets[(ReportTarget(e.target_kind), e.target_id)])
        for e in entries
    ], next_cursor


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def create_report(
    db: Session,
    reporter: User,
    kind: ReportTarget,
    ref: str,
    reason: ReportReason,
    note: str | None,
    *,
    now: datetime | None = None,
) -> Report:
    """Report something the reporter can see.

    One open report per reporter and target, and none for `REPORT_COOLING_OFF`
    after one of theirs on it was dismissed.
    """
    target = load_target(db, kind, ref, reporter)
    if target.kind is ReportTarget.USER and reporter.has_id(target.id):
        raise CannotReportSelfError()
    dismissed = db.scalar(
        select(Report.id)
        .where(
            Report.reporter_id == reporter.id,
            Report.target_kind == target.kind.value,
            Report.target_id == target.id,
            Report.status == ReportStatus.DISMISSED.value,
            Report.resolved_at > (now or _now()) - REPORT_COOLING_OFF,
        )
        .limit(1)
    )
    if dismissed is not None:
        raise RecentlyDismissedError()
    report = Report(
        reporter_id=reporter.id,
        target_kind=target.kind.value,
        target_id=target.id,
        reason=ReportReason(reason).value,
        note=note,
    )
    try:
        with db.begin_nested():
            db.add(report)
            db.flush()
    except IntegrityError as exc:
        if is_unique_violation(exc, OPEN_REPORT_CONSTRAINT):
            raise AlreadyReportedError() from None
        raise
    return report


def due_at(report: Report) -> datetime | None:
    """When the law expects an open report to have been dealt with, for the reasons that have a deadline."""
    hours = REPORT_DUE_HOURS.get(ReportReason(report.reason))
    if hours is None or report.status != ReportStatus.OPEN.value:
        return None
    return report.created_at + timedelta(hours=hours)


@dataclass(frozen=True)
class QueuedReport:
    report: Report
    reporter: User
    target: TargetSummary
    # Open reports on the same target, this one included.
    open_on_target: int
    due_at: datetime | None
    resolver: User | None


def _involves(moderator: User) -> ColumnElement[bool]:
    """Reports `moderator` made, or about them or something they posted."""
    return or_(
        Report.reporter_id == moderator.id,
        *(
            (Report.target_kind == kind.value)
            & Report.target_id.in_(select(_MODELS[kind].id).where(owner == moderator.id))
            for kind, owner in _OWNER_COLUMNS.items()
        ),
    )


def report_queue(
    db: Session,
    moderator: User,
    *,
    status: ReportStatus = ReportStatus.OPEN,
    reason: ReportReason | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[QueuedReport], str | None]:
    """Reports in one state, oldest first, each with a summary of its target.

    Leaves out the reports `moderator` may not resolve: those they made, and
    those about them or their work.
    """
    _require_moderator(moderator)
    query = select(Report).where(Report.status == status.value, ~_involves(moderator)).order_by(Report.id)
    if reason is not None:
        query = query.where(Report.reason == reason.value)
    if cursor is not None:
        query = query.where(Report.id > int_from_cursor(cursor))
    reports, next_cursor = paginate(db.scalars(query.limit(limit + 1)).all(), limit, lambda r: [r.id])
    return _queued(db, reports), next_cursor


def _queued(db: Session, reports: Sequence[Report]) -> list[QueuedReport]:
    if not reports:
        return []
    pairs = [(ReportTarget(r.target_kind), r.target_id) for r in reports]
    targets = summarise(db, pairs)
    people = findings.users_by_id(
        db, {r.reporter_id for r in reports} | {r.resolved_by for r in reports if r.resolved_by is not None}
    )
    open_counts: dict[tuple[str, int], int] = {
        (kind, target_id): number
        for kind, target_id, number in db.execute(
            select(Report.target_kind, Report.target_id, func.count())
            .where(
                Report.status == ReportStatus.OPEN.value,
                Report.target_id.in_({r.target_id for r in reports}),
            )
            .group_by(Report.target_kind, Report.target_id)
        ).all()
    }
    return [
        QueuedReport(
            report=r,
            reporter=people[r.reporter_id],
            target=targets[(ReportTarget(r.target_kind), r.target_id)],
            open_on_target=open_counts.get((r.target_kind, r.target_id), 0),
            due_at=due_at(r),
            resolver=people.get(r.resolved_by) if r.resolved_by is not None else None,
        )
        for r in reports
    ]


def resolve_report(
    db: Session,
    report_id: int,
    moderator: User,
    outcome: ReportStatus,
    note: str,
    *,
    now: datetime | None = None,
) -> tuple[QueuedReport, int]:
    """Uphold or dismiss a report, and every other open report on the same target.

    Returns the report as the queue shows it, and how many reports were
    resolved. Hiding the target is a separate action.
    """
    _require_moderator(moderator)
    assert outcome is not ReportStatus.OPEN, "a report is resolved as upheld or dismissed"
    report = db.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        raise ReportNotFoundError()
    if report.status != ReportStatus.OPEN.value:
        raise ReportResolvedError()
    kind = ReportTarget(report.target_kind)
    target = summarise(db, [(kind, report.target_id)])[(kind, report.target_id)]
    if moderator.has_id(report.reporter_id) or (
        target.owner is not None and moderator.has_id(target.owner.id)
    ):
        raise OwnReportError()
    now = now or _now()
    resolved = db.scalars(
        update(Report)
        .where(
            Report.target_kind == kind.value,
            Report.target_id == report.target_id,
            Report.status == ReportStatus.OPEN.value,
        )
        .values(status=outcome.value, resolved_by=moderator.id, resolved_at=now)
        .returning(Report.id)
    ).all()
    assert report.id in resolved, "the report being resolved was open"
    log_action(
        db,
        moderator,
        ModerationActionKind.RESOLVE_REPORT,
        kind,
        report.target_id,
        note,
        {"outcome": outcome.value, "reports": sorted(resolved)},
    )
    db.refresh(report)
    (queued,) = _queued(db, [report])
    return queued, len(resolved)


# --------------------------------------------------------------------------
# Hiding
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HiddenState:
    kind: ReportTarget
    ref: str
    hidden_at: datetime | None


def _recount(db: Session, finding_id: int) -> None:
    """Set a finding's comment and mention counts from what is shown."""
    comments = (
        select(func.count())
        .where(Comment.finding_id == finding_id, Comment.deleted_at.is_(None), Comment.hidden_at.is_(None))
        .scalar_subquery()
    )
    mentions = (
        select(func.count())
        .where(Mention.finding_id == finding_id, Mention.deleted_at.is_(None), Mention.hidden_at.is_(None))
        .scalar_subquery()
    )
    db.execute(
        update(Finding).where(Finding.id == finding_id).values(comment_count=comments, mention_count=mentions)
    )


def set_hidden(
    db: Session,
    kind: ReportTarget,
    ref: str,
    moderator: User,
    *,
    hidden: bool,
    reason: str,
    now: datetime | None = None,
) -> HiddenState:
    """Hide a target, or show it again. Takes effect for everyone on the next request."""
    _require_moderator(moderator)
    kind = ReportTarget(kind)
    if kind not in HIDEABLE:
        raise NotHideableError()
    target = load_target(db, kind, ref, moderator)
    if moderator.has_id(target.owner_id):
        raise OwnContentError()
    row, finding = target.row, target.finding
    assert not isinstance(row, User)
    if finding is not None:
        findings.lock(db, finding)
        db.refresh(row)
    elif isinstance(row, Investigation):
        # Every change to an investigation takes its row lock first.
        db.refresh(row, with_for_update=True)
    if (row.hidden_at is not None) == hidden:
        raise AlreadyHiddenError() if hidden else NotHiddenError()
    row.hidden_at = (now or _now()) if hidden else None
    db.flush()
    if isinstance(row, Comment | Mention):
        assert finding is not None
        _recount(db, finding.id)
    elif isinstance(row, Evidence):
        assert finding is not None
        findings.reassess(db, finding, None)
    log_action(
        db,
        moderator,
        ModerationActionKind.HIDE if hidden else ModerationActionKind.UNHIDE,
        kind,
        row.id,
        reason,
    )
    if finding is not None:
        db.refresh(finding)
    return HiddenState(kind, ref_of(kind, row), row.hidden_at)


# --------------------------------------------------------------------------
# Location sensitivity
# --------------------------------------------------------------------------


def set_sensitivity(db: Session, public_id: str, moderator: User, level: Sensitivity, reason: str) -> Finding:
    """A moderator sets a finding's level, lower as well as higher (Decision 0005)."""
    _require_moderator(moderator)
    finding = findings.lock_finding(db, public_id, moderator)
    check_may_set_sensitivity(finding, moderator, level)
    before = finding.sensitivity
    sensitivity.change_sensitivity(db, finding, moderator, level)
    if finding.sensitivity != before:
        log_action(
            db,
            moderator,
            ModerationActionKind.CHANGE_SENSITIVITY,
            ReportTarget.FINDING,
            finding.id,
            reason,
            {"from": before, "to": finding.sensitivity},
        )
    return finding


def raise_sensitivity(db: Session, finding: Finding, actor: User, level: Sensitivity) -> Finding:
    """`PUT /findings/{public_id}/sensitivity`: raise a level, as a finder or trusted member may.

    A moderator who raises the level of someone else's finding here is still
    acting as a moderator, so the change is logged, with no reason, as
    `change_sensitivity`. A finder raising their own isn't logged, whatever
    their role. The caller holds the finding's lock and commits.
    """
    before = finding.sensitivity
    sensitivity.raise_sensitivity(db, finding, actor, level)
    if finding.sensitivity != before and is_moderator(actor) and not actor.has_id(finding.author_id):
        log_action(
            db,
            actor,
            ModerationActionKind.CHANGE_SENSITIVITY,
            ReportTarget.FINDING,
            finding.id,
            None,
            {"from": before, "to": finding.sensitivity},
        )
    return finding


# --------------------------------------------------------------------------
# Photos
# --------------------------------------------------------------------------


def _queued_photo(db: Session, media_id: int, approver: User) -> Media:
    photo = db.scalar(select(Media).where(Media.id == media_id).with_for_update())
    if photo is None or not media.may_see_media(photo, approver):
        raise MediaNotFoundError()
    return photo


def approve_photo(db: Session, media_id: int, approver: User) -> Media:
    """A moderator or trusted member approves a photo, so everyone may see it."""
    photo = _queued_photo(db, media_id, approver)
    already = photo.approved_at is not None
    media.approve_media(db, photo, approver)
    if not already:
        log_action(db, approver, ModerationActionKind.APPROVE_PHOTO, ReportTarget.PHOTO, photo.id, None)
    return photo


def reject_photo(db: Session, media_id: int, approver: User, reason: str) -> Media:
    """A moderator or trusted member refuses a photo waiting for approval.

    The caller commits, then deletes its bytes with `media.delete_files`.
    """
    photo = _queued_photo(db, media_id, approver)
    media.reject_media(db, photo, approver)
    log_action(db, approver, ModerationActionKind.REJECT_PHOTO, ReportTarget.PHOTO, photo.id, reason)
    return photo


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


def get_user(db: Session, handle: str, *, lock: bool = False) -> User:
    query = select(User).where(User.handle == handle, User.deleted_at.is_(None))
    user = db.scalar(query.with_for_update() if lock else query)
    if user is None:
        raise UserNotFoundError()
    return user


def contributed_findings(db: Session, user: User) -> list[int]:
    """Every finding the person marked, answered, added evidence to, voted on or verified, by id."""
    touched = union(
        select(Finding.id).where(Finding.author_id == user.id),
        select(Observation.finding_id).where(Observation.user_id == user.id),
        select(Evidence.finding_id).where((Evidence.user_id == user.id) | (Evidence.verified_by == user.id)),
        select(Evidence.finding_id)
        .join(EvidenceVote, EvidenceVote.evidence_id == Evidence.id)
        .where(EvidenceVote.user_id == user.id),
    ).subquery()
    return sorted(db.scalars(select(touched.c[0])))


def reassess_contributions(db: Session, user: User) -> int:
    """Reassess every finding the person touched, after their weight or standing changed.

    The changes come from a moderator, not from anyone's answer, but the
    events carry no actor so that nobody is named. Findings are locked in id
    order, as every other path that locks several does.
    """
    finding_ids = contributed_findings(db, user)
    for finding_id in finding_ids:
        finding = db.get(Finding, finding_id)
        assert finding is not None
        findings.reassess(db, findings.lock(db, finding), None)
    return len(finding_ids)


def check_role_change(actor: User, target: User, new_role: Role) -> None:
    """Refuse a role change the rules forbid. See the module docstring."""
    _require_moderator(actor)
    current = Role(target.role)
    if actor.has_id(target.id):
        raise RoleChangeForbiddenError("Nobody changes their own role.")
    if Role.ADMIN in (current, new_role):
        raise RoleChangeForbiddenError("Admins are made and unmade outside Field Club.")
    if Role.MODERATOR in (current, new_role) and Role(actor.role) is not Role.ADMIN:
        raise RoleChangeForbiddenError("Only an admin makes or unmakes a moderator.")
    assert {current, new_role} <= MODERATOR_MANAGED_ROLES | {Role.MODERATOR}
    if target.is_banned:
        raise UserBannedError()
    if current is Role.MEMBER and new_role is Role.TRUSTED and target.reputation < TRUSTED_AT:
        raise NotEligibleError()


def change_role(db: Session, handle: str, actor: User, new_role: Role, reason: str) -> User:
    """Give someone a new role, log it, and reassess what they have done. A no-op if it's the same."""
    target = get_user(db, handle, lock=True)
    new_role = Role(new_role)
    check_role_change(actor, target, new_role)
    before = Role(target.role)
    if before is new_role:
        return target
    target.role = new_role.value
    db.flush()
    log_action(
        db,
        actor,
        ModerationActionKind.CHANGE_ROLE,
        ReportTarget.USER,
        target.id,
        reason,
        {"from": before.value, "to": new_role.value},
    )
    reassess_contributions(db, target)
    return target


def check_may_ban(actor: User, target: User) -> None:
    _require_moderator(actor)
    if actor.has_id(target.id):
        raise BanForbiddenError("You can't ban or unban yourself.")
    role = Role(target.role)
    if role is Role.ADMIN:
        raise BanForbiddenError("An admin can't be banned from inside Field Club.")
    if role is Role.MODERATOR and Role(actor.role) is not Role.ADMIN:
        raise BanForbiddenError("Only an admin can ban or unban a moderator.")


@dataclass(frozen=True)
class BanResult:
    user: User
    sessions_ended: int
    findings_reassessed: int


def ban(db: Session, handle: str, actor: User, reason: str, *, now: datetime | None = None) -> BanResult:
    """Ban someone: end their sessions now, and stop their answers, evidence and votes counting."""
    target = get_user(db, handle, lock=True)
    check_may_ban(actor, target)
    if target.is_banned:
        raise AlreadyBannedError()
    target.banned_at = now or _now()
    db.flush()
    ended = revoke_all_sessions(db, target)
    log_action(db, actor, ModerationActionKind.BAN, ReportTarget.USER, target.id, reason, {"sessions": ended})
    return BanResult(target, ended, reassess_contributions(db, target))


def unban(db: Session, handle: str, actor: User, reason: str) -> BanResult:
    """Lift a ban. Their work counts again at once. They sign in again themselves."""
    target = get_user(db, handle, lock=True)
    check_may_ban(actor, target)
    if not target.is_banned:
        raise NotBannedError()
    target.banned_at = None
    db.flush()
    log_action(db, actor, ModerationActionKind.UNBAN, ReportTarget.USER, target.id, reason)
    return BanResult(target, 0, reassess_contributions(db, target))


# --------------------------------------------------------------------------
# Who could be made trusted
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PointSource:
    """Points one person earned from one finding, and who else worked on it."""

    finding: Finding | None
    points: float
    reasons: list[str]
    # Everyone else who marked, answered, added evidence to, voted on or verified it.
    others: list[User]


@dataclass(frozen=True)
class Associate:
    user: User
    # How many of the findings this person's points came from the associate also worked on.
    shared_findings: int


@dataclass(frozen=True)
class EligibleMember:
    user: User
    sources: list[PointSource]
    associates: list[Associate]


def _answers_seen(db: Session, found: Iterable[Finding], viewer: User) -> set[int]:
    """The findings whose answers `viewer` may see: those they found or answered (Decision 0008)."""
    found = list(found)
    mine = {
        obs.finding_id: obs
        for obs in db.scalars(
            select(Observation).where(
                Observation.user_id == viewer.id, Observation.finding_id.in_([f.id for f in found])
            )
        )
    }
    return {f.id for f in found if findings.answers_visible(f, viewer, mine.get(f.id))}


def _people_on(db: Session, finding_ids: set[int], answers_seen: set[int]) -> dict[int, set[int]]:
    """Everyone who worked on each finding, by finding id. Answerers only on `answers_seen`."""
    if not finding_ids:
        return {}
    assert answers_seen <= finding_ids
    rows = union(
        select(Finding.id, Finding.author_id).where(Finding.id.in_(finding_ids)),
        select(Observation.finding_id, Observation.user_id).where(Observation.finding_id.in_(answers_seen)),
        select(Evidence.finding_id, Evidence.user_id).where(Evidence.finding_id.in_(finding_ids)),
        select(Evidence.finding_id, Evidence.verified_by).where(
            Evidence.finding_id.in_(finding_ids), Evidence.verified_by.is_not(None)
        ),
        select(Evidence.finding_id, EvidenceVote.user_id)
        .join(EvidenceVote, EvidenceVote.evidence_id == Evidence.id)
        .where(Evidence.finding_id.in_(finding_ids)),
    )
    people: dict[int, set[int]] = defaultdict(set)
    for finding_id, user_id in db.execute(rows).all():
        people[finding_id].add(user_id)
    return people


def eligible_members(
    db: Session, moderator: User, *, limit: int, cursor: str | None = None
) -> tuple[list[EligibleMember], str | None]:
    """Active members with fifty points or more, in the order they joined, with where the points came from.

    Points can be farmed by a few accounts working together, which is why a
    moderator decides (Decision 0005). Each member comes with the findings
    their points came from, the other people on each, and those people
    counted across all of them, most often first. Who answered a finding, and
    the points someone earned by answering it, are shown only when
    `moderator` found or answered it (see the module docstring).
    """
    _require_moderator(moderator)
    query = (
        select(User)
        .where(
            User.role == Role.MEMBER.value,
            User.reputation >= TRUSTED_AT,
            User.banned_at.is_(None),
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
    )
    if cursor is not None:
        query = query.where(User.id > int_from_cursor(cursor))
    members, next_cursor = paginate(db.scalars(query.limit(limit + 1)).all(), limit, lambda user: [user.id])
    if not members:
        return [], next_cursor
    events = db.scalars(
        select(ReputationEvent)
        .where(ReputationEvent.user_id.in_([m.id for m in members]))
        .order_by(ReputationEvent.id)
    ).all()
    finding_ids = {e.finding_id for e in events if e.finding_id is not None}
    loaded = (
        {f.id: f for f in db.scalars(select(Finding).where(Finding.id.in_(finding_ids)))}
        if finding_ids
        else {}
    )
    answers_seen = _answers_seen(db, loaded.values(), moderator)
    people_on = _people_on(db, finding_ids, answers_seen)
    people = findings.users_by_id(db, {uid for uids in people_on.values() for uid in uids})

    by_member: dict[int, dict[int | None, list[ReputationEvent]]] = defaultdict(lambda: defaultdict(list))
    blind: dict[int, float] = defaultdict(float)
    for event in events:
        if event.reason in ANSWER_REASONS and event.finding_id not in answers_seen:
            blind[event.user_id] += event.delta
        else:
            by_member[event.user_id][event.finding_id].append(event)
    result = []
    for member in members:
        sources: list[PointSource] = []
        if member.id in blind:
            sources.append(
                PointSource(finding=None, points=blind[member.id], reasons=[SECOND_LOOKS], others=[])
            )
        shared: dict[int, int] = defaultdict(int)
        for finding_id, earned in by_member[member.id].items():
            others = sorted(people_on.get(finding_id, set()) - {member.id}) if finding_id is not None else []
            for other in others:
                shared[other] += 1
            sources.append(
                PointSource(
                    finding=loaded.get(finding_id) if finding_id is not None else None,
                    points=sum(e.delta for e in earned),
                    reasons=[e.reason for e in earned],
                    others=[people[uid] for uid in others],
                )
            )
        sources.sort(key=lambda source: -source.points)
        associates = sorted(
            (Associate(people[uid], number) for uid, number in shared.items()),
            key=lambda a: (-a.shared_findings, a.user.id),
        )
        result.append(EligibleMember(member, sources, associates))
    return result, next_cursor
