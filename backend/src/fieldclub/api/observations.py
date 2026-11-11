"""Second looks on a finding: give, reveal, take back and list answers (Decision 0008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, PageQuery, private, rate_limit
from fieldclub.api.findings import detail
from fieldclub.models import Finding, User
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import (
    AnswerCounts,
    AnswerHeld,
    ComparisonOut,
    ObservationDetailIn,
    ObservationIn,
    ObservationOut,
    Reveal,
)
from fieldclub.services import findings, review
from fieldclub.vocab import Visible

router = APIRouter(tags=["observations"])

ANSWER_LIMIT = Depends(rate_limit("observations", 600, per_seconds=3600))


def _reply(db: Db, finding: Finding, user: User, result: review.AnswerResult) -> Reveal | AnswerHeld:
    observation = ObservationOut.build(result.observation, user, finding=finding, viewer=user)
    comparison = result.comparison
    if comparison is None:
        assert not result.revealed, "a revealed answer is compared"
        return AnswerHeld(observation=observation)
    moved = result.reassessment
    return Reveal(
        observation=observation,
        finding=detail(db, finding, user),
        comparison=ComparisonOut(
            finder_class=comparison.finder_class,
            community_class=comparison.community_class,
            matches_finder=comparison.matches_finder,
            others=AnswerCounts(
                yes=comparison.others[Visible.YES],
                unsure=comparison.others[Visible.UNSURE],
                no=comparison.others[Visible.NO],
            ),
        ),
        tier_before=moved.tier_before,
        tier_after=moved.tier_after,
        state_before=moved.state_before,
        state_after=moved.state_after,
        moved_up=moved.moved_up,
    )


@router.put(
    "/findings/{public_id}/observation", response_model=Reveal | AnswerHeld, dependencies=[ANSWER_LIMIT]
)
def put_observation(
    public_id: str, body: ObservationIn, user: Contributor, db: Db, response: Response
) -> Reveal | AnswerHeld:
    """Give or change your second look. The reply reveals the finding in full and how your answer compares.

    With `detail_follows`, the answer is stored and counts, and the reply
    (`revealed: false`) shows nothing. Add the detail, or skip it, with
    `POST /findings/{public_id}/observation/reveal`.
    """
    finding = findings.get_finding(db, public_id, user)
    result = review.put_observation(db, finding, user, review.Answer(**body.model_dump()))
    db.commit()
    private(response)
    return _reply(db, finding, user, result)


@router.post("/findings/{public_id}/observation/reveal", response_model=Reveal, dependencies=[ANSWER_LIMIT])
def reveal(
    public_id: str,
    user: Contributor,
    db: Db,
    response: Response,
    body: Annotated[ObservationDetailIn | None, Body()] = None,
) -> Reveal:
    """Add the detail to an answer given with `detail_follows`, or send none to skip it, and see the finding.

    The detail is added once. Asked again, it answers the same reveal while the
    detail sent matches the stored one, and `answer_final` otherwise.
    """
    finding = findings.get_finding(db, public_id, user)
    given = review.Detail(**(body or ObservationDetailIn()).model_dump())
    result = review.reveal(db, finding, user, given)
    db.commit()
    private(response)
    reply = _reply(db, finding, user, result)
    assert isinstance(reply, Reveal), "the reveal route always reveals"
    return reply


@router.delete(
    "/findings/{public_id}/observation", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ANSWER_LIMIT]
)
def delete_observation(public_id: str, user: Contributor, db: Db) -> None:
    """Take back your second look."""
    review.delete_observation(db, findings.get_finding(db, public_id, user), user)
    db.commit()


@router.get("/findings/{public_id}/observations", response_model=Page[ObservationOut])
def list_observations(
    public_id: str, page: PageQuery, db: Db, viewer: OptionalUser, response: Response
) -> Page[ObservationOut]:
    """Everyone's answers, for the finder and those whose own answer was revealed. Others: `answer_first`."""
    finding = findings.get_finding(db, public_id, viewer)
    found = review.list_observations(db, finding, viewer, limit=page.limit, cursor=page.cursor)
    private(response)
    return Page[ObservationOut](
        items=[
            ObservationOut.build(obs, found.people[obs.user_id], finding=finding, viewer=viewer)
            for obs in found.observations
        ],
        next_cursor=found.next_cursor,
    )
