"""Investigations: the shared notebook, its items, its members and its exports.

Responses hold findings at the position this viewer may see, and say what
the viewer's role is, so each is private and varies by cookie.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Response, status
from shapely.geometry.base import BaseGeometry

from fieldclub.api.deps import (
    BBoxQuery,
    Contributor,
    CurrentUser,
    Db,
    OptionalUser,
    PageQuery,
    private,
    rate_limit,
)
from fieldclub.errors import ValidationFailedError
from fieldclub.models import User
from fieldclub.schemas.common import MAX_ID, GeoJSONGeometry, Page, from_geojson, parse_bbox
from fieldclub.schemas.investigations import (
    AREA_MAX_POINTS,
    InvestigationCreate,
    InvestigationDetail,
    InvestigationItemOut,
    InvestigationSummary,
    InvestigationUpdate,
    ItemIn,
    ItemMove,
    ItemUpdate,
    Member,
    MemberIn,
    item_data,
)
from fieldclub.services import geo, investigation_exports, investigations
from fieldclub.services.investigations import Access, Need, NewItem, Scope
from fieldclub.vocab import InvestigationRole

router = APIRouter(tags=["investigations"])

EDIT_LIMIT = Depends(rate_limit("investigations_edit", 600, per_seconds=3600))
EXPORT_LIMIT = Depends(rate_limit("investigations_export", 60, per_seconds=3600))

AREA_TYPES = ("Polygon", "MultiPolygon")
HANDLE_MAX = 64

ItemId = Annotated[int, Path(ge=1, le=MAX_ID)]


def _area(geometry: GeoJSONGeometry | None) -> BaseGeometry | None:
    if geometry is None:
        return None
    area = from_geojson(geometry, allowed=AREA_TYPES, max_points=AREA_MAX_POINTS)
    geo.check_in_british_isles(area)
    return area


def _detail(db: Db, access: Access, viewer: User | None) -> InvestigationDetail:
    investigation = access.investigation
    counts = investigations.counts(db, investigation)
    owner = db.get(User, investigation.owner_id)
    assert owner is not None
    return InvestigationDetail.build(
        investigation,
        owner,
        item_count=counts.items,
        member_count=counts.members,
        role=access.role,
        guard=investigations.position_guard(db, investigation, viewer),
        invited_as=access.invited,
    )


def _item_out(db: Db, access: Access, item_id: int, viewer: User) -> InvestigationItemOut:
    item = investigations.get_item(db, access.investigation, item_id)
    (view,) = investigations.item_views(db, [item], viewer)
    return InvestigationItemOut.build(
        view, viewer, investigations.position_guard(db, access.investigation, viewer)
    )


# --------------------------------------------------------------------------
# Investigations
# --------------------------------------------------------------------------


@router.get("/investigations", response_model=Page[InvestigationSummary])
def list_investigations(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    page: PageQuery,
    scope: Scope = Scope.PUBLIC,
    bbox: BBoxQuery = None,
) -> Page[InvestigationSummary]:
    """Public investigations. `bbox` matches their area.

    `scope=mine` lists every one you belong to, `scope=invited` the ones
    you've been invited to and haven't answered, and `scope=unlisted` every
    unlisted one, for moderators only (`investigation_moderator_only`).
    """
    rows, next_cursor = investigations.list_investigations(
        db, viewer, scope, bbox=parse_bbox(bbox), limit=page.limit, cursor=page.cursor
    )
    private(response)
    return Page[InvestigationSummary](
        items=[InvestigationSummary.from_listed(row) for row in rows], next_cursor=next_cursor
    )


@router.post(
    "/investigations",
    response_model=InvestigationDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("investigations_create", 30, per_seconds=3600))],
)
def create_investigation(
    body: InvestigationCreate, user: Contributor, db: Db, response: Response
) -> InvestigationDetail:
    """Start an investigation. It is private, with you as its one member, unless you say otherwise."""
    investigation = investigations.create_investigation(
        db,
        user,
        title=body.title,
        summary=body.summary,
        notes=body.notes,
        visibility=body.visibility,
        area=_area(body.area),
    )
    db.commit()
    private(response)
    return _detail(db, Access(investigation, InvestigationRole.OWNER), user)


@router.get("/investigations/{public_id}", response_model=InvestigationDetail)
def get_investigation(
    public_id: str, db: Db, viewer: OptionalUser, response: Response
) -> InvestigationDetail:
    """An investigation's page. A private one is found only by its owner."""
    private(response)
    return _detail(db, investigations.load(db, public_id, viewer), viewer)


