"""Every tier boundary in the contract, tested from both sides."""

from __future__ import annotations

import pytest

from fieldclub.services.confidence import Thresholds
from fieldclub.vocab import (
    Check,
    EvidenceKind,
    Explanation,
    FeatureClass,
    Outcome,
    Relation,
    Role,
    Stance,
    Tier,
)
from tests.confidence.builders import (
    ADMIN,
    ENCLOSURE,
    EXPERT,
    FINDER,
    MEMBER,
    MODERATOR,
    TRUSTED,
    item,
    many,
    no,
    probable_answers,
    run,
    seen_answers,
    two_desk_strands,
    unsure,
    verified,
    vote,
    yes,
)

FIELD_SYSTEM = FeatureClass.FIELD_SYSTEM


def test_a_new_finding_is_spotted() -> None:
    assessment = run()
    assert (assessment.tier, assessment.score, assessment.satisfied) == (Tier.SPOTTED, 10, {Tier.SPOTTED})


# --------------------------------------------------------------------------
# Seen by others
# --------------------------------------------------------------------------


def test_two_members_who_can_see_it_make_it_seen() -> None:
    assert run([yes(), yes()]).tier is Tier.SEEN


def test_one_member_is_not_enough() -> None:
    assert run([yes()]).tier is Tier.SPOTTED


def test_one_expert_has_the_weight_but_is_one_observer() -> None:
    assessment = run([yes(EXPERT)])
    assert (assessment.seen, assessment.observers, assessment.tier) == (3.0, 1, Tier.SPOTTED)


@pytest.mark.parametrize(("weight", "tier"), [(2.5, Tier.SEEN), (2.6, Tier.SPOTTED)])
def test_the_seen_weight_is_a_boundary_of_its_own(weight: float, tier: Tier) -> None:
    # Two observers always weigh 2.0 or more, so the weight only binds when it is raised.
    assert run([yes(), yes(TRUSTED)], thresholds=Thresholds(seen_weight=weight)).tier is tier


@pytest.mark.parametrize(("seen", "unseen", "tier"), [(67, 33, Tier.SEEN), (66, 34, Tier.SPOTTED)])
def test_the_seen_ratio_is_at_least_067(seen: int, unseen: int, tier: Tier) -> None:
    assessment = run([*many(seen), *many(unseen, no)])
    assert assessment.seen_ratio == pytest.approx(seen / 100)
    assert assessment.tier is tier


def test_two_in_three_meets_the_seen_ratio() -> None:
    assessment = run([yes(), yes(), no()])
    assert assessment.seen_ratio == pytest.approx(2 / 3)
    assert assessment.tier is Tier.SEEN
    assert run([*many(65), *many(35, no)]).tier is Tier.SPOTTED


def test_unsure_answers_count_for_neither_side() -> None:
    assessment = run([yes(), yes(), *many(5, unsure)])
    assert (assessment.seen, assessment.unseen, assessment.tier) == (2.0, 0.0, Tier.SEEN)


# --------------------------------------------------------------------------
# Corroborated
# --------------------------------------------------------------------------


def test_two_desk_strands_and_class_agreement_corroborate() -> None:
    assert run(seen_answers(), two_desk_strands()).tier is Tier.CORROBORATED


def test_one_desk_strand_is_not_enough() -> None:
    assert run(seen_answers(), [item(EvidenceKind.AERIAL)]).tier is Tier.SEEN


def test_two_items_in_one_strand_are_one_strand() -> None:
    assessment = run(seen_answers(), [item(EvidenceKind.AERIAL), item(EvidenceKind.AERIAL)])
    assert (len(assessment.desk_strands), assessment.tier) == (1, Tier.SEEN)


@pytest.mark.parametrize(
    "kind", [EvidenceKind.PHOTO, EvidenceKind.FIELD_VISIT, EvidenceKind.GEOPHYSICS, EvidenceKind.HER_RECORD]
)
def test_field_and_official_strands_are_not_desk_strands(kind: EvidenceKind) -> None:
    assert run(seen_answers(), [item(EvidenceKind.AERIAL), item(kind)]).tier is Tier.SEEN


@pytest.mark.parametrize(
    ("relation", "tier"),
    [
        (Relation.RELATED, Tier.CORROBORATED),
        (Relation.PART_OF, Tier.CORROBORATED),
        (Relation.SAME_AS, Tier.SEEN),
    ],
)
def test_a_record_link_is_a_strand_only_when_related_or_part_of(relation: Relation, tier: Tier) -> None:
    evidence = [item(EvidenceKind.AERIAL), item(EvidenceKind.RECORD_LINK, relation=relation)]
    assert run(seen_answers(), evidence).tier is tier


def test_class_agreement_of_exactly_two_thirds_is_enough() -> None:
    answers = [yes(cls=ENCLOSURE), yes(cls=FIELD_SYSTEM)]  # with the finder's enclosure, 2 of 3
    assessment = run(answers, two_desk_strands())
    assert assessment.class_agreement == pytest.approx(2 / 3)
    assert (assessment.community_class, assessment.tier) == (ENCLOSURE, Tier.CORROBORATED)


