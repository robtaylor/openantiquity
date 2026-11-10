"""Discussion on a finding, and following one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, PageQuery, rate_limit
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import CommentIn, CommentOut, FollowOut
from fieldclub.services import findings

router = APIRouter(tags=["discussion"])


@router.get("/findings/{public_id}/comments", response_model=Page[CommentOut])
def list_comments(public_id: str, page: PageQuery, db: Db, viewer: OptionalUser) -> Page[CommentOut]:
    """A finding's comments, oldest first. A deleted one stays as a placeholder for its replies."""
    finding = findings.get_finding(db, public_id, viewer)
    found = findings.list_comments(db, finding, limit=page.limit, cursor=page.cursor)
    return Page[CommentOut](
        items=[CommentOut.build(comment, found.authors[comment.user_id]) for comment in found.comments],
        next_cursor=found.next_cursor,
    )


@router.post(
    "/findings/{public_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("comments", 60, per_seconds=3600))],
)
def add_comment(public_id: str, body: CommentIn, user: Contributor, db: Db) -> CommentOut:
    """Comment on a finding. Everyone following it is told."""
    finding = findings.get_finding(db, public_id, user)
    comment = findings.add_comment(db, finding, user, body.body, body.parent_id)
    db.commit()
    return CommentOut.build(comment, user)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("comments", 60, per_seconds=3600))],
)
def delete_comment(comment_id: int, user: Contributor, db: Db) -> None:
    """Remove your comment. A moderator can remove anyone's."""
    findings.delete_comment(db, comment_id, user)
    db.commit()


@router.put(
    "/findings/{public_id}/follow",
    response_model=FollowOut,
    dependencies=[Depends(rate_limit("follows", 300, per_seconds=3600))],
)
def follow(public_id: str, user: Contributor, db: Db, response: Response) -> FollowOut:
    """Follow a finding, to hear when it changes."""
    findings.follow(db, user, findings.get_finding(db, public_id, user))
    db.commit()
    return FollowOut(following=True)


@router.delete(
    "/findings/{public_id}/follow",
    response_model=FollowOut,
    dependencies=[Depends(rate_limit("follows", 300, per_seconds=3600))],
)
def unfollow(public_id: str, user: Contributor, db: Db) -> FollowOut:
    """Stop following a finding."""
    findings.unfollow(db, user, findings.get_finding(db, public_id, user))
    db.commit()
    return FollowOut(following=False)
