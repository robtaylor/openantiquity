"""Request and response shapes for findings, second looks, evidence, discussion and review.

Every position in a response is built by `location_out`, which goes through
`services.sensitivity.visible_location`. Nothing here reads `Finding.location`,
`Finding.outline` or `Finding.grid_ref` for itself.

What a viewer who hasn't answered may see follows Decision 0008: the finding's
title and claim, its tier, state and score, and its next steps without their
numbers (`review.blind_step`), but no person's answer, no tally of answers
and no name of anyone who answered. The score moves as answers come in, as a
tier does, so the people who answered aren't credited to this viewer at all
(Decision 0010). `FindingDetail.from_view` applies all this from
`FindingView.answers_visible`.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, UrlConstraints, model_validator
from shapely.geometry.base import BaseGeometry

from fieldclub import gridref
from fieldclub.models import Comment, Finding, FindingShapeChange, Observation, User
from fieldclub.schemas.common import (
    ApiModel,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    PublicUser,
    RequestModel,
    geojson_geometry,
    geojson_point,
)
from fieldclub.services import actions, review, sensitivity, shapes
from fieldclub.services.actions import Action
from fieldclub.services.confidence import (
    ANSWER_CREDIT_KINDS,
    Assessment,
    CreditKind,
    EvidenceStatus,
    NextStep,
)
from fieldclub.services.findings import EvidenceView, FindingView, may_see_hidden_comment
from fieldclub.services.media import may_see_media
from fieldclub.vocab import (
    CHECK_EXPLANATIONS,
    EvidenceKind,
    Explanation,
    FeatureClass,
    FindingState,
    NextStepCode,
    Outcome,
    Period,
    PointKind,
    Relation,
    Sensitivity,
    ShapeChangeKind,
    ShapeKind,
    Stance,
    Strand,
    Tier,
    Visible,
)

TITLE_MAX = 120
TEXT_MAX = 5000
URL_MAX = 2000
REFERENCE_MAX = 200


def _maybe[E: (FeatureClass, Period, Explanation, Relation, Outcome)](
    enum: type[E], value: str | None
) -> E | None:
    return enum(value) if value is not None else None


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------


class ViewState(BaseModel):
    """What the finder was looking at. Opening the finding restores it.

    The keys are fixed so that a view can't carry anything else, such as a
    centre point or a note, onto a blind review card.
    """

    model_config = ConfigDict(extra="forbid")

    layer: str | None = Field(default=None, max_length=40, pattern=r"^[a-z0-9_-]+$")
    zoom: float | None = Field(default=None, ge=0, le=24)
    bearing: float | None = Field(default=None, ge=-360, le=360)
    pitch: float | None = Field(default=None, ge=0, le=85)
    sun_azimuth: float | None = Field(default=None, ge=0, le=360)
    sun_altitude: float | None = Field(default=None, ge=0, le=90)
    exaggeration: float | None = Field(default=None, ge=0, le=20)

    @classmethod
    def from_stored(cls, stored: dict[str, Any] | None) -> ViewState:
        """A stored view, keeping only the known keys with values that pass validation."""
        kept: dict[str, Any] = {}
        for name in cls.model_fields:
            value = (stored or {}).get(name)
            if value is None:
                continue
            try:
                cls.model_validate({name: value})
            except ValueError:
                continue
            kept[name] = value
        return cls.model_validate(kept)

    def to_stored(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Location(ApiModel):
    """A finding's position as this viewer may see it (Decision 0005).

    For a finding drawn as a line or shape this is its anchor, the one point
    everything that places a finding by a point uses.
    """

    lon: float
    lat: float
    # True when the position is the centre of a 1 km square, not the finding itself.
    obscured: bool
    # `SU 1025 6996` when exact, `SU 10 69` when obscured.
    grid_ref: str | None
    # The compact square, such as `SU1069`, when obscured.
    square: str | None
    # The drawn shape, on a finding's page only (`LocationDetail`). Always null
    # in a list, so a page of long lines costs nothing, and when obscured.
    outline: GeoJSONGeometry | None
    # `line` or `area` for a finding drawn as one. Always null when obscured.
    shape_kind: ShapeKind | None = None


def location_out(finding: Finding, viewer: User | None) -> Location:
    """The one way a response gets a finding's position: its point, with no shape."""
    seen = sensitivity.visible_location(finding, viewer)
    return Location(
        lon=round(seen.lon, 6),
        lat=round(seen.lat, 6),
        obscured=seen.obscured,
        grid_ref=seen.grid_ref,
        square=seen.square,
        outline=None,
        shape_kind=seen.shape_kind,
    )