def test_class_agreement_just_below_two_thirds_is_not() -> None:
    answers = [yes(cls=ENCLOSURE), yes(TRUSTED, cls=FIELD_SYSTEM)]  # 2.0 of 3.5
    assessment = run(answers, two_desk_strands())
    assert assessment.class_agreement == pytest.approx(2 / 3.5)
    assert (assessment.community_class, assessment.tier) == (None, Tier.SEEN)


def test_class_agreement_needs_two_people() -> None:
    # The finder isn't sure and one expert says enclosure: full agreement from one person.
    answers = [yes(EXPERT, cls=ENCLOSURE), yes()]
    assessment = run(answers, two_desk_strands(), feature_class=FeatureClass.UNKNOWN)
    assert (assessment.community_class, assessment.class_people, assessment.tier) == (ENCLOSURE, 1, Tier.SEEN)
    answers.append(yes(cls=ENCLOSURE))
    assessment = run(answers, two_desk_strands(), feature_class=FeatureClass.UNKNOWN)
    assert (assessment.class_people, assessment.tier) == (2, Tier.CORROBORATED)


@pytest.mark.parametrize(("support", "tier"), [(2.0, Tier.CORROBORATED), (2.5, Tier.SEEN)])
def test_the_class_support_total_is_a_boundary_of_its_own(support: float, tier: Tier) -> None:
    # Two people always weigh 2.0 or more, so the total only binds when it is raised.
    assessment = run(
        [yes(cls=ENCLOSURE), yes()], two_desk_strands(), thresholds=Thresholds(class_support=support)
    )
    assert assessment.class_support == {ENCLOSURE: 2.0}
    assert assessment.tier is tier


def test_the_community_may_disagree_with_the_finder_and_still_agree() -> None:
    answers = [yes(cls=FIELD_SYSTEM), yes(cls=FIELD_SYSTEM), yes(cls=FIELD_SYSTEM)]
    assessment = run(answers, two_desk_strands())
    assert (assessment.community_class, assessment.class_agreement) == (FIELD_SYSTEM, 0.75)
    assert assessment.tier is Tier.CORROBORATED


def test_not_sure_is_ignored_in_class_support() -> None:
    answers = [yes(cls=FeatureClass.UNKNOWN), yes(cls=FeatureClass.UNKNOWN)]
    assessment = run(answers, two_desk_strands(), feature_class=FeatureClass.UNKNOWN)
    assert (assessment.class_support, assessment.class_agreement, assessment.tier) == ({}, 0.0, Tier.SEEN)


def test_a_tie_has_no_leader() -> None:
    assessment = run([yes(cls=FIELD_SYSTEM), yes()], two_desk_strands())
    assert (assessment.class_leader, assessment.class_agreement) == (None, 0.5)


# --------------------------------------------------------------------------
# Probable
# --------------------------------------------------------------------------


def test_cleared_checks_and_a_trusted_yes_make_it_probable() -> None:
    assert run(probable_answers(), two_desk_strands()).tier is Tier.PROBABLE


@pytest.mark.parametrize("role", [TRUSTED, EXPERT, MODERATOR, ADMIN])
def test_every_reviewer_role_counts_as_a_trusted_yes(role: Role) -> None:
    answers = [*probable_answers()[:2], yes(role)]
    assert run(answers, two_desk_strands()).tier is Tier.PROBABLE


def test_without_a_reviewer_it_stays_corroborated() -> None:
    answers = [*probable_answers()[:2], yes()]
    assert run(answers, two_desk_strands()).tier is Tier.CORROBORATED


@pytest.mark.parametrize(("members", "tier"), [(7, Tier.PROBABLE), (6, Tier.CORROBORATED)])
def test_seven_members_stand_in_for_a_reviewer(members: int, tier: Tier) -> None:
    answers = [*probable_answers()[:2], *many(members - 2)]
    assessment = run(answers, two_desk_strands())
    assert assessment.seen == members
    assert assessment.tier is tier


def test_a_reviewer_who_explains_it_away_is_not_a_yes() -> None:
    answers = [*probable_answers()[:2], yes(TRUSTED, explanation=Explanation.MODERN)]
    assessment = run(answers, two_desk_strands())
    assert (assessment.reviewers, assessment.tier) == ((), Tier.CORROBORATED)


@pytest.mark.parametrize(
    ("roles", "cleared"), [((MEMBER, MEMBER), True), ((TRUSTED,), False), ((MEMBER,), False)]
)
def test_a_check_needs_weight_of_two(roles: tuple[Role, ...], cleared: bool) -> None:
    answers = [*seen_answers(), yes(TRUSTED), *(yes(role, checks=True) for role in roles)]
    assessment = run(answers, two_desk_strands())
    assert all(status.cleared is cleared for status in assessment.checks)
    assert assessment.tier is (Tier.PROBABLE if cleared else Tier.CORROBORATED)


