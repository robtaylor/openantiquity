"""Second looks (Decision 0008): answers, the blind queue and the help-wanted list.

A second look is an observation: one per person per finding, never the
finder's own, and only from someone who can see the finding's exact position,
because nobody can check a feature from a 1 km square.

Blindness:

- A review card carries the place and the finder's view, and nothing else.
- The queue is ordered by how many answers would move a finding up, then by
  how long it has waited. Nothing about the finder's claim enters the order.
- A person sees other people's individual answers, and any tally of them,
  only once they have answered, or when they are the finder
  (`findings.answers_visible`). Error messages say nothing about answers.
- Help-wanted tasks that are answered by a second look are as blind as a
  card. Tasks for evidence show the finding, because finding an old map for
  it needs to know what it is.

Services flush and never commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Select, cast, exists, func, not_, select
from sqlalchemy.orm import Session

from fieldclub.errors import ForbiddenError, NotFoundError
from fieldclub.models import Finding, Observation, User
from fieldclub.models.common import SRID
from fieldclub.schemas.common import encode_cursor, paginate
from fieldclub.services import activity, findings, sensitivity
from fieldclub.services.confidence import NextStep
from fieldclub.services.findings import ANSWER_CODES, Reassessment
from fieldclub.vocab import (
    ActivityKind,
    Explanation,
    FeatureClass,
    FindingState,
    NextStepCode,
    Period,
    Visible,
)


class OwnFindingError(ForbiddenError):
    code = "own_finding"
    message = "You can't take a second look at your own finding."


class LocationHiddenError(ForbiddenError):
    code = "location_hidden"
    message = "You can only take a second look at a finding whose exact position you can see."


class AnswerFirstError(ForbiddenError):
    code = "answer_first"
    message = "Give your own answer first. Other people's answers are shown once you have."


class ObservationNotFoundError(NotFoundError):
    code = "observation_not_found"
    message = "You haven't answered this finding."


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    visible: Visible
    feature_class: FeatureClass | None = None
    period: Period | None = None
    explanation: Explanation | None = None
    not_modern: bool | None = None
    not_natural: bool | None = None
    not_artefact: bool | None = None
    note: str | None = None


@dataclass(frozen=True)
class Comparison:
    """How one person's answer compares with the finder's claim and everyone else's answers."""

    finder_class: FeatureClass
    community_class: FeatureClass | None
    matches_finder: bool | None
    others: dict[Visible, int]


@dataclass(frozen=True)
class AnswerResult:
    observation: Observation
    reassessment: Reassessment
    comparison: Comparison


def put_observation(db: Session, finding: Finding, user: User, answer: Answer) -> AnswerResult:
    """Give or change your second look, and reassess the finding under its lock."""
    findings.lock(db, finding)
    findings.check_open(finding)
    if user.has_id(finding.author_id):
        raise OwnFindingError()
    if not sensitivity.sees_exact(finding, user):
        raise LocationHiddenError()
    observation = findings.my_observation(db, finding, user)
    is_new = observation is None
    if observation is None:
        observation = Observation(finding_id=finding.id, user_id=user.id)
        db.add(observation)
    observation.visible = Visible(answer.visible).value
    observation.feature_class = answer.feature_class.value if answer.feature_class is not None else None
    observation.period = answer.period.value if answer.period is not None else None
    observation.explanation = answer.explanation.value if answer.explanation is not None else None
    observation.not_modern = answer.not_modern
    observation.not_natural = answer.not_natural
    observation.not_artefact = answer.not_artefact
    observation.note = answer.note
    db.flush()
    findings.follow(db, user, finding)
    if is_new:
        # No answer in the data: followers who haven't answered must not learn it.
        activity.record(db, ActivityKind.OBSERVATION_ADDED, user, finding)
    result = findings.reassess(db, finding, user)
    db.refresh(observation)
    return AnswerResult(observation, result, compare(db, finding, user, observation))


def compare(db: Session, finding: Finding, user: User, observation: Observation) -> Comparison:
    others = dict.fromkeys(Visible, 0)
    for visible, number in db.execute(
        select(Observation.visible, func.count())
        .where(
            Observation.finding_id == finding.id,
            Observation.user_id != user.id,
            Observation.user_id != finding.author_id,
        )
        .group_by(Observation.visible)
    ):
        others[Visible(visible)] = number
    named = observation.feature_class
    return Comparison(
        finder_class=FeatureClass(finding.feature_class),
        community_class=FeatureClass(finding.community_class) if finding.community_class else None,
        matches_finder=None if named is None else named == finding.feature_class,
        others=others,
    )


def delete_observation(db: Session, finding: Finding, user: User) -> Reassessment:
    """Take back your second look, and reassess the finding under its lock."""
    findings.lock(db, finding)
    observation = findings.my_observation(db, finding, user)
    if observation is None:
        raise ObservationNotFoundError()
    db.delete(observation)
    db.flush()
    return findings.reassess(db, finding, user)


