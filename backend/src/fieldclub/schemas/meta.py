"""The shape of `GET /meta`, as fixed in docs/ARCHITECTURE.md."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from fieldclub.schemas.common import ApiModel

# One shape for a source, in `/meta` as in `GET /sources`.
from fieldclub.schemas.records import SourceOut
from fieldclub.services.confidence import Endorsement, MetBy
from fieldclub.vocab import (
    AgeBand,
    EvidenceKind,
    LinkCoverage,
    LinkShows,
    NextStepCode,
    Outcome,
    Relation,
    Sensitivity,
    SourceReuse,
    Stance,
)

# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------


class FeatureClassOut(ApiModel):
    id: str
    label: str
    hint: str
    fish_term: str
    # The level a new finding of this class starts at (`services.sensitivity.default_sensitivity`).
    sensitivity: Sensitivity


class PeriodOut(ApiModel):
    id: str
    label: str
    hint: str


class EvidenceKindOut(ApiModel):
    id: str
    label: str
    strand: str
    group: str
    hint: str


class TierOut(ApiModel):
    id: str
    label: str
    description: str
    base_score: int


class State(ApiModel):
    id: str
    label: str
    description: str


class CheckOut(ApiModel):
    id: str
    question: str
    hint: str


class ExplanationOut(ApiModel):
    id: str
    label: str
    hint: str


class MentionKindOut(ApiModel):
    id: str
    label: str


class RecordCategoryOut(ApiModel):
    id: str
    label: str
    colour: str


class ReportReasonOut(ApiModel):
    id: str
    label: str
    hint: str
    # Hours within which the law expects a report for this reason to be dealt with, or null.
    due_hours: int | None


class NextStepRuleOut(ApiModel):
    """What meets one next step, from `services.confidence.STEP_RULES`. `id` is the step's code.

    `label` and `description` name the work it asks of someone, for the
    help-wanted lists: "Another kind of evidence", "Check old maps, ...".
    """

    id: NextStepCode
    label: str
    description: str
    met_by: MetBy
    # For a step met by evidence: the kinds that count, and what the item must say.
    evidence_kinds: list[EvidenceKind]
    # The relations with which a `record_link` counts. Empty when no record link does.
    record_relations: list[Relation]
    # What a field item's outcome must be, or null where its stance decides.
    outcome: Outcome | None
    stance: Stance | None
    # When the item counts only once someone other than its contributor and
    # the finder endorses it: `not_needed`, `if_added_by_finder`, or
    # `unless_added_by_trusted_other` (endorsed, or added by a trusted member,
    # archaeologist or moderator who isn't the finder). Every item counts only
    # while its votes sum to zero or more.
    endorsement: Endorsement
    # True when the item counts only once an archaeologist or moderator verifies it.
    needs_verification: bool


class LinkShowsOut(ApiModel):
    """What an external viewer shows at a place, as `GET /context/links` gives its `shows`."""

    id: LinkShows
    label: str
    description: str


class LinkCoverageOut(ApiModel):
    """Where an external viewer has something to show, as `GET /context/links` gives its `coverage`."""

    id: LinkCoverage
    label: str


class Vocab(BaseModel):
    feature_classes: list[FeatureClassOut]
    periods: list[PeriodOut]
    evidence_kinds: list[EvidenceKindOut]
    tiers: list[TierOut]
    states: list[State]
    checks: list[CheckOut]
    explanations: list[ExplanationOut]
    mention_kinds: list[MentionKindOut]
    record_categories: list[RecordCategoryOut]
    report_reasons: list[ReportReasonOut]
    next_steps: list[NextStepRuleOut]
    link_shows: list[LinkShowsOut]
    link_coverages: list[LinkCoverageOut]


# --------------------------------------------------------------------------
# Layers
# --------------------------------------------------------------------------

ViewGroup = Literal["lidar", "imagery", "historic", "map", "geology"]

# West, south, east, north in degrees.
Bounds = tuple[float, float, float, float]


class RasterView(BaseModel):
    """A tiled image that can be the main layer or the comparison layer."""

    id: str
    title: str
    description: str
    group: ViewGroup
    type: Literal["raster"] = "raster"
    tiles: list[str] = Field(min_length=1)
    tile_size: int
    minzoom: int
    maxzoom: int
    attribution: str
    # Every layer someone else publishes says under what terms, as a source does (Decision 0004).
    licence: str
    licence_url: str
    reuse: SourceReuse
    bounds: Bounds | None = None
    default: bool = False


class RakingView(BaseModel):
    """Raking light, drawn in the browser as a hillshade of the `dem` source."""

    id: str
    title: str
    group: ViewGroup
    type: Literal["raking"] = "raking"
    description: str
    attribution: str
    licence: str
    licence_url: str
    reuse: SourceReuse


View = Annotated[RasterView | RakingView, Field(discriminator="type")]


class DemSource(BaseModel):
    tiles: list[str] = Field(min_length=1)
    tile_size: int
    encoding: Literal["terrarium"] = "terrarium"
    minzoom: int
    maxzoom: int
    attribution: str
    licence: str
    licence_url: str
    reuse: SourceReuse


class OpenMapTilesOverlay(BaseModel):
    """An OpenMapTiles-schema vector source, styled by the frontend as thin lines and labels."""

    id: str
    title: str
    type: Literal["openmaptiles"] = "openmaptiles"
    tilejson: str
    glyphs: str
    default_opacity: float = Field(ge=0, le=1)
    attribution: str
    licence: str
    licence_url: str
    reuse: SourceReuse


class RecordsOverlay(BaseModel):
    id: str
    title: str
    type: Literal["records"] = "records"
    tiles: list[str] = Field(min_length=1)


class FindingsOverlay(BaseModel):
    """Findings, fetched from `GET /findings?bbox=&format=geojson`. Never tiled, because the answer
    depends on the viewer."""

    id: str
    title: str
    type: Literal["findings"] = "findings"


class CoverageOverlay(BaseModel):
    id: str
    title: str
    type: Literal["coverage"] = "coverage"


Overlay = Annotated[
    OpenMapTilesOverlay | RecordsOverlay | FindingsOverlay | CoverageOverlay, Field(discriminator="type")
]


class InitialView(BaseModel):
    # Longitude then latitude.
    center: tuple[float, float]
    zoom: int | float


class Layers(BaseModel):
    views: list[View]
    dem: DemSource
    overlays: list[Overlay]
    initial_view: InitialView


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


class AppInfo(BaseModel):
    name: str
    version: str
    contribution_licence: str


class Provider(BaseModel):
    id: str
    label: str
    # True only when the provider's sign-in flow is built and its credentials
    # are configured. The sign-in sheet offers only enabled providers.
    enabled: bool


class Terms(BaseModel):
    """The contributor terms the welcome step asks people to accept, from settings."""

    summary: str
    # A path on this site or a full https address.
    url: str


class AuthInfo(BaseModel):
    # Every sign-in provider, in the order the sign-in sheet shows them.
    providers: list[Provider]
    # True where `POST /auth/dev-login` exists: development and test, when asked for.
    dev_login: bool
    # The age bands `POST /auth/welcome` accepts, youngest first (`FIELDCLUB_MIN_AGE`).
    age_bands: list[AgeBand]
    terms: Terms


class FieldVisitNotices(BaseModel):
    england: list[str]
    scotland: list[str]
    wales: list[str]
    northern_ireland: list[str]


class FindReporting(BaseModel):
    """Where to report an object found in one nation. Field Club stores nothing about finds."""

    scheme: str
    # The scheme's own site, or null where none is known.
    url: str | None
    text: str


class FindReportingNotices(BaseModel):
    england: FindReporting
    scotland: FindReporting
    wales: FindReporting
    northern_ireland: FindReporting


class Notices(BaseModel):
    field_visit: FieldVisitNotices
    # Shown with the nation's lines to an account in the 16 to 17 band.
    field_visit_16_17: str
    sensitivity: str
    # The route for reporting a find, per nation (Decision 0005, item 9).
    find_reporting: FindReportingNotices


class OverviewState(BaseModel):
    # Null when the overview's state couldn't be read just now.
    built: bool | None
    # When the current build was made, as an ISO 8601 time, or null before the first.
    built_at: str | None
    # How many of the 5 km tiles of 1 m elevation the build holds.
    tiles: int


class TerrainState(BaseModel):
    """Facts for the map's terrain messages: "zoom in for detail", "the overview is still being prepared"."""

    # From this zoom up, terrain tiles are drawn from the 1 m data. Below it, from the national overview.
    fine_minzoom: int
    # How many 5 km tiles of 1 m elevation exist.
    catalogue_tiles: int
    overview: OverviewState


class Meta(BaseModel):
    app: AppInfo
    auth: AuthInfo
    vocab: Vocab
    layers: Layers
    sources: list[SourceOut]
    notices: Notices
    terrain: TerrainState
