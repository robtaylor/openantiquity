"""The public activity feed.

Every item's finding carries its position as this viewer may see it
(Decision 0005), so responses are private and vary by cookie.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from fieldclub.api.deps import BBoxQuery, Db, OptionalUser, PageQuery, private
from fieldclub.auth.handles import HANDLE_MAX_LENGTH
from fieldclub.schemas.activity import ActivityOut
from fieldclub.schemas.common import Page, parse_bbox
from fieldclub.services import feed, findings, ids, investigations, people
from fieldclub.services.feed import FeedFilters
from fieldclub.vocab import ActivityKind

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=Page[ActivityOut])
def list_activity(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    page: PageQuery,
    bbox: BBoxQuery = None,
    kind: Annotated[list[ActivityKind] | None, Query(max_length=len(ActivityKind))] = None,
    finding: Annotated[
        str | None, Query(max_length=ids.LENGTH + 8, description="A finding's public id")
    ] = None,
    investigation: Annotated[
        str | None, Query(max_length=ids.LENGTH + 8, description="A public investigation's id")
    ] = None,
    person: Annotated[str | None, Query(max_length=HANDLE_MAX_LENGTH, description="A handle")] = None,
) -> Page[ActivityOut]:
    """What has happened, newest first.

    `bbox` matches the centre of each finding's 1 km square, never its spot.
    A second look's events name nobody. Events on hidden or withdrawn
    findings, on investigations that aren't public, and by banned accounts
    are left out.
    """
    private(response)
    filters = FeedFilters(
        bbox=parse_bbox(bbox),
        kinds=tuple(dict.fromkeys(kind or ())),
        finding_id=findings.get_finding(db, finding, viewer).id if finding is not None else None,
        investigation_id=feed.public_investigation(db, investigation, viewer).id
        if investigation is not None
        else None,
        actor_id=people.get_person(db, person).id if person is not None else None,
    )
    found = feed.list_feed(db, viewer, filters, limit=page.limit, cursor=page.cursor)
    shown = {
        item.investigation.id: item.investigation for item in found.items if item.investigation is not None
    }
    guards = investigations.position_guards(db, list(shown.values()), viewer)
    return Page[ActivityOut](
        items=[
            ActivityOut.build(
                item.activity,
                item.actor,
                item.finding,
                item.investigation,
                viewer,
                guards[item.investigation.id] if item.investigation is not None else None,
            )
            for item in found.items
        ],
        next_cursor=found.next_cursor,
    )
