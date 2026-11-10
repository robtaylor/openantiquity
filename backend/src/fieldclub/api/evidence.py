"""Evidence on a finding, votes on evidence, and verification of official evidence."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from fieldclub.api.deps import Contributor, Db, private, rate_limit
from fieldclub.api.findings import detail
from fieldclub.schemas.findings import EvidenceIn, FindingDetail, VoteIn, VoteOut
from fieldclub.services import findings

router = APIRouter(tags=["evidence"])


@router.post(
    "/findings/{public_id}/evidence",
    response_model=FindingDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("evidence", 120, per_seconds=3600))],
)
def add_evidence(
    public_id: str, body: EvidenceIn, user: Contributor, db: Db, response: Response
) -> FindingDetail:
    """Add evidence. Which fields each kind needs is in the `invalid_evidence` message when one is missing."""
    fields = body.model_dump(exclude={"url", "view"})
    finding = findings.lock_finding(db, public_id, user)
    findings.add_evidence(
        db,
        finding,
        user,
        findings.EvidenceFields(
            **fields,
            url=str(body.url) if body.url is not None else None,
            view=body.view.to_stored() if body.view is not None else None,
        ),
    )
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.delete(
    "/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("evidence", 120, per_seconds=3600))],
)
def delete_evidence(evidence_id: int, user: Contributor, db: Db) -> None:
    """Remove evidence you added. A moderator can remove anyone's."""
    findings.delete_evidence(db, evidence_id, user)
    db.commit()


@router.put(
    "/evidence/{evidence_id}/vote",
    response_model=VoteOut,
    dependencies=[Depends(rate_limit("evidence_votes", 600, per_seconds=3600))],
)
def vote(evidence_id: int, body: VoteIn, user: Contributor, db: Db, response: Response) -> VoteOut:
    """Endorse (+1) or object to (-1) evidence, or take your vote back (0)."""
    private(response)
    findings.vote(db, evidence_id, user, body.value)
    db.commit()
    return VoteOut(evidence_id=evidence_id, value=body.value)


@router.post(
    "/evidence/{evidence_id}/verify",
    response_model=FindingDetail,
    dependencies=[Depends(rate_limit("evidence_verify", 120, per_seconds=3600))],
)
def verify(evidence_id: int, user: Contributor, db: Db, response: Response) -> FindingDetail:
    """An archaeologist or moderator confirms an HER entry, designation or publication."""
    moved = findings.verify(db, evidence_id, user)
    db.commit()
    private(response)
    return detail(db, moved.finding, user)
