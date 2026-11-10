"""Work around findings: investigations, square surveys, activity, notifications, reports."""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

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
    polygon,
)
from fieldclub.vocab import (
    ActivityKind,
    InvestigationItemKind,
    InvestigationRole,
    ReportStatus,
    SurveyResult,
    Visibility,
)


class Investigation(Base):
    """A shared notebook tied to the map."""

    __tablename__ = "investigations"
    __table_args__ = (enum_check("visibility", Visibility),)

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    public_id: Mapped[str] = mapped_column(Text, unique=True)
    owner_id: Mapped[int] = fk("users.id", index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # Markdown.
    notes: Mapped[str | None] = mapped_column(Text)
    area: Mapped[WKBElement | None] = mapped_column(any_geometry())
    visibility: Mapped[str] = mapped_column(
        Text, default=Visibility.PRIVATE.value, server_default=Visibility.PRIVATE.value
    )
    updated_at: Mapped[datetime] = mapped_column(TimestampTz, server_default=func.now(), onupdate=func.now())


class InvestigationMember(Base):
    __tablename__ = "investigation_members"
    __table_args__ = (enum_check("role", InvestigationRole),)

    investigation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[CreatedAt]


class InvestigationItem(Base):
    """One entry in an investigation: a finding, a record, a saved view, a note and so on."""

    __tablename__ = "investigation_items"
    __table_args__ = (
        enum_check("kind", InvestigationItemKind),
        # Two items never share a place. Checked at commit, so a reorder can
        # renumber rows one at a time inside its transaction.
        UniqueConstraint("investigation_id", "position", deferrable=True, initially="DEFERRED"),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    investigation_id: Mapped[int] = fk("investigations.id", ondelete="CASCADE", index=True)
    kind: Mapped[str] = mapped_column(Text)
    finding_id: Mapped[int | None] = fk("findings.id", ondelete="CASCADE", index=True)
    record_id: Mapped[int | None] = fk("records.id", ondelete="SET NULL")
    title: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    data: Mapped[JsonDict | None] = json_column()
    position: Mapped[int] = mapped_column(Integer)
    added_by: Mapped[int] = fk("users.id")


class SquareSurvey(Base):
    """One person's scan of one 1 km grid square. Empty squares matter as much as busy ones."""

    __tablename__ = "square_surveys"
    __table_args__ = (
        UniqueConstraint("user_id", "square"),
        enum_check("result", SurveyResult),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id")
    # A compact 1 km grid reference such as SU1069.
    square: Mapped[str] = mapped_column(Text, index=True)
    geom: Mapped[WKBElement] = mapped_column(polygon())
    result: Mapped[str] = mapped_column(Text)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    seconds: Mapped[int | None] = mapped_column(Integer)


class Activity(Base):
    """Something that happened, for feeds and the event stream."""

    __tablename__ = "activity"
    __table_args__ = (
        enum_check("kind", ActivityKind),
        Index("ix_activity_created_at", text("created_at DESC")),
        # The feed filtered by kind, newest first, for kinds however rare.
        Index("ix_activity_kind_id", "kind", text("id DESC")),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    kind: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = fk("users.id", ondelete="SET NULL", index=True)
    finding_id: Mapped[int | None] = fk("findings.id", ondelete="CASCADE", index=True)
    investigation_id: Mapped[int | None] = fk("investigations.id", ondelete="CASCADE", index=True)
    data: Mapped[JsonDict | None] = json_column()
    # Roughly where it happened: the centre of the finding's 1 km grid square,
    # whatever its sensitivity. Never an exact position, because a finding can
    # be restricted after the event and this copy would not follow. Use it to
    # filter a feed by area. To show a position, go through
    # `services.sensitivity.visible_location`.
    location: Mapped[WKBElement | None] = mapped_column(point())


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
        # One person's notifications newest first, a page at a time.
        Index("ix_notifications_user_id_id", "user_id", text("id DESC")),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = fk("users.id", ondelete="SET NULL")
    finding_id: Mapped[int | None] = fk("findings.id", ondelete="CASCADE", index=True)
    data: Mapped[JsonDict | None] = json_column()
    read_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class Report(Base):
    """A report of a finding, comment or piece of evidence, for moderators."""

    __tablename__ = "reports"
    __table_args__ = (
        enum_check("status", ReportStatus),
        Index("ix_reports_status_created_at", "status", "created_at"),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    reporter_id: Mapped[int] = fk("users.id")
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, default=ReportStatus.OPEN.value, server_default=ReportStatus.OPEN.value
    )
    resolved_by: Mapped[int | None] = fk("users.id")
    resolved_at: Mapped[datetime | None] = mapped_column(TimestampTz)


class WatchChannel(Base):
    """A channel scanned for links back to findings."""

    __tablename__ = "watch_channels"
    __table_args__ = (UniqueConstraint("provider", "channel_id"),)

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    provider: Mapped[str] = mapped_column(Text)
    channel_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


__all__ = [
    "Activity",
    "Investigation",
    "InvestigationItem",
    "InvestigationMember",
    "Notification",
    "Report",
    "SquareSurvey",
    "WatchChannel",
]