# --------------------------------------------------------------------------
# Lines and shapes
# --------------------------------------------------------------------------


class PathPoint(RequestModel):
    """A point the finder tapped. A segment between two corners is straight."""

    lon: float
    lat: float
    kind: PointKind


class Path(RequestModel):
    """The points a finding's line or shape goes through, in order (`services.shapes`).

    An open path has two points or more and a closed one three or more,
    without repeating the first. `curve` may be left out, and the server
    writes it. The server derives the shape and checks the limits in
    `GET /meta`'s `shapes`.
    """

    closed: bool = False
    # Checked by the server, which refuses any other curve with `unknown_curve`.
    curve: str | None = Field(default=None, max_length=64)
    # Counted by the server, which refuses more than `shapes.path_max_points` with `path_too_many_points`.
    points: list[PathPoint]


class PathPointOut(ApiModel):
    lon: float
    lat: float
    kind: PointKind


class PathOut(ApiModel):
    closed: bool
    curve: str
    points: list[PathPointOut]


class AddedView(ApiModel):
    """A centre and a zoom that frame what an extension added."""

    lon: float
    lat: float
    zoom: float


class ShapeChangeOut(ApiModel):
    # `changed` for a viewer who sees only the square, who learns the date and nothing else.
    kind: ShapeChangeKind | Literal["changed"]
    on: date
    added_length_m: float | None = None
    added_view: AddedView | None = None


class ShapeOut(ApiModel):
    """A finding's shape as this viewer may know it.

    For a viewer who sees only the square, every field is null but
    `changes`, which says that the shape changed and when.

    `changes` holds the newest 50 changes to the shape, oldest first.
    """

    kind: ShapeKind | None
    # The geodesic length of a line, or the perimeter of an area.
    length_m: float | None
    # The `path_revision` a change to the shape names.
    revision: int | None
    # West, south, east, north.
    extent: list[float] | None
    changes: list[ShapeChangeOut]
    # How much of the shape, a line's length or an area's edge, lies further
    # than `/meta` `shapes.looked_at_max_move_m` from what second looks were
    # given on, and a centre and zoom that frame it. Null before any second
    # look and when nothing lies beyond.
    added_since_looked_m: float | None
    added_view: AddedView | None = None
    # What second looks were given on, which an edit must keep most of close
    # (`/meta` `shapes.looked_at_max_move_m` and `looked_at_min_kept`). Only for
    # someone who may change the finding (`actions.edit`), and null before any second look.
    looked_at: GeoJSONGeometry | None = None


class LocationDetail(Location):
    """A finding's position on its page, with its path and what has changed in its shape.

    `outline` is the shape simplified to a few metres (`outline_mid`). The
    full shape is in downloads, and the editor derives it from `path`.
    """

    path: PathOut | None
    shape: ShapeOut


def location_detail(
    finding: Finding,
    viewer: User | None,
    changes: list[FindingShapeChange],
    *,
    may_change: bool = False,
) -> LocationDetail:
    """The page's `location`, through `sensitivity.visible_location` and `visible_shape`."""
    shape = sensitivity.visible_shape(finding, viewer, changes, may_change=may_change)
    where = location_out(finding, viewer)
    return LocationDetail(
        **where.model_dump(exclude={"outline"}),
        outline=geojson_geometry(shape.outline, decimals=shapes.DECIMALS),
        path=PathOut.model_validate(shape.path) if shape.path is not None else None,
        shape=ShapeOut(
            kind=shape.kind,
            length_m=shape.length_m,
            revision=shape.revision,
            extent=list(shape.extent) if shape.extent is not None else None,
            changes=[ShapeChangeOut.model_validate(change) for change in shape.changes],
            added_since_looked_m=shape.added_since_looked_m,
            added_view=AddedView.model_validate(shape.added_view) if shape.added_view is not None else None,
            looked_at=geojson_geometry(shape.looked_at, decimals=shapes.DECIMALS),
        ),
    )