@dataclass(frozen=True)
class ObservationPage:
    observations: list[Observation]
    people: dict[int, User]
    next_cursor: str | None


def list_observations(
    db: Session, finding: Finding, viewer: User | None, *, limit: int, cursor: str | None = None
) -> ObservationPage:
    """Everyone's answers, oldest first, or `AnswerFirstError` for someone who hasn't answered."""
    answered = findings.my_observation(db, finding, viewer) is not None
    if not findings.answers_visible(finding, viewer, answered):
        raise AnswerFirstError()
    query = select(Observation).where(Observation.finding_id == finding.id).order_by(Observation.id)
    if cursor is not None:
        query = query.where(Observation.id > findings.id_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda obs: [obs.id])
    return ObservationPage(items, findings.users_by_id(db, (obs.user_id for obs in items)), next_cursor)


# --------------------------------------------------------------------------
# The blind queue
# --------------------------------------------------------------------------

# Cards within this distance of the point given come first.
NEARBY_M = 25_000
# States that still take answers. A ruled-out or withdrawn finding offers no next step.
_REVIEWABLE_STATES = (FindingState.OPEN.value, FindingState.KNOWN.value, FindingState.DISPUTED.value)
_NO_ANSWER_COUNT = 32767


def _answerable(viewer: User | None) -> ColumnElement[bool]:
    """Findings this viewer could take a second look at: exactly visible, not theirs, not yet answered."""
    clause = findings.as_sql(findings.exact_clause(viewer)) & Finding.hidden_at.is_(None)
    clause &= Finding.state.in_(_REVIEWABLE_STATES)
    if viewer is not None and viewer.is_active:
        answered = exists().where(Observation.finding_id == Finding.id, Observation.user_id == viewer.id)
        clause &= (Finding.author_id != viewer.id) & not_(answered)
    return clause


def _queue_order(viewer: User | None, near: tuple[float, float] | None) -> list[ColumnElement[Any]]:
    priority = func.coalesce(Finding.answers_to_next, _NO_ANSWER_COUNT)
    if near is None:
        return [priority.asc(), Finding.created_at.asc(), Finding.id.asc()]
    # Every row is one the viewer sees exactly, but a signed-out visitor's
    # query still measures on the public position only.
    column = Finding.location if viewer is not None and viewer.is_active else Finding.location_public
    here = func.ST_SetSRID(func.ST_MakePoint(*near), SRID)
    distance = func.ST_Distance(cast(column, Geography), cast(here, Geography))
    return [(distance > NEARBY_M).asc(), priority.asc(), distance.asc(), Finding.id.asc()]


def _offset_page(
    db: Session, query: Select[Finding], *, limit: int, cursor: str | None
) -> tuple[list[Finding], str | None]:
    offset = 0 if cursor is None else findings.id_from_cursor(cursor)
    rows = db.scalars(query.offset(offset).limit(limit + 1)).all()
    items = list(rows[:limit])
    return items, encode_cursor([offset + limit]) if len(rows) > limit else None


def review_queue(
    db: Session,
    viewer: User | None,
    *,
    near: tuple[float, float] | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Finding], str | None]:
    """Findings waiting for a second look from this viewer, best first."""
    query = select(Finding).where(_answerable(viewer)).order_by(*_queue_order(viewer, near))
    return _offset_page(db, query, limit=limit, cursor=cursor)


# --------------------------------------------------------------------------
# Help wanted
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    finding: Finding
    code: NextStepCode
    # The engine's step, for tasks that aren't answered by a second look.
    step: NextStep | None


@dataclass(frozen=True)
class TaskGroup:
    code: NextStepCode
    total: int
    tasks: list[Task]
    next_cursor: str | None


def _task_query(code: NextStepCode, viewer: User | None) -> Select[Finding]:
    query = select(Finding).where(Finding.open_steps.contains([code.value]))
    if code in ANSWER_CODES:
        return query.where(_answerable(viewer)).order_by(*_queue_order(viewer, None))
    return query.where(Finding.hidden_at.is_(None)).order_by(Finding.updated_at.desc(), Finding.id.desc())


def _step(finding: Finding, code: NextStepCode) -> NextStep:
    assessment = findings.current_assessment(finding)
    return next(step for step in assessment.next_steps if step.code is code)


def tasks(
    db: Session,
    viewer: User | None,
    *,
    code: NextStepCode | None = None,
    limit: int,
    cursor: str | None = None,
) -> list[TaskGroup]:
    """Open next steps across findings, grouped by code. The cursor pages a single code."""
    assert code is not None or cursor is None, "a cursor pages one code's tasks"
    groups = []
    for each in [code] if code is not None else list(NextStepCode):
        query = _task_query(each, viewer)
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        assert total is not None
        rows, next_cursor = _offset_page(db, query, limit=limit, cursor=cursor)
        blind = each in ANSWER_CODES
        groups.append(
            TaskGroup(
                code=each,
                total=total,
                tasks=[Task(f, each, None if blind else _step(f, each)) for f in rows],
                next_cursor=next_cursor,
            )
        )
    return groups
