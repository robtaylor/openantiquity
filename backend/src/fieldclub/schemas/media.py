"""Request and response shapes for uploaded photos."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from fieldclub.models import Media, User
from fieldclub.schemas.common import ApiModel, PublicUser, RequestModel

REASON_MAX = 1000


def media_url(media_id: int) -> str:
    """Where the browser fetches a photo. Only through the API, never the storage address."""
    return f"/api/v1/media/{media_id}"


class MediaOut(ApiModel):
    """An uploaded photo, as the person who may see it is told about it."""

    id: int
    url: str
    content_type: str
    width: int | None
    height: int | None
    bytes: int
    created_at: datetime
    # Waiting for a moderator or trusted member while false. Nobody else sees it until then.
    approved: bool
    # Refused from the queue. Its file is gone.
    rejected: bool
    hidden: bool

    @classmethod
    def build(cls, media: Media) -> MediaOut:
        return cls(
            id=media.id,
            url=media_url(media.id),
            content_type=media.content_type,
            width=media.width,
            height=media.height,
            bytes=media.bytes,
            created_at=media.created_at,
            approved=media.approved_at is not None,
            rejected=media.rejected_at is not None,
            hidden=media.hidden_at is not None,
        )


class QueuedMediaOut(MediaOut):
    """A photo waiting for approval, with who uploaded it and which findings it is attached to."""

    uploader: PublicUser
    findings: list[str]

    @classmethod
    def build_queued(cls, media: Media, uploader: User, findings: list[str]) -> QueuedMediaOut:
        return cls(
            **MediaOut.build(media).model_dump(), uploader=PublicUser.from_user(uploader), findings=findings
        )


class MediaRejection(RequestModel):
    reason: str = Field(min_length=1, max_length=REASON_MAX)
