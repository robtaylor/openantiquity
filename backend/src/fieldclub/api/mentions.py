"""Mentions of a finding, the preview that fetches a link's title, and the recent feed.

`POST /mentions/preview` and `POST /findings/{public_id}/mentions` make this
server fetch an address a member typed, so both are rate-limited per member
and share one budget for the whole process as well.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, PageQuery, private, rate_limit
from fieldclub.ratelimit import enforce_key, get_limiter
from fieldclub.schemas.common import Page
from fieldclub.schemas.mentions import (
    MentionedFinding,
    MentionIn,
    MentionOut,
    MentionPreviewIn,
    MentionPreviewOut,
    RecentMentionOut,
)
from fieldclub.services import findings, mentions

router = APIRouter(tags=["mentions"])

# Fetches this process makes for everyone together, whoever asks.
_all_fetches = get_limiter("mention-fetches-all", 600, per_seconds=3600)


def fetch_budget() -> None:
    """Spend one of the process's fetches, or a 429 when they're used up."""
    enforce_key(_all_fetches, "all")


@router.post(
    "/mentions/preview",
    response_model=MentionPreviewOut,
    dependencies=[Depends(rate_limit("mention-previews", 20, per_seconds=3600)), Depends(fetch_budget)],
)
def preview(body: MentionPreviewIn, user: Contributor) -> MentionPreviewOut:
    """What a mention of this address would show. Nothing is saved, and a failed fetch is not an error."""
    return MentionPreviewOut.build(mentions.preview(body.url))


@router.get("/findings/{public_id}/mentions", response_model=Page[MentionOut])
def list_mentions(public_id: str, page: PageQuery, db: Db, viewer: OptionalUser) -> Page[MentionOut]:
    """A finding's mentions, newest first."""
    finding = findings.get_finding(db, public_id, viewer)
    found = mentions.for_finding(db, finding, limit=page.limit, cursor=page.cursor)
    return Page[MentionOut](
        items=[
            MentionOut.build(m, found.adders[m.user_id] if m.user_id is not None else None)
            for m in found.mentions
        ],
        next_cursor=found.next_cursor,
    )


@router.post(
    "/findings/{public_id}/mentions",
    response_model=MentionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("mentions", 30, per_seconds=3600)), Depends(fetch_budget)],
)
def add_mention(public_id: str, body: MentionIn, user: Contributor, db: Db) -> MentionOut:
    """Say where a finding was talked about. Its finder and everyone who helped are told."""
    finding = findings.get_finding(db, public_id, user)
    mention = mentions.add(
        db, finding, user, body.url, kind=body.kind, start_seconds=body.start_seconds, note=body.note
    )
    db.commit()
    return MentionOut.build(mention, user)


@router.delete(
    "/mentions/{mention_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("mentions", 30, per_seconds=3600))],
)
def delete_mention(mention_id: int, user: Contributor, db: Db) -> None:
    """Remove a mention you added. A moderator can remove anyone's."""
    mentions.remove(db, mention_id, user)
    db.commit()


@router.get("/mentions/recent", response_model=Page[RecentMentionOut])
def recent(page: PageQuery, db: Db, viewer: OptionalUser, response: Response) -> Page[RecentMentionOut]:
    """The newest mentions across the map. Each finding's position is the one this viewer may see."""
    found = mentions.recent(db, viewer, limit=page.limit, cursor=page.cursor)
    private(response)
    items: list[RecentMentionOut] = []
    for mention in found.mentions:
        finding = found.finding_by_id[mention.finding_id]
        adder = found.adders[mention.user_id] if mention.user_id is not None else None
        items.append(
            RecentMentionOut(
                # dict(), not model_dump(), so `added_by` stays a PublicUser.
                **dict(MentionOut.build(mention, adder)),
                finding=MentionedFinding.build(finding, found.finders[finding.author_id], viewer),
            )
        )
    return Page[RecentMentionOut](items=items, next_cursor=found.next_cursor)
