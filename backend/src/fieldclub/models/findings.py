"""Findings and everything attached to one: observations, evidence, talk and mentions."""

from __future__ import annotations

from datetime import date, datetime

from geoalchemy2 import WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    event,
    false,
    func,
    inspect,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from fieldclub import gridref
from fieldclub.db import Base
from fieldclub.models.common import (
    CreatedAt,
    IdPk,
    JsonDict,
    TimestampTz,
    any_geometry,
    enum_check,
    fk,
    json_column,
    point,
    point_lon_lat,
)
from fieldclub.vocab import (
    EvidenceKind,
    Explanation,
    FeatureClass,
    FindingState,
    MentionKind,
    Nation,
    Outcome,
    Period,
    Relation,
    Sensitivity,
    Stance,
    StateReason,
    Tier,
    Visible,
)


class Finding(Base):
    """A claim that something is there: who saw what, where, and what they think it is."""

    __tablename__ = "findings"
    __table_args__ = (
        enum_check("feature_class", FeatureClass),
        enum_check("community_class", FeatureClass),
        enum_check("period", Period),
        enum_check("sensitivity", Sensitivity),
        enum_check("tier", Tier),
        enum_check("state", FindingState),
        enum_check("state_reason", StateReason),
        enum_check("nation", Nation),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence_range"),
        # The help-wanted queue looks findings up by open step.
        Index("ix_findings_open_steps", "open_steps", postgresql_using="gin"),
        # Lists sort newest first by default.
        Index("ix_findings_created_at_id", "created_at", "id"),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    public_id: Mapped[str] = mapped_column(Text, unique=True)
    author_id: Mapped[int] = fk("users.id", index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    feature_class: Mapped[str] = mapped_column(Text)
    community_class: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str] = mapped_column(
        Text, default=Period.UNKNOWN.value, server_default=Period.UNKNOWN.value
    )
    location: Mapped[WKBElement] = mapped_column(point())
    # The position anyone may see: `location` when open, the centre of its 1 km
    # grid square otherwise. Written on every save by the listener below.
    # Queries for signed-out visitors use this column only.
    location_public: Mapped[WKBElement] = mapped_column(point())
    outline: Mapped[WKBElement | None] = mapped_column(any_geometry(spatial_index=False))
    # Left unset, a new finding takes its feature class's default level
    # (`services.sensitivity.default_sensitivity`) when it is first saved.
    sensitivity: Mapped[str] = mapped_column(Text, server_default=Sensitivity.OPEN.value)
    # What the finder was looking at: layer, zoom, bearing, pitch, sun_azimuth,
    # sun_altitude and exaggeration. Opening the finding restores it.
    view_state: Mapped[JsonDict] = json_column(default=dict, server_default="{}")
    nation: Mapped[str | None] = mapped_column(Text)
    grid_ref: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text, default=Tier.SPOTTED.value, server_default=Tier.SPOTTED.value)
    state: Mapped[str] = mapped_column(
        Text, default=FindingState.OPEN.value, server_default=FindingState.OPEN.value
    )
    state_reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(SmallInteger, default=10, server_default="10")
    assessment: Mapped[JsonDict] = json_column(default=dict, server_default="{}")
    observation_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(TimestampTz, server_default=func.now(), onupdate=func.now())
    tier_changed_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    hidden_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    # The codes of the assessment's next steps, so the help-wanted queue can
    # find them with an index. Written with the assessment by
    # `services.findings.reassess`.
    open_steps: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    # How many more second looks, at a member's weight, would move the finding
    # up a tier. None when answers alone can't. The second-look queue offers
    # the smallest first. Written with the assessment.
    answers_to_next: Mapped[int | None] = mapped_column(SmallInteger)

    def __repr__(self) -> str:
        return f"<Finding {self.public_id} {self.feature_class} {self.tier}/{self.state}>"


@event.listens_for(Finding, "before_insert")
def _before_insert_finding(_mapper: Mapper[Finding], _conn: Connection, finding: Finding) -> None:
    # Imported here because services import the models.
    from fieldclub.services import sensitivity

    if finding.sensitivity is None:
        finding.sensitivity = sensitivity.default_sensitivity(finding.feature_class).value
    sensitivity.refresh_location_public(finding)
    _refresh_grid_ref(finding)