@pytest.mark.parametrize(("asserting", "cleared"), [(2, False), (3, True)])
def test_a_check_must_beat_twice_the_matching_explanation(asserting: int, cleared: bool) -> None:
    answers = [
        *seen_answers(),
        yes(TRUSTED),
        *many(asserting, yes, checks=True),
        no(explanation=Explanation.MODERN),
    ]
    status = run(answers, two_desk_strands()).check(Check.NOT_MODERN)
    assert (status.asserted, status.against, status.cleared) == (asserting, 1.0, cleared)
    assert run(answers, two_desk_strands()).check(Check.NOT_NATURAL).cleared


def test_probable_needs_corroborated_first() -> None:
    assert run(probable_answers(), [item(EvidenceKind.AERIAL)]).tier is Tier.SEEN


# --------------------------------------------------------------------------
# Checked on the ground
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [EvidenceKind.PHOTO, EvidenceKind.FIELD_VISIT, EvidenceKind.GEOPHYSICS])
def test_an_endorsed_field_item_that_supports_it_is_ground_checked(kind: EvidenceKind) -> None:
    evidence = [item(kind, outcome=Outcome.SUPPORTS, votes=[vote()])]
    assert run(evidence=evidence).tier is Tier.GROUND_CHECKED


def test_an_unendorsed_report_by_a_member_is_not() -> None:
    assert run(evidence=[item(EvidenceKind.FIELD_VISIT, outcome=Outcome.SUPPORTS)]).tier is Tier.SPOTTED


@pytest.mark.parametrize(("role", "tier"), [(TRUSTED, Tier.GROUND_CHECKED), (EXPERT, Tier.GROUND_CHECKED)])
def test_a_report_by_a_trusted_member_or_expert_needs_no_endorsement(role: Role, tier: Tier) -> None:
    evidence = [item(EvidenceKind.EXCAVATION, role=role, outcome=Outcome.SUPPORTS)]
    assert run(evidence=evidence).tier is tier


@pytest.mark.parametrize("outcome", [Outcome.INCONCLUSIVE, Outcome.CONTRADICTS, None])
def test_only_a_supporting_outcome_checks_it(outcome: Outcome | None) -> None:
    evidence = [item(EvidenceKind.FIELD_VISIT, role=EXPERT, outcome=outcome)]
    assert run(evidence=evidence).tier is Tier.SPOTTED


def test_an_endorsement_by_the_reporter_does_not_count() -> None:
    reporter = 5000
    evidence = [
        item(EvidenceKind.FIELD_VISIT, by=reporter, outcome=Outcome.SUPPORTS, votes=[vote(user=reporter)])
    ]
    assert run(evidence=evidence).tier is Tier.SPOTTED


def test_a_report_voted_below_zero_does_not_stand() -> None:
    evidence = [
        item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS, votes=[vote(value=-1)])
    ]
    assert run(evidence=evidence).tier is Tier.SPOTTED
    evidence = [
        item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS, votes=[vote(value=-1), vote()])
    ]
    assert run(evidence=evidence).tier is Tier.GROUND_CHECKED, "a net total of zero still stands"


def test_ground_checked_does_not_need_the_desk_tiers() -> None:
    assessment = run(evidence=[item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)])
    assert (assessment.tier, assessment.satisfied) == (
        Tier.GROUND_CHECKED,
        {Tier.SPOTTED, Tier.GROUND_CHECKED},
    )


# --------------------------------------------------------------------------
# On record
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", [EvidenceKind.HER_RECORD, EvidenceKind.DESIGNATION, EvidenceKind.PUBLICATION]
)
@pytest.mark.parametrize("verifier", [EXPERT, MODERATOR, ADMIN])
def test_a_verified_official_item_puts_it_on_record(kind: EvidenceKind, verifier: Role) -> None:
    assessment = run(evidence=[verified(kind, verifier)])
    assert (assessment.tier, assessment.score) == (Tier.CONFIRMED, 100)


@pytest.mark.parametrize("verifier", [MEMBER, TRUSTED])
def test_a_trusted_member_cannot_verify(verifier: Role) -> None:
    assert run(evidence=[verified(verifier=verifier)]).tier is Tier.SPOTTED


def test_an_unverified_official_item_does_not() -> None:
    assert run(evidence=[item(EvidenceKind.DESIGNATION, role=EXPERT)]).tier is Tier.SPOTTED


def test_a_verified_item_voted_down_does_not_stand() -> None:
    assert run(evidence=[verified(votes=[vote(TRUSTED, -1)])]).tier is Tier.SPOTTED


def test_the_finder_cannot_verify_their_own_finding() -> None:
    evidence = [item(EvidenceKind.HER_RECORD, verified_by=FINDER, verifier_role=EXPERT)]
    assert run(evidence=evidence, finder_role=EXPERT).tier is Tier.SPOTTED


def test_an_official_item_that_contradicts_it_does_not_put_it_on_record() -> None:
    assert run(evidence=[verified(stance=Stance.CONTRADICTS)]).tier is Tier.SPOTTED


def test_on_record_outranks_ground_checked() -> None:
    evidence = [verified(), item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)]
    assessment = run(probable_answers(), [*two_desk_strands(), *evidence])
    assert assessment.tier is Tier.CONFIRMED
    assert assessment.satisfied == set(Tier)