@router.patch("/investigations/{public_id}", response_model=InvestigationDetail, dependencies=[EDIT_LIMIT])
def update_investigation(
    public_id: str, body: InvestigationUpdate, user: Contributor, db: Db, response: Response
) -> InvestigationDetail:
    """Change the title, summary, notes or area (owner or editor), or the visibility (owner).

    Making it public publishes it to the activity feed. It can't be made
    private while it has collaborators.
    """
    changes = body.model_dump(exclude_unset=True)
    if "area" in changes:
        changes["area"] = _area(body.area)
    for name in ("title", "visibility"):
        if name in changes and changes[name] is None:
            raise ValidationFailedError(f"{name} can't be removed.", code="invalid_investigation")
    access = investigations.load(db, public_id, user, Need.EDIT, lock=True)
    investigations.update_investigation(db, access, user, changes)
    db.commit()
    private(response)
    return _detail(db, access, user)


@router.delete(
    "/investigations/{public_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[EDIT_LIMIT]
)
def delete_investigation(public_id: str, user: Contributor, db: Db) -> None:
    """Delete an investigation with everything in it. Only its owner can."""
    investigations.delete_investigation(db, investigations.load(db, public_id, user, Need.OWN, lock=True))
    db.commit()


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


@router.get("/investigations/{public_id}/items", response_model=Page[InvestigationItemOut])
def list_items(
    public_id: str, db: Db, viewer: OptionalUser, response: Response, page: PageQuery
) -> Page[InvestigationItemOut]:
    """The items in order. One whose finding or record can't be shown has `unavailable` set instead."""
    access = investigations.load(db, public_id, viewer)
    items, next_cursor = investigations.list_items(
        db, access.investigation, limit=page.limit, cursor=page.cursor
    )
    private(response)
    guard = investigations.position_guard(db, access.investigation, viewer)
    return Page[InvestigationItemOut](
        items=[
            InvestigationItemOut.build(view, viewer, guard)
            for view in investigations.item_views(db, items, viewer)
        ],
        next_cursor=next_cursor,
    )


@router.post(
    "/investigations/{public_id}/items",
    response_model=InvestigationItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[EDIT_LIMIT],
)
def add_item(
    public_id: str, body: ItemIn, user: Contributor, db: Db, response: Response
) -> InvestigationItemOut:
    """Add a finding, record, map view, note, reference or height profile at the end."""
    new = NewItem(
        kind=body.kind,
        finding=getattr(body, "finding", None),
        record_id=getattr(body, "record_id", None),
        title=body.title,
        note=body.note,
        data=item_data(body),
    )
    access = investigations.load(db, public_id, user, Need.EDIT, lock=True)
    item = investigations.add_item(db, access, user, new)
    db.commit()
    private(response)
    return _item_out(db, access, item.id, user)


@router.patch(
    "/investigations/{public_id}/items/{item_id}",
    response_model=InvestigationItemOut,
    dependencies=[EDIT_LIMIT],
)
def update_item(
    public_id: str, item_id: ItemId, body: ItemUpdate, user: Contributor, db: Db, response: Response
) -> InvestigationItemOut:
    """Change an item's title, note or content. What it points at stays."""
    access = investigations.load(db, public_id, user, Need.EDIT, lock=True)
    investigations.update_item(db, access, user, item_id, body.changes(), body.content_kinds())
    db.commit()
    private(response)
    return _item_out(db, access, item_id, user)


@router.post(
    "/investigations/{public_id}/items/{item_id}/move",
    response_model=InvestigationItemOut,
    dependencies=[EDIT_LIMIT],
)
def move_item(
    public_id: str, item_id: ItemId, body: ItemMove, user: Contributor, db: Db, response: Response
) -> InvestigationItemOut:
    """Put an item straight after another, or first with `after: null`. Places are renumbered from 0."""
    access = investigations.load(db, public_id, user, Need.EDIT, lock=True)
    investigations.move_item(db, access, item_id, body.after)
    db.commit()
    private(response)
    return _item_out(db, access, item_id, user)