class NextStepOut(ApiModel):
    code: NextStepCode
    prompt: str
    people: int | None = None
    check: str | None = None
    strands_needed: int | None = None
    missing_strands: list[str] = Field(default_factory=list)
    weight_needed: float | None = None
    pending_evidence: list[int] = Field(default_factory=list)

    @classmethod
    def from_step(cls, step: NextStep) -> NextStepOut:
        return cls(
            code=step.code,
            prompt=step.prompt,
            people=step.people,
            check=step.check.value if step.check is not None else None,
            strands_needed=step.strands_needed,
            missing_strands=[strand.value for strand in step.missing_strands],
            weight_needed=step.weight_needed,
            pending_evidence=list(step.pending_evidence),
        )


# --------------------------------------------------------------------------
# Findings: requests
# --------------------------------------------------------------------------


class FindingCreate(RequestModel):
    """A new finding: a point or a path, or both, and the feature class.

    Without a point the server places one on the shape. `outline`, a
    LineString or a one-ring Polygon read as a path of corners, is accepted
    for a release, and never with a `path`.
    """

    location: GeoJSONGeometry | None = None
    feature_class: FeatureClass
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    period: Period = Period.UNKNOWN
    path: Path | None = None
    outline: GeoJSONGeometry | None = None
    view_state: ViewState | None = None
    # A request below the class default is honoured only from a moderator.
    sensitivity: Sensitivity | None = None
    # The browser's own name for the draft this saves, up to 64 printable
    # ASCII characters without spaces, such as a UUID. Sent again by the same
    # person, it answers 200 with the finding already made and stores nothing.
    client_ref: str | None = Field(default=None, pattern=r"^[\x21-\x7e]{1,64}$")


class FindingUpdate(RequestModel):
    """Changes the finder makes. Fields left out are left alone.

    `path` replaces the whole path and `path: null` removes the shape. Either
    needs `path_revision`, the shape's `revision` it started from: another
    is 409 `shape_changed`. `outline` is read as `path` is, for a release.
    """

    location: GeoJSONGeometry | None = None
    feature_class: FeatureClass | None = None
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    period: Period | None = None
    path: Path | None = None
    path_revision: int | None = Field(default=None, ge=0)
    outline: GeoJSONGeometry | None = None
    view_state: ViewState | None = None


class SensitivityChange(RequestModel):
    level: Sensitivity


# --------------------------------------------------------------------------
# Findings: responses
# --------------------------------------------------------------------------


class FindingSummary(ApiModel):
    """A finding in a list. No answers and no tallies of answers."""

    public_id: str
    title: str
    feature_class: FeatureClass
    period: Period
    tier: Tier
    state: FindingState
    state_reason: str | None
    confidence: int
    sensitivity: Sensitivity
    location: Location
    author: PublicUser
    created_at: datetime
    updated_at: datetime
    evidence_count: int
    comment_count: int
    mention_count: int

    @classmethod
    def build(cls, finding: Finding, author: User, viewer: User | None) -> FindingSummary:
        return cls(**_summary_fields(finding, author, viewer))


def _summary_fields(finding: Finding, author: User, viewer: User | None) -> dict[str, Any]:
    assert author.has_id(finding.author_id), "the author passed is not the finding's author"
    return {
        "public_id": finding.public_id,
        "title": sensitivity.visible_text(finding, viewer, finding.title),
        "feature_class": finding.feature_class,
        "period": finding.period,
        "tier": finding.tier,
        "state": finding.state,
        "state_reason": finding.state_reason,
        "confidence": finding.confidence,
        "sensitivity": finding.sensitivity,
        "location": location_out(finding, viewer),
        "author": PublicUser.from_user(author),
        "created_at": finding.created_at,
        "updated_at": finding.updated_at,
        "evidence_count": finding.evidence_count,
        "comment_count": finding.comment_count,
        "mention_count": finding.mention_count,
    }


