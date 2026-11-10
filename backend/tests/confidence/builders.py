"""Short ways to build confidence-engine inputs. Import as `from tests.confidence.builders import ...`.

Every person a builder makes up gets a fresh user id, so two calls never
collide. The finder is always user `FINDER`.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

from fieldclub.services.confidence import (
    Assessment,
    EvidenceInput,
    FindingInputs,
    ObservationInput,
    Thresholds,
    VoteInput,
    assess,
)
from fieldclub.vocab import (
    EvidenceKind,
    Explanation,
    FeatureClass,
    FindingState,
    Outcome,
    Relation,
    Role,
    Stance,
    Visible,
)

FINDER = 1
_people = itertools.count(1000)
_items = itertools.count(1)

MEMBER, TRUSTED, EXPERT, MODERATOR, ADMIN = Role.MEMBER, Role.TRUSTED, Role.EXPERT, Role.MODERATOR, Role.ADMIN
ENCLOSURE = FeatureClass.ENCLOSURE


def person() -> int:
    return next(_people)


def answer(
    visible: Visible,
    role: Role = MEMBER,
    *,
    user: int | None = None,
    cls: FeatureClass | None = None,
    explanation: Explanation | None = None,
    checks: bool | None = None,
) -> ObservationInput:
    return ObservationInput(
        user_id=user if user is not None else person(),
        role=role,
        visible=visible,
        feature_class=cls,
        explanation=explanation,
        not_modern=checks,
        not_natural=checks,
        not_artefact=checks,
    )


yes = partial(answer, Visible.YES)
no = partial(answer, Visible.NO)
unsure = partial(answer, Visible.UNSURE)


def many(n: int, make: Callable[..., ObservationInput] = yes, **kwargs: Any) -> list[ObservationInput]:
    """`n` answers from different people, "yes" from members unless told otherwise."""
    return [make(**kwargs) for _ in range(n)]


def vote(role: Role = MEMBER, value: int = 1, *, user: int | None = None) -> VoteInput:
    return VoteInput(user_id=user if user is not None else person(), role=role, value=value)


def item(
    kind: EvidenceKind,
    *,
    by: int | None = None,
    role: Role = MEMBER,
    stance: Stance = Stance.SUPPORTS,
    outcome: Outcome | None = None,
    relation: Relation | None = None,
    votes: Iterable[VoteInput] = (),
    deleted: bool = False,
    verified_by: int | None = None,
    verifier_role: Role | None = None,
    id: int | None = None,
) -> EvidenceInput:
    return EvidenceInput(
        id=id if id is not None else next(_items),
        user_id=by if by is not None else person(),
        role=role,
        kind=kind,
        stance=stance,
        outcome=outcome,
        relation=relation,
        deleted=deleted,
        verified_by=verified_by,
        verifier_role=verifier_role,
        votes=tuple(votes),
    )


def verified(
    kind: EvidenceKind = EvidenceKind.HER_RECORD, verifier: Role = EXPERT, **kwargs: Any
) -> EvidenceInput:
    """An official item verified by a new person with the `verifier` role."""
    return item(kind, verified_by=person(), verifier_role=verifier, **kwargs)


def finding(
    observations: Iterable[ObservationInput] = (),
    evidence: Iterable[EvidenceInput] = (),
    *,
    feature_class: FeatureClass = ENCLOSURE,
    finder_role: Role = MEMBER,
    state: FindingState = FindingState.OPEN,
) -> FindingInputs:
    return FindingInputs(
        author_id=FINDER,
        author_role=finder_role,
        feature_class=feature_class,
        state=state,
        observations=tuple(observations),
        evidence=tuple(evidence),
    )


def run(
    observations: Iterable[ObservationInput] = (),
    evidence: Iterable[EvidenceInput] = (),
    *,
    thresholds: Thresholds | None = None,
    **kwargs: Any,
) -> Assessment:
    inputs = finding(observations, evidence, **kwargs)
    return assess(inputs) if thresholds is None else assess(inputs, thresholds)


# Ready-made sets of contributions that reach each desk tier with nothing to spare.


def seen_answers() -> list[ObservationInput]:
    """Two members who can see it and agree it's an enclosure."""
    return [yes(cls=ENCLOSURE), yes(cls=ENCLOSURE)]


def two_desk_strands() -> list[EvidenceInput]:
    """An aerial photo and an old map, each added by someone other than the finder."""
    return [item(EvidenceKind.AERIAL), item(EvidenceKind.HISTORIC_MAP)]


def probable_answers() -> list[ObservationInput]:
    """Seen, class agreement, every check cleared by two people, and a trusted yes."""
    return [yes(cls=ENCLOSURE, checks=True), yes(cls=ENCLOSURE, checks=True), yes(TRUSTED)]


def codes(assessment: Assessment) -> list[str]:
    return [step.code.value for step in assessment.next_steps]
