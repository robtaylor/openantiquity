"""Request and response shapes for findings, second looks, evidence, discussion and review.

Every position in a response is built by `location_out`, which goes through
`services.sensitivity.visible_location`. Nothing here reads `Finding.location`,
`Finding.outline` or `Finding.grid_ref` for itself.

What a viewer who hasn't answered may see follows Decision 0008: the finding's
title and claim, its tier, state and next steps, but no person's answer and
no tally of answers. `FindingDetail.from_view` applies it from
`FindingView.answers_visible`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from fieldclub.models import Comment, Finding, Observation, User
from fieldclub.schemas.common import (
    ApiModel,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    PublicUser,
    RequestModel,
    to_geojson,
)
from fieldclub.services import sensitivity
from fieldclub.services.confidence import Assessment, CreditKind, EvidenceStatus, NextStep
from fieldclub.services.findings import EvidenceView, FindingView
from fieldclub.services.media import may_see_media
from fieldclub.vocab import (
    EvidenceKind,
    Explanation,
    FeatureClass,
    FindingState,
    NextStepCode,
    Outcome,
    Period,
    Relation,
    Sensitivity,
    Stance,
    Tier,
    Visible,
)

TITLE_MAX = 120


def _maybe[E: (FeatureClass, Period, Explanation, Relation, Outcome)](
    enum: type[E], value: str | None
) -> E | None:
    return enum(value) if value is not None else None


TEXT_MAX = 5000
URL_MAX = 2000
REFERENCE_MAX = 200


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


class LocationOut(ApiModel):
    """A finding's position as this viewer may see it (Decision 0005)."""

    lon: float
    lat: float
    # True when the position is the centre of a 1 km square, not the finding itself.
    obscured: bool
    # `SU 1025 6996` when exact, `SU 10 69` when obscured.
    grid_ref: str | None
    # The compact square, such as `SU1069`, when obscured.
    square: str | None
    # The drawn outline. Always null when obscured.
    outline: GeoJSONGeometry | None


def location_out(finding: Finding, viewer: User | None) -> LocationOut:
    """The one way a response gets a finding's position."""
    seen = sensitivity.visible_location(finding, viewer)
    return location_from(seen)