class CheckOut(ApiModel):
    check: str
    asserted: float
    against: float
    cleared: bool


class Tallies(ApiModel):
    """How people answered, in total. Shown only to the finder and to people who have answered."""

    observation_count: int
    seen: float
    unseen: float
    observers: int
    seen_ratio: float | None
    class_support: dict[str, float]
    class_agreement: float
    community_class: FeatureClass | None
    explanations: dict[str, float]
    checks: list[CheckOut]

    @classmethod
    def from_assessment(cls, assessment: Assessment, observation_count: int) -> Tallies:
        return cls(
            observation_count=observation_count,
            seen=assessment.seen,
            unseen=assessment.unseen,
            observers=assessment.observers,
            seen_ratio=assessment.seen_ratio,
            class_support={key.value: value for key, value in assessment.class_support.items()},
            class_agreement=assessment.class_agreement,
            community_class=assessment.community_class,
            explanations={key.value: value for key, value in assessment.explanations.items()},
            checks=[
                CheckOut(check=c.check.value, asserted=c.asserted, against=c.against, cleared=c.cleared)
                for c in assessment.checks
            ],
        )


class AssessmentOut(ApiModel):
    """The ladder as the finding page shows it: the meter, the step and what's missing."""

    tier: Tier
    state: FindingState
    state_reason: str | None
    score: int
    next_tier: Tier | None
    next_steps: list[NextStepOut]
    # Null for someone who hasn't answered yet (Decision 0008).
    tallies: Tallies | None


class CreditOut(ApiModel):
    user: PublicUser
    kind: CreditKind
    evidence_id: int | None = None


class ActionOut(ApiModel):
    """Whether this viewer may do something, and if not, the code the route would refuse with."""

    allowed: bool
    # Null when allowed. Otherwise an error code, or `already_answered`,
    # `answer_withdrawn`, `highest_level`, `lowest_level` or
    # `nothing_to_verify` when there is nothing to do (`services.actions`).
    reason: str | None

    @classmethod
    def build(cls, action: Action) -> ActionOut:
        return cls(allowed=action.allowed, reason=action.reason)


class FindingActionsOut(ApiModel):
    """What this viewer may do on the finding, from the rules its routes enforce (`services.actions`)."""

    answer: ActionOut
    add_evidence: ActionOut
    comment: ActionOut
    edit: ActionOut
    withdraw: ActionOut
    # To the next level up, through `PUT /findings/{public_id}/sensitivity`.
    raise_level: ActionOut
    # To the next level down, through `PUT /mod/findings/{public_id}/sensitivity`.
    lower_level: ActionOut
    # An official item someone else added. Each item's own `actions.verify` says which.
    verify: ActionOut


class EvidenceActionsOut(ApiModel):
    vote: ActionOut
    verify: ActionOut


class EvidenceOut(ApiModel):
    """One evidence item.

    For a viewer who can't see the finding's exact position, everything that
    could point at it (the address, the record, the reference, the photo and
    the view) is left out and `redacted` is true.
    """

    id: int
    kind: EvidenceKind
    stance: Stance
    title: str | None
    note: str | None
    url: str | None
    record_id: int | None
    source_key: str | None
    reference: str | None
    relation: Relation | None
    media_id: int | None
    view: ViewState | None
    occurred_on: date | None
    organisation: str | None
    outcome: Outcome | None
    contributor: PublicUser
    created_at: datetime
    verified_by: PublicUser | None
    # The weighted sum of the votes the engine counts, and how many people cast
    # them each way: neither the contributor's nor the finder's votes count,
    # nor those of a banned account.
    vote_total: float
    endorsements: int
    disputes: int
    standing: bool
    independent: bool
    my_vote: int | None
    redacted: bool
    actions: EvidenceActionsOut


