"""The moderation log: who did what, to which target, when and why."""

from __future__ import annotations

from sqlalchemy import BigInteger, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from fieldclub.db import Base
from fieldclub.models.common import CreatedAt, IdPk, JsonDict, enum_check, fk, json_column
from fieldclub.vocab import ModerationActionKind, ReportTarget


class ModerationAction(Base):
    """One thing a moderator did, or a trusted member did to a photo. Rows are never changed.

    `target_id` is the target's own `id`, as in `reports`. `data` holds what
    the action changed, such as `{"from": "member", "to": "trusted"}`.
    """

    __tablename__ = "moderation_actions"
    __table_args__ = (
        enum_check("action", ModerationActionKind),
        enum_check("target_kind", ReportTarget),
        Index("ix_moderation_actions_target_kind_target_id", "target_kind", "target_id"),
        Index("ix_moderation_actions_created_at", text("created_at DESC")),
    )

    id: Mapped[IdPk]
    created_at: Mapped[CreatedAt]
    actor_id: Mapped[int] = fk("users.id", index=True)
    action: Mapped[str] = mapped_column(Text)
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text)
    data: Mapped[JsonDict | None] = json_column()


__all__ = ["ModerationAction"]
