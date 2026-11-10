"""Reputation awards, worked out from an assessment before and after a change."""

from __future__ import annotations

import itertools

from fieldclub.services.confidence import Assessment
from fieldclub.services.reputation import (
    KNOWN_RECORD,
    OBSERVATION_CORROBORATED,
    OBSERVATION_RULED_OUT,
    Award,
    awards,
    evidence_reason,
    tier_reason,
)
from fieldclub.vocab import EvidenceKind, Explanation, FindingState, Outcome, Relation, Tier
from tests.confidence.builders import (
    ENCLOSURE,
    EXPERT,
    FINDER,
    TRUSTED,
    item,
    many,
    no,
    person,
    probable_answers,
    run,
    seen_answers,
    two_desk_strands,
    unsure,
    verified,
    vote,
    yes,
)


def reasons(found: list[Award]) -> list[tuple[int, str]]:
    return [(award.user_id, award.reason) for award in found]


def test_a_new_finding_earns_nothing() -> None:
    assert awards(None, run()) == []


def test_reaching_seen_earns_the_finder_two() -> None:
    assert awards(run([yes()]), run([yes(), yes()])) == [Award(FINDER, 2, tier_reason(Tier.SEEN))]


def test_staying_put_earns_nothing() -> None:
    answers = seen_answers()
    assert awards(run(answers), run(answers)) == []


def test_each_tier_pays_its_own_points() -> None:
    answers, desk = probable_answers(), two_desk_strands()
    visit = item(EvidenceKind.FIELD_VISIT, role=TRUSTED, outcome=Outcome.SUPPORTS)
    record = verified()
    steps = [
        run(answers[:1]),
        run(answers[:2]),
        run(answers[:2], desk),
        run(answers, desk),
        run(answers, [*desk, visit]),
        run(answers, [*desk, visit, record]),
    ]
    finder_points = [
        sum(a.points for a in awards(old, new) if a.user_id == FINDER)
        for old, new in itertools.pairwise(steps)
    ]
    assert finder_points == [2, 5, 10, 20, 30]


def test_a_jump_pays_for_every_tier_newly_met() -> None:
    found = awards(run(), run(probable_answers(), two_desk_strands()))
    tiers = [award.reason for award in found if award.user_id == FINDER]
    assert tiers == [tier_reason(Tier.CORROBORATED), tier_reason(Tier.PROBABLE), tier_reason(Tier.SEEN)]


def test_on_record_without_the_desk_tiers_pays_only_for_on_record() -> None:
    assert reasons(awards(run(), run(evidence=[verified()]))) == [(FINDER, tier_reason(Tier.CONFIRMED))]


def test_people_who_saw_it_earn_one_when_it_is_corroborated() -> None:
    helper, doubter = person(), person()
    answers = [yes(user=helper, cls=ENCLOSURE), yes(cls=ENCLOSURE), no(user=doubter)]
    answers += [yes(), yes()]  # keep the ratio above 0.67
    found = awards(run(answers, [item(EvidenceKind.AERIAL)]), run(answers, two_desk_strands()))
    matched = [award.user_id for award in found if award.reason == OBSERVATION_CORROBORATED]
    assert helper in matched
    assert doubter not in matched
    assert len(matched) == 4


def test_people_who_said_no_or_explained_it_earn_one_when_it_is_ruled_out() -> None:
    answers = [*many(2, no), no(explanation=Explanation.MODERN), yes(), unsure()]
    before, after = run(answers[:2]), run(answers)
    assert after.state is FindingState.RULED_OUT
    matched = [award.user_id for award in awards(before, after) if award.reason == OBSERVATION_RULED_OUT]
    assert matched == sorted(obs.user_id for obs in answers[:3])


def test_staying_ruled_out_pays_no_one_again() -> None:
    answers = many(4, no)
    assert awards(run(answers[:3]), run(answers)) == []


def test_ruled_out_findings_earn_their_finder_nothing() -> None:
    answers = [yes(), yes(), *many(6, no)]
    after = run(answers)
    assert after.state is FindingState.RULED_OUT
    assert all(award.user_id != FINDER for award in awards(None, after))


def test_evidence_endorsed_by_two_other_people_earns_its_contributor_one() -> None:
    contributor = person()
    once = item(EvidenceKind.AERIAL, by=contributor, votes=[vote()], id=501)
    twice = item(EvidenceKind.AERIAL, by=contributor, votes=[*once.votes, vote()], id=501)
    assert reasons(awards(run(evidence=[once]), run(evidence=[twice]))) == [
        (contributor, evidence_reason(501))
    ]
    assert awards(run(evidence=[twice]), run(evidence=[twice])) == []


def test_endorsements_by_the_contributor_or_the_finder_do_not_count() -> None:
    contributor = person()
    votes = [vote(user=contributor), vote(user=FINDER), vote()]
    assert awards(None, run(evidence=[item(EvidenceKind.AERIAL, by=contributor, votes=votes)])) == []


def test_evidence_that_does_not_stand_earns_nothing() -> None:
    votes = [vote(), vote(), vote(EXPERT, -1)]
    assert awards(None, run(evidence=[item(EvidenceKind.AERIAL, votes=votes)])) == []


def test_matching_a_known_record_earns_the_finder_one() -> None:
    link = item(EvidenceKind.RECORD_LINK, role=EXPERT, relation=Relation.SAME_AS)
    after = run(evidence=[link])
    assert reasons(awards(run(), after)) == [(FINDER, KNOWN_RECORD)]
    assert awards(after, after) == []


def test_a_withdrawn_finding_earns_nothing() -> None:
    assert awards(None, run(probable_answers(), two_desk_strands(), state=FindingState.WITHDRAWN)) == []


def test_coming_back_from_ruled_out_pays_for_the_tier_then() -> None:
    answers = [yes(), yes()]
    ruled_out = run([*answers, *many(3, unsure, explanation=Explanation.NATURAL)])
    assert (ruled_out.state, ruled_out.tier) == (FindingState.RULED_OUT, Tier.SEEN)
    assert all(award.reason != tier_reason(Tier.SEEN) for award in awards(None, ruled_out))
    back = run(answers)  # the three explanations were taken back
    assert (back.state, back.tier) == (FindingState.OPEN, Tier.SEEN)
    assert reasons(awards(ruled_out, back)) == [(FINDER, tier_reason(Tier.SEEN))]


def test_there_are_no_penalties() -> None:
    higher, lower = run(probable_answers(), two_desk_strands()), run()
    assert awards(higher, lower) == []


def test_awards_come_from_a_stored_assessment_too() -> None:
    before = Assessment.from_json(run([yes()]).to_json())
    assert reasons(awards(before, run([yes(), yes()]))) == [(FINDER, tier_reason(Tier.SEEN))]
