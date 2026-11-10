"""Uploaded photos: cleaning and storing them, who may see one, and who may approve one.

An uploaded photo isn't shown to other people until a moderator or trusted
member has approved it (Decision 0009). The uploader always sees their own.
The people who may approve photos see unapproved ones too, because they have
to look at a photo to approve it. Every route that returns media goes through
`may_see_media`, and `GET /media/{id}` through `may_fetch_media`, which also
applies the position rules of the findings a photo is attached to.

A banned or deleted account is treated as signed out.

Uploads
=======

`clean_image` is the only way bytes from a person reach storage. It refuses
anything Pillow can't identify as a JPEG, PNG or WebP, anything over
`MAX_UPLOAD_BYTES`, anything with more than `MAX_PIXELS` (a decompression
bomb is a small file that claims a huge picture), a picture over `MAX_SIDE`
squared in a file too small to hold a photo of that size
(`MIN_BYTES_PER_PIXEL`), and anything truncated. A multi-picture JPEG, which
many phones write, is read as its first picture. It then copies the pixels
into a new image and encodes that, so no metadata survives: no EXIF, so no
GPS position (which would defeat Decision 0005), no XMP, no ICC profile, no
comments. The EXIF orientation is applied to the pixels first, so a phone
photo stays the right way up. The result is a JPEG, or a PNG when the
picture has transparency, at most `MAX_SIDE` pixels across.

Decoding is the costly part. Pillow holds a colour picture at four bytes a
pixel, and scaling one needs room for a part-scaled copy, so a 49 million
pixel PNG peaks at about 400 MB. A JPEG is decoded at a half, a quarter or an
eighth of its size where that still leaves at least `JPEG_DRAFT_SIDE` pixels
across, which takes a 48 megapixel phone photo to 4000 by 3000 before it is
held in memory. The picture is scaled down before anything else copies it,
and only `DECODE_SLOTS` uploads are decoded at once in the whole process. An
upload that waits longer than `DECODE_WAIT_SECONDS` for its turn is refused
with `uploads_busy`.

Stored files sit under a random 128-bit key in the `media` storage, and the
key is never sent to a client. Photos are served only through the API.

A photo a moderator hides, or one refused from the queue, is never served
again to anyone but moderators and, for a hidden one, its uploader. Refusing
one deletes its bytes. An upload whose cleaned bytes match a refused or
hidden photo is refused (`media_blocked`), which catches a straight re-upload.
"""

from __future__ import annotations

import hashlib
import io
import logging
import secrets
import threading
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime

from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fieldclub.errors import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from fieldclub.models import Evidence, Finding, Media, User
from fieldclub.schemas.common import int_from_cursor, paginate
from fieldclub.services.sensitivity import active_viewer, sees_exact
from fieldclub.storage import Storage, get_storage
from fieldclub.vocab import MEDIA_APPROVER_ROLES, MODERATOR_ROLES, Role

logger = logging.getLogger(__name__)

MEDIA_NAMESPACE = "media"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
# A 48 megapixel phone photo fits. Pillow's own bomb warning starts at about 89.
MAX_PIXELS = 50_000_000
MAX_SIDE = 4096
# A JPEG may be decoded small, but never below this across. Three quarters of MAX_SIDE.
JPEG_DRAFT_SIDE = 3072
JPEG_QUALITY = 85
# A picture bigger than MAX_SIDE squared needs at least this many bytes of file per pixel. A
# phone photo has 0.1 or more; a flat bomb of 7000 by 7000 pixels squeezes into 0.003.
MIN_BYTES_PER_PIXEL = 0.005
# Uploads decoded at the same time in the whole process, and how long one waits for its turn.
DECODE_SLOTS = 1
DECODE_WAIT_SECONDS = 30.0

# What Pillow may read. Everything else, SVG and HEIC included, is refused.
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
# A phone's multi-picture JPEG opens as MPO. Only its first picture is read.
MULTI_PICTURE_JPEG = "MPO"
# Modes Pillow scales well as they are. Anything else becomes colour first.
_SCALES_AS_IS = frozenset({"RGB", "RGBA", "L", "LA"})
# What is stored, and so the only content types ever served.
SERVED_TYPES = {"image/jpeg": "jpg", "image/png": "png"}

_ORIENTATION_TAG = 0x0112
_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


