"""Request and response shapes for mentions.

A mention carries no position. A recent-feed item carries its finding, whose
position comes from `schemas.findings.location_out`, as that viewer may see it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from fieldclub.models import Finding, Mention, User
from fieldclub.schemas.common import ApiModel, PublicUser, RequestModel
from fieldclub.schemas.findings import Location, location_out
from fieldclub.services.mentions import NOTE_MAX, Preview
from fieldclub.services.unfurl import MAX_START_SECONDS, URL_MAX, FetchStatus
from fieldclub.vocab import FeatureClass, FindingState, MentionKind, Tier


class MentionPreviewIn(RequestModel):
    # A web address, or a DOI in any form such as `doi:10.5284/1040209`.
    url: str = Field(min_length=1, max_length=URL_MAX)


class MentionIn(RequestModel):
    url: str = Field(min_length=1, max_length=URL_MAX)
    # Left out, the kind the address looks like: a YouTube link is a video, a DOI a paper.
    kind: MentionKind | None = None
    # Where in a video or podcast the finding comes up. Left out, the start time in the link, if any.
    start_seconds: int | None = Field(default=None, ge=0, le=MAX_START_SECONDS)
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class MentionPreview(ApiModel):
    url: str
    canonical_url: str
    kind: MentionKind
    provider: str
    start_seconds: int | None
    # `ok` when the title and the rest were fetched, `refused` when the address
    # isn't one we fetch, `failed` when it gave nothing. Either way the mention can be saved.
    fetch_status: FetchStatus
    title: str | None
    author_name: str | None
    thumbnail_url: str | None
    published_at: datetime | None

    @classmethod
    def build(cls, found: Preview) -> MentionPreview:
        address, meta = found.address, found.metadata
        return cls(
            url=address.url,
            canonical_url=address.canonical_url,
            kind=address.kind,
            provider=address.provider,
            start_seconds=address.start_seconds,
            fetch_status=found.status,
            title=meta.title,
            author_name=meta.author_name,
            thumbnail_url=meta.thumbnail_url,
            published_at=meta.published_at,
        )


class MentionOut(ApiModel):
    id: int
    kind: MentionKind
    url: str
    canonical_url: str
    provider: str | None
    title: str | None
    # The author, channel or publisher.
    author_name: str | None
    thumbnail_url: str | None
    published_at: datetime | None
    start_seconds: int | None
    note: str | None
    # True when the channel scan found it. Then `added_by` is null.
    auto_detected: bool
    added_by: PublicUser | None
    created_at: datetime
    # True only for the moderators and the adder who still see a hidden mention.
    hidden: bool = False

    @classmethod
    def build(cls, mention: Mention, adder: User | None) -> MentionOut:
        assert (adder is None) == (mention.user_id is None), "pass the adder exactly when there is one"
        assert adder is None or adder.has_id(mention.user_id), "the adder passed did not add this mention"
        return cls(
            id=mention.id,
            kind=MentionKind(mention.kind),
            url=mention.url,
            canonical_url=mention.canonical_url,
            provider=mention.provider,
            title=mention.title,
            author_name=mention.author_name,
            thumbnail_url=mention.thumbnail_url,
            published_at=mention.published_at,
            start_seconds=mention.start_seconds,
            note=mention.note,
            auto_detected=mention.auto_detected,
            added_by=PublicUser.from_user(adder) if adder is not None else None,
            created_at=mention.created_at,
            hidden=mention.hidden_at is not None,
        )


class MentionedFinding(ApiModel):
    """The finding a mention in the recent feed is about. No answers, and the position this viewer may see."""

    public_id: str
    title: str
    feature_class: FeatureClass
    tier: Tier
    state: FindingState
    location: Location
    author: PublicUser

    @classmethod
    def build(cls, finding: Finding, author: User, viewer: User | None) -> MentionedFinding:
        assert author.has_id(finding.author_id), "the author passed is not the finding's author"
        return cls(
            public_id=finding.public_id,
            title=finding.title,
            feature_class=FeatureClass(finding.feature_class),
            tier=Tier(finding.tier),
            state=FindingState(finding.state),
            location=location_out(finding, viewer),
            author=PublicUser.from_user(author),
        )


class RecentMention(MentionOut):
    finding: MentionedFinding
