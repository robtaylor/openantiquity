"""Second looks on a finding: give, take back and list answers (Decision 0008)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, PageQuery, rate_limit
from fieldclub.api.findings import detail, private
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import AnswerCounts, Comparison, ObservationIn, ObservationOut, Reveal
from fieldclub.services import findings, review
from fieldclub.vocab import Visible

router = APIRouter(tags=["observations"])


@router.put(
    "/findings/{public_id}/observation",
    response_model=Reveal,
    dependencies=[Depends(rate_limit("observations", 600, per_seconds=3600))],
)
def put_observation(
    public_id: str, body: ObservationIn, user: Contributor, db: Db, response: Response
) -> Reveal:
    """Give or change your second look. The reply reveals the finding in full and how your answer compares."""
    finding = findings.get_finding(db, public_id, user)
    result = review.put_observation(db, finding, user, review.Answer(**body.model_dump()))
    db.commit()
    private(response)
    comparison = result.comparison
    moved = result.reassessment
    return Reveal(
        observation=ObservationOut.build(result.observation, user),
        finding=detail(db, finding, user),
        comparison=Comparison(
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


@router.delete(
    "/findings/{public_id}/observation",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("observations", 600, per_seconds=3600))],
)
def delete_observation(public_id: str, user: Contributor, db: Db) -> None:
    """Take back your second look."""
    review.delete_observation(db, findings.get_finding(db, public_id, user), user)
    db.commit()


@router.get("/findings/{public_id}/observations", response_model=Page[ObservationOut])
def list_observations(
    public_id: str, page: PageQuery, db: Db, viewer: OptionalUser, response: Response
) -> Page[ObservationOut]:
    """Everyone's answers, for the finder and for people who have answered. Others get `answer_first`."""
    finding = findings.get_finding(db, public_id, viewer)
    found = review.list_observations(db, finding, viewer, limit=page.limit, cursor=page.cursor)
    private(response)
    return Page[ObservationOut](
        items=[ObservationOut.build(obs, found.people[obs.user_id]) for obs in found.observations],
        next_cursor=found.next_cursor,
    )
