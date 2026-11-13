"""Second looks and help wanted: the blind queue and open next steps (Decision 0008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy.orm import Session

from fieldclub.api.deps import CursorQuery, Db, OptionalUser, PageQuery, private
from fieldclub.errors import BadRequestError
from fieldclub.models import Finding, User
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import (
    NextStepOut,
    ReviewCard,
    ReviewPlace,
    StrandCount,
    TaskFinding,
    TaskGroupOut,
    TaskGroups,
    TaskItem,
    review_view,
)
from fieldclub.services import review, sensitivity
from fieldclub.vocab import FindingState, NextStepCode, Strand, Tier, stored_class

router = APIRouter(prefix="/review", tags=["review"])

CARD_DEFAULT_LIMIT = 10
CARD_MAX_LIMIT = 50


def _near(lon: float | None, lat: float | None) -> tuple[float, float] | None:
    if lon is None and lat is None:
        return None
    if lon is None or lat is None:
        raise BadRequestError("Give both lon and lat, or neither.", code="invalid_point")
    return lon, lat


@router.get("/next", response_model=Page[ReviewCard])
def next_cards(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    limit: Annotated[int, Query(ge=1, le=CARD_MAX_LIMIT)] = CARD_DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[ReviewCard]:
    """Findings waiting for a second look, one answer from moving up first.

    Each card has the place and the finder's view only: no title, class,
    description, tier or anyone's answers. Give `lon` and `lat` to prefer
    nearby findings.
    """
    chosen, next_cursor = review.review_queue(db, viewer, near=_near(lon, lat), limit=limit, cursor=cursor)
    private(response)
    return Page[ReviewCard](items=[_card(db, finding, viewer) for finding in chosen], next_cursor=next_cursor)


def _card(db: Session, finding: Finding, viewer: User | None) -> ReviewCard:
    where, view = review_view(finding, viewer, review.new_part_view(db, finding, viewer))
    assert not where.obscured, "the queue offers only findings the viewer sees exactly"
    return ReviewCard(
        public_id=finding.public_id,
        place=ReviewPlace(lon=where.lon, lat=where.lat, grid_ref=where.grid_ref),
        view_state=view,
        shape_revision=finding.shape_revision,
    )


@router.get("/tasks", response_model=TaskGroups)
def tasks(
    db: Db,
    viewer: OptionalUser,
    page: PageQuery,
    response: Response,
    code: NextStepCode | None = None,
    strand: Strand | None = None,
) -> TaskGroups:
    """Open next steps across findings, grouped by code, so people can pick the help they like.

    Without `code`, every group with its first `limit` tasks. With `code`, that
    group alone, paged by `cursor`. Steps met by a second look are blind. The
    evidence step, `need_strand`, also counts its findings by each kind of desk
    evidence they lack (`strands`), and `code=need_strand&strand=` lists only
    those lacking that kind.
    """
    if page.cursor is not None and code is None:
        raise BadRequestError("A cursor pages one code's tasks. Give the code too.", code="code_required")
    groups = review.tasks(db, viewer, code=code, strand=strand, limit=page.limit, cursor=page.cursor)
    private(response)
    return TaskGroups(
        groups=[
            TaskGroupOut(
                code=group.code,
                total=group.total,
                items=[_task(db, task, viewer) for task in group.tasks],
                next_cursor=group.next_cursor,
                strands=[StrandCount(strand=kind, total=total) for kind, total in group.strands],
            )
            for group in groups
        ]
    )


def _task(db: Session, task: review.Task, viewer: User | None) -> TaskItem:
    finding = task.finding
    new_part = (
        review.new_part_view(db, finding, viewer) if task.code is NextStepCode.LOOK_AT_NEW_PART else None
    )
    place, view = review_view(finding, viewer, new_part)
    return TaskItem(
        public_id=finding.public_id,
        code=task.code,
        place=place,
        view_state=view,
        step=NextStepOut.from_step(task.step) if task.step is not None else None,
        finding=(
            TaskFinding(
                title=sensitivity.visible_text(finding, viewer, finding.title) or "",
                feature_class=stored_class(finding.feature_class),
                tier=Tier(finding.tier),
                state=FindingState(finding.state),
            )
            if task.step is not None
            else None
        ),
        shape_revision=None if place.obscured else finding.shape_revision,
    )
