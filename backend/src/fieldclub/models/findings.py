"""Findings and everything attached to one: observations, evidence, talk and mentions."""

from __future__ import annotations

from datetime import date, datetime

from geoalchemy2 import WKBElement
from sqlalchemy import (
    REAL,
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
    text,
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
    Role,
    Sensitivity,
    ShapeChangeKind,
    ShapeKind,
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
        enum_check("shape_kind", ShapeKind),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence_range"),
        # The help-wanted queue looks findings up by open step.
        Index("ix_findings_open_steps", "open_steps", postgresql_using="gin"),
        # Lists sort newest first by default.
        Index("ix_findings_created_at_id", "created_at", "id"),
        # One finding per person and client reference, so a draft sent twice is saved once.
        Index(
            "uq_findings_author_client_ref",
            "author_id",
            "client_ref",
            unique=True,
            postgresql_where=text("client_ref IS NOT NULL"),
        ),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    public_id: Mapped[str] = mapped_column(Text, unique=True)
    author_id: Mapped[int] = fk("users.id", index=True)
    title: Mapped[str] = mapped_column(Text)
    # The title with every position written in it replaced (`services.text_positions`),
    # which a search for someone who doesn't see the exact position matches. Written
    # on save, as `location_public` is.
    title_public: Mapped[str | None] = mapped_column(Text)
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
    # The full shape, derived from `path` (`services.shapes`): a LineString or a
    # one-ring Polygon. An outline saved before paths existed may be any line
    # or polygon, and has no path until it is next saved. Loaded only when
    # read: no list sends it, and a line may have 50,000 vertices.
    outline: Mapped[WKBElement | None] = mapped_column(any_geometry(), deferred=True)
    # The points the finder tapped and whether the shape is closed, as
    # `services.shapes.Path.to_json` writes them. The source of truth for `outline`.
    # It and the simplified copies are loaded only when read: a list of findings needs none of them.
    path: Mapped[JsonDict | None] = json_column(deferred=True)
    # `outline` simplified at 0.00005 degrees, for zooms 13 to 15 and the finding page.
    outline_mid: Mapped[WKBElement | None] = mapped_column(any_geometry(spatial_index=False), deferred=True)
    # `outline` simplified at 0.0005 degrees, for zooms 9 to 12.
    outline_low: Mapped[WKBElement | None] = mapped_column(any_geometry(), deferred=True)
    shape_kind: Mapped[str | None] = mapped_column(Text)
    # The geodesic length of a line, or the perimeter of an area, in metres.
    shape_length_m: Mapped[float | None] = mapped_column(REAL)
    # Raised by one on every change to the shape. An edit of the path names the
    # revision it started from, so one tab can't undo another's change unseen.
    shape_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The ground second looks were given on: the union of the finding's shape,
    # an area as its edge, or its point when it had none, at each second look.
    # It only grows. An edit must keep most of it close (`services.looked_at`).
    # Shape: never served but to someone who sees the finding exactly and may change it.
    looked_at: Mapped[WKBElement | None] = mapped_column(any_geometry(spatial_index=False), deferred=True)
    # How much of the shape lies further than `looked_at.LOOKED_AT_MAX_MOVE_M`
    # from `looked_at`: a line's length there, an area's edge there. Null
    # before any second look and when nothing lies beyond. With `added_view`,
    # a centre and zoom that frame that part, it is worked out when the shape
    # changes and when a second look is given (`looked_at.refresh_added`), so
    # no read buffers a long line. `added_view` is shape.
    added_since_looked_m: Mapped[float | None] = mapped_column(REAL)
    added_view: Mapped[JsonDict | None] = json_column()
    # True when the server chose `location` from the shape, because the finder drew it without one.
    location_derived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
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
    # The reference the finder's browser sent with the draft this was saved
    # from, if any. Never shown to anyone. See `services.findings.create_finding_once`.
    client_ref: Mapped[str | None] = mapped_column(Text)

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
    sensitivity.refresh_title_public(finding)


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
    # On every update, not only when the title changes, so a title written
    # before the position rules last changed catches up when the finding is next
    # saved, as every answer, vote and edit saves it.
    sensitivity.refresh_title_public(finding)


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
        enum_check("tier_at_answer", Tier),
        enum_check("state_at_answer", FindingState),
        enum_check("role_at_answer", Role),
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
    # When the person was shown the finding and the other answers. Null between
    # an answer given with "detail follows" and its detail or reveal: until then
    # they are someone who hasn't seen the answers (Decision 0008).
    revealed_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    # The finding's tier and state before an answer given in two steps first
    # counted, so its reveal can show the move the answer made.
    tier_at_answer: Mapped[str | None] = mapped_column(Text)
    state_at_answer: Mapped[str | None] = mapped_column(Text)
    # The answerer's role when they answered, which sets the answer's weight for
    # good. A later change of role or a ban moves no score through an answer,
    # so neither can show how a named person answered (Decision 0019).
    role_at_answer: Mapped[str] = mapped_column(Text)
    # The finding's `shape_revision` when the answer was given, so the page can
    # say what has been added to its shape since anyone looked.
    shape_revision: Mapped[int | None] = mapped_column(Integer)


class FindingShapeChange(Base):
    """One change to a finding's shape. Never served whole: no route sends `path_before`."""

    __tablename__ = "finding_shape_changes"
    __table_args__ = (
        UniqueConstraint("finding_id", "revision"),
        enum_check("kind", ShapeChangeKind),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE")
    user_id: Mapped[int] = fk("users.id", index=True)
    # The finding's `shape_revision` after this change.
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    points_before: Mapped[int] = mapped_column(Integer)
    points_after: Mapped[int] = mapped_column(Integer)
    length_before_m: Mapped[float | None] = mapped_column(REAL)
    length_after_m: Mapped[float | None] = mapped_column(REAL)
    # For an extension: the length it added, and a centre and zoom that frame
    # the added part (`services.shapes.added_view`).
    added_length_m: Mapped[float | None] = mapped_column(REAL)
    added_view: Mapped[JsonDict | None] = json_column()
    # The path as it was, for moderators and a later undo. Loaded only when read.
    path_before: Mapped[JsonDict | None] = json_column(deferred=True)


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
    # Set by a moderator. Hidden evidence stops counting and leaves every
    # page, list and export (`services.moderation`).
    hidden_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class EvidenceVote(Base):
    """An endorsement (+1) or objection (-1) to a piece of evidence."""

    __tablename__ = "evidence_votes"
    __table_args__ = (
        CheckConstraint("value IN (-1, 1)", name="value_valid"),
        enum_check("role_at_vote", Role),
    )

    evidence_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    value: Mapped[int] = mapped_column(SmallInteger)
    # The voter's role when they voted, which sets the vote's weight, as an
    # answer's role does (Decision 0019). An item gives its votes only as counts.
    role_at_vote: Mapped[str] = mapped_column(Text)
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
    # Set by a moderator. Everyone but moderators and the author sees a
    # hidden comment as removed (`services.moderation`).
    hidden_at: Mapped[datetime | None] = mapped_column(TimestampTz)


# The mentions that hold their address on a finding: every live one, and a
# hidden one even after its adder removed it, so that while a moderator keeps
# it hidden neither a member nor the channel scan can add that address again.
MENTION_HOLDS_ADDRESS = "deleted_at IS NULL OR hidden_at IS NOT NULL"


class Mention(Base):
    """Somewhere a finding was talked about: a video, an article, a podcast, a paper."""

    __tablename__ = "mentions"
    __table_args__ = (
        # One live mention per address on a finding. A hidden one keeps its
        # place here even once removed.
        Index(
            "uq_mentions_finding_id_match_key",
            "finding_id",
            "match_key",
            unique=True,
            postgresql_where=text(MENTION_HOLDS_ADDRESS),
        ),
        enum_check("kind", MentionKind),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    finding_id: Mapped[int] = fk("findings.id", ondelete="CASCADE", index=True)
    user_id: Mapped[int | None] = fk("users.id", ondelete="SET NULL")
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    # The canonical address less scheme, `www.` and trailing slash
    # (`unfurl.Address.match_key`). Left out, the canonical address itself.
    match_key: Mapped[str] = mapped_column(
        Text, default=lambda context: context.get_current_parameters()["canonical_url"]
    )
    provider: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Removed by the person who added it. The row stays as a record.
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    # Set by a moderator (`services.moderation`). A hidden mention is left out
    # of every list and feed for everyone but moderators and its adder, and
    # holds its address on the finding while it stays hidden.
    hidden_at: Mapped[datetime | None] = mapped_column(TimestampTz)


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
    __table_args__ = (
        CheckConstraint("approved_at IS NULL OR rejected_at IS NULL", name="approved_or_rejected"),
    )

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
    # Refused from the approval queue. The stored bytes are deleted, the row
    # stays so that an identical upload can be refused (`services.media`).
    rejected_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    rejected_by: Mapped[int | None] = fk("users.id", ondelete="SET NULL")
    # Set by a moderator on an approved photo. Only moderators and the uploader see it.
    hidden_at: Mapped[datetime | None] = mapped_column(TimestampTz)


__all__ = [
    "Comment",
    "Evidence",
    "EvidenceVote",
    "Finding",
    "FindingShapeChange",
    "Follow",
    "Media",
    "Mention",
    "Observation",
]
