"""Every state boundary in the contract, tested from both sides, and how states rank."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from fieldclub.services.confidence import EvidenceInput, VoteInput
from fieldclub.vocab import (
    EvidenceKind,
    Explanation,
    FindingState,
    Outcome,
    Relation,
    Role,
    Stance,
    StateReason,
    Tier,
)
from tests.confidence.builders import (
    EXPERT,
    FINDER,
    MEMBER,
    TRUSTED,
    item,
    many,
    no,
    run,
    seen_answers,
    two_desk_strands,
    vote,
    yes,
)

OPEN, KNOWN, DISPUTED, RULED_OUT, WITHDRAWN = (
    FindingState.OPEN,
    FindingState.KNOWN,
    FindingState.DISPUTED,
    FindingState.RULED_OUT,
    FindingState.WITHDRAWN,
)


def same_as(
    role: Role = MEMBER, *, endorsers: tuple[Role, ...] = (), votes: Iterable[VoteInput] = (), **kwargs: Any
) -> EvidenceInput:
    """A link saying the finding is an existing record, endorsed by people with these roles."""
    votes = [*(vote(r) for r in endorsers), *votes]
    return item(EvidenceKind.RECORD_LINK, role=role, relation=Relation.SAME_AS, votes=votes, **kwargs)


def test_a_new_finding_is_open() -> None:
    assert (run().state, run().state_reason) == (OPEN, None)


# --------------------------------------------------------------------------
# Known
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "endorsers", "state"),
    [
        (MEMBER, (), OPEN),
        (MEMBER, (MEMBER,), KNOWN),
        (TRUSTED, (), OPEN),
        (TRUSTED, (MEMBER,), KNOWN),
        (EXPERT, (), KNOWN),
    ],
)
def test_a_same_as_link_needs_weight_of_two(
    role: Role, endorsers: tuple[Role, ...], state: FindingState
) -> None:
    assessment = run(evidence=[same_as(role, endorsers=endorsers)])
    assert (assessment.state, assessment.known) == (state, state is KNOWN)


def test_the_finder_linking_a_record_and_one_endorsement_is_known() -> None:
    assert run(evidence=[same_as(by=FINDER, endorsers=(MEMBER,))]).state is KNOWN
    assert run(evidence=[same_as(by=FINDER)]).state is OPEN


def test_a_link_voted_below_zero_is_not_known() -> None:
    assert run(evidence=[same_as(EXPERT, votes=[vote(MEMBER, -1), vote()])]).state is KNOWN, "net zero stands"
    assert run(evidence=[same_as(EXPERT, votes=[vote(EXPERT, -1), vote(MEMBER, -1)])]).state is OPEN


@pytest.mark.parametrize("relation", [Relation.RELATED, Relation.PART_OF])
def test_only_same_as_makes_it_known(relation: Relation) -> None:
    assert run(evidence=[item(EvidenceKind.RECORD_LINK, role=EXPERT, relation=relation)]).state is OPEN


# --------------------------------------------------------------------------
# Disputed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seen", "unseen", "state"),
    [
        (2, 2, DISPUTED),  # 0.5
        (4, 2, DISPUTED),  # 0.667, just below the top of the band
        (67, 33, OPEN),  # 0.67, the top of the band, is Seen instead
        (34, 66, DISPUTED),  # 0.34
        (2, 4, DISPUTED),  # 0.333, just above the bottom of the band
        (33, 67, RULED_OUT),  # 0.33, the bottom of the band, is ruled out instead
    ],
)
def test_the_disputed_band_is_open_at_both_ends(seen: int, unseen: int, state: FindingState) -> None:
    assert run([*many(seen), *many(unseen, no)]).state is state


@pytest.mark.parametrize(("seen", "unseen"), [([MEMBER], [MEMBER, MEMBER]), ([MEMBER, MEMBER], [TRUSTED])])
def test_disputed_needs_weight_of_two_on_each_side(seen: list[Role], unseen: list[Role]) -> None:
    answers = [*(yes(role) for role in seen), *(no(role) for role in unseen)]
    assert run(answers).state is OPEN


def test_one_contradicting_strand_against_one_supporting_is_disputed() -> None:
    evidence = [item(EvidenceKind.AERIAL), item(EvidenceKind.HISTORIC_MAP, stance=Stance.CONTRADICTS)]
    assert run(seen_answers(), evidence).state is DISPUTED


def test_one_contradicting_strand_against_two_supporting_is_not() -> None:
    evidence = [*two_desk_strands(), item(EvidenceKind.DOCUMENT, stance=Stance.CONTRADICTS)]
    assessment = run(seen_answers(), evidence)
    assert (assessment.state, assessment.tier) == (OPEN, Tier.CORROBORATED)


def test_no_strands_either_way_is_not_disputed() -> None:
    assert run(evidence=[item(EvidenceKind.AERIAL, stance=Stance.NEUTRAL)]).state is OPEN


def test_contradicting_evidence_must_stand() -> None:
    evidence = [item(EvidenceKind.AERIAL, stance=Stance.CONTRADICTS, votes=[vote(value=-1)])]
    assert run(evidence=evidence).state is OPEN


def test_ground_items_that_disagree_dispute_it() -> None:
    evidence = [
        item(EvidenceKind.FIELD_VISIT, outcome=Outcome.SUPPORTS),
        item(EvidenceKind.GEOPHYSICS, outcome=Outcome.CONTRADICTS),
    ]
    assert run(evidence=evidence).state is DISPUTED


def test_an_inconclusive_ground_item_disagrees_with_nothing() -> None:
    evidence = [
        item(EvidenceKind.FIELD_VISIT, outcome=Outcome.SUPPORTS),
        item(EvidenceKind.FIELD_VISIT, outcome=Outcome.INCONCLUSIVE),
    ]
    assert run(evidence=evidence).state is OPEN


# --------------------------------------------------------------------------
# Ruled out
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("unseen", "state"),
    [([MEMBER, MEMBER, MEMBER], RULED_OUT), ([MEMBER, MEMBER], OPEN), ([EXPERT], RULED_OUT)],
)
def test_unseen_weight_of_three_rules_it_out(unseen: list[Role], state: FindingState) -> None:
    assessment = run([no(role) for role in unseen])
    assert assessment.state is state
    if state is RULED_OUT:
        assert (assessment.state_reason, assessment.score, assessment.next_steps) == (
            StateReason.NOT_VISIBLE,
            0,
            (),
        )


@pytest.mark.parametrize(
    ("explainers", "seen", "state"), [(3, 0, RULED_OUT), (2, 0, OPEN), (3, 2, RULED_OUT)]
)
def test_an_explanation_of_weight_three_rules_it_out(explainers: int, seen: int, state: FindingState) -> None:
    answers = [*many(explainers, no, explanation=Explanation.NATURAL), *many(seen)]
    assessment = run(answers)
    assert assessment.state is state
    if state is RULED_OUT:
        assert assessment.state_reason is StateReason.NATURAL


def test_an_explanation_must_outweigh_the_people_who_see_it() -> None:
    answers = [*many(3, no, explanation=Explanation.MODERN), *many(3)]
    assert run(answers).state is DISPUTED, "3 against 3 is in the disputed band, not ruled out"
    answers = [*many(3, no, explanation=Explanation.MODERN), *many(4)]
    assert run(answers).state is not RULED_OUT


def test_people_who_see_a_drain_rule_it_out_as_modern() -> None:
    assessment = run(many(3, yes, explanation=Explanation.MODERN))
    assert (assessment.seen, assessment.observers) == (0.0, 0)
    assert (assessment.state, assessment.state_reason, assessment.tier) == (
        RULED_OUT,
        StateReason.MODERN,
        Tier.SPOTTED,
    )


def test_a_ground_item_that_contradicts_it_rules_it_out() -> None:
    assessment = run(seen_answers(), [item(EvidenceKind.FIELD_VISIT, outcome=Outcome.CONTRADICTS)])
    assert (assessment.state, assessment.state_reason, assessment.score) == (
        RULED_OUT,
        StateReason.GROUND_CHECK,
        0,
    )


def test_a_ground_item_that_contradicts_it_but_does_not_stand_does_not() -> None:
    evidence = [item(EvidenceKind.FIELD_VISIT, outcome=Outcome.CONTRADICTS, votes=[vote(value=-1)])]
    assert run(evidence=evidence).state is OPEN


def test_the_ground_reason_comes_first_then_the_explanation_then_visibility() -> None:
    answers = many(3, no, explanation=Explanation.ARTEFACT)
    assert run(answers).state_reason is StateReason.ARTEFACT
    evidence = [item(EvidenceKind.FIELD_VISIT, outcome=Outcome.CONTRADICTS)]
    assert run(answers, evidence).state_reason is StateReason.GROUND_CHECK


def test_the_heaviest_explanation_is_the_reason() -> None:
    answers = [
        *many(3, no, explanation=Explanation.MODERN),
        no(EXPERT, explanation=Explanation.NATURAL),
        no(),
    ]
    assert run(answers).state_reason is StateReason.MODERN
    answers = [
        *many(3, no, explanation=Explanation.MODERN),
        *many(2, no, role=EXPERT, explanation=Explanation.NATURAL),
    ]
    assert run(answers).state_reason is StateReason.NATURAL


def test_it_is_never_ruled_out_at_ground_checked_or_above() -> None:
    evidence = [item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)]
    assessment = run(many(5, no), evidence)
    assert assessment.tier is Tier.GROUND_CHECKED
    assert (assessment.state, assessment.state_reason) == (DISPUTED, StateReason.NOT_VISIBLE)
    assert assessment.score == 85


# --------------------------------------------------------------------------
# Withdrawn and precedence
# --------------------------------------------------------------------------


def test_a_withdrawn_finding_stays_withdrawn_and_asks_for_nothing() -> None:
    assessment = run(seen_answers(), state=WITHDRAWN)
    assert (assessment.state, assessment.tier, assessment.score, assessment.next_steps) == (
        WITHDRAWN,
        Tier.SEEN,
        30,
        (),
    )


def test_withdrawn_outranks_ruled_out() -> None:
    assert run(many(3, no), state=WITHDRAWN).state is WITHDRAWN


@pytest.mark.parametrize("stored", [KNOWN, DISPUTED, RULED_OUT])
def test_every_other_stored_state_is_recomputed(stored: FindingState) -> None:
    assert run(state=stored).state is OPEN


def test_ruled_out_outranks_disputed_and_known() -> None:
    evidence = [same_as(EXPERT), item(EvidenceKind.AERIAL, stance=Stance.CONTRADICTS)]
    assessment = run(many(3, no), evidence)
    assert (assessment.state, assessment.known) == (RULED_OUT, True)


def test_disputed_outranks_known() -> None:
    assessment = run([yes(), yes(), no(), no()], [same_as(EXPERT)])
    assert (assessment.state, assessment.known) == (DISPUTED, True)