class ObservationOut(ApiModel):
    user: PublicUser
    visible: Visible
    feature_class: FeatureClass | None
    period: Period | None
    explanation: Explanation | None
    not_modern: bool | None
    not_natural: bool | None
    not_artefact: bool | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    # True once taken back. It no longer counts, and can't be replaced by another answer.
    withdrawn: bool
    # False while an answer given with `detail_follows` waits for its detail or its reveal.
    revealed: bool

    @classmethod
    def build(
        cls, observation: Observation, user: User, *, finding: Finding, viewer: User | None
    ) -> ObservationOut:
        """`user` gave the answer and `viewer` reads it, whose view of `finding` its note follows."""
        assert user.has_id(observation.user_id), "the user passed did not give this observation"
        assert observation.finding_id == finding.id, "the answer is on another finding"
        return cls(
            user=PublicUser.from_user(user),
            visible=Visible(observation.visible),
            feature_class=_maybe(FeatureClass, observation.feature_class),
            period=_maybe(Period, observation.period),
            explanation=_maybe(Explanation, observation.explanation),
            not_modern=observation.not_modern,
            not_natural=observation.not_natural,
            not_artefact=observation.not_artefact,
            note=sensitivity.visible_text(finding, viewer, observation.note),
            created_at=observation.created_at,
            updated_at=observation.updated_at,
            withdrawn=observation.withdrawn_at is not None,
            revealed=observation.revealed_at is not None,
        )


class FindingDetail(FindingSummary):
    """A finding's page."""

    location: LocationDetail  # pyright: ignore[reportIncompatibleVariableOverride]
    description: str | None
    nation: str | None
    view_state: ViewState
    assessment: AssessmentOut
    evidence: list[EvidenceOut]
    credits: list[CreditOut]
    # Whether this viewer may see other people's answers: the finder, or someone who has answered.
    answers_visible: bool
    my_observation: ObservationOut | None
    following: bool
    actions: FindingActionsOut

    @classmethod
    def from_view(cls, view: FindingView, viewer: User | None) -> FindingDetail:
        finding, assessment = view.finding, view.assessment
        statuses = {status.id: status for status in assessment.evidence}
        exact = sensitivity.sees_exact(finding, viewer)
        tallies = (
            Tallies.from_assessment(assessment, finding.observation_count) if view.answers_visible else None
        )
        allowed = actions.finding_actions(
            finding, viewer, view.my_observation, [item.evidence for item in view.evidence]
        )
        fields = _summary_fields(finding, view.author, viewer)
        fields["location"] = location_detail(
            finding,
            viewer,
            view.shape_changes,
            may_change=allowed.edit.allowed,
        )
        # Asking for a look at what was added to a line says it is a line.
        steps = [
            step for step in assessment.next_steps if exact or step.code is not NextStepCode.LOOK_AT_NEW_PART
        ]
        return cls(
            **fields,
            description=sensitivity.visible_text(finding, viewer, finding.description),
            nation=view.nation,
            view_state=ViewState.from_stored(sensitivity.visible_view_state(finding, viewer)),
            assessment=AssessmentOut(
                tier=assessment.tier,
                state=assessment.state,
                state_reason=assessment.state_reason.value if assessment.state_reason is not None else None,
                score=assessment.score,
                next_tier=assessment.next_tier,
                next_steps=[
                    NextStepOut.from_step(step if view.answers_visible else review.blind_step(step))
                    for step in steps
                ],
                tallies=tallies,
            ),
            evidence=[
                _evidence_out(item, statuses, finding=finding, exact=exact, viewer=viewer)
                for item in view.evidence
            ],
            credits=_credits(view),
            answers_visible=view.answers_visible,
            my_observation=(
                ObservationOut.build(view.my_observation, viewer, finding=finding, viewer=viewer)
                if view.my_observation is not None and viewer is not None
                else None
            ),
            following=view.following,
            actions=_finding_actions(allowed),
        )


def _credits(view: FindingView) -> list[CreditOut]:
    """Who did what. People who answered are named only to those who may see answers.

    The score and tier move with each answer, so naming them to anyone else
    would let a reload tie a yes or a no to a person (Decision 0010).
    """
    return [
        CreditOut(
            user=PublicUser.from_user(view.people[credit.user_id]),
            kind=credit.kind,
            evidence_id=credit.evidence_id,
        )
        for credit in view.assessment.credits
        if view.answers_visible or credit.kind not in ANSWER_CREDIT_KINDS
    ]


