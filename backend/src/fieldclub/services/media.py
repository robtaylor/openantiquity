"""Who may see an uploaded photo, and who may approve one.

An uploaded photo isn't shown to other people until a moderator or trusted
member has approved it (Decision 0009). The uploader always sees their own.
The people who may approve photos see unapproved ones too, because they have
to look at a photo to approve it. Every route that returns media goes through
`may_see_media`.

A banned or deleted account is treated as signed out.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from fieldclub.errors import ForbiddenError
from fieldclub.models import Media, User
from fieldclub.vocab import MEDIA_APPROVER_ROLES, Role


class MediaApprovalForbiddenError(ForbiddenError):
    code = "media_approval_forbidden"
    message = "Only a moderator or trusted member can approve a photo, and not their own."


def may_see_media(media: Media, viewer: User | None) -> bool:
    """Whether `viewer` may see `media`. `viewer` is None for the public."""
    if media.approved_at is not None:
        return True
    if viewer is None or not viewer.is_active:
        return False
    return viewer.has_id(media.user_id) or Role(viewer.role) in MEDIA_APPROVER_ROLES


def may_approve_media(media: Media, approver: User | None) -> bool:
    """Whether `approver` may approve `media`. Nobody approves their own upload."""
    if approver is None or not approver.is_active:
        return False
    return Role(approver.role) in MEDIA_APPROVER_ROLES and not approver.has_id(media.user_id)


def approve_media(db: Session, media: Media, approver: User, *, now: datetime | None = None) -> Media:
    """Approve a photo so everyone can see it. The caller commits."""
    if not may_approve_media(media, approver):
        raise MediaApprovalForbiddenError()
    if media.approved_at is None:
        media.approved_at = now or datetime.now(UTC)
        media.approved_by = approver.id
        db.flush()
    return media
