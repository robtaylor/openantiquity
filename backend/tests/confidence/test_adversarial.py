"""Cases built to break the engine: pile-ons, lopsided weights, self-endorsement, balanced evidence."""

from __future__ import annotations

import pytest

from fieldclub.services.confidence import (
    EvidenceInput,
    FindingInputs,
    InvalidInputsError,
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
    StateReason,
    Tier,
    Visible,
)
from tests.confidence.builders import (
    ENCLOSURE,
    EXPERT,
    FINDER,
    MEMBER,
    TRUSTED,
    item,
    many,
    no,
    person,
    probable_answers,
    run,
    seen_answers,
    two_desk_strands,
    vote,
    yes,
)

DESK_KINDS = (
    EvidenceKind.LIDAR_VIEW,
    EvidenceKind.AERIAL,
    EvidenceKind.HISTORIC_MAP,
    EvidenceKind.DOCUMENT,
)
FIELD_SYSTEM = FeatureClass.FIELD_SYSTEM


# --------------------------------------------------------------------------
# Sock puppets
# --------------------------------------------------------------------------


def test_a_finder_and_one_puppet_cannot_leave_spotted() -> None:
    puppet = person()
    answers = [
        yes(user=FINDER, cls=ENCLOSURE, checks=True),
        yes(user=puppet, cls=ENCLOSURE, checks=True),
    ]
    mine = [item(kind, by=FINDER, votes=[vote(user=puppet)]) for kind in DESK_KINDS]
    theirs = [item(kind, by=puppet, votes=[vote(user=FINDER)]) for kind in DESK_KINDS]
    link = item(EvidenceKind.RECORD_LINK, by=puppet, relation=Relation.RELATED)
    assessment = run(answers, [*mine, *theirs, link])
    assert len(assessment.desk_strands) == 5, "the strands are there"
    assert (assessment.observers, assessment.tier) == (1, Tier.SPOTTED), "but one other person has looked"
    assert [step.people for step in assessment.next_steps] == [1]


def test_a_puppet_cannot_answer_twice() -> None:
    puppet = person()
    with pytest.raises(InvalidInputsError):
        FindingInputs(
            author_id=FINDER,
            author_role=Role.MEMBER,
            feature_class=ENCLOSURE,
            observations=(yes(user=puppet), yes(user=puppet)),
        )


def test_a_puppet_cannot_vote_twice() -> None:
    puppet = person()
    with pytest.raises(InvalidInputsError):
        item(EvidenceKind.AERIAL, votes=[vote(user=puppet), vote(user=puppet)])


def test_two_puppets_reach_corroborated_but_not_probable() -> None:
    # Decision 0003 accepts this: a trusted reviewer, or seven people, is the gate.
    answers = many(2, cls=ENCLOSURE, checks=True)
    assessment = run(answers, two_desk_strands())
    assert assessment.tier is Tier.CORROBORATED
    assert [step.code.value for step in assessment.next_steps] == ["need_trusted_review"]


def test_a_pile_on_of_objections_sinks_evidence_but_not_the_finding() -> None:
    against = [vote(value=-1) for _ in range(20)]
    evidence = [item(EvidenceKind.AERIAL, role=EXPERT, votes=against), item(EvidenceKind.HISTORIC_MAP)]
    assessment = run(seen_answers(), evidence)
    assert (assessment.tier, len(assessment.desk_strands)) == (Tier.SEEN, 1)
    assert assessment.state is FindingState.OPEN, "objections to evidence are not a dispute about the finding"


# --------------------------------------------------------------------------
# One expert against five members
# --------------------------------------------------------------------------


def test_an_expert_who_cannot_see_it_against_five_who_can_disputes_it() -> None:
    assessment = run([*many(5), no(EXPERT)])
    assert assessment.seen_ratio == pytest.approx(5 / 8)
    assert (assessment.tier, assessment.state) == (Tier.SPOTTED, FindingState.DISPUTED)


def test_an_expert_who_cannot_see_it_against_two_who_can_does_not_rule_it_out() -> None:
    assessment = run([yes(), yes(), no(EXPERT)])
    assert assessment.seen_ratio == pytest.approx(0.4)
    assert assessment.state is FindingState.DISPUTED


def test_an_experts_explanation_does_not_outweigh_five_members() -> None:
    assessment = run([*many(5), unsure_expert_explaining(Explanation.NATURAL)])
    assert (assessment.tier, assessment.state) == (Tier.SEEN, FindingState.OPEN)


def test_an_experts_explanation_does_outweigh_two_members() -> None:
    assessment = run([yes(), yes(), unsure_expert_explaining(Explanation.NATURAL)])
    assert (assessment.state, assessment.state_reason) == (FindingState.RULED_OUT, StateReason.NATURAL)


def unsure_expert_explaining(explanation: Explanation) -> ObservationInput:
    return ObservationInput(user_id=person(), role=EXPERT, visible=Visible.UNSURE, explanation=explanation)


@pytest.mark.parametrize(("members", "community"), [(5, ENCLOSURE), (4, None)])
def test_an_expert_naming_another_class_against_the_members(
    members: int, community: FeatureClass | None
) -> None:
    answers = [*many(members, cls=ENCLOSURE), yes(EXPERT, cls=FIELD_SYSTEM)]
    assessment = run(answers)
    # The finder and the members against 3.0: 6 of 9 is two thirds exactly, 5 of 8 is not.
    assert assessment.community_class == community