class MediaApprovalForbiddenError(ForbiddenError):
    code = "media_approval_forbidden"
    message = "Only a moderator or trusted member can approve a photo, and not their own."


class MediaRejectionForbiddenError(ForbiddenError):
    code = "media_rejection_forbidden"
    message = "Only a moderator or trusted member can refuse a photo, and not their own."


class MediaNotFoundError(NotFoundError):
    code = "media_not_found"
    message = "There's no photo with that id."


class MediaAlreadyDecidedError(ConflictError):
    code = "media_already_decided"
    message = "This photo has already been approved or refused."


class NotAnImageError(ValidationFailedError):
    code = "not_an_image"
    message = "That file isn't a photo we can read. Send a JPEG, PNG or WebP image."


class UnsupportedImageError(AppError):
    status_code = 415
    code = "unsupported_image"
    message = "Send a JPEG, PNG or WebP image."


class ImageTooLargeError(AppError):
    status_code = 413
    code = "image_too_large"
    message = f"A photo can be at most {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."


class ImageTooManyPixelsError(AppError):
    status_code = 413
    code = "image_too_many_pixels"
    message = f"A photo can have at most {MAX_PIXELS // 1_000_000} million pixels."


class UploadsBusyError(AppError):
    status_code = 503
    code = "uploads_busy"
    message = "Too many photos are being uploaded at once. Try again in a minute."


class MediaBlockedError(ValidationFailedError):
    code = "media_blocked"
    message = "This photo has been removed from Field Club and can't be uploaded again."


# --------------------------------------------------------------------------
# Who sees what
# --------------------------------------------------------------------------


def _is_moderator(viewer: User | None) -> bool:
    return viewer is not None and Role(viewer.role) in MODERATOR_ROLES


def may_see_media(media: Media, viewer: User | None) -> bool:
    """Whether `viewer` may see `media`. `viewer` is None for the public.

    A refused photo has no bytes, so nobody sees it. A hidden one is seen only
    by moderators and its uploader.
    """
    if media.rejected_at is not None:
        return False
    active = active_viewer(viewer)
    if media.hidden_at is not None:
        return active is not None and (active.has_id(media.user_id) or _is_moderator(active))
    if media.approved_at is not None:
        return True
    if active is None:
        return False
    return active.has_id(media.user_id) or Role(active.role) in MEDIA_APPROVER_ROLES


def may_fetch_media(db: Session, media: Media, viewer: User | None) -> bool:
    """Whether `viewer` may download the photo itself, through `GET /media/{id}`.

    `may_see_media`, and for anyone but its uploader and moderators also:
    the uploader isn't banned, and every finding the photo is attached to is
    one this viewer may open and whose exact position they see. A photo of a
    protected site shows where it is as well as a grid reference does, so
    finding pages already leave it out for those viewers (Decision 0005).
    """
    if not may_see_media(media, viewer):
        return False
    active = active_viewer(viewer)
    if active is not None and (active.has_id(media.user_id) or _is_moderator(active)):
        return True
    uploader = db.get(User, media.user_id)
    if uploader is None or uploader.is_banned:
        return False
    attached = db.execute(
        select(Evidence.hidden_at, Finding)
        .join(Finding, Finding.id == Evidence.finding_id)
        .where(Evidence.media_id == media.id)
    ).all()
    for hidden_at, finding in attached:
        if hidden_at is not None or finding.hidden_at is not None or not sees_exact(finding, active):
            return False
    return True


def may_approve_media(media: Media, approver: User | None) -> bool:
    """Whether `approver` may approve, or refuse, `media`. Nobody decides on their own upload."""
    active = active_viewer(approver)
    if active is None:
        return False
    return Role(active.role) in MEDIA_APPROVER_ROLES and not active.has_id(media.user_id)


def approve_media(db: Session, media: Media, approver: User, *, now: datetime | None = None) -> Media:
    """Approve a photo so everyone can see it. The caller commits."""
    if not may_approve_media(media, approver):
        raise MediaApprovalForbiddenError()
    if media.rejected_at is not None:
        raise MediaAlreadyDecidedError()
    if media.approved_at is None:
        media.approved_at = now or datetime.now(UTC)
        media.approved_by = approver.id
        db.flush()
    return media


