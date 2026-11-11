"""Shapes for people's public pages."""

from __future__ import annotations

from datetime import datetime

from fieldclub.models import Finding, ReputationEvent, User
from fieldclub.schemas.activity import ActivityFinding
from fieldclub.schemas.common import ApiModel, PublicUser
from fieldclub.services.people import Contribution, ContributionKind, Profile


class ProfileCounts(ApiModel):
    """What the person has done, counting only what this viewer could list."""

    findings: int
    # The findings they took a second look at, for the person themselves.
    # Null for everyone else (Decisions 0008 and 0010).
    second_looks: int | None
    evidence: int
    comments: int
    mentions: int


class ProfileOut(ApiModel):
    """A person's public page.

    Someone in the 16 to 17 band, or who hasn't chosen a band, shows only
    their handle: `display_name` is the handle, and there is no picture or bio
    (Decision 0009).
    """

    handle: str
    display_name: str
    avatar_url: str | None
    role: str
    bio: str | None
    joined_at: datetime
    # Points that say nothing about how the person answered second looks.
    reputation: float
    # Every point, for the person themselves. Null for everyone else.
    reputation_total: float | None
    counts: ProfileCounts
    is_me: bool

    @classmethod
    def build(cls, found: Profile) -> ProfileOut:
        person = found.person
        public = PublicUser.from_user(person)
        return cls(
            handle=public.handle,
            display_name=public.display_name,
            avatar_url=public.avatar_url,
            role=public.role,
            bio=None if person.shows_handle_only else person.bio,
            joined_at=person.created_at,
            reputation=found.reputation,
            reputation_total=found.reputation_total,
            counts=ProfileCounts(**vars(found.counts)),
            is_me=found.is_self,
        )


class ContributionOut(ApiModel):
    """One thing the person helped with.

    `second_look` says only that they took one: never how, and never when
    (Decision 0008). Its `id` and `created_at` are null. Second looks are
    listed only to the person themselves (Decision 0010).
    """

    kind: ContributionKind
    id: int | None
    created_at: datetime | None
    finding: ActivityFinding
    # The evidence kind, or the mention kind.
    subkind: str | None

    @classmethod
    def build(cls, item: Contribution, viewer: User | None) -> ContributionOut:
        return cls(
            kind=item.kind,
            id=item.id,
            created_at=item.created_at,
            finding=ActivityFinding.build(item.finding, viewer),
            subkind=item.subkind,
        )


class PointOut(ApiModel):
    """One award of points, for the person themselves."""

    id: int
    delta: float
    reason: str
    created_at: datetime
    # Null when the finding has since been hidden, withdrawn or removed.
    finding: ActivityFinding | None

    @classmethod
    def build(cls, event: ReputationEvent, finding: Finding | None, viewer: User) -> PointOut:
        assert viewer.has_id(event.user_id), "points are shown only to the person who earned them"
        return cls(
            id=event.id,
            delta=event.delta,
            reason=event.reason,
            created_at=event.created_at,
            finding=ActivityFinding.build(finding, viewer) if finding is not None else None,
        )
