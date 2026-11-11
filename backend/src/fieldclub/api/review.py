"""Second looks and help wanted: the blind queue and open next steps (Decision 0008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from fieldclub.api.deps import CursorQuery, Db, OptionalUser, PageQuery, private
from fieldclub.errors import BadRequestError
from fieldclub.models import Finding, User
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import (
    Location,
    NextStepOut,
    ReviewCard,
    ReviewPlace,
    TaskFinding,
    TaskGroupOut,
    TaskGroups,
    TaskItem,
    ViewState,
    location_out,
)
from fieldclub.services import review, sensitivity
from fieldclub.vocab import FeatureClass, FindingState, NextStepCode, Tier

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
    return Page[ReviewCard](items=[_card(finding, viewer) for finding in chosen], next_cursor=next_cursor)


def _card(finding: Finding, viewer: User | None) -> ReviewCard:
    where = location_out(finding, viewer)
    assert not where.obscured, "the queue offers only findings the viewer sees exactly"
    return ReviewCard(
        public_id=finding.public_id,
        place=ReviewPlace(lon=where.lon, lat=where.lat, grid_ref=where.grid_ref),
        view_state=ViewState.from_stored(finding.view_state),
    )


@router.get("/tasks", response_model=TaskGroups)
def tasks(
    db: Db,
    viewer: OptionalUser,
    page: PageQuery,
    response: Response,
    code: NextStepCode | None = None,
) -> TaskGroups:
    """Open next steps across findings, grouped by code, so people can pick the help they like.

    Without `code`, every group with its first `limit` tasks. With `code`, that
    group alone, paged by `cursor`. Steps met by a second look are blind.
    """
    if page.cursor is not None and code is None:
        raise BadRequestError("A cursor pages one code's tasks. Give the code too.", code="code_required")
    groups = review.tasks(db, viewer, code=code, limit=page.limit, cursor=page.cursor)
    private(response)
    return TaskGroups(
        groups=[
            TaskGroupOut(
                code=group.code,
                total=group.total,
                items=[_task(task, viewer) for task in group.tasks],
                next_cursor=group.next_cursor,
            )
            for group in groups
        ]
    )


def _task(task: review.Task, viewer: User | None) -> TaskItem:
    finding = task.finding
    place: Location = location_out(finding, viewer)
    return TaskItem(
        public_id=finding.public_id,
        code=task.code,
        place=place,
        view_state=ViewState.from_stored(finding.view_state),
        step=NextStepOut.from_step(task.step) if task.step is not None else None,
        finding=(
            TaskFinding(
                title=sensitivity.visible_text(finding, viewer, finding.title) or "",
                feature_class=FeatureClass(finding.feature_class),
                tier=Tier(finding.tier),
                state=FindingState(finding.state),
            )
            if task.step is not None
            else None
        ),
    )
