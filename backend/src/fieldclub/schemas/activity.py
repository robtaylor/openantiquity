"""Shapes for the activity feed, notifications and the event stream.

A finding in any of these carries its position as the viewer may see it,
through `schemas.findings.location_out`. Nothing here carries a stored
`activity.location`, a comment's text or an evidence link, any of which
could hold a position or more than the viewer may see.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from fieldclub.models import Activity, Finding, Investigation, Notification, User
from fieldclub.schemas.common import ApiModel, Page, PublicUser, RequestModel
from fieldclub.schemas.findings import Location, location_out
from fieldclub.services import sensitivity
from fieldclub.vocab import ActivityKind, EvidenceKind, FeatureClass, FindingState, StateReason, Tier

# How many notifications one request may mark read by id.
MAX_MARK_IDS = 200
MAX_ID = 2**63 - 1


class ActivityFinding(ApiModel):
    """The finding an event is about, as this viewer may see it."""

    public_id: str
    title: str
    feature_class: FeatureClass
    tier: Tier
    state: FindingState
    location: Location

    @classmethod
    def build(cls, finding: Finding, viewer: User | None) -> ActivityFinding:
        return cls(
            public_id=finding.public_id,
            title=sensitivity.visible_text(finding, viewer, finding.title) or "",
            feature_class=FeatureClass(finding.feature_class),
            tier=Tier(finding.tier),
            state=FindingState(finding.state),
            location=location_out(finding, viewer),
        )


class ActivityInvestigation(ApiModel):
    public_id: str
    title: str


class ActivityDetails(ApiModel):
    """What changed, for the kinds that say. Every field is empty for the others.

    Taken from the row's `data` key by key, so nothing new reaches a client
    until it is named here.
    """

    tier_from: Tier | None = None
    tier_to: Tier | None = None
    state_from: FindingState | None = None
    state_to: FindingState | None = None
    state_reason: StateReason | None = None
    # The item added, for `evidence_added` and `followup_logged`. For
    # `tier_changed`, the item whose adding, removal, vote or verification
    # caused the step, or null: a step a second look caused names none. The
    # item may since have been hidden or removed, so it may not be on the
    # finding's page.
    evidence_id: int | None = None
    evidence_kind: EvidenceKind | None = None
    comment_id: int | None = None
    mention_id: int | None = None

    @classmethod
    def from_data(cls, kind: ActivityKind | str, data: dict[str, Any] | None) -> ActivityDetails:
        kind = ActivityKind(kind)
        data = data or {}
        if kind is ActivityKind.OBSERVATION_ADDED:
            # Decision 0008: a second look's event says nothing about the answer.
            assert not data, "observation_added must carry no data"
            return cls()
        if kind is ActivityKind.TIER_CHANGED:
            # The evidence item that caused the step, when one did. Never one for a second look's step.
            return cls(
                tier_from=data.get("from"), tier_to=data.get("to"), evidence_id=data.get("evidence_id")
            )
        if kind is ActivityKind.STATE_CHANGED:
            return cls(state_from=data.get("from"), state_to=data.get("to"), state_reason=data.get("reason"))
        if kind in (ActivityKind.EVIDENCE_ADDED, ActivityKind.FOLLOWUP_LOGGED):
            return cls(evidence_id=data.get("evidence_id"), evidence_kind=data.get("kind"))
        if kind is ActivityKind.COMMENT_ADDED:
            return cls(comment_id=data.get("comment_id"))
        if kind is ActivityKind.MENTION_ADDED:
            return cls(mention_id=data.get("mention_id"))
        return cls()


class ActivityOut(ApiModel):
    """One event in the feed."""

    id: int
    kind: ActivityKind
    created_at: datetime
    # Null when nobody is credited: a second look (Decision 0008), something
    # the system did, or an account that has been deleted.
    actor: PublicUser | None
    finding: ActivityFinding | None
    investigation: ActivityInvestigation | None
    details: ActivityDetails

    @classmethod
    def build(
        cls,
        activity: Activity,
        actor: User | None,
        finding: Finding | None,
        investigation: Investigation | None,
        viewer: User | None,
        guard: sensitivity.PositionGuard | None = None,
    ) -> ActivityOut:
        """The event as `viewer` reads it. `guard` is the investigation's for the viewer
        (`services.investigations.position_guards`), whose title it passes through as the
        investigation's page does."""
        assert (finding is None) == (activity.finding_id is None), "the finding passed is not the event's"
        assert (investigation is None) == (activity.investigation_id is None), "wrong investigation"
        assert (investigation is None) == (guard is None), "an investigation comes with its guard"
        return cls(
            id=activity.id,
            kind=ActivityKind(activity.kind),
            created_at=activity.created_at,
            actor=PublicUser.from_user(actor) if actor is not None else None,
            finding=ActivityFinding.build(finding, viewer) if finding is not None else None,
            investigation=(
                ActivityInvestigation(
                    public_id=investigation.public_id,
                    title=guard.text(investigation.title) or investigation.title,
                )
                if investigation is not None and guard is not None
                else None
            ),
            details=ActivityDetails.from_data(activity.kind, activity.data),
        )


class NotificationOut(ApiModel):
    id: int
    kind: ActivityKind
    created_at: datetime
    read: bool
    actor: PublicUser | None
    finding: ActivityFinding | None
    # The public id of the investigation an `investigation_invitation` is to.
    # Its title isn't sent: a notification carries no free text (Decision 0009).
    investigation: str | None = None
    details: ActivityDetails

    @classmethod
    def build(
        cls,
        notification: Notification,
        actor: User | None,
        finding: Finding | None,
        viewer: User,
        investigation: Investigation | None = None,
    ) -> NotificationOut:
        assert viewer.has_id(notification.user_id), "a notification goes only to its own account"
        assert (investigation is None) == (notification.investigation_id is None), "wrong investigation"
        return cls(
            id=notification.id,
            kind=ActivityKind(notification.kind),
            created_at=notification.created_at,
            read=notification.read_at is not None,
            actor=PublicUser.from_user(actor) if actor is not None else None,
            finding=ActivityFinding.build(finding, viewer) if finding is not None else None,
            investigation=investigation.public_id if investigation is not None else None,
            details=ActivityDetails.from_data(notification.kind, notification.data),
        )


class NotificationPageOut(Page[NotificationOut]):
    unread_count: int


class MarkRead(RequestModel):
    """Mark notifications read: those listed in `ids`, or with `all`, every one (up to `up_to` if given)."""

    ids: list[int] | None = Field(default=None, min_length=1, max_length=MAX_MARK_IDS)
    all: bool = False
    # The newest notification the person has seen, so one that arrives meanwhile stays unread.
    up_to: int | None = Field(default=None, ge=1, le=MAX_ID)

    @model_validator(mode="after")
    def _one_way(self) -> MarkRead:
        if (self.ids is not None) == self.all:
            raise ValueError("Send either ids or all, not both.")
        if self.up_to is not None and not self.all:
            raise ValueError("up_to goes with all.")
        if self.ids is not None and any(not 1 <= value <= MAX_ID for value in self.ids):
            raise ValueError("Each id is a positive whole number.")
        return self


class MarkReadOut(ApiModel):
    marked: int
    unread_count: int


class StreamEvent(ApiModel):
    """One live event. Public ids and kinds only: fetch the details through the API.

    It carries no position and nothing about an answer, so the client
    refetches through routes that apply the viewer's rights.
    """

    id: int
    kind: ActivityKind
    finding: str | None
    investigation: str | None
    actor: str | None
