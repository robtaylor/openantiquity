"""Photo uploads, serving them, and the approval queue moderators and trusted members share (Decision 0009).

`POST /media` takes the image itself as the request body, not a form: the
browser sends the file with `fetch(url, {method: "POST", body: file})`. The
body is read here with a cap, so an oversized upload is refused before it is
held in memory, which a form parser can't promise.

A photo is only ever served by `GET /media/{id}`, as a JPEG or PNG that
`services.media` made itself, with headers that stop a browser running it or
guessing another type.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, PageQuery, private, rate_limit
from fieldclub.errors import ForbiddenError
from fieldclub.models import User
from fieldclub.schemas.common import Page
from fieldclub.schemas.media import MediaOut, MediaRejection, QueuedMediaOut
from fieldclub.services import media, moderation
from fieldclub.vocab import MEDIA_APPROVER_ROLES, Role

router = APIRouter(tags=["media"])

MediaId = Annotated[int, Path(ge=1, le=2**63 - 1)]

# Headers on every photo served. `nosniff` holds the browser to the stated
# type, the sandbox policy stops anything in it running even if opened as a
# page, and `inline` with a fixed name shows it rather than offering a file.
SERVE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
}


async def upload_body(request: Request) -> bytes:
    """The request body, refused with `image_too_large` as soon as it passes the limit.

    Async because reading the body is, and the endpoint stays a plain `def`
    (Decision 0001). A `Content-Length` over the limit is refused unread.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > media.MAX_UPLOAD_BYTES:
        raise media.ImageTooLargeError()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > media.MAX_UPLOAD_BYTES:
            raise media.ImageTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


_IMAGE_BODY = {"schema": {"type": "string", "format": "binary"}}


@router.post(
    "/media",
    response_model=MediaOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("media_upload", 30, per_seconds=3600))],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"image/jpeg": _IMAGE_BODY, "image/png": _IMAGE_BODY, "image/webp": _IMAGE_BODY},
        }
    },
)
def upload(user: Contributor, raw: Annotated[bytes, Depends(upload_body)], db: Db) -> MediaOut:
    """Upload a photo as the request body: a JPEG, PNG or WebP of up to 15 MB and 50 million pixels.

    It is re-encoded with no metadata, so a phone's record of where it was
    taken is gone. Nobody but you, moderators and trusted members sees it
    until one of them approves it. Attach it to evidence by its `id`.
    """
    stored = media.upload(db, user, raw)
    db.commit()
    return MediaOut.build(stored)


@router.get(
    "/media/{media_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}, 404: {"description": "Not found"}},
)
def get_media(media_id: MediaId, db: Db, viewer: OptionalUser) -> Response:
    """The photo itself. Before approval, only for its uploader, moderators and trusted members.

    A photo attached to a finding is served only to someone who sees that
    finding's exact position. Anything else is the same 404 as an id never used.
    """
    photo = media.get_media(db, media_id, viewer)
    data = media.read_bytes(photo)
    extension = media.SERVED_TYPES[photo.content_type]
    response = Response(content=data, media_type=photo.content_type, headers=SERVE_HEADERS)
    response.headers["Content-Disposition"] = f'inline; filename="fieldclub-photo-{photo.id}.{extension}"'
    private(response)
    return response


# --------------------------------------------------------------------------
# The approval queue
# --------------------------------------------------------------------------


def require_photo_approver(user: Contributor) -> User:
    """A moderator or trusted member (experts and admins count) who has finished the welcome step."""
    if Role(user.role) not in MEDIA_APPROVER_ROLES:
        raise ForbiddenError(
            "Only moderators and trusted members approve photos.", code="photo_approvers_only"
        )
    return user


PhotoApprover = Annotated[User, Depends(require_photo_approver)]
_decisions = [Depends(rate_limit("media_decisions", 600, per_seconds=3600))]


@router.get("/mod/media", response_model=Page[QueuedMediaOut], dependencies=[Depends(private)])
def approval_queue(approver: PhotoApprover, db: Db, page: PageQuery) -> Page[QueuedMediaOut]:
    """Photos waiting for approval, oldest first. Your own are left out: someone else decides on them."""
    queued, next_cursor = media.approval_queue(db, approver, limit=page.limit, cursor=page.cursor)
    return Page[QueuedMediaOut](
        items=[QueuedMediaOut.build_queued(item.media, item.uploader, item.findings) for item in queued],
        next_cursor=next_cursor,
    )


@router.post("/mod/media/{media_id}/approve", response_model=MediaOut, dependencies=_decisions)
def approve(media_id: MediaId, approver: PhotoApprover, db: Db) -> MediaOut:
    """Approve a photo, so that everyone who may see its finding sees it."""
    photo = moderation.approve_photo(db, media_id, approver)
    db.commit()
    return MediaOut.build(photo)


@router.post("/mod/media/{media_id}/reject", response_model=MediaOut, dependencies=_decisions)
def reject(media_id: MediaId, body: MediaRejection, approver: PhotoApprover, db: Db) -> MediaOut:
    """Refuse a photo waiting for approval. Its file is deleted, and the same file can't be uploaded again."""
    photo = moderation.reject_photo(db, media_id, approver, body.reason)
    db.commit()
    return MediaOut.build(photo)
