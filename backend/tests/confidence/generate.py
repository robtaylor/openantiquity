"""A small seeded generator of confidence-engine inputs, for invariants over many cases.

`random_inputs(rng)` draws a finding with a handful of people, each with one
role throughout, and a mix of answers, evidence, votes, deletions and
verifications. It leans towards agreement, and half the findings get desk evidence only, so
that every tier turns up.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from fieldclub.services.confidence import (
    FIELD_STRANDS,
    EvidenceInput,
    FindingInputs,
    ObservationInput,
    VoteInput,
)
from fieldclub.vocab import (
    DESK_STRANDS,
    EVIDENCE_STRANDS,
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
from tests.confidence.builders import FINDER

CASES = 600

_ROLES = (Role.MEMBER,) * 6 + (Role.TRUSTED,) * 2 + (Role.EXPERT, Role.MODERATOR, Role.ADMIN)
_CLASSES = (
    FeatureClass.ENCLOSURE,
    FeatureClass.FIELD_SYSTEM,
    FeatureClass.ROUND_BARROW,
    FeatureClass.UNKNOWN,
)
_FIELD = frozenset(kind for kind, strand in EVIDENCE_STRANDS.items() if strand in FIELD_STRANDS)

_DESK_KINDS = tuple(kind for kind, strand in EVIDENCE_STRANDS.items() if strand in DESK_STRANDS)


def _pick[T](rng: random.Random, options: Sequence[T], weights: Sequence[float] | None = None) -> T:
    return rng.choices(options, weights=weights)[0]


def random_observation(
    rng: random.Random, user: int, role: Role, finder_class: FeatureClass
) -> ObservationInput:
    visible = _pick(rng, (Visible.YES, Visible.NO, Visible.UNSURE), (0.6, 0.25, 0.15))
    cls = _pick(rng, (None, finder_class, *_CLASSES), (0.3, 0.4, 0.1, 0.1, 0.05, 0.05))
    explanation = _pick(rng, (None, *Explanation), (0.8, 0.07, 0.07, 0.06))

    def check() -> bool | None:
        return _pick(rng, (True, None, False), (0.55, 0.35, 0.1))

    return ObservationInput(
        user_id=user,
        role=role,
        visible=visible,
        feature_class=cls,
        explanation=explanation,
        not_modern=check(),
        not_natural=check(),
        not_artefact=check(),
    )


def random_evidence(
    rng: random.Random,
    evidence_id: int,
    people: dict[int, Role],
    kinds: Sequence[EvidenceKind] = tuple(EvidenceKind),
) -> EvidenceInput:
    kind = _pick(rng, kinds)
    contributor = _pick(rng, list(people))
    voters = rng.sample(list(people), k=rng.randint(0, min(4, len(people))))
    votes = tuple(VoteInput(user_id=v, role=people[v], value=_pick(rng, (1, -1), (0.8, 0.2))) for v in voters)
    verifier = _pick(rng, list(people)) if rng.random() < 0.3 else None
    return EvidenceInput(
        id=evidence_id,
        user_id=contributor,
        role=people[contributor],
        kind=kind,
        stance=_pick(rng, list(Stance), (0.75, 0.1, 0.15)),
        outcome=_pick(rng, (None, *Outcome), (0.2, 0.55, 0.1, 0.15)) if kind in _FIELD else None,
        relation=_pick(rng, list(Relation)) if kind is EvidenceKind.RECORD_LINK else None,
        deleted=rng.random() < 0.08,
        verified_by=verifier,
        verifier_role=people[verifier] if verifier is not None else None,
        votes=votes,
    )


def random_inputs(rng: random.Random) -> FindingInputs:
    finder_role = _pick(rng, _ROLES)
    others = {1000 + n: _pick(rng, _ROLES) for n in range(rng.randint(0, 12))}
    people = {FINDER: finder_role, **others}
    feature_class = _pick(rng, _CLASSES)
    observations = [
        random_observation(rng, user, role, feature_class)
        for user, role in others.items()
        if rng.random() < 0.75
    ]
    if rng.random() < 0.2:
        observations.append(random_observation(rng, FINDER, finder_role, feature_class))
    # Half the findings get desk evidence only, so the middle of the ladder turns up often.
    kinds = _DESK_KINDS if rng.random() < 0.5 else tuple(EvidenceKind)
    evidence = [random_evidence(rng, n, people, kinds) for n in range(1, rng.randint(0, 8) + 1)]
    state = _pick(rng, list(FindingState), (0.8, 0.03, 0.03, 0.04, 0.1))
    return FindingInputs(
        author_id=FINDER,
        author_role=finder_role,
        feature_class=feature_class,
        state=state,
        observations=tuple(observations),
        evidence=tuple(evidence),
    )


def cases(seed: int = 20261110, count: int = CASES) -> list[tuple[int, FindingInputs]]:
    """`count` cases, each with the seed that rebuilds it on its own."""
    return [(seed + n, random_inputs(random.Random(seed + n))) for n in range(count)]
