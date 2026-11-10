"""Helpers for the moderation and media tests. Import as `from tests.moderation.support import ...`."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Comment, Finding, Media, Mention, ModerationAction, User
from fieldclub.services import findings, media
from fieldclub.vocab import MentionKind

API = "/api/v1"
REASON = {"reason": "Breaks the contributor terms."}


def comment(db: Session, finding: Finding, user: User, body: str = "A plain comment.") -> Comment:
    """A comment through the service, committed."""
    made = findings.add_comment(db, finding, user, body)
    db.commit()
    return made


def mention(db: Session, finding: Finding, user: User | None, title: str = "A video about it") -> Mention:
    """A mention row made by hand, as the mentions track would store it, and the count it keeps."""
    made = Mention(
        finding_id=finding.id,
        user_id=user.id if user is not None else None,
        kind=MentionKind.VIDEO.value,
        url=f"https://video.example/{title.replace(' ', '-')}",
        canonical_url=f"https://video.example/{title.replace(' ', '-')}",
        title=title,
    )
    db.add(made)
    finding.mention_count += 1
    db.commit()
    return made


def jpeg(
    width: int = 64, height: int = 48, *, colour: tuple[int, int, int] = (120, 90, 60), **save: Any
) -> bytes:
    """A small JPEG. Extra keywords go to `Image.save`, such as `exif=`."""
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "JPEG", **save)
    return out.getvalue()


def png(width: int = 32, height: int = 32, mode: str = "RGB", **save: Any) -> bytes:
    out = io.BytesIO()
    Image.new(mode, (width, height)).save(out, "PNG", **save)
    return out.getvalue()


def photo(db: Session, user: User, *, approved_by: User | None = None, data: bytes | None = None) -> Media:
    """A photo uploaded through the service, committed, and approved when `approved_by` is given."""
    stored = media.upload(db, user, data or jpeg())
    if approved_by is not None:
        media.approve_media(db, stored, approved_by)
    db.commit()
    return stored


def log_entries(db: Session) -> list[ModerationAction]:
    db.expire_all()
    return list(db.scalars(select(ModerationAction).order_by(ModerationAction.id)))