def _finding_actions(found: actions.FindingActions) -> FindingActionsOut:
    return FindingActionsOut(
        **{f.name: ActionOut.build(getattr(found, f.name)) for f in dataclasses.fields(found)}
    )


def _evidence_out(
    item: EvidenceView,
    statuses: dict[int, EvidenceStatus],
    *,
    finding: Finding,
    exact: bool,
    viewer: User | None,
) -> EvidenceOut:
    evidence = item.evidence
    status = statuses.get(evidence.id)
    data = evidence.data or {}
    shows_media = item.media is not None and may_see_media(item.media, viewer)
    allowed = actions.evidence_actions(finding, evidence, viewer)
    return EvidenceOut(
        id=evidence.id,
        kind=EvidenceKind(evidence.kind),
        stance=Stance(evidence.stance),
        title=sensitivity.visible_text(finding, viewer, evidence.title),
        note=sensitivity.visible_text(finding, viewer, evidence.note),
        url=sensitivity.visible_url(finding, viewer, evidence.url),
        record_id=evidence.record_id if exact else None,
        source_key=data.get("source_key") if exact else None,
        reference=evidence.reference if exact else None,
        relation=_maybe(Relation, evidence.relation),
        media_id=evidence.media_id if exact and shows_media else None,
        view=ViewState.from_stored(data.get("view")) if exact and data.get("view") else None,
        occurred_on=evidence.occurred_on,
        organisation=evidence.organisation,
        outcome=_maybe(Outcome, evidence.outcome),
        contributor=PublicUser.from_user(item.contributor),
        created_at=evidence.created_at,
        verified_by=PublicUser.from_user(item.verifier) if item.verifier is not None else None,
        vote_total=status.vote_total if status is not None else 0.0,
        endorsements=item.endorsements,
        disputes=item.disputes,
        standing=status.standing if status is not None else True,
        independent=status.independent if status is not None else False,
        my_vote=item.my_vote,
        redacted=not exact,
        actions=EvidenceActionsOut(
            vote=ActionOut.build(allowed.vote), verify=ActionOut.build(allowed.verify)
        ),
    )


# --------------------------------------------------------------------------
# GeoJSON for the map
# --------------------------------------------------------------------------


class FindingFeatureProperties(ApiModel):
    public_id: str
    title: str
    feature_class: FeatureClass
    period: Period
    tier: Tier
    state: FindingState
    confidence: int
    sensitivity: Sensitivity
    obscured: bool
    square: str | None
    grid_ref: str | None
    # The line or shape, simplified for the zoom and cut to the box, for a
    # viewer who sees the finding exactly. Null otherwise.
    shape: GeoJSONGeometry | None = None


class FindingFeature(BaseModel):
    """A finding on the map: always a point, at the position this viewer may see.

    A finding drawn as a line or shape carries it in `properties.shape`.
    """

    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONGeometry
    properties: FindingFeatureProperties


class FindingFeatureCollection(GeoJSONFeatureCollection):
    """The map's findings. `next_cursor` is a foreign member, null on the last page."""

    features: list[FindingFeature] = Field(default_factory=list)  # pyright: ignore[reportIncompatibleVariableOverride]
    next_cursor: str | None = None


def finding_feature(
    finding: Finding, viewer: User | None, shape: BaseGeometry | None = None
) -> FindingFeature:
    """`shape` comes from `services.shape_edits.map_shapes`, which gives one only to an exact viewer."""
    where = location_out(finding, viewer)
    assert shape is None or not where.obscured, "an obscured finding has no shape on the map"
    return FindingFeature(
        id=finding.public_id,
        geometry=geojson_point(where.lon, where.lat),
        properties=FindingFeatureProperties(
            public_id=finding.public_id,
            title=sensitivity.visible_text(finding, viewer, finding.title) or "",
            feature_class=FeatureClass(finding.feature_class),
            period=Period(finding.period),
            tier=Tier(finding.tier),
            state=FindingState(finding.state),
            confidence=finding.confidence,
            sensitivity=Sensitivity(finding.sensitivity),
            obscured=where.obscured,
            square=where.square,
            grid_ref=where.grid_ref,
            shape=geojson_geometry(shape, decimals=shapes.DECIMALS),
        ),
    )


