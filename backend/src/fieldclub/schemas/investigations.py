"""Request and response shapes for investigations, their items and their members.

A finding inside an investigation is a `FindingSummary`, whose position comes
from `location_out` and so from `services.sensitivity` for this viewer. A
record is a `RecordSummary`, which carries its source's licence and
attribution (Decision 0004). An item whose target the viewer may not see
has `unavailable` set and neither.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, UrlConstraints

from fieldclub.models import Investigation, User
from fieldclub.schemas.common import (
    MAX_ID,
    ApiModel,
    GeoJSONGeometry,
    PublicUser,
    RequestModel,
    geojson_geometry,
)
from fieldclub.schemas.findings import FindingSummary, ViewState
from fieldclub.schemas.records import RecordSummary, record_summary
from fieldclub.services.investigations import ItemView, Listed, MemberView, Unavailable
from fieldclub.vocab import InvestigationItemKind, InvestigationRole, Visibility

TITLE_MAX = 120
SUMMARY_MAX = 1000
NOTES_MAX = 50_000
ITEM_TITLE_MAX = 200
ITEM_NOTE_MAX = 10_000
CITATION_MAX = 1000
URL_MAX = 2000
# The most points an area may have, counting every ring.
AREA_MAX_POINTS = 2000
# The most points a height profile's line may have. The profile endpoint takes the same.
PROFILE_MAX_POINTS = 200
PUBLIC_ID_MAX = 20

Lon = Annotated[float, Field(ge=-180, le=180)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Position = tuple[Lon, Lat]
WebUrl = Annotated[HttpUrl, UrlConstraints(max_length=URL_MAX)]

# --------------------------------------------------------------------------
# Item contents
# --------------------------------------------------------------------------


class SavedView(ViewState):
    """A map view to come back to: where it was centred and how the map was set."""

    centre: Position
    # The layer shown in the comparison pane, if one was open.
    compare_layer: str | None = Field(default=None, max_length=40, pattern=r"^[a-z0-9_-]+$")


class ReferenceData(BaseModel):
    """A book, paper, web page or archive source. The item's title is the reference's title."""

    model_config = ConfigDict(extra="forbid")

    url: WebUrl | None = None
    # Authors, year, publisher, pages: however the person writes it.
    citation: str | None = Field(default=None, min_length=1, max_length=CITATION_MAX)


class ProfileLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["LineString"]
    coordinates: list[Position] = Field(min_length=2, max_length=PROFILE_MAX_POINTS)


class ProfileData(BaseModel):
    """A height profile: the line it runs along. The heights come from `POST /terrain/profile`."""

    model_config = ConfigDict(extra="forbid")

    line: ProfileLine
    samples: int = Field(default=200, ge=2, le=1000)


ItemTitle = Annotated[str | None, Field(default=None, min_length=1, max_length=ITEM_TITLE_MAX)]
ItemNote = Annotated[str | None, Field(default=None, min_length=1, max_length=ITEM_NOTE_MAX)]


class FindingItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.FINDING]
    finding: str = Field(min_length=1, max_length=PUBLIC_ID_MAX, description="The finding's public id")
    title: ItemTitle = None
    note: ItemNote = None


class RecordItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.RECORD]
    record_id: int = Field(ge=1, le=MAX_ID)
    title: ItemTitle = None
    note: ItemNote = None


class ViewItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.VIEW]
    view: SavedView
    title: ItemTitle = None
    note: ItemNote = None


class NoteItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.NOTE]
    note: str = Field(min_length=1, max_length=ITEM_NOTE_MAX)
    title: ItemTitle = None


class ReferenceItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.REFERENCE]
    title: str = Field(min_length=1, max_length=ITEM_TITLE_MAX)
    reference: ReferenceData
    note: ItemNote = None


class ProfileItemIn(RequestModel):
    kind: Literal[InvestigationItemKind.PROFILE]
    profile: ProfileData
    title: ItemTitle = None
    note: ItemNote = None


ItemIn = Annotated[
    FindingItemIn | RecordItemIn | ViewItemIn | NoteItemIn | ReferenceItemIn | ProfileItemIn,
    Field(discriminator="kind"),
]


# The fields that carry an item's content, each named after its kind.
CONTENT_FIELDS = ("view", "reference", "profile")


def item_data(body: BaseModel) -> dict[str, Any] | None:
    """What an item stores in `data`: the view, reference or profile sent, as JSON."""
    for name in CONTENT_FIELDS:
        value = getattr(body, name, None)
        if value is not None:
            return value.model_dump(mode="json", exclude_none=True)
    return None


class ItemUpdate(RequestModel):
    """Changes to an item. Fields left out are left alone; `null` clears a title or note.

    Give the content of the item's own kind only: `view` for a view,
    `reference` for a reference, `profile` for a profile.
    """

    title: ItemTitle = None
    note: ItemNote = None
    view: SavedView | None = None
    reference: ReferenceData | None = None
    profile: ProfileData | None = None

    def changes(self) -> dict[str, Any]:
        """The title, note and stored `data` sent, for `services.investigations.update_item`."""
        sent = self.model_fields_set
        changes = {name: getattr(self, name) for name in ("title", "note") if name in sent}
        if self.content_kinds():
            changes["data"] = item_data(self)
        return changes

    def content_kinds(self) -> list[InvestigationItemKind]:
        """Which kinds of content were sent. The service accepts only the item's own."""
        return [InvestigationItemKind(name) for name in CONTENT_FIELDS if name in self.model_fields_set]


