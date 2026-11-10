"""The score and the next steps: the numbers people see and act on."""

from __future__ import annotations

import pytest

from fieldclub.services.confidence import EvidenceInput, ObservationInput
from fieldclub.vocab import Check, EvidenceKind, Explanation, NextStepCode, Outcome, Strand, Tier
from tests.confidence.builders import (
    ENCLOSURE,
    FINDER,
    TRUSTED,
    codes,
    item,
    many,
    no,
    probable_answers,
    run,
    seen_answers,
    two_desk_strands,
    unsure,
    verified,
    yes,
)


def test_a_new_finding_needs_two_more_people() -> None:
    (step,) = run().next_steps
    assert (step.code, step.people, step.prompt) == (
        NextStepCode.NEED_OBSERVERS,
        2,
        "Two more people need to say they can see it.",
    )


def test_one_more_person() -> None:
    (step,) = run([yes()]).next_steps
    assert (step.people, step.prompt) == (1, "One more person needs to say they can see it.")


def test_the_observer_count_allows_for_people_who_cannot_see_it() -> None:
    (step,) = run([yes(), yes(), no(), no()]).next_steps
    assert step.people == 2  # 3 of 5 is below two thirds; 4 of 6 is not
    assert run([*many(3), no(), no()]).tier is Tier.SPOTTED
    assert run([*many(4), no(), no()]).tier is Tier.SEEN


def test_seen_needs_strands_and_class_agreement() -> None:
    assessment = run([yes(), yes()], feature_class=ENCLOSURE)
    strand, agreement = assessment.next_steps
    assert (strand.code, strand.strands_needed, strand.missing_strands) == (
        NextStepCode.NEED_STRAND,
        2,
        (Strand.LIDAR, Strand.AERIAL, Strand.HISTORIC_MAP, Strand.RECORDS, Strand.LITERATURE),
    )
    assert strand.prompt.startswith("It needs two more kinds of evidence")
    assert (agreement.code, agreement.people, agreement.prompt) == (
        NextStepCode.NEED_CLASS_AGREEMENT,
        1,
        "One more person needs to agree what it is.",
    )


def test_one_strand_short() -> None:
    (step,) = run(seen_answers(), [item(EvidenceKind.AERIAL)]).next_steps
    assert (step.strands_needed, step.prompt) == (
        1,
        "It needs one more kind of evidence, such as an aerial photo or an old map.",
    )
    assert Strand.AERIAL not in step.missing_strands


def test_a_strand_waiting_for_an_endorsement_is_named() -> None:
    mine = item(EvidenceKind.AERIAL, by=FINDER)
    (step, _) = run([yes(), yes()], [mine]).next_steps
    assert step.pending_evidence == (mine.id,)
    assert "endorses" in step.prompt


def test_corroborated_needs_checks_and_a_review() -> None:
    assessment = run(seen_answers(), two_desk_strands())
    assert codes(assessment) == ["need_check", "need_check", "need_check", "need_trusted_review"]
    assert [step.check for step in assessment.next_steps[:3]] == list(Check)
    assert assessment.next_steps[0].prompt == "Two more people need to say it isn't modern."
    review = assessment.next_steps[3]
    assert (review.people, review.weight_needed) == (1, 5.0)
    assert (
        review.prompt
        == "A trusted member or an archaeologist needs to say they can see it, or five more people."
    )


def test_a_check_against_an_explanation_needs_more_people() -> None:
    answers = [*seen_answers(), yes(TRUSTED), yes(checks=True), unsure(explanation=Explanation.ARTEFACT)]
    steps = {step.check: step for step in run(answers, two_desk_strands()).next_steps}
    assert steps[Check.NOT_MODERN].people == 1  # 1.0 asserting needs to reach 2.0
    assert steps[Check.NOT_ARTEFACT].people == 2  # and must also exceed twice the 1.0 against


def test_probable_needs_the_ground() -> None:
    (step,) = run(probable_answers(), two_desk_strands()).next_steps
    assert (step.code, step.prompt) == (
        NextStepCode.NEED_GROUND,
        "Someone needs to visit or survey it and report what they find.",
    )


def test_a_site_report_waiting_for_an_endorsement_is_named() -> None:
    visit = item(EvidenceKind.FIELD_VISIT, outcome=Outcome.SUPPORTS)
    (step,) = run(probable_answers(), [*two_desk_strands(), visit]).next_steps
    assert step.pending_evidence == (visit.id,)


def test_ground_checked_needs_an_official_record() -> None:
    visit = item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)
    (step,) = run(evidence=[visit]).next_steps
    assert (step.code, step.pending_evidence) == (NextStepCode.NEED_OFFICIAL, ())


def test_there_is_nothing_left_to_do_on_record() -> None:
    assessment = run(evidence=[verified()])
    assert (assessment.next_tier, assessment.next_steps, assessment.progress) == (None, (), 0.0)


@pytest.mark.parametrize(
    ("answers", "evidence", "score"),
    [
        ((), (), 10),
        ((yes(),), (), 16),  # 1 of the 3 seen requirements (the ratio) met
        ((yes(), yes()), (), 30),
        (tuple(seen_answers()), (item(EvidenceKind.AERIAL),), 43),  # 2 of 3
        (tuple(seen_answers()), tuple(two_desk_strands()), 50),
        (tuple(probable_answers()[:2]), tuple(two_desk_strands()), 65),  # 3 of 4
        (tuple(probable_answers()), tuple(two_desk_strands()), 70),
        ((), (item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS),), 85),
        ((), (verified(),), 100),
    ],
)
def test_the_score(
    answers: tuple[ObservationInput, ...], evidence: tuple[EvidenceInput, ...], score: int
) -> None:
    assert run(answers, evidence).score == score


def test_a_ruled_out_finding_scores_zero() -> None:
    assessment = run([*seen_answers(), *many(6, no)])
    assert (assessment.state.value, assessment.score) == ("ruled_out", 0)