# --------------------------------------------------------------------------
# Second looks
# --------------------------------------------------------------------------


class ObservationDetailIn(RequestModel):
    """What you think it is, beyond whether you can see it. Every part is optional.

    A check can't be asserted together with its matching explanation, such
    as `not_modern` with `explanation: modern`.
    """

    feature_class: FeatureClass | None = None
    period: Period | None = None
    explanation: Explanation | None = None
    not_modern: bool | None = None
    not_natural: bool | None = None
    not_artefact: bool | None = None
    note: str | None = Field(default=None, max_length=TEXT_MAX)

    @model_validator(mode="after")
    def _consistent(self) -> ObservationDetailIn:
        check = review.contradicted_check(self)
        if check is not None:
            raise ValueError(f"An answer can't say both {check.value} and {CHECK_EXPLANATIONS[check].value}.")
        return self


class ObservationIn(ObservationDetailIn):
    """A second look: can you see it, and optionally what do you think it is.

    It is final once given: only `note` can change afterwards. With
    `detail_follows`, it carries `visible` alone. It is stored and counts at
    once, the reply reveals nothing, and the detail or the reveal alone
    follows through `POST /findings/{public_id}/observation/reveal`.
    """

    visible: Visible
    detail_follows: bool = False
    # The `shape_revision` of the finding as it was shown, from the review card,
    # the task or `location.shape.revision`. When the shape has changed since,
    # the answer is refused with 409 `shape_changed` and nothing is stored.
    # Left out, the answer is taken as given on the shape as it is now.
    shape_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _detail_later(self) -> ObservationIn:
        if self.detail_follows and any(
            getattr(self, name) is not None for name in ObservationDetailIn.model_fields
        ):
            raise ValueError("An answer whose detail follows carries only `visible`. Send the detail next.")
        return self


class AnswerCounts(ApiModel):
    yes: int
    unsure: int
    no: int


class ComparisonOut(ApiModel):
    """How your answer compares, shown once you have given it."""

    finder_class: FeatureClass
    community_class: FeatureClass | None
    # Null when you didn't say what you think it is.
    matches_finder: bool | None
    # Everyone else's answers, not counting yours or the finder's.
    others: AnswerCounts


class AnswerHeld(ApiModel):
    """An answer given with `detail_follows`: stored and counted, and nothing shown yet."""

    revealed: Literal[False] = False
    observation: ObservationOut


class Reveal(ApiModel):
    """What answering a second look shows you: the finding in full, and whether it moved.

    The tiers and states are those before and after this request. After an
    answer given in two steps, the reveal compares the tier before and after
    the detail, so a move the answer made on its own isn't shown as one.
    """

    revealed: Literal[True] = True
    observation: ObservationOut
    finding: FindingDetail
    comparison: ComparisonOut
    tier_before: Tier
    tier_after: Tier
    state_before: FindingState
    state_after: FindingState
    moved_up: bool


class ReviewPlace(ApiModel):
    lon: float
    lat: float
    grid_ref: str | None


class ReviewCard(ApiModel):
    """A blind second look: where to look and how, and nothing about what anyone thought."""

    public_id: str
    place: ReviewPlace
    view_state: ViewState
    # The finding's shape revision, which the answer names (`ObservationIn.shape_revision`).
    shape_revision: int


def review_view(
    finding: Finding, viewer: User | None, new_part: dict[str, Any] | None
) -> tuple[Location, ViewState]:
    """Where a second look is asked for, and how: the finding as the viewer sees it, with the finder's view.

    While the finding asks for a look at what was added to its line,
    `new_part` (`review.new_part_view`) moves the place to the added part
    and zooms to frame it.
    """
    where = location_out(finding, viewer)
    view = ViewState.from_stored(sensitivity.visible_view_state(finding, viewer))
    if new_part is None:
        return where, view
    assert not where.obscured, "the new part is shown only to exact viewers"
    lon, lat = new_part["lon"], new_part["lat"]
    place = where.model_copy(update={"lon": lon, "lat": lat, "grid_ref": gridref.to_gridref(lon, lat)})
    return place, view.model_copy(update={"zoom": float(new_part["zoom"])})


