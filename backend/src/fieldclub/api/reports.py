"""Reporting something to the moderators. The queue itself is in `api.moderation`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from fieldclub.api.deps import Contributor, Db, rate_limit
from fieldclub.schemas.moderation import ReportCreated, ReportIn
from fieldclub.services import moderation
from fieldclub.vocab import ReportReason, ReportTarget

router = APIRouter(tags=["reports"])


@router.post(
    "/reports",
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("reports", 30, per_seconds=3600))],
)
def create_report(body: ReportIn, user: Contributor, db: Db) -> ReportCreated:
    """Report a finding, comment, piece of evidence, mention, photo or person to the moderators.

    One open report per person and target: a second answers `already_reported`.
    """
    report = moderation.create_report(db, user, body.target_kind, body.target_id, body.reason, body.note)
    db.commit()
    return ReportCreated(
        id=report.id,
        target_kind=ReportTarget(report.target_kind),
        target_id=body.target_id,
        reason=ReportReason(report.reason),
        created_at=report.created_at,
    )