class ItemMove(RequestModel):
    """Where to put the item: straight after the item `after`, or first when it is null."""

    after: int | None = Field(ge=1, le=MAX_ID)


# --------------------------------------------------------------------------
# Investigations: requests
# --------------------------------------------------------------------------


class InvestigationCreate(RequestModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    summary: str | None = Field(default=None, max_length=SUMMARY_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX, description="Markdown")
    # Private until you choose otherwise. Collaborators need public or unlisted.
    visibility: Visibility = Visibility.PRIVATE
    # The area it covers, a Polygon or MultiPolygon. Public ones are found by it on the map.
    area: GeoJSONGeometry | None = None


class InvestigationUpdate(RequestModel):
    """Fields left out are left alone. `visibility` is the owner's to change."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    summary: str | None = Field(default=None, max_length=SUMMARY_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    visibility: Visibility | None = None
    area: GeoJSONGeometry | None = None


class MemberIn(RequestModel):
    role: Literal[InvestigationRole.EDITOR, InvestigationRole.VIEWER]


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------


class InvestigationSummary(ApiModel):
    public_id: str
    title: str
    summary: str | None
    visibility: Visibility
    owner: PublicUser
    area: GeoJSONGeometry | None
    item_count: int
    created_at: datetime
    updated_at: datetime
    # True when a moderator has hidden it, which only its members and moderators then see.
    hidden: bool = False

    @classmethod
    def from_listed(cls, listed: Listed) -> InvestigationSummary:
        return cls(**_summary_fields(listed.investigation, listed.owner, listed.item_count))


def _summary_fields(investigation: Investigation, owner: User, item_count: int) -> dict[str, Any]:
    assert owner.has_id(investigation.owner_id), "the owner passed doesn't own the investigation"
    return {
        "public_id": investigation.public_id,
        "title": investigation.title,
        "summary": investigation.summary,
        "visibility": investigation.visibility,
        "owner": PublicUser.from_user(owner),
        "area": geojson_geometry(investigation.area),
        "item_count": item_count,
        "created_at": investigation.created_at,
        "updated_at": investigation.updated_at,
        "hidden": investigation.hidden_at is not None,
    }


class InvestigationDetail(InvestigationSummary):
    notes: str | None
    member_count: int
    # Your role, or null when you aren't a member.
    my_role: InvestigationRole | None
    # The role you've been invited to take, until you accept or decline. Null otherwise.
    invited_as: InvestigationRole | None

    @classmethod
    def build(
        cls,
        investigation: Investigation,
        owner: User,
        *,
        item_count: int,
        member_count: int,
        role: InvestigationRole | None,
        invited_as: InvestigationRole | None = None,
    ) -> InvestigationDetail:
        return cls(
            **_summary_fields(investigation, owner, item_count),
            notes=investigation.notes,
            member_count=member_count,
            my_role=role,
            invited_as=invited_as,
        )


class MemberOut(ApiModel):
    user: PublicUser
    role: InvestigationRole
    # When they were invited, or for the owner when the investigation began.
    joined_at: datetime
    # True until the person accepts the invitation. Until then they can't edit.
    pending: bool

    @classmethod
    def build(cls, view: MemberView) -> MemberOut:
        return cls(
            user=PublicUser.from_user(view.user),
            role=view.role,
            joined_at=view.joined_at,
            pending=not view.accepted,
        )


class InvestigationItemOut(ApiModel):
    """One entry in the notebook.

    `finding` is set for a finding item and `record` for a record item, when
    the viewer may see them. Otherwise `unavailable` says why: `hidden` (a
    moderator hid the finding), `withdrawn` (its finder took it back) or
    `gone` (the record has left the index). Show the item as a line saying so.
    """

    id: int
    kind: InvestigationItemKind
    position: int
    title: str | None
    note: str | None
    finding: FindingSummary | None = None
    record: RecordSummary | None = None
    view: SavedView | None = None
    reference: ReferenceData | None = None
    profile: ProfileData | None = None
    unavailable: Unavailable | None = None
    added_by: PublicUser
    created_at: datetime

    @classmethod
    def build(cls, view: ItemView, viewer: User | None) -> InvestigationItemOut:
        item = view.item
        kind = InvestigationItemKind(item.kind)
        contents: dict[str, Any] = {}
        if kind is InvestigationItemKind.VIEW:
            contents["view"] = SavedView.model_validate(item.data)
        elif kind is InvestigationItemKind.REFERENCE:
            contents["reference"] = ReferenceData.model_validate(item.data)
        elif kind is InvestigationItemKind.PROFILE:
            contents["profile"] = ProfileData.model_validate(item.data)
        if view.finding is not None:
            assert view.finding_author is not None, "a shown finding comes with its author"
            contents["finding"] = FindingSummary.build(view.finding, view.finding_author, viewer)
        if view.record is not None:
            contents["record"] = record_summary(view.record)
        return cls(
            id=item.id,
            kind=kind,
            position=item.position,
            title=item.title,
            note=item.note,
            unavailable=view.unavailable,
            added_by=PublicUser.from_user(view.added_by),
            created_at=item.created_at,
            **contents,
        )