@event.listens_for(Finding, "before_update")
def _before_update_finding(_mapper: Mapper[Finding], _conn: Connection, finding: Finding) -> None:
    from fieldclub.services import sensitivity

    state = inspect(finding)
    class_history = state.attrs.feature_class.history
    if class_history.has_changes() and class_history.deleted:
        # A move to a more sensitive class raises the level and never lowers it.
        raised = sensitivity.level_after_class_change(
            finding.sensitivity, class_history.deleted[0], finding.feature_class
        )
        if raised.value != finding.sensitivity:
            finding.sensitivity = raised.value
    if (
        state.attrs.location.history.has_changes()
        or state.attrs.sensitivity.history.has_changes()
        or finding.location_public is None
    ):
        sensitivity.refresh_location_public(finding)
    if state.attrs.location.history.has_changes():
        _refresh_grid_ref(finding)


def _refresh_grid_ref(finding: Finding) -> None:
    """Keep `grid_ref` in step with `location`: the 10 m reference, or None off both grids."""
    lon, lat = point_lon_lat(finding.location, f"finding {finding.public_id}")
    try:
        finding.grid_ref = gridref.to_gridref(lon, lat)
    except gridref.GridRefError:
        finding.grid_ref = None


class Observation(Base):
    """One person's second look: can they see it, and what do they think it is."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("finding_id", "user_id"),
        enum_check("visible", Visible),
        enum_check("feature_class", FeatureClass),
        enum_check("period", Period),
        enum_check("explanation", Explanation),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE")
    user_id: Mapped[int] = fk("users.id", index=True)
    visible: Mapped[str] = mapped_column(Text)
    feature_class: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    not_modern: Mapped[bool | None] = mapped_column(Boolean)
    not_natural: Mapped[bool | None] = mapped_column(Boolean)
    not_artefact: Mapped[bool | None] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(TimestampTz, server_default=func.now(), onupdate=func.now())
    # Set when the person takes their answer back. The row stays, so an answer
    # given after the reveal can't replace it (Decision 0008).
    withdrawn_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class Evidence(Base):
    """Something that bears on a finding: a map, a photo, a record, a visit, a publication."""

    __tablename__ = "evidence"
    __table_args__ = (
        enum_check("kind", EvidenceKind),
        enum_check("stance", Stance),
        enum_check("relation", Relation),
        enum_check("outcome", Outcome),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE", index=True)
    user_id: Mapped[int] = fk("users.id", index=True)
    kind: Mapped[str] = mapped_column(Text)
    stance: Mapped[str] = mapped_column(
        Text, default=Stance.SUPPORTS.value, server_default=Stance.SUPPORTS.value
    )
    title: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    # A record that disappears upstream is removed by ingest. The evidence stays.
    record_id: Mapped[int | None] = fk("records.id", ondelete="SET NULL", index=True)
    relation: Mapped[str | None] = mapped_column(Text)
    media_id: Mapped[int | None] = fk("media.id", ondelete="SET NULL")
    occurred_on: Mapped[date | None] = mapped_column(Date)
    organisation: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    data: Mapped[JsonDict | None] = json_column()
    verified_by: Mapped[int | None] = fk("users.id")
    verified_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class EvidenceVote(Base):
    """An endorsement (+1) or objection (-1) to a piece of evidence."""

    __tablename__ = "evidence_votes"
    __table_args__ = (CheckConstraint("value IN (-1, 1)", name="value_valid"),)

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[CreatedAt]


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE", index=True)
    user_id: Mapped[int] = fk("users.id", index=True)
    body: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = fk("comments.id", ondelete="CASCADE")
    edited_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class Mention(Base):
    """Somewhere a finding was talked about: a video, an article, a podcast, a paper."""

    __tablename__ = "mentions"
    __table_args__ = (
        UniqueConstraint("finding_id", "canonical_url"),
        enum_check("kind", MentionKind),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE")
    user_id: Mapped[int | None] = fk("users.id", ondelete="SET NULL")
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class Follow(Base):
    """A person following a finding. Followers are told when it changes."""

    __tablename__ = "follows"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    finding_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[CreatedAt]


class Media(Base):
    """An uploaded file. The bytes live in `Storage` under `storage_key`."""

    __tablename__ = "media"

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id", index=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text, index=True)
    # Nobody but the uploader sees a photo until a moderator or trusted member
    # approves it (Decision 0009). See `services.media`.
    approved_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    approved_by: Mapped[int | None] = fk("users.id", ondelete="SET NULL")


__all__ = ["Comment", "Evidence", "EvidenceVote", "Finding", "Follow", "Media", "Mention", "Observation"]
