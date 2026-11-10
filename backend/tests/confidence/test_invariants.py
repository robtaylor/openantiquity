"""Properties that hold for every finding, checked over seeded generated cases."""

from __future__ import annotations

import dataclasses
import itertools
import json
import random
from collections import Counter
from functools import cache
from typing import Any

import pytest

from fieldclub.services.confidence import (
    THRESHOLDS,
    Assessment,
    FindingInputs,
    ObservationInput,
    assess,
    load_assessment,
)
from fieldclub.vocab import (
    DESK_STRANDS,
    TIER_BASE_SCORES,
    TIER_ORDER,
    Check,
    EvidenceKind,
    FeatureClass,
    FindingState,
    NextStepCode,
    Role,
    Tier,
    Visible,
    tier_rank,
)
from tests.confidence.generate import FINDER, cases, random_evidence, random_observation

T = THRESHOLDS
FRESH = 900_000  # user ids above every generated person


@cache
def assessed() -> list[tuple[int, FindingInputs, Assessment]]:
    return [(seed, inputs, assess(inputs)) for seed, inputs in cases()]


def members(n: int, start: int, **fields: Any) -> list[ObservationInput]:
    """`n` new members, each answering with these fields."""
    return [ObservationInput(user_id=start + i, role=Role.MEMBER, **fields) for i in range(n)]


def with_(inputs: FindingInputs, **changes: Any) -> FindingInputs:
    return dataclasses.replace(inputs, **changes)


def test_the_generator_reaches_every_tier_and_state() -> None:
    results = assessed()
    tiers = Counter(a.tier for _, _, a in results)
    states = Counter(a.state for _, _, a in results)
    assert set(tiers) == set(Tier), tiers
    assert set(states) == set(FindingState), states


def test_the_finders_own_opinion_never_changes_anything() -> None:
    for seed, inputs, assessment in assessed():
        rng = random.Random(seed)
        others = tuple(obs for obs in inputs.observations if obs.user_id != FINDER)
        own = random_observation(rng, FINDER, inputs.author_role, inputs.feature_class)
        for observations in (others, (*others, own)):
            again = assess(with_(inputs, observations=observations))
            assert again == assessment, f"seed {seed}"
            assert again.seen == assessment.seen, f"seed {seed}"


def _agreeing_class(assessment: Assessment, finder_class: FeatureClass) -> FeatureClass | None:
    if assessment.class_support:
        order = list(FeatureClass)
        return max(assessment.class_support, key=lambda c: (assessment.class_support[c], -order.index(c)))
    return None if finder_class is FeatureClass.UNKNOWN else finder_class


@pytest.mark.parametrize("role", [Role.MEMBER, Role.TRUSTED, Role.EXPERT])
def test_an_agreeing_answer_never_lowers_the_tier(role: Role) -> None:
    for seed, inputs, assessment in assessed():
        agreeing = ObservationInput(
            user_id=FRESH,
            role=role,
            visible=Visible.YES,
            feature_class=_agreeing_class(assessment, inputs.feature_class),
            not_modern=True,
            not_natural=True,
            not_artefact=True,
        )
        after = assess(with_(inputs, observations=(*inputs.observations, agreeing)))
        assert tier_rank(after.tier) >= tier_rank(assessment.tier), f"seed {seed}"
        assert after.satisfied >= assessment.satisfied, f"seed {seed}"


def test_reordering_the_inputs_never_changes_the_result() -> None:
    for seed, inputs, assessment in assessed():
        rng = random.Random(seed)
        observations = list(inputs.observations)
        rng.shuffle(observations)
        evidence = []
        for item in inputs.evidence:
            votes = list(item.votes)
            rng.shuffle(votes)
            evidence.append(dataclasses.replace(item, votes=tuple(votes)))
        rng.shuffle(evidence)
        shuffled = with_(inputs, observations=tuple(observations), evidence=tuple(evidence))
        assert assess(shuffled) == assessment, f"seed {seed}"
        assert assess(shuffled).to_json() == assessment.to_json(), f"seed {seed}"


def test_the_score_is_monotonic_in_the_tier() -> None:
    by_tier: dict[Tier, list[int]] = {tier: [] for tier in Tier}
    for seed, _, assessment in assessed():
        if assessment.state is FindingState.RULED_OUT:
            assert assessment.score == 0, f"seed {seed}: a ruled-out finding scores zero"
            continue
        rank = tier_rank(assessment.tier)
        base = TIER_BASE_SCORES[assessment.tier]
        ceiling = TIER_BASE_SCORES[TIER_ORDER[rank + 1]] if rank + 1 < len(TIER_ORDER) else base + 1
        assert base <= assessment.score < ceiling, f"seed {seed}"
        by_tier[assessment.tier].append(assessment.score)
    scores = [scores for scores in by_tier.values() if scores]
    for lower, higher in itertools.pairwise(scores):
        assert max(lower) < min(higher)


def test_the_tier_is_the_highest_satisfied_and_the_desk_tiers_nest() -> None:
    desk = list(TIER_ORDER[:4])
    for seed, _, assessment in assessed():
        assert assessment.tier is max(assessment.satisfied, key=tier_rank), f"seed {seed}"
        held = [tier in assessment.satisfied for tier in desk]
        assert held == sorted(held, reverse=True), f"seed {seed}: desk tiers must be reached in order"