def location_from(seen: sensitivity.VisibleLocation) -> LocationOut:
    outline = to_geojson(seen.outline)
    return LocationOut(
        lon=round(seen.lon, 6),
        lat=round(seen.lat, 6),
        obscured=seen.obscured,
        grid_ref=seen.grid_ref,
        square=seen.square,
        outline=GeoJSONGeometry.model_validate(outline) if outline is not None else None,
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
    """A new finding. Only the point and the feature class are required."""

    location: GeoJSONGeometry
    feature_class: FeatureClass
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    period: Period = Period.UNKNOWN
    outline: GeoJSONGeometry | None = None
    view_state: ViewState | None = None
    # A request below the class default is honoured only from a moderator.
    sensitivity: Sensitivity | None = None


class FindingUpdate(RequestModel):
    """Changes the finder makes. Fields left out are left alone. `outline: null` removes it."""

    location: GeoJSONGeometry | None = None
    feature_class: FeatureClass | None = None
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    period: Period | None = None
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
    location: LocationOut
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
        "title": finding.title,
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


# "answered" stands in for how a person answered when answers are hidden.
CreditOutKind = Literal[
    "spotted",
    "saw_it",
    "could_not_see",
    "unsure",
    "explained",
    "answered",
    "added_evidence",
    "endorsed",
    "verified",
]

ANSWER_CREDITS = frozenset(
    {CreditKind.SAW_IT, CreditKind.COULD_NOT_SEE, CreditKind.UNSURE, CreditKind.EXPLAINED}
)


class CreditOut(ApiModel):
    user: PublicUser
    kind: CreditOutKind
    evidence_id: int | None = None


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
    vote_total: float
    standing: bool
    independent: bool
    my_vote: int | None
    redacted: bool


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

    @classmethod
    def build(cls, observation: Observation, user: User) -> ObservationOut:
        assert user.has_id(observation.user_id), "the user passed did not give this observation"
        return cls(
            user=PublicUser.from_user(user),
            visible=Visible(observation.visible),
            feature_class=_maybe(FeatureClass, observation.feature_class),
            period=_maybe(Period, observation.period),
            explanation=_maybe(Explanation, observation.explanation),
            not_modern=observation.not_modern,
            not_natural=observation.not_natural,
            not_artefact=observation.not_artefact,
            note=observation.note,
            created_at=observation.created_at,
            updated_at=observation.updated_at,
        )


class FindingDetail(FindingSummary):
    """A finding's page."""

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

    @classmethod
    def from_view(cls, view: FindingView, viewer: User | None) -> FindingDetail:
        finding, assessment = view.finding, view.assessment
        statuses = {status.id: status for status in assessment.evidence}
        exact = sensitivity.sees_exact(finding, viewer)
        tallies = (
            Tallies.from_assessment(assessment, finding.observation_count) if view.answers_visible else None
        )
        return cls(
            **_summary_fields(finding, view.author, viewer),
            description=finding.description,
            nation=finding.nation,
            view_state=ViewState.from_stored(finding.view_state),
            assessment=AssessmentOut(
                tier=assessment.tier,
                state=assessment.state,
                state_reason=assessment.state_reason.value if assessment.state_reason is not None else None,
                score=assessment.score,
                next_tier=assessment.next_tier,
                next_steps=[NextStepOut.from_step(step) for step in assessment.next_steps],
                tallies=tallies,
            ),
            evidence=[_evidence_out(item, statuses, exact=exact, viewer=viewer) for item in view.evidence],
            credits=_credits(view),
            answers_visible=view.answers_visible,
            my_observation=(
                ObservationOut.build(view.my_observation, viewer)
                if view.my_observation is not None and viewer is not None
                else None
            ),
            following=view.following,
        )


def _credits(view: FindingView) -> list[CreditOut]:
    """Who did what. How each person answered is shown only when answers are visible."""
    credits: list[CreditOut] = []
    seen: set[tuple[int, str, int | None]] = set()
    for credit in view.assessment.credits:
        kind: str = credit.kind.value
        if credit.kind in ANSWER_CREDITS and not view.answers_visible:
            kind = "answered"
        key = (credit.user_id, kind, credit.evidence_id)
        if key in seen:
            continue
        seen.add(key)
        credits.append(
            CreditOut(
                user=PublicUser.from_user(view.people[credit.user_id]),
                kind=kind,
                evidence_id=credit.evidence_id,
            )
        )
    return credits


def _evidence_out(
    item: EvidenceView, statuses: dict[int, EvidenceStatus], *, exact: bool, viewer: User | None
) -> EvidenceOut:
    evidence = item.evidence
    status = statuses.get(evidence.id)
    data = evidence.data or {}
    shows_media = item.media is not None and may_see_media(item.media, viewer)
    return EvidenceOut(
        id=evidence.id,
        kind=EvidenceKind(evidence.kind),
        stance=Stance(evidence.stance),
        title=evidence.title,
        note=evidence.note,
        url=evidence.url if exact else None,
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
        standing=status.standing if status is not None else True,
        independent=status.independent if status is not None else False,
        my_vote=item.my_vote,
        redacted=not exact,
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


class FindingFeature(BaseModel):
    """A finding on the map: always a point, at the position this viewer may see."""

    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONGeometry
    properties: FindingFeatureProperties


class FindingFeatureCollection(GeoJSONFeatureCollection):
    """The map's findings. `next_cursor` is a foreign member, null on the last page."""

    features: list[FindingFeature] = Field(default_factory=list)  # pyright: ignore[reportIncompatibleVariableOverride]
    next_cursor: str | None = None


def finding_feature(finding: Finding, viewer: User | None) -> FindingFeature:
    where = location_out(finding, viewer)
    return FindingFeature(
        id=finding.public_id,
        geometry=GeoJSONGeometry(type="Point", coordinates=[where.lon, where.lat]),
        properties=FindingFeatureProperties(
            public_id=finding.public_id,
            title=finding.title,
            feature_class=FeatureClass(finding.feature_class),
            period=Period(finding.period),
            tier=Tier(finding.tier),
            state=FindingState(finding.state),
            confidence=finding.confidence,
            sensitivity=Sensitivity(finding.sensitivity),
            obscured=where.obscured,
            square=where.square,
            grid_ref=where.grid_ref,
        ),
    )


# --------------------------------------------------------------------------
# Second looks
# --------------------------------------------------------------------------


class ObservationIn(RequestModel):
    """A second look: can you see it, and optionally what do you think it is."""

    visible: Visible
    feature_class: FeatureClass | None = None
    period: Period | None = None
    explanation: Explanation | None = None
    not_modern: bool | None = None
    not_natural: bool | None = None
    not_artefact: bool | None = None
    note: str | None = Field(default=None, max_length=TEXT_MAX)


class AnswerCounts(ApiModel):
    yes: int
    unsure: int
    no: int


class Comparison(ApiModel):
    """How your answer compares, shown once you have given it."""

    finder_class: FeatureClass
    community_class: FeatureClass | None
    # Null when you didn't say what you think it is.
    matches_finder: bool | None
    # Everyone else's answers, not counting yours or the finder's.
    others: AnswerCounts


class Reveal(ApiModel):
    """What answering a second look shows you: the finding in full, and whether it moved."""

    observation: ObservationOut
    finding: FindingDetail
    comparison: Comparison
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
    place: LocationOut
    view_state: ViewState
    step: NextStepOut | None
    finding: TaskFinding | None


class TaskGroup(ApiModel):
    code: NextStepCode
    total: int
    items: list[TaskItem]
    next_cursor: str | None


class TaskGroups(ApiModel):
    groups: list[TaskGroup]


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class EvidenceIn(RequestModel):
    """A piece of evidence. Which fields each kind needs is checked by `services.findings`."""

    kind: EvidenceKind
    stance: Stance = Stance.SUPPORTS
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX * 2)
    note: str | None = Field(default=None, max_length=TEXT_MAX)
    url: HttpUrl | None = Field(default=None)
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


class VoteOut(ApiModel):
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
    deleted: bool

    @classmethod
    def build(cls, comment: Comment, author: User) -> CommentOut:
        assert author.has_id(comment.user_id), "the author passed did not write this comment"
        deleted = comment.deleted_at is not None
        return cls(
            id=comment.id,
            parent_id=comment.parent_id,
            author=None if deleted else PublicUser.from_user(author),
            body=None if deleted else comment.body,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted=deleted,
        )


class FollowOut(ApiModel):
    following: bool
