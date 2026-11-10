"""The signed-in person's own notifications.

A notification goes only to the account it was written for, and every
query here is limited to the caller's own rows.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from fieldclub.api.deps import Contributor, CurrentUser, Db, PageQuery, private, rate_limit
from fieldclub.schemas.activity import MarkRead, MarkReadResult, NotificationOut, NotificationPage
from fieldclub.services import feed

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationPage)
def list_notifications(user: CurrentUser, db: Db, page: PageQuery, response: Response) -> NotificationPage:
    """Your notifications, newest first, with how many are unread."""
    private(response)
    found = feed.list_notifications(db, user, limit=page.limit, cursor=page.cursor)
    return NotificationPage(
        items=[
            NotificationOut.build(item.notification, item.actor, item.finding, user) for item in found.items
        ],
        next_cursor=found.next_cursor,
        unread_count=found.unread_count,
    )


@router.post(
    "/notifications/read",
    response_model=MarkReadResult,
    dependencies=[Depends(rate_limit("notifications_read", 600, per_seconds=3600))],
)
def mark_read(body: MarkRead, user: Contributor, db: Db, response: Response) -> MarkReadResult:
    """Mark some of your notifications read, or all of them."""
    private(response)
    marked = feed.mark_read(db, user, ids=body.ids, up_to=body.up_to)
    db.commit()
    return MarkReadResult(marked=marked, unread_count=feed.unread_count(db, user))