def test_one_expert_cannot_see_it_alone() -> None:
    assessment = run([yes(EXPERT, cls=ENCLOSURE, checks=True)], two_desk_strands())
    assert assessment.tier is Tier.SPOTTED


# --------------------------------------------------------------------------
# Evidence the finder endorses themselves
# --------------------------------------------------------------------------


def test_the_finder_cannot_corroborate_their_own_finding_with_screenshots() -> None:
    screenshots = [
        item(kind, by=FINDER, role=EXPERT, votes=[vote(EXPERT, user=FINDER)]) for kind in DESK_KINDS
    ]
    assessment = run(seen_answers(), screenshots, finder_role=EXPERT)
    assert (assessment.tier, assessment.desk_strands) == (Tier.SEEN, frozenset())
    strand_step = assessment.next_steps[0]
    assert set(strand_step.pending_evidence) == {e.id for e in screenshots}


def test_the_finder_cannot_put_their_own_record_on_record() -> None:
    record = item(EvidenceKind.HER_RECORD, by=FINDER, role=EXPERT, verified_by=FINDER, verifier_role=EXPERT)
    assert run(evidence=[record], finder_role=EXPERT).tier is Tier.SPOTTED


def test_an_endorsement_from_someone_too_light_does_not_make_it_independent() -> None:
    endorsed = item(EvidenceKind.AERIAL, by=FINDER, votes=[vote()])
    thresholds = Thresholds(endorsement_weight=1.5)
    assert not run(evidence=[endorsed], thresholds=thresholds).evidence[0].independent
    assert run(evidence=[endorsed]).evidence[0].independent


# --------------------------------------------------------------------------
# Balanced evidence
# --------------------------------------------------------------------------


def test_contradicting_strands_equal_to_supporting_ones_dispute_it_but_keep_the_tier() -> None:
    against = [
        item(EvidenceKind.LIDAR_VIEW, stance=Stance.CONTRADICTS),
        item(EvidenceKind.DOCUMENT, stance=Stance.CONTRADICTS),
    ]
    assessment = run(probable_answers(), [*two_desk_strands(), *against])
    assert (len(assessment.supporting_strands), len(assessment.contradicting_strands)) == (2, 2)
    assert (assessment.tier, assessment.state) == (Tier.PROBABLE, FindingState.DISPUTED)


def test_one_strand_both_supporting_and_contradicting_counts_both_ways() -> None:
    evidence = [item(EvidenceKind.AERIAL), item(EvidenceKind.AERIAL, stance=Stance.CONTRADICTS)]
    assessment = run(seen_answers(), evidence)
    assert assessment.supporting_strands == assessment.contradicting_strands
    assert assessment.state is FindingState.DISPUTED


def test_contradicting_evidence_from_the_finder_needs_an_endorsement_too() -> None:
    assessment = run(evidence=[item(EvidenceKind.AERIAL, by=FINDER, stance=Stance.CONTRADICTS)])
    assert (assessment.contradicting_strands, assessment.state) == (frozenset(), FindingState.OPEN)


def test_a_contradicting_ground_check_against_a_desk_case_rules_it_out() -> None:
    visit = item(EvidenceKind.EXCAVATION, role=EXPERT, outcome=Outcome.CONTRADICTS)
    assessment = run(probable_answers(), [*two_desk_strands(), visit])
    assert (assessment.tier, assessment.state, assessment.score) == (Tier.PROBABLE, FindingState.RULED_OUT, 0)


def test_an_inconclusive_excavation_changes_nothing() -> None:
    visit = item(EvidenceKind.EXCAVATION, role=EXPERT, outcome=Outcome.INCONCLUSIVE)
    with_visit = run(probable_answers(), [*two_desk_strands(), visit])
    assert (with_visit.tier, with_visit.state) == (Tier.PROBABLE, FindingState.OPEN)


# --------------------------------------------------------------------------
# Bad inputs fail loudly
# --------------------------------------------------------------------------


def test_a_bad_stored_value_raises() -> None:
    with pytest.raises(InvalidInputsError, match="kind"):
        EvidenceInput(id=1, user_id=2, role=MEMBER, kind="selfie")  # type: ignore[arg-type]


def test_stored_strings_are_accepted() -> None:
    observation = ObservationInput(user_id=2, role="trusted", visible="yes", feature_class="moat")  # type: ignore[arg-type]
    assert (observation.role, observation.visible, observation.feature_class) == (
        TRUSTED,
        Visible.YES,
        FeatureClass.MOAT,
    )


def test_a_vote_is_plus_or_minus_one() -> None:
    with pytest.raises(InvalidInputsError):
        VoteInput(user_id=2, role=MEMBER, value=2)


def test_a_verifier_needs_a_role() -> None:
    with pytest.raises(InvalidInputsError):
        item(EvidenceKind.HER_RECORD, verified_by=person())


def test_evidence_ids_are_unique() -> None:
    with pytest.raises(InvalidInputsError):
        assess(
            FindingInputs(
                author_id=FINDER,
                author_role=MEMBER,
                feature_class=ENCLOSURE,
                evidence=(item(EvidenceKind.AERIAL, id=7), item(EvidenceKind.PHOTO, id=7)),
            )
        )
