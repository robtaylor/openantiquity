"""Suggestions to a marking's shape, and its keeping: offering it to someone and taking it on.

Every route finds the finding through `findings.get_finding`, so it answers
`finding_not_found` to anyone who may not see a hidden finding before any
other refusal, and never a code that says the finding is hidden. Each answer
is the finding's page as the caller may see it, so it is sent private.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from fieldclub.api.deps import Contributor, Db, private, rate_limit
from fieldclub.api.findings import detail
from fieldclub.models import ShapeSuggestion, User
from fieldclub.schemas.findings import (
    FindingDetail,
    KeepingOfferIn,
    SuggestionAccept,
    SuggestionIn,
    SuggestionOut,
)
from fieldclub.services import findings, keeping, sensitivity, shapes, suggestions

router = APIRouter(tags=["findings"])

_edits = [Depends(rate_limit("findings_edit", 120, per_seconds=3600))]
SuggestionId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def _suggestion_out(db: Db, public_id: str, suggestion: ShapeSuggestion, viewer: User) -> SuggestionOut:
    """The suggestion as the writer may see it, through `sensitivity.visible_suggestion`."""
    finding = findings.get_finding(db, public_id, viewer)
    by = db.get(User, suggestion.user_id)
    assert by is not None, "a suggestion has a suggester"
    shown = sensitivity.visible_suggestion(finding, viewer, suggestion, by)
    # Everyone who may write sees every finding exactly (Decision 0032).
    assert shown is not None, "a writer is a signed-in member who sees the finding exactly"
    return SuggestionOut.build(shown)


@router.post(
    "/findings/{public_id}/suggestions",
    response_model=SuggestionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("suggestions", 30, per_seconds=3600))],
)
def suggest_change(
    public_id: str, body: SuggestionIn, user: Contributor, db: Db, response: Response
) -> SuggestionOut:
    """Suggest a change to someone else's marking: the whole path, on the shape's revision now.

    Held to what an edit is held to, so one that couldn't be accepted is
    refused now. A pending suggestion of yours on the same finding is
    withdrawn. Its keeper is told.
    """
    finding = findings.lock_finding(db, public_id, user)
    made = suggestions.suggest(
        db, finding, user, path=shapes.read_path(body.path.model_dump()), revision=body.path_revision
    )
    db.commit()
    private(response)
    return _suggestion_out(db, public_id, made, user)


@router.delete(
    "/findings/{public_id}/suggestions/{suggestion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_edits,
)
def withdraw_suggestion(public_id: str, suggestion_id: SuggestionId, user: Contributor, db: Db) -> Response:
    """Take back a suggestion of yours that is still waiting."""
    finding = findings.lock_finding(db, public_id, user)
    suggestions.withdraw(db, finding, user, suggestion_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/findings/{public_id}/suggestions/{suggestion_id}/accept",
    response_model=FindingDetail,
    dependencies=_edits,
)
def accept_suggestion(
    public_id: str,
    suggestion_id: SuggestionId,
    body: SuggestionAccept,
    user: Contributor,
    db: Db,
    response: Response,
) -> FindingDetail:
    """The keeper accepts a suggestion, which changes the shape, credited to its suggester.

    `shape_revision` is the revision the keeper saw it against. A suggestion
    made on an older shape replaces the changes since.
    """
    finding = findings.lock_finding(db, public_id, user)
    suggestions.accept(db, finding, user, suggestion_id, shape_revision=body.shape_revision)
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.post(
    "/findings/{public_id}/suggestions/{suggestion_id}/decline",
    response_model=SuggestionOut,
    dependencies=_edits,
)
def decline_suggestion(
    public_id: str, suggestion_id: SuggestionId, user: Contributor, db: Db, response: Response
) -> SuggestionOut:
    """The keeper declines a suggestion. Talk about why goes in the finding's comments."""
    finding = findings.lock_finding(db, public_id, user)
    declined = suggestions.decline(db, finding, user, suggestion_id)
    db.commit()
    private(response)
    return _suggestion_out(db, public_id, declined, user)


@router.put("/findings/{public_id}/keeping/offer", response_model=FindingDetail, dependencies=_edits)
def offer_keeping(
    public_id: str, body: KeepingOfferIn, user: Contributor, db: Db, response: Response
) -> FindingDetail:
    """Offer the keeping of a marking to another member, replacing any offer standing.

    Its keeper may, and an admin may for a marking whose keeper's account is
    deleted or banned. An unknown, deleted or banned handle is
    `user_not_found` alike. The person offered is told once.
    """
    finding = findings.lock_finding(db, public_id, user)
    keeping.offer(db, finding, user, body.handle)
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.delete(
    "/findings/{public_id}/keeping/offer", status_code=status.HTTP_204_NO_CONTENT, dependencies=_edits
)
def withdraw_keeping_offer(public_id: str, user: Contributor, db: Db) -> Response:
    """Take back the standing offer: its keeper, or the person offered, who declines it."""
    finding = findings.lock_finding(db, public_id, user)
    keeping.withdraw_offer(db, finding, user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/findings/{public_id}/keeping/accept", response_model=FindingDetail, dependencies=_edits)
def take_keeping(public_id: str, user: Contributor, db: Db, response: Response) -> FindingDetail:
    """Take on the keeping offered to you. Its followers are told, and you follow it."""
    finding = findings.lock_finding(db, public_id, user)
    keeping.take(db, finding, user)
    db.commit()
    private(response)
    return detail(db, finding, user)
