"""Cases where the contract is silent or two rules pull apart, settled as the module docstring says."""

from __future__ import annotations

from fieldclub.services.confidence import Credit, CreditKind
from fieldclub.vocab import (
    EvidenceKind,
    Explanation,
    FindingState,
    NextStepCode,
    Outcome,
    Relation,
    Stance,
    StateReason,
    Strand,
    Tier,
)
from tests.confidence.builders import (
    ENCLOSURE,
    EXPERT,
    FINDER,
    TRUSTED,
    codes,
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


def test_the_finder_observing_their_own_finding_changes_nothing() -> None:
    answers, evidence = [yes(cls=ENCLOSURE)], two_desk_strands()
    own = yes(EXPERT, user=FINDER, cls=ENCLOSURE, checks=True)
    assert run([*answers, own], evidence) == run(answers, evidence)
    assert run([*answers, own], evidence, finder_role=EXPERT).tier is Tier.SPOTTED


def test_the_finder_saying_it_is_modern_does_not_rule_it_out() -> None:
    own = no(EXPERT, user=FINDER, explanation=Explanation.MODERN)
    assert run([own]).state is FindingState.OPEN


def test_one_person_can_give_both_an_observation_and_evidence() -> None:
    helper = person()
    answers = [yes(user=helper, cls=ENCLOSURE), yes(cls=ENCLOSURE)]
    evidence = [item(EvidenceKind.AERIAL, by=helper), item(EvidenceKind.HISTORIC_MAP, by=helper)]
    assessment = run(answers, evidence)
    assert assessment.tier is Tier.CORROBORATED
    assert {credit.kind.value for credit in assessment.credits if credit.user_id == helper} == {
        "saw_it",
        "added_evidence",
    }


def test_evidence_the_finder_added_counts_once_one_other_person_endorses_it() -> None:
    mine = item(EvidenceKind.AERIAL, by=FINDER)
    endorsed = item(EvidenceKind.HISTORIC_MAP, by=FINDER, votes=[vote()])
    assessment = run(seen_answers(), [mine, endorsed])
    assert assessment.desk_strands == {Strand.HISTORIC_MAP}
    status = {e.id: e for e in assessment.evidence}
    assert (status[mine.id].independent, status[endorsed.id].independent) == (False, True)


def test_the_finder_endorsing_their_own_evidence_does_not_count() -> None:
    evidence = [item(kind, by=FINDER, votes=[vote(EXPERT, user=FINDER)]) for kind in EvidenceKind]
    assessment = run(seen_answers(), evidence)
    assert assessment.supporting_strands == frozenset()
    assert assessment.tier is Tier.SEEN


def test_a_vote_by_the_evidence_contributor_is_ignored() -> None:
    contributor = person()
    against = item(
        EvidenceKind.AERIAL, by=contributor, stance=Stance.CONTRADICTS, votes=[vote(user=contributor)]
    )
    status = run(evidence=[against]).evidence[0]
    assert (status.vote_total, status.endorsers) == (0.0, ())
    sinking = item(EvidenceKind.AERIAL, by=contributor, votes=[vote(EXPERT, -1, user=contributor)])
    assert run(evidence=[sinking]).evidence[0].standing


def test_the_finder_cannot_vote_down_evidence_against_their_finding() -> None:
    against = item(EvidenceKind.AERIAL, stance=Stance.CONTRADICTS, votes=[vote(EXPERT, -1, user=FINDER)])
    assessment = run(evidence=[against], finder_role=EXPERT)
    assert assessment.evidence[0].standing
    assert assessment.state is FindingState.DISPUTED


def test_a_known_finding_that_is_later_disputed_shows_as_disputed() -> None:
    link = item(EvidenceKind.RECORD_LINK, role=EXPERT, relation=Relation.SAME_AS)
    assert run(seen_answers(), [link]).state is FindingState.KNOWN
    assessment = run([*seen_answers(), no(), no()], [link])
    assert (assessment.state, assessment.known) == (FindingState.DISPUTED, True)


def test_ruled_out_by_weight_then_supported_on_the_ground_is_disputed() -> None:
    answers = many(3, no, explanation=Explanation.MODERN)
    assert run(answers).state is FindingState.RULED_OUT
    visit = item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)
    assessment = run(answers, [visit])
    assert (assessment.tier, assessment.state, assessment.state_reason) == (
        Tier.GROUND_CHECKED,
        FindingState.DISPUTED,
        StateReason.MODERN,
    )
    assert codes(assessment) == ["need_official"]


