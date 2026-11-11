"""Request and response shapes for reports, the moderation queue, roles, bans and the log.

Everything here but `ReportIn` and `ReportCreatedOut` is for moderators only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from fieldclub.models import Finding, User
from fieldclub.schemas.common import ApiModel, PublicUser, RequestModel
from fieldclub.schemas.media import REASON_MAX, media_url
from fieldclub.services import moderation
from fieldclub.vocab import ModerationActionKind, ReportReason, ReportStatus, ReportTarget, Role, Sensitivity

NOTE_MAX = 2000
TARGET_REF_MAX = 64


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class ReportIn(RequestModel):
    """A report. `target_id` is a finding's public id, a person's handle, or the id of anything else."""

    target_kind: ReportTarget
    target_id: str = Field(min_length=1, max_length=TARGET_REF_MAX)
    reason: ReportReason
    # Read only by moderators.
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class ResolveIn(RequestModel):
    outcome: Literal["upheld", "dismissed"]
    # Why, for the moderation log. Nobody but moderators reads it.
    note: str = Field(min_length=1, max_length=NOTE_MAX)


class ReasonIn(RequestModel):
    """Why a moderator did this, for the moderation log."""

    reason: str = Field(min_length=1, max_length=REASON_MAX)


class RoleIn(ReasonIn):
    role: Role


class ModSensitivityIn(ReasonIn):
    level: Sensitivity


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------


class ReportCreatedOut(ApiModel):
    """What the reporter is told: that the report was received, and nothing about what happens next."""

    id: int
    target_kind: ReportTarget
    target_id: str
    reason: ReportReason
    created_at: datetime


class TargetFindingOut(ApiModel):
    public_id: str
    title: str
    hidden: bool

    @classmethod
    def build(cls, finding: Finding) -> TargetFindingOut:
        return cls(public_id=finding.public_id, title=finding.title, hidden=finding.hidden_at is not None)


class TargetOut(ApiModel):
    """A reported or moderated thing as it is now, with enough of it to decide."""

    kind: ReportTarget
    id: int
    # How the other routes name it: a public id, a handle or the id. Null once it no longer exists.
    ref: str | None
    exists: bool
    hidden: bool
    # Deleted by its author, a photo refused, or a person who deleted their account.
    removed: bool
    finding: TargetFindingOut | None
    # Who posted it. For a person, the person.
    owner: PublicUser | None
    title: str | None
    body: str | None
    url: str | None
    photo_url: str | None
    created_at: datetime | None

    @classmethod
    def build(cls, summary: moderation.TargetSummary) -> TargetOut:
        return cls(
            kind=summary.kind,
            id=summary.id,
            ref=summary.ref,
            exists=summary.exists,
            hidden=summary.hidden,
            removed=summary.removed,
            finding=TargetFindingOut.build(summary.finding) if summary.finding is not None else None,
            owner=PublicUser.from_user(summary.owner) if summary.owner is not None else None,
            title=summary.title,
            body=summary.body,
            url=summary.url,
            photo_url=media_url(summary.photo_id) if summary.photo_id is not None else None,
            created_at=summary.created_at,
        )


class ReportOut(ApiModel):
    id: int
    created_at: datetime
    reason: ReportReason
    note: str | None
    status: ReportStatus
    reporter: PublicUser
    target: TargetOut
    # Open reports on the same target, this one included.
    open_on_target: int
    # Set while open for a reason the law gives a deadline, such as an intimate image (48 hours).
    due_at: datetime | None
    resolved_by: PublicUser | None
    resolved_at: datetime | None

    @classmethod
    def build(cls, queued: moderation.QueuedReport) -> ReportOut:
        report = queued.report
        return cls(
            id=report.id,
            created_at=report.created_at,
            reason=ReportReason(report.reason),
            note=report.note,
            status=ReportStatus(report.status),
            reporter=PublicUser.from_user(queued.reporter),
            target=TargetOut.build(queued.target),
            open_on_target=queued.open_on_target,
            due_at=queued.due_at,
            resolved_by=PublicUser.from_user(queued.resolver) if queued.resolver is not None else None,
            resolved_at=report.resolved_at,
        )


class ResolvedOut(ApiModel):
    report: ReportOut
    # How many reports this resolved: every open one on the same target.
    resolved: int


class HiddenOut(ApiModel):
    target_kind: ReportTarget
    target_id: str
    hidden: bool
    hidden_at: datetime | None

    @classmethod
    def build(cls, state: moderation.HiddenState) -> HiddenOut:
        return cls(
            target_kind=state.kind,
            target_id=state.ref,
            hidden=state.hidden_at is not None,
            hidden_at=state.hidden_at,
        )


class ModUserOut(ApiModel):
    """A person as moderators see them. The name and picture follow `PublicUser`'s rules."""

    handle: str
    display_name: str
    role: Role
    avatar_url: str | None
    reputation: float
    age_band: str | None
    created_at: datetime
    banned: bool
    banned_at: datetime | None

    @classmethod
    def build(cls, user: User) -> ModUserOut:
        return cls(
            **PublicUser.from_user(user).model_dump(),
            reputation=user.reputation,
            age_band=user.age_band,
            created_at=user.created_at,
            banned=user.is_banned,
            banned_at=user.banned_at,
        )


class BanOut(ApiModel):
    user: ModUserOut
    sessions_ended: int
    # Findings reassessed because the person's work stopped, or started again, counting.
    findings_reassessed: int


class PointSourceOut(ApiModel):
    # Null for points not tied to a finding.
    finding: TargetFindingOut | None
    points: float
    reasons: list[str]
    others: list[PublicUser]


class AssociateOut(ApiModel):
    user: PublicUser
    shared_findings: int


class EligibleOut(ApiModel):
    """A member with fifty points or more who isn't trusted yet, and where the points came from."""

    user: ModUserOut
    sources: list[PointSourceOut]
    # The other people on those findings, most often first. The same few names on every
    # finding is the pattern to look for.
    associates: list[AssociateOut]

    @classmethod
    def build(cls, eligible: moderation.EligibleMember) -> EligibleOut:
        return cls(
            user=ModUserOut.build(eligible.user),
            sources=[
                PointSourceOut(
                    finding=TargetFindingOut.build(s.finding) if s.finding is not None else None,
                    points=s.points,
                    reasons=s.reasons,
                    others=[PublicUser.from_user(u) for u in s.others],
                )
                for s in eligible.sources
            ],
            associates=[
                AssociateOut(user=PublicUser.from_user(a.user), shared_findings=a.shared_findings)
                for a in eligible.associates
            ],
        )


class ActionOut(ApiModel):
    id: int
    created_at: datetime
    actor: PublicUser
    action: ModerationActionKind
    target: TargetOut
    reason: str | None
    data: dict[str, Any] | None

    @classmethod
    def build(cls, logged: moderation.LoggedAction) -> ActionOut:
        entry = logged.entry
        return cls(
            id=entry.id,
            created_at=entry.created_at,
            actor=PublicUser.from_user(logged.actor),
            action=ModerationActionKind(entry.action),
            target=TargetOut.build(logged.target),
            reason=entry.reason,
            data=entry.data,
        )