class TaskFinding(ApiModel):
    title: str
    feature_class: FeatureClass
    tier: Tier
    state: FindingState


class TaskItem(ApiModel):
    """One open next step on one finding.

    For a step that is answered by a second look, `step` and `finding` are
    null, so the task stays as blind as a review card.
    """

    public_id: str
    code: NextStepCode
    place: Location
    view_state: ViewState
    step: NextStepOut | None
    finding: TaskFinding | None
    # The finding's shape revision, which an answer names (`ObservationIn.shape_revision`).
    # Null for a viewer who sees only the square, who can't answer.
    shape_revision: int | None = None


class StrandCount(ApiModel):
    """How many findings in the evidence step lack one kind of desk evidence."""

    strand: Strand
    total: int


class TaskGroupOut(ApiModel):
    code: NextStepCode
    total: int
    items: list[TaskItem]
    next_cursor: str | None
    # For `need_strand` only: its findings counted by each kind of desk evidence they lack, in the
    # order of `Strand`. A finding lacking several counts under each. Empty for every other code.
    strands: list[StrandCount]


class TaskGroups(ApiModel):
    groups: list[TaskGroupOut]


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class EvidenceIn(RequestModel):
    """A piece of evidence. Which fields each kind needs is checked by `services.findings`."""

    kind: EvidenceKind
    stance: Stance = Stance.SUPPORTS
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX * 2)
    note: str | None = Field(default=None, max_length=TEXT_MAX)
    url: Annotated[HttpUrl, UrlConstraints(max_length=URL_MAX)] | None = None
    record_id: int | None = Field(default=None, ge=1)
    source_key: str | None = Field(default=None, min_length=1, max_length=100)
    reference: str | None = Field(default=None, min_length=1, max_length=REFERENCE_MAX)
    relation: Relation | None = None
    media_id: int | None = Field(default=None, ge=1)
    view: ViewState | None = None
    occurred_on: date | None = None
    organisation: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX * 2)
    outcome: Outcome | None = None


class VoteIn(RequestModel):
    """+1 endorses, -1 objects, 0 takes your vote back."""

    value: Literal[-1, 0, 1]


class Vote(ApiModel):
    evidence_id: int
    value: int


# --------------------------------------------------------------------------
# Discussion
# --------------------------------------------------------------------------


class CommentIn(RequestModel):
    body: str = Field(min_length=1, max_length=TEXT_MAX)
    parent_id: int | None = Field(default=None, ge=1)


class CommentOut(ApiModel):
    id: int
    parent_id: int | None
    # Null once deleted, so a thread keeps its shape.
    author: PublicUser | None
    body: str | None
    created_at: datetime
    edited_at: datetime | None
    # True once deleted, and for a comment a moderator hid, to everyone who may not see it.
    deleted: bool
    # True only for the moderators and the author who still see a hidden comment.
    hidden: bool = False

    @classmethod
    def build(cls, comment: Comment, author: User, viewer: User | None, *, finding: Finding) -> CommentOut:
        """The comment as `viewer` may see it. A hidden one reads as deleted unless they may see it.

        Positions written in it are hidden from a viewer who doesn't see `finding` exactly.
        """
        assert author.has_id(comment.user_id), "the author passed did not write this comment"
        assert comment.finding_id == finding.id, "the comment is on another finding"
        hidden = comment.hidden_at is not None
        shows_hidden = hidden and may_see_hidden_comment(comment, viewer)
        removed = comment.deleted_at is not None or (hidden and not shows_hidden)
        return cls(
            id=comment.id,
            parent_id=comment.parent_id,
            author=None if removed else PublicUser.from_user(author),
            body=None if removed else sensitivity.visible_text(finding, viewer, comment.body),
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted=removed,
            hidden=shows_hidden and comment.deleted_at is None,
        )


class FollowOut(ApiModel):
    following: bool