def reject_media(
    db: Session, media: Media, approver: User, *, storage: Storage | None = None, now: datetime | None = None
) -> Media:
    """Refuse a photo waiting for approval and delete its bytes. The caller commits.

    An approved photo is hidden by a moderator instead, so that the decision
    can be undone.
    """
    if not may_approve_media(media, approver):
        raise MediaRejectionForbiddenError()
    if media.approved_at is not None or media.rejected_at is not None:
        raise MediaAlreadyDecidedError()
    media.rejected_at = now or datetime.now(UTC)
    media.rejected_by = approver.id
    db.flush()
    (storage or media_storage()).delete(media.storage_key)
    return media


# --------------------------------------------------------------------------
# Uploading
# --------------------------------------------------------------------------


def media_storage() -> Storage:
    return get_storage(MEDIA_NAMESPACE)


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    content_type: str
    width: int
    height: int

    @property
    def extension(self) -> str:
        return SERVED_TYPES[self.content_type]


def _orientation(image: Image.Image) -> int:
    try:
        value = image.getexif().get(_ORIENTATION_TAG, 1)
    except (OSError, ValueError, SyntaxError, KeyError, TypeError):
        # Unreadable EXIF is dropped with the rest of it.
        logger.info("An upload had EXIF that couldn't be read; it is discarded")
        return 1
    return value if isinstance(value, int) else 1


_decode_slots = threading.BoundedSemaphore(DECODE_SLOTS)


