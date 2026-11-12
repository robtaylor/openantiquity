"""Request and response shapes for reports, the moderation queue, roles, bans and the log.

Everything here but `ReportIn` and `ReportCreated` is for moderators only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from fieldclub.models import Finding, User
from fieldclub.schemas.common import ApiModel, PublicUser, RequestModel
from fieldclub.schemas.findings import ActionOut
from fieldclub.schemas.media import REASON_MAX, media_url
from fieldclub.services import moderation
from fieldclub.services.actions import PersonActions
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


class ReportCreated(ApiModel):
    """What the reporter is told: that the report was received, and nothing about what happens next."""

    id: int
    target_kind: ReportTarget
    target_id: str
    reason: ReportReason
    created_at: datetime


class TargetFinding(ApiModel):
    public_id: str
    title: str
    hidden: bool

    @classmethod
    def build(cls, finding: Finding) -> TargetFinding:
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
    finding: TargetFinding | None
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
            finding=TargetFinding.build(summary.finding) if summary.finding is not None else None,
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


class Resolved(ApiModel):
    report: ReportOut
    # How many reports this resolved: every open one on the same target.
    resolved: int


class Hidden(ApiModel):
    target_kind: ReportTarget
    target_id: str
    hidden: bool
    hidden_at: datetime | None

    @classmethod
    def build(cls, state: moderation.HiddenState) -> Hidden:
        return cls(
            target_kind=state.kind,
            target_id=state.ref,
            hidden=state.hidden_at is not None,
            hidden_at=state.hidden_at,
        )


class ModUser(ApiModel):
    """A person as moderators see them. The name follows `PublicUser`'s rules."""

    handle: str
    display_name: str
    role: Role
    reputation: float
    age_band: str | None
    created_at: datetime
    banned: bool
    banned_at: datetime | None

    @classmethod
    def build(cls, user: User) -> ModUser:
        return cls(
            **PublicUser.from_user(user).model_dump(),
            reputation=user.reputation,
            age_band=user.age_band,
            created_at=user.created_at,
            banned=user.is_banned,
            banned_at=user.banned_at,
        )


class RoleActionsOut(ApiModel):
    """Whether the moderator may give the person each role, through `PUT /mod/users/{handle}/role`."""

    member: ActionOut
    trusted: ActionOut
    expert: ActionOut
    moderator: ActionOut
    admin: ActionOut


class PersonActionsOut(ApiModel):
    """What this moderator may do to the person, in the shape a finding page's actions take.

    Each is `{allowed, reason}`, and `reason` is the code the route would
    refuse with, or `current_role` for the role the person has now.
    """

    ban: ActionOut
    unban: ActionOut
    roles: RoleActionsOut

    @classmethod
    def build(cls, actions: PersonActions) -> PersonActionsOut:
        assert set(actions.roles) == set(Role), "every role is answered"
        return cls(
            ban=ActionOut.build(actions.ban),
            unban=ActionOut.build(actions.unban),
            roles=RoleActionsOut(
                **{role.value: ActionOut.build(action) for role, action in actions.roles.items()}
            ),
        )


class ModPerson(ModUser):
    """One person as a moderator sees them, banned and deleted accounts included.

    No email address and no sign-in identities: a moderator acts on the
    account, and never needs to reach the person outside OpenAntiquity.
    """

    # True for an account its owner deleted. Its name has gone, and nothing can be done to it.
    deleted: bool
    actions: PersonActionsOut

    @classmethod
    def build_for(cls, user: User, actions: PersonActions) -> ModPerson:
        return cls(
            **ModUser.build(user).model_dump(),
            deleted=user.is_deleted,
            actions=PersonActionsOut.build(actions),
        )


class Ban(ApiModel):
    user: ModUser
    sessions_ended: int


class PointSourceOut(ApiModel):
    # Null for points not tied to a finding.
    finding: TargetFinding | None
    points: float
    reasons: list[str]
    others: list[PublicUser]


class AssociateOut(ApiModel):
    user: PublicUser
    shared_findings: int


class Eligible(ApiModel):
    """A member with fifty points or more who isn't trusted yet, and where the points came from."""

    user: ModUser
    sources: list[PointSourceOut]
    # The other people on those findings, most often first. The same few names on every
    # finding is the pattern to look for.
    associates: list[AssociateOut]

    @classmethod
    def build(cls, eligible: moderation.EligibleMember) -> Eligible:
        return cls(
            user=ModUser.build(eligible.user),
            sources=[
                PointSourceOut(
                    finding=TargetFinding.build(s.finding) if s.finding is not None else None,
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


class Action(ApiModel):
    id: int
    created_at: datetime
    actor: PublicUser
    action: ModerationActionKind
    target: TargetOut
    reason: str | None
    data: dict[str, Any] | None

    @classmethod
    def build(cls, logged: moderation.LoggedAction) -> Action:
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
