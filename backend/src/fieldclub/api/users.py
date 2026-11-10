"""People's public pages.

Deleted and banned accounts answer `user_not_found`. Findings carry their
positions as this viewer may see them (Decision 0005), so responses are
private and vary by cookie.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from fieldclub.api.deps import Db, OptionalUser, PageQuery, private
from fieldclub.auth.handles import HANDLE_MAX_LENGTH
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import FindingSummary
from fieldclub.schemas.people import ContributionOut, PersonProfile, PointOut
from fieldclub.services import people
from fieldclub.services.people import ContributionKind

router = APIRouter(tags=["people"])

Handle = Annotated[str, Path(min_length=1, max_length=HANDLE_MAX_LENGTH)]


@router.get("/users/{handle}", response_model=PersonProfile)
def get_profile(handle: Handle, db: Db, viewer: OptionalUser, response: Response) -> PersonProfile:
    """Someone's page: who they are, when they joined, what they have done and their points."""
    private(response)
    return PersonProfile.build(people.profile(db, people.get_person(db, handle), viewer))


@router.get("/users/{handle}/findings", response_model=Page[FindingSummary])
def list_findings(
    handle: Handle, db: Db, viewer: OptionalUser, page: PageQuery, response: Response
) -> Page[FindingSummary]:
    """Their findings, newest first, as you may see them. Withdrawn and hidden ones are left out."""
    private(response)
    person = people.get_person(db, handle)
    found = people.list_person_findings(db, person, viewer, limit=page.limit, cursor=page.cursor)
    return Page[FindingSummary](
        items=[FindingSummary.build(finding, person, viewer) for finding in found.findings],
        next_cursor=found.next_cursor,
    )


@router.get("/users/{handle}/contributions", response_model=Page[ContributionOut])
def list_contributions(
    handle: Handle,
    db: Db,
    viewer: OptionalUser,
    page: PageQuery,
    response: Response,
    kind: Annotated[
        ContributionKind | None,
        Query(description="Left out: evidence, comments and mentions together. second_look on its own."),
    ] = None,
) -> Page[ContributionOut]:
    """What they helped with. A second look says only that they took one, never how or when."""
    private(response)
    person = people.get_person(db, handle)
    found = people.list_contributions(db, person, viewer, kind=kind, limit=page.limit, cursor=page.cursor)
    return Page[ContributionOut](
        items=[ContributionOut.build(item, viewer) for item in found.items], next_cursor=found.next_cursor
    )


@router.get("/users/{handle}/points", response_model=Page[PointOut])
def list_points(
    handle: Handle, db: Db, viewer: OptionalUser, page: PageQuery, response: Response
) -> Page[PointOut]:
    """Where each of your points came from, newest first. Only for your own handle."""
    private(response)
    person = people.get_person(db, handle)
    found = people.list_points(db, person, viewer, limit=page.limit, cursor=page.cursor)
    assert viewer is not None, "list_points refuses anyone but the person themselves"
    return Page[PointOut](
        items=[PointOut.build(event, found.finding_of(event), viewer) for event in found.events],
        next_cursor=found.next_cursor,
    )