def _fitted(size: tuple[int, int], side: int) -> tuple[int, int]:
    """`size` scaled to fit in a `side` square, keeping its shape."""
    width, height = size
    scale = min(1.0, side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _open(raw: bytes) -> Image.Image:
    """Open and fully decode an upload, refusing what isn't a whole, modest image of an accepted kind.

    A JPEG is decoded at the smallest of a half, a quarter or an eighth of
    its size that is still `JPEG_DRAFT_SIDE` across.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageTooLargeError()
    if not raw:
        raise NotAnImageError()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(io.BytesIO(raw), formats=sorted(ACCEPTED_FORMATS))
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ImageTooManyPixelsError() from None
        except UnidentifiedImageError:
            raise NotAnImageError() from None
        except (OSError, ValueError, SyntaxError):
            raise NotAnImageError() from None
        width, height = image.size
        if width < 1 or height < 1:
            raise NotAnImageError()
        pixels = width * height
        if pixels > MAX_PIXELS:
            raise ImageTooManyPixelsError()
        if pixels > MAX_SIDE * MAX_SIDE and len(raw) < pixels * MIN_BYTES_PER_PIXEL:
            raise ImageTooManyPixelsError(
                "A picture this big can't fit in so small a file. Send a smaller one."
            )
        if image.format == MULTI_PICTURE_JPEG:
            # The first picture is the photo. The others are previews or depth maps.
            image.seek(0)
        elif getattr(image, "n_frames", 1) != 1:
            raise UnsupportedImageError("Send a still image, not an animation.")
        if image.format in ("JPEG", MULTI_PICTURE_JPEG):
            image.draft("RGB", _fitted(image.size, JPEG_DRAFT_SIDE))
        try:
            image.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            # Truncated or corrupt data fails here, once the pixels are decoded.
            raise NotAnImageError() from None
    assert image.format in ACCEPTED_FORMATS | {MULTI_PICTURE_JPEG}, (
        f"Pillow opened a {image.format} it was told not to"
    )
    return image


def _in_mode(image: Image.Image, mode: str) -> Image.Image:
    if image.mode == mode:
        return image
    try:
        return image.convert(mode)
    except ValueError:
        # A mode Pillow can't turn into colour, such as some 16-bit greyscale.
        raise UnsupportedImageError() from None


def clean_image(raw: bytes) -> CleanImage:
    """The upload as a fresh JPEG or PNG with no metadata at all, or an `AppError` saying why not.

    Waits for one of the `DECODE_SLOTS`, or refuses with `uploads_busy`.
    """
    if not _decode_slots.acquire(timeout=DECODE_WAIT_SECONDS):
        raise UploadsBusyError()
    try:
        return _clean(raw)
    finally:
        _decode_slots.release()


def _clean(raw: bytes) -> CleanImage:
    image = _open(raw)
    transpose = _TRANSPOSE.get(_orientation(image))
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    mode = "RGBA" if has_alpha else "RGB"
    if image.mode not in _SCALES_AS_IS:
        # Pillow scales a palette or one-bit picture by picking pixels, which looks ragged.
        image = _in_mode(image, mode)
    if max(image.size) > MAX_SIDE:
        # Scaled before anything copies it, so no copy of the full-sized picture is made.
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    image = _in_mode(image, mode)
    if transpose is not None:
        image = image.transpose(transpose)
    # A new image with the pixels alone, so nothing in `info` can be carried into the file.
    clean = Image.new(image.mode, image.size)
    clean.paste(image)
    assert not clean.info, "a fresh image carries no metadata"
    assert max(clean.size) <= MAX_SIDE, f"scaled to {clean.size}"
    out = io.BytesIO()
    if has_alpha:
        clean.save(out, "PNG", optimize=True)
        content_type = "image/png"
    else:
        clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        content_type = "image/jpeg"
    return CleanImage(data=out.getvalue(), content_type=content_type, width=clean.width, height=clean.height)


def _blocked(db: Session, sha256: str) -> bool:
    return (
        db.scalar(
            select(Media.id)
            .where(Media.sha256 == sha256, or_(Media.rejected_at.is_not(None), Media.hidden_at.is_not(None)))
            .limit(1)
        )
        is not None
    )


def upload(db: Session, user: User, raw: bytes, *, storage: Storage | None = None) -> Media:
    """Clean an upload, store it under a key nobody can guess, and record it unapproved.

    The caller commits.
    """
    cleaned = clean_image(raw)
    sha256 = hashlib.sha256(cleaned.data).hexdigest()
    if _blocked(db, sha256):
        raise MediaBlockedError()
    storage = storage or media_storage()
    key = f"{secrets.token_hex(16)}.{cleaned.extension}"
    storage.put(key, cleaned.data, cleaned.content_type)
    media = Media(
        user_id=user.id,
        storage_key=key,
        content_type=cleaned.content_type,
        width=cleaned.width,
        height=cleaned.height,
        bytes=len(cleaned.data),
        sha256=sha256,
    )
    try:
        db.add(media)
        db.flush()
    except BaseException:
        storage.delete(key)
        raise
    return media


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def get_media(db: Session, media_id: int, viewer: User | None) -> Media:
    """The photo with this id, if `viewer` may download it, or `MediaNotFoundError`.

    Nobody learns that a photo they may not see exists: it is the same 404 as
    an id that was never used.
    """
    media = db.get(Media, media_id)
    if media is None or not may_fetch_media(db, media, viewer):
        raise MediaNotFoundError()
    return media


def read_bytes(media: Media, *, storage: Storage | None = None) -> bytes:
    assert media.content_type in SERVED_TYPES, f"media {media.id} has a type that is never stored"
    return (storage or media_storage()).get(media.storage_key)


@dataclass(frozen=True)
class QueuedMedia:
    media: Media
    uploader: User
    # The findings it is attached to, through evidence.
    findings: list[str]


def approval_queue(
    db: Session, approver: User, *, limit: int, cursor: str | None = None
) -> tuple[list[QueuedMedia], str | None]:
    """Photos waiting for approval, oldest first, leaving out the approver's own and banned uploaders'."""
    query = (
        select(Media, User)
        .join(User, User.id == Media.user_id)
        .where(
            Media.approved_at.is_(None),
            Media.rejected_at.is_(None),
            Media.hidden_at.is_(None),
            Media.user_id != approver.id,
            User.banned_at.is_(None),
        )
        .order_by(Media.id)
    )
    if cursor is not None:
        query = query.where(Media.id > int_from_cursor(cursor))
    rows = db.execute(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda row: [row[0].id])
    attached: dict[int, list[str]] = {}
    if items:
        for media_id, public_id in db.execute(
            select(Evidence.media_id, Finding.public_id)
            .join(Finding, Finding.id == Evidence.finding_id)
            # A hidden finding's id is for moderators and its finder only.
            .where(Evidence.media_id.in_([media.id for media, _ in items]), Finding.hidden_at.is_(None))
            .order_by(Finding.public_id)
        ).all():
            assert media_id is not None
            attached.setdefault(media_id, []).append(public_id)
    return [
        QueuedMedia(media, uploader, attached.get(media.id, [])) for media, uploader in items
    ], next_cursor
