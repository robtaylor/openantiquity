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
- An answer is final. Giving it reveals the finding and everyone's answers,
  so an answer changed afterwards would no longer be independent. Once
  given, only its note can change. Taking it back marks it withdrawn and it
  stops counting, but the row stays, so a new answer can't replace it. The
  same answer given again restores it.
- Activity doesn't say who answered. `observation_added`, and any tier or
  state change an answer causes, are recorded with no actor, so a follower
  can't read someone's answer from the event that follows it.
- On a finding's page, a viewer who hasn't answered sees the next steps
  without the numbers that would let them work out the tallies
  (`blind_step`).

Known limits, accepted:

- A card carries the finding's public id, which the answer is sent to.
  Someone who opens `/findings/{id}` first sees the claim there, as Decision
  0008 allows for a page opened directly.
- The queue's order reflects how many answers a finding needs, which follows
  from other people's answers.
- The queue and the help-wanted lists page by offset, because their order
  changes as people answer. A card can shift between pages or appear twice.

Services flush and never commit.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Select, cast, exists, func, not_, select
from sqlalchemy.orm import Session

from fieldclub.errors import ConflictError, ForbiddenError, NotFoundError
from fieldclub.models import Finding, Observation, User
from fieldclub.models.common import SRID
from fieldclub.schemas.common import int_from_cursor, offset_from_cursor, offset_page, paginate
from fieldclub.services import activity, findings, sensitivity
from fieldclub.services.confidence import CHECK_PHRASES, NextStep, load_next_steps
from fieldclub.services.findings import ANSWER_CODES, Reassessment
from fieldclub.vocab import (
    CHECK_EXPLANATIONS,
    ActivityKind,
    Check,
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


class AnswerFirstError(ForbiddenError):
    code = "answer_first"
    message = "Give your own answer first. Other people's answers are shown once you have."


class AnswerFinalError(ConflictError):
    code = "answer_final"
    message = (
        "You've already answered, and seen the other answers, so your answer can't change. "
        "You can still change its note."
    )


class ObservationNotFoundError(NotFoundError):
    code = "observation_not_found"
    message = "You haven't answered this finding."


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------


# Everything in an answer but its note: the part that can't change once given.
_FINAL_COLUMNS = (
    "visible",
    "feature_class",
    "period",
    "explanation",
    "not_modern",
    "not_natural",
    "not_artefact",
)


def contradicted_check(answer: Any) -> Check | None:
    """A check asserted alongside its matching explanation, such as `not_modern` with `modern`."""
    return next(
        (
            check
            for check, explanation in CHECK_EXPLANATIONS.items()
            if getattr(answer, check.value) and answer.explanation is explanation
        ),
        None,
    )


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

    def __post_init__(self) -> None:
        assert contradicted_check(self) is None, "an answer can't assert a check and its explanation"

    def columns(self) -> dict[str, Any]:
        """The answer as `Observation` columns, without the note."""
        return {name: _column(getattr(self, name)) for name in _FINAL_COLUMNS}


def _column(value: StrEnum | bool | None) -> str | bool | None:
    return value.value if isinstance(value, StrEnum) else value


def _stored(observation: Observation) -> dict[str, Any]:
    return {name: getattr(observation, name) for name in _FINAL_COLUMNS}


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
    """Give your second look, or change its note, and reassess the finding under its lock.

    The answer itself is final once given (see the module docstring):
    anything but the note that differs from the stored answer is refused
    with `AnswerFinalError`, and so is the same answer given again after
    it was taken back, unless it matches.
    """
    findings.lock(db, finding)
    findings.check_open(finding)
    if user.has_id(finding.author_id):
        raise OwnFindingError()
    findings.require_exact(finding, user)
    observation = findings.my_observation(db, finding, user)
    is_new = observation is None
    if observation is None:
        observation = Observation(finding_id=finding.id, user_id=user.id, **answer.columns())
        db.add(observation)
    elif _stored(observation) != answer.columns():
        raise AnswerFinalError()
    observation.note = answer.note
    observation.withdrawn_at = None
    db.flush()
    if is_new:
        # No actor and no data: followers learn that someone answered, not who
        # or how. The answerer is left out of the notifications instead.
        activity.record(db, ActivityKind.OBSERVATION_ADDED, None, finding, quiet_for=user)
    findings.follow(db, user, finding)
    result = findings.reassess(db, finding, None, quiet_for=user)
    db.refresh(observation)
    return AnswerResult(observation, result, compare(result, user, observation))


def compare(result: Reassessment, user: User, observation: Observation) -> Comparison:
    """Compare an answer with the assessment it just went into.

    The assessment's answers are the standing ones other than the finder's,
    so leaving out this person's own leaves everyone else's.
    """
    finding = result.finding
    others = dict.fromkeys(Visible, 0)
    others.update(Counter(obs.visible for obs in result.assessment.observations if obs.user_id != user.id))
    named = observation.feature_class
    return Comparison(
        finder_class=FeatureClass(finding.feature_class),
        community_class=FeatureClass(finding.community_class) if finding.community_class else None,
        matches_finder=None if named is None else named == finding.feature_class,
        others=others,
    )


def delete_observation(db: Session, finding: Finding, user: User) -> Reassessment:
    """Take back your second look, and reassess the finding under its lock.

    The answer is marked withdrawn, not deleted, so it can't be replaced.
    """
    findings.lock(db, finding)
    observation = findings.my_observation(db, finding, user)
    if observation is None or observation.withdrawn_at is not None:
        raise ObservationNotFoundError()
    observation.withdrawn_at = datetime.now(UTC)
    db.flush()
    return findings.reassess(db, finding, None, quiet_for=user)


@dataclass(frozen=True)
class ObservationPage:
    observations: list[Observation]
    people: dict[int, User]
    next_cursor: str | None


def list_observations(
    db: Session, finding: Finding, viewer: User | None, *, limit: int, cursor: str | None = None
) -> ObservationPage:
    """Everyone's standing answers, oldest first, or `AnswerFirstError` for someone who hasn't answered.

    Someone who answered and took it back has seen the answers already, so
    they still may.
    """
    answered = findings.my_observation(db, finding, viewer) is not None
    if not findings.answers_visible(finding, viewer, answered):
        raise AnswerFirstError()
    query = (
        select(Observation)
        .where(Observation.finding_id == finding.id, Observation.withdrawn_at.is_(None))
        .order_by(Observation.id)
    )
    if cursor is not None:
        query = query.where(Observation.id > int_from_cursor(cursor))
    rows = db.scalars(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda obs: [obs.id])
    return ObservationPage(items, findings.users_by_id(db, (obs.user_id for obs in items)), next_cursor)


_BLIND_PROMPTS: dict[NextStepCode, str] = {
    NextStepCode.NEED_OBSERVERS: "More people need to say whether they can see it.",
    NextStepCode.NEED_CLASS_AGREEMENT: "More people need to say what they think it is.",
    NextStepCode.NEED_TRUSTED_REVIEW: (
        "A trusted member or an archaeologist needs to say whether they can see it, or more people do."
    ),
}
assert set(_BLIND_PROMPTS) | {NextStepCode.NEED_CHECK} == ANSWER_CODES


def blind_step(step: NextStep) -> NextStep:
    """A step as shown to someone who may not see the answers: what's wanted, but no numbers.

    How many more people a step needs, and the weight a trusted review would
    stand in for, are worked out from the tallies, so they're left out of
    every step a second look meets. Other steps are returned unchanged.
    """
    if step.code not in ANSWER_CODES:
        return step
    if step.code is NextStepCode.NEED_CHECK:
        assert step.check is not None, "a check step names its check"
        prompt = f"More people need to say it {CHECK_PHRASES[step.check]}."
    else:
        prompt = _BLIND_PROMPTS[step.code]
    return replace(step, prompt=prompt, people=None, weight_needed=None)


# --------------------------------------------------------------------------
# The blind queue
# --------------------------------------------------------------------------

# Cards within this distance of the point given come first.
NEARBY_M = 25_000
# States that still take answers. A ruled-out or withdrawn finding offers no next step.
_REVIEWABLE_STATES = (FindingState.OPEN.value, FindingState.KNOWN.value, FindingState.DISPUTED.value)


def _answerable(viewer: User | None) -> ColumnElement[bool]:
    """Findings this viewer could take a second look at: exactly visible, not theirs, not yet answered."""
    clause = sensitivity.as_sql(sensitivity.sees_exact_clause(viewer)) & Finding.hidden_at.is_(None)
    clause &= Finding.state.in_(_REVIEWABLE_STATES)
    active = sensitivity.active_viewer(viewer)
    if active is not None:
        answered = exists().where(Observation.finding_id == Finding.id, Observation.user_id == active.id)
        clause &= (Finding.author_id != active.id) & not_(answered)
    return clause


def _queue_order(viewer: User | None, near: tuple[float, float] | None) -> list[ColumnElement[Any]]:
    priority = func.coalesce(Finding.answers_to_next, findings.ANSWERS_TO_NEXT_MAX)
    if near is None:
        return [priority.asc(), Finding.created_at.asc(), Finding.id.asc()]
    # Every row is one the viewer sees exactly, but a signed-out visitor's
    # query still measures on the public position only.
    column = Finding.location if sensitivity.active_viewer(viewer) is not None else Finding.location_public
    here = func.ST_SetSRID(func.ST_MakePoint(*near), SRID)
    distance = func.ST_Distance(cast(column, Geography), cast(here, Geography))
    return [(distance > NEARBY_M).asc(), priority.asc(), distance.asc(), Finding.id.asc()]


def _offset_page(
    db: Session, query: Select[Finding], *, limit: int, cursor: str | None
) -> tuple[list[Finding], str | None]:
    offset = offset_from_cursor(cursor)
    return offset_page(db.scalars(query.offset(offset).limit(limit + 1)).all(), offset, limit)


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


def _step(steps: tuple[NextStep, ...], code: NextStepCode) -> NextStep:
    return next(step for step in steps if step.code is code)


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
    # Each finding's stored next steps, decoded once even when it has a task in several groups.
    steps: dict[int, tuple[NextStep, ...]] = {}

    def task(finding: Finding, each: NextStepCode) -> Task:
        if each in ANSWER_CODES:
            return Task(finding, each, None)
        if finding.id not in steps:
            steps[finding.id] = load_next_steps(finding.assessment)
        return Task(finding, each, _step(steps[finding.id], each))

    for each in [code] if code is not None else list(NextStepCode):
        query = _task_query(each, viewer)
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        assert total is not None
        rows, next_cursor = _offset_page(db, query, limit=limit, cursor=cursor)
        groups.append(
            TaskGroup(
                code=each,
                total=total,
                tasks=[task(f, each) for f in rows],
                next_cursor=next_cursor,
            )
        )
    return groups