@router.delete(
    "/investigations/{public_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[EDIT_LIMIT],
)
def remove_item(public_id: str, item_id: ItemId, user: Contributor, db: Db) -> None:
    access = investigations.load(db, public_id, user, Need.EDIT, lock=True)
    investigations.remove_item(db, access, item_id)
    db.commit()


# --------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------

Handle = Annotated[str, Path(max_length=HANDLE_MAX)]


@router.get("/investigations/{public_id}/members", response_model=Page[Member])
def list_members(
    public_id: str, db: Db, viewer: OptionalUser, response: Response, page: PageQuery
) -> Page[Member]:
    """Who works on it: the owner first, then everyone else in the order they joined."""
    access = investigations.load(db, public_id, viewer)
    members, next_cursor = investigations.list_members(
        db, access.investigation, limit=page.limit, cursor=page.cursor
    )
    private(response)
    return Page[Member](items=[Member.build(member) for member in members], next_cursor=next_cursor)


@router.put(
    "/investigations/{public_id}/members/{handle}",
    response_model=Member,
    responses={201: {"model": Member, "description": "The person was added"}},
    dependencies=[EDIT_LIMIT],
)
def put_member(
    public_id: str, handle: Handle, body: MemberIn, user: Contributor, db: Db, response: Response
) -> Member:
    """Invite a contributor by handle as an editor or viewer, or change their role. The owner's call.

    The person is a member once they accept (`POST .../invitation`); until
    then the member list shows them as `pending`. A private investigation
    takes nobody: make it public or unlisted first.
    """
    access = investigations.load(db, public_id, user, Need.OWN, lock=True)
    person = investigations.find_user(db, handle)
    member, created = investigations.put_member(db, access, person, body.role)
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    private(response)
    return Member.build(
        investigations.MemberView(person, body.role, member.created_at, member.accepted_at is not None)
    )


@router.post(
    "/investigations/{public_id}/invitation", response_model=InvestigationDetail, dependencies=[EDIT_LIMIT]
)
def accept_invitation(public_id: str, user: Contributor, db: Db, response: Response) -> InvestigationDetail:
    """Accept your invitation, and become a member with the role offered. Decline by leaving."""
    access = investigations.load(db, public_id, user, lock=True)
    member = investigations.accept_invitation(db, access, user)
    db.commit()
    private(response)
    return _detail(db, Access(access.investigation, InvestigationRole(member.role)), user)


@router.delete(
    "/investigations/{public_id}/members/{handle}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[EDIT_LIMIT],
)
def remove_member(public_id: str, handle: Handle, user: CurrentUser, db: Db) -> None:
    """Remove a member or withdraw an invitation (the owner), or leave or decline (anyone else).

    Leaving needs only a session, so someone who hasn't finished the welcome step can still go.
    """
    access = investigations.load(db, public_id, user, lock=True)
    investigations.remove_member(db, access, user, handle)
    db.commit()


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


@router.get(
    "/investigations/{public_id}/export",
    response_class=Response,
    responses={200: {"content": {"application/geo+json": {}, "text/csv": {}, "text/html": {}}}},
    dependencies=[EXPORT_LIMIT],
)
def export_investigation(
    public_id: str,
    db: Db,
    viewer: OptionalUser,
    format: Literal["geojson", "csv", "html"] = "geojson",
) -> Response:
    """The investigation as GeoJSON, as a spreadsheet with HER field names, or as a printable report.

    Protected and restricted findings carry their 1 km square unless you
    are their finder or trusted. Every record carries its source's licence.
    """
    access = investigations.load(db, public_id, viewer)
    export = investigation_exports.gather(db, access.investigation, viewer)
    name = f"openantiquity-investigation-{access.investigation.public_id}"
    if format == "html":
        response = Response(
            content=investigation_exports.to_html(export), media_type="text/html; charset=utf-8"
        )
        response.headers["Content-Security-Policy"] = f"{investigation_exports.REPORT_CSP}; sandbox"
        response.headers["Content-Disposition"] = f'inline; filename="{name}.html"'
    elif format == "csv":
        response = Response(
            content=investigation_exports.to_csv(export), media_type="text/csv; charset=utf-8"
        )
        response.headers["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    else:
        response = Response(
            content=json.dumps(investigation_exports.to_geojson(export), separators=(",", ":")),
            media_type="application/geo+json",
        )
        response.headers["Content-Disposition"] = f'attachment; filename="{name}.geojson"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    private(response)
    return response