def test_an_unverified_official_item_waits_for_verification() -> None:
    record = item(EvidenceKind.HER_RECORD)
    visit = item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)
    assessment = run(evidence=[record, visit])
    assert assessment.tier is Tier.GROUND_CHECKED
    (step,) = assessment.next_steps
    assert (step.code, step.pending_evidence) == (NextStepCode.NEED_OFFICIAL, (record.id,))
    assert "verify" in step.prompt
    assert assessment.supporting_strands == {Strand.OFFICIAL, Strand.GROUND}, "it still supports, as a strand"


def test_an_unverified_official_item_is_not_offered_before_its_tier_is_next() -> None:
    assessment = run(evidence=[item(EvidenceKind.HER_RECORD)])
    assert codes(assessment) == ["need_observers"]


def test_a_withdrawn_finding_returns_to_its_computed_state_when_reopened() -> None:
    answers = [*seen_answers(), no(), no()]
    assert run(answers, state=FindingState.WITHDRAWN).state is FindingState.WITHDRAWN
    assert run(answers, state=FindingState.OPEN).state is FindingState.DISPUTED


def test_a_yes_that_explains_it_away_is_neither_seen_nor_unseen() -> None:
    assessment = run([yes(), yes(explanation=Explanation.NATURAL), no()])
    assert (assessment.seen, assessment.unseen, assessment.observers) == (1.0, 1.0, 1)
    assert assessment.explanations == {Explanation.NATURAL: 1.0}


def test_a_field_item_points_the_way_its_outcome_says() -> None:
    visit = item(EvidenceKind.FIELD_VISIT, stance=Stance.SUPPORTS, outcome=Outcome.CONTRADICTS)
    assert run(evidence=[visit]).evidence[0].direction is Stance.CONTRADICTS
    visit = item(EvidenceKind.GEOPHYSICS, stance=Stance.SUPPORTS, outcome=Outcome.INCONCLUSIVE)
    assert run(evidence=[visit]).evidence[0].direction is Stance.NEUTRAL
    photo = item(EvidenceKind.PHOTO, stance=Stance.CONTRADICTS)
    assert run(evidence=[photo]).evidence[0].direction is Stance.CONTRADICTS


def test_a_trusted_finder_cannot_check_their_own_finding_on_the_ground() -> None:
    visit = item(EvidenceKind.FIELD_VISIT, by=FINDER, role=TRUSTED, outcome=Outcome.SUPPORTS)
    assessment = run(evidence=[visit], finder_role=TRUSTED)
    assert assessment.tier is Tier.SPOTTED
    endorsed = item(
        EvidenceKind.FIELD_VISIT, by=FINDER, role=TRUSTED, outcome=Outcome.SUPPORTS, votes=[vote()]
    )
    assert run(evidence=[endorsed], finder_role=TRUSTED).tier is Tier.GROUND_CHECKED


def test_satisfied_tiers_can_skip_rungs() -> None:
    record = item(EvidenceKind.DESIGNATION, verified_by=person(), verifier_role=EXPERT)
    assessment = run(probable_answers(), [*two_desk_strands(), record])
    assert assessment.satisfied == {Tier.SPOTTED, Tier.SEEN, Tier.CORROBORATED, Tier.PROBABLE, Tier.CONFIRMED}


def test_credits_name_who_did_what() -> None:
    saw, doubted, explained, endorser, verifier = (person() for _ in range(5))
    record = item(
        EvidenceKind.HER_RECORD,
        by=saw,
        votes=[vote(user=endorser), vote(user=FINDER), vote(user=saw)],
        verified_by=verifier,
        verifier_role=EXPERT,
    )
    unverified = item(EvidenceKind.DESIGNATION, verified_by=person(), verifier_role=TRUSTED)
    answers = [
        yes(user=saw),
        no(user=doubted),
        yes(user=explained, explanation=Explanation.MODERN),
        yes(user=FINDER),
    ]
    credits = set(run(answers, [record, unverified]).credits)
    assert {
        Credit(FINDER, CreditKind.SPOTTED),
        Credit(saw, CreditKind.SAW_IT),
        Credit(saw, CreditKind.ADDED_EVIDENCE, record.id),
        Credit(doubted, CreditKind.COULD_NOT_SEE),
        Credit(explained, CreditKind.EXPLAINED),
        Credit(endorser, CreditKind.ENDORSED, record.id),
        Credit(verifier, CreditKind.VERIFIED, record.id),
        Credit(unverified.user_id, CreditKind.ADDED_EVIDENCE, unverified.id),
    } == credits, "no credit for the finder's own answer or votes, or for a verification that doesn't count"
