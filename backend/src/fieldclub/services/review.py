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
- An answer can come in two steps, so the optional detail is asked for after
  the answer, never before it (docs/UI.md). The answer is sent saying that
  detail follows: it is stored and counts at once, and the reply reveals
  nothing. Then the detail (class, period, explanation, checks, note) is
  added once, or skipped, and that reply is the reveal (`reveal`). Until
  then the person hasn't seen the answers, on every route: `revealed_at` is
  empty, and `findings.answers_visible` turns on it. The detail counts
  exactly as detail sent with the answer does. The reveal reports the tier
  move from before the first step.
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
- An answer given in two steps counts at the first, so between the steps
  the reviewer can see the tier and score move with it, as any visitor can,
  before choosing the detail.

Services flush and never commit.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Select, Text, cast, column, exists, func, not_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from fieldclub.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from fieldclub.models import Finding, Observation, User
from fieldclub.models.common import SRID
from fieldclub.schemas.common import int_from_cursor, offset_from_cursor, offset_page, paginate
from fieldclub.services import activity, findings, looked_at, sensitivity, shape_edits
from fieldclub.services.confidence import CHECK_PHRASES, NEW_PART_PROMPT, NextStep, load_next_steps
from fieldclub.services.findings import ANSWER_CODES, Reassessment
from fieldclub.vocab import (
    CHECK_EXPLANATIONS,
    DESK_STRANDS,
    ActivityKind,
    Check,
    Explanation,
    FeatureClass,
    FindingState,
    NextStepCode,
    Period,
    Strand,
    Tier,
    Visible,
    stored_class,
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


# The optional detail of an answer, but its note.
_DETAIL_COLUMNS = (
    "feature_class",
    "period",
    "explanation",
    "not_modern",
    "not_natural",
    "not_artefact",
)
# Everything in an answer but its note: the part that can't change once given.
_FINAL_COLUMNS = ("visible", *_DETAIL_COLUMNS)


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
class Detail:
    """What someone thinks a feature is, beyond whether they can see it. Every part is optional."""

    feature_class: FeatureClass | None = None
    period: Period | None = None
    explanation: Explanation | None = None
    not_modern: bool | None = None
    not_natural: bool | None = None
    not_artefact: bool | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        assert contradicted_check(self) is None, "an answer can't assert a check and its explanation"

    def detail_columns(self) -> dict[str, Any]:
        """The detail as `Observation` columns, without the note."""
        return {name: _column(getattr(self, name)) for name in _DETAIL_COLUMNS}

    @property
    def is_empty(self) -> bool:
        return self.note is None and all(value is None for value in self.detail_columns().values())


@dataclass(frozen=True, kw_only=True)
class Answer(Detail):
    """A second look. With `detail_follows` it carries no detail, which `reveal` adds later."""

    visible: Visible
    detail_follows: bool = False
    # The finding's `shape_revision` the answer was given on, when the client says.
    shape_revision: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        assert not (self.detail_follows and not self.is_empty), "an answer whose detail follows has none yet"

    def columns(self) -> dict[str, Any]:
        """The answer as `Observation` columns, without the note."""
        return {"visible": _column(self.visible), **self.detail_columns()}


def _column(value: StrEnum | bool | None) -> str | bool | None:
    return value.value if isinstance(value, StrEnum) else value


def _stored(observation: Observation) -> dict[str, Any]:
    """The stored answer as this version reads it, to compare with one sent again.

    A class a later version added reads as "Not sure", the class this version
    showed, so sending it back keeps the stored class and changes nothing
    (Decision 0035).
    """
    stored = {name: getattr(observation, name) for name in _FINAL_COLUMNS}
    return stored | {"feature_class": _column(stored_class(stored["feature_class"]))}


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
    # None while the answer waits for its detail: the reply then shows nothing.
    comparison: Comparison | None

    @property
    def revealed(self) -> bool:
        return self.observation.revealed_at is not None


def check_may_answer(finding: Finding, user: User) -> None:
    """Refuse a second look, or a change to one, that `put_observation` would refuse before reading it."""
    findings.check_open(finding)
    if user.has_id(finding.author_id):
        raise OwnFindingError()
    findings.require_exact(finding, user)


def check_shape_seen(finding: Finding, revision: int | None) -> None:
    """Refuse an answer given on a shape the finder has since changed. Hold the lock.

    Otherwise the answer would be credited to ground the person never saw:
    `looked_at` would grow by it and `look_at_new_part` would clear. An
    answer that names no revision, from a page opened before answers named
    one, is taken as given on the shape as it is now.
    """
    if revision is not None and revision != finding.shape_revision:
        raise shape_edits.ShapeChangedError(
            "The finder changed the shape since you opened it. Look at it again and give your answer."
        )


def put_observation(db: Session, finding: Finding, user: User, answer: Answer) -> AnswerResult:
    """Give your second look, or change its note, and reassess the finding under its lock.

    The answer itself is final once given (see the module docstring):
    anything but the note that differs from the stored answer is refused
    with `AnswerFinalError`, and so is the same answer given again after
    it was taken back, unless it matches. An answer sent with
    `detail_follows` is stored, counts and isn't revealed. Sent again
    without it, with the same `visible`, its detail is added as `reveal`
    adds it. An answer that names the `shape_revision` it was given on is
    refused with `ShapeChangedError` when the shape has changed since
    (`check_shape_seen`), and nothing is stored.
    """
    findings.lock(db, finding)
    check_may_answer(finding, user)
    check_shape_seen(finding, answer.shape_revision)
    observation = findings.my_observation(db, finding, user)
    if observation is not None and observation.revealed_at is None:
        if observation.visible != answer.visible.value:
            raise AnswerFinalError()
        observation.withdrawn_at = None
        if not answer.detail_follows:
            return _add_detail(db, finding, user, observation, answer)
        db.flush()
        return _held(db, finding, user, observation)
    if observation is not None:
        if answer.detail_follows:
            # Already revealed: nothing to hold back, and nothing changes.
            if observation.visible != answer.visible.value:
                raise AnswerFinalError()
        elif _stored(observation) != answer.columns():
            raise AnswerFinalError()
        else:
            observation.note = answer.note
        observation.withdrawn_at = None
        db.flush()
        return _revealed(db, finding, user, observation)

    observation = Observation(
        finding_id=finding.id,
        user_id=user.id,
        note=answer.note,
        revealed_at=None if answer.detail_follows else datetime.now(UTC),
        # Kept for the reveal, which is where the move this answer makes is shown.
        tier_at_answer=finding.tier if answer.detail_follows else None,
        state_at_answer=finding.state if answer.detail_follows else None,
        role_at_answer=user.role,
        # The shape the answer was given on, which the page counts what was added since from.
        shape_revision=finding.shape_revision,
        **answer.columns(),
    )
    db.add(observation)
    db.flush()
    looked_at.grow(db, finding, observation)
    # No actor and no data: followers learn that someone answered, not who
    # or how. The answerer is left out of the notifications instead.
    activity.record(db, ActivityKind.OBSERVATION_ADDED, None, finding, quiet_for=user)
    if answer.detail_follows:
        return _held(db, finding, user, observation)
    return _revealed(db, finding, user, observation)


def reveal(db: Session, finding: Finding, user: User, detail: Detail) -> AnswerResult:
    """Add the detail to an answer given with "detail follows", or skip it, and reveal the finding.

    The detail is added once. Asked again after the reveal, it answers the
    same as long as the detail matches what is stored (`AnswerFinalError`
    otherwise), and the note can change, as `put_observation` allows. An
    answer taken back has nothing to reveal until it is restored.

    A reveal that carries any detail or a note changes the answer, so it is
    refused wherever `put_observation` would refuse it (`check_may_answer`):
    on a withdrawn finding, and for someone who no longer sees the exact
    position. One that carries nothing changes nothing the person wrote, so
    it is allowed there too: the answer was given while it could be, and its
    reveal, which shows the answers they are owed, must not be stranded.
    """
    findings.lock(db, finding)
    observation = findings.my_observation(db, finding, user)
    if observation is None or observation.withdrawn_at is not None:
        raise ObservationNotFoundError()
    if not detail.is_empty:
        check_may_answer(finding, user)
    if observation.revealed_at is None:
        return _add_detail(db, finding, user, observation, detail)
    given = {name: value for name, value in detail.detail_columns().items() if value is not None}
    stored = _stored(observation)
    if any(stored[name] != value for name, value in given.items()):
        raise AnswerFinalError()
    if detail.note is not None:
        observation.note = detail.note
    db.flush()
    return _revealed(db, finding, user, observation)


def _add_detail(
    db: Session, finding: Finding, user: User, observation: Observation, detail: Detail
) -> AnswerResult:
    """Store an unrevealed answer's detail, which the caller has checked may be given, and reveal it."""
    assert observation.revealed_at is None, "the detail is added once, before the reveal"
    for name, value in detail.detail_columns().items():
        setattr(observation, name, value)
    observation.note = detail.note
    observation.revealed_at = datetime.now(UTC)
    db.flush()
    return _revealed(db, finding, user, observation)


def _reassessed(db: Session, finding: Finding, user: User, observation: Observation) -> Reassessment:
    findings.follow(db, user, finding)
    result = findings.reassess(db, finding, None, quiet_for=user)
    db.refresh(observation)
    return result


def _held(db: Session, finding: Finding, user: User, observation: Observation) -> AnswerResult:
    return AnswerResult(observation, _reassessed(db, finding, user, observation), None)


def _revealed(db: Session, finding: Finding, user: User, observation: Observation) -> AnswerResult:
    """Reassess and compare. An answer given in two steps reports the move from before its first step."""
    assert observation.revealed_at is not None, "only a revealed answer is compared"
    result = _reassessed(db, finding, user, observation)
    if observation.tier_at_answer is not None:
        assert observation.state_at_answer is not None, "the tier and state are kept together"
        result = replace(
            result,
            tier_before=Tier(observation.tier_at_answer),
            state_before=FindingState(observation.state_at_answer),
        )
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
    finder_class = stored_class(finding.feature_class)
    return Comparison(
        finder_class=finder_class,
        community_class=stored_class(finding.community_class),
        matches_finder=None if named is None else stored_class(named) is finder_class,
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
    """Everyone's standing answers, oldest first, or `AnswerFirstError` for someone who hasn't seen them.

    Someone whose answer was revealed and who took it back has seen the
    answers already, so they still may. Someone whose answer waits for its
    detail hasn't.
    """
    if not findings.answers_visible(finding, viewer, findings.my_observation(db, finding, viewer)):
        raise AnswerFirstError()
    # Every answer that counts, a banned person's included (Decision 0019).
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
    NextStepCode.LOOK_AT_NEW_PART: NEW_PART_PROMPT,
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


def new_part_view(db: Session, finding: Finding, viewer: User | None) -> dict[str, Any] | None:
    """The view that frames what was added to a line, while the finding asks for a look at it.

    It is shape, so only for a viewer who sees the finding exactly, whom the
    queue and the second-look tasks are the only ones to offer it to.
    """
    if NextStepCode.LOOK_AT_NEW_PART.value not in finding.open_steps:
        return None
    assert sensitivity.sees_exact(finding, viewer), "the new part is shown only to exact viewers"
    return finding.added_view


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
    # For the evidence step, how many of its findings each kind of desk evidence would help,
    # in `Strand` order. A finding missing several kinds counts under each. Empty for other steps.
    strands: list[tuple[Strand, int]]


class StrandNeedsStepError(BadRequestError):
    code = "strand_needs_need_strand"
    message = "Only the evidence step, need_strand, is split by strand. Give code=need_strand with it."


def _missing(strand: Strand) -> ColumnElement[bool]:
    """Findings whose stored evidence step lists `strand` among the kinds it lacks."""
    step = [{"code": NextStepCode.NEED_STRAND.value, "missing_strands": [strand.value]}]
    return Finding.assessment["next_steps"].contains(step)


def _task_query(code: NextStepCode, viewer: User | None, strand: Strand | None = None) -> Select[Finding]:
    query = select(Finding).where(Finding.open_steps.contains([code.value]))
    if code in ANSWER_CODES:
        return query.where(_answerable(viewer)).order_by(*_queue_order(viewer, None))
    if strand is not None:
        query = query.where(_missing(strand))
    return query.where(Finding.hidden_at.is_(None)).order_by(Finding.updated_at.desc(), Finding.id.desc())


def _strand_counts(db: Session, viewer: User | None) -> list[tuple[Strand, int]]:
    """How many findings with an open evidence step lack each kind, read from their stored assessments."""
    listed = _task_query(NextStepCode.NEED_STRAND, viewer).order_by(None).subquery()
    steps = (
        func.jsonb_array_elements(listed.c.assessment["next_steps"])
        .table_valued(column("value", JSONB))
        .alias("step")
    )
    missing = (
        func.jsonb_array_elements_text(steps.c.value["missing_strands"])
        .table_valued(column("value", Text))
        .alias("kind")
    )
    rows = db.execute(
        select(missing.c.value, func.count(func.distinct(listed.c.id)))
        .select_from(listed)
        .join(steps, true())
        .join(missing, true())
        .where(steps.c.value["code"].astext == NextStepCode.NEED_STRAND.value)
        .group_by(missing.c.value)
    ).all()
    counted = {Strand(kind): count for kind, count in rows}
    return [(strand, counted.get(strand, 0)) for strand in Strand if strand in DESK_STRANDS]


def _step(steps: tuple[NextStep, ...], code: NextStepCode) -> NextStep:
    return next(step for step in steps if step.code is code)


def tasks(
    db: Session,
    viewer: User | None,
    *,
    code: NextStepCode | None = None,
    strand: Strand | None = None,
    limit: int,
    cursor: str | None = None,
) -> list[TaskGroup]:
    """Open next steps across findings, grouped by code. The cursor pages a single code.

    `strand`, with `code` the evidence step, lists only the findings that lack that kind.
    """
    assert code is not None or cursor is None, "a cursor pages one code's tasks"
    if strand is not None and code is not NextStepCode.NEED_STRAND:
        raise StrandNeedsStepError()
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
        query = _task_query(each, viewer, strand)
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        assert total is not None
        rows, next_cursor = _offset_page(db, query, limit=limit, cursor=cursor)
        groups.append(
            TaskGroup(
                code=each,
                total=total,
                tasks=[task(f, each) for f in rows],
                next_cursor=next_cursor,
                strands=_strand_counts(db, viewer) if each is NextStepCode.NEED_STRAND else [],
            )
        )
    return groups