def _unmet(assessment: Assessment) -> list[tuple[NextStepCode, Check | None]]:
    """The unmet requirements of the next tier, worked out again from the published quantities."""
    nxt = assessment.next_tier
    unmet: list[tuple[NextStepCode, Check | None]] = []
    if nxt is Tier.SEEN:
        return [(NextStepCode.NEED_OBSERVERS, None)]
    if nxt is Tier.CORROBORATED:
        if len(assessment.supporting_strands & DESK_STRANDS) < T.corroborating_strands:
            unmet.append((NextStepCode.NEED_STRAND, None))
        if assessment.community_class is None or assessment.class_people < T.class_people:
            unmet.append((NextStepCode.NEED_CLASS_AGREEMENT, None))
        return unmet
    if nxt is Tier.PROBABLE:
        unmet += [(NextStepCode.NEED_CHECK, s.check) for s in assessment.checks if not s.cleared]
        if not assessment.reviewers and assessment.seen < T.probable_seen_without_reviewer:
            unmet.append((NextStepCode.NEED_TRUSTED_REVIEW, None))
        return unmet
    if nxt is Tier.GROUND_CHECKED:
        return [(NextStepCode.NEED_GROUND, None)]
    assert nxt is Tier.CONFIRMED
    return [(NextStepCode.NEED_OFFICIAL, None)]


def test_the_next_steps_are_exactly_the_unmet_requirements_of_the_next_tier() -> None:
    for seed, _, assessment in assessed():
        steps = [(step.code, step.check) for step in assessment.next_steps]
        if assessment.tier is Tier.CONFIRMED:
            assert (assessment.next_tier, steps) == (None, []), f"seed {seed}"
            continue
        assert assessment.next_tier is TIER_ORDER[tier_rank(assessment.tier) + 1], f"seed {seed}"
        if assessment.state in (FindingState.RULED_OUT, FindingState.WITHDRAWN):
            assert steps == [], f"seed {seed}: nobody is asked to work on it"
            continue
        unmet = _unmet(assessment)
        assert unmet, f"seed {seed}: with nothing unmet it would be in the next tier"
        assert steps == unmet, f"seed {seed}"


def test_doing_what_a_step_asks_meets_it_and_one_person_fewer_does_not() -> None:
    checked = Counter[NextStepCode]()
    for seed, inputs, assessment in assessed():
        for step in assessment.next_steps:
            if step.people is None or step.code not in (
                NextStepCode.NEED_OBSERVERS,
                NextStepCode.NEED_CLASS_AGREEMENT,
                NextStepCode.NEED_CHECK,
            ):
                continue
            checked[step.code] += 1
            fields: dict[str, Any] = {"visible": Visible.UNSURE}
            if step.code is NextStepCode.NEED_OBSERVERS:
                fields = {"visible": Visible.YES}
            elif step.code is NextStepCode.NEED_CLASS_AGREEMENT:
                fields["feature_class"] = (
                    _agreeing_class(assessment, inputs.feature_class) or FeatureClass.ENCLOSURE
                )
            else:
                assert step.check is not None
                fields[step.check.value] = True

            def met(
                n: int,
                step_code: NextStepCode = step.code,
                check: Check | None = step.check,
                inputs: FindingInputs = inputs,
                fields: dict[str, Any] = fields,
            ) -> bool:
                extra = members(n, FRESH, **fields)
                after = assess(with_(inputs, observations=(*inputs.observations, *extra)))
                if step_code is NextStepCode.NEED_OBSERVERS:
                    return Tier.SEEN in after.satisfied
                if step_code is NextStepCode.NEED_CLASS_AGREEMENT:
                    return after.community_class is not None and after.class_people >= T.class_people
                assert check is not None
                return after.check(check).cleared

            assert step.people >= 1, f"seed {seed}"
            assert met(step.people), f"seed {seed}: {step}"
            assert not met(step.people - 1), f"seed {seed}: {step} asks for more people than it needs"
    assert set(checked) == {
        NextStepCode.NEED_OBSERVERS,
        NextStepCode.NEED_CLASS_AGREEMENT,
        NextStepCode.NEED_CHECK,
    }
    assert min(checked.values()) >= 20, checked


def test_deleted_evidence_changes_nothing() -> None:
    for seed, inputs, assessment in assessed():
        rng = random.Random(seed)
        people = {FINDER: inputs.author_role, **{obs.user_id: obs.role for obs in inputs.observations}}
        deleted = [
            dataclasses.replace(random_evidence(rng, 10_000 + n, people), deleted=True) for n in range(3)
        ]
        assert assess(with_(inputs, evidence=(*inputs.evidence, *deleted))) == assessment, f"seed {seed}"


def test_deleting_an_item_is_the_same_as_leaving_it_out() -> None:
    for seed, inputs, _ in assessed():
        for item in inputs.evidence:
            rest = tuple(other for other in inputs.evidence if other is not item)
            marked = (*rest, dataclasses.replace(item, deleted=True))
            assert assess(with_(inputs, evidence=marked)) == assess(with_(inputs, evidence=rest)), (
                f"seed {seed}"
            )


def test_the_assessment_survives_a_trip_through_json() -> None:
    for seed, _, assessment in assessed():
        stored = json.loads(json.dumps(assessment.to_json()))
        assert load_assessment(stored) == assessment, f"seed {seed}"


def test_an_empty_or_older_assessment_loads_as_none() -> None:
    assert load_assessment({}) is None
    assert load_assessment(None) is None
    assert load_assessment({"version": 0, "tier": "seen"}) is None


def test_the_generator_covers_the_tricky_inputs() -> None:
    kinds = Counter(item.kind for _, inputs, _ in assessed() for item in inputs.evidence)
    assert set(kinds) == set(EvidenceKind)
    finder_items = sum(item.user_id == FINDER for _, inputs, _ in assessed() for item in inputs.evidence)
    finder_answers = sum(obs.user_id == FINDER for _, inputs, _ in assessed() for obs in inputs.observations)
    assert finder_items > 50
    assert finder_answers > 50
