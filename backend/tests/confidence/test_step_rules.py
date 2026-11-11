"""The rules `/meta` serves for each next step say what the engine counts.

`STEP_RULES` is how the web client tells a member whether their evidence
meets a step, so a rule that says yes where the engine says no misleads
them. Every combination of kind, stance, outcome, relation, contributor,
votes and verification goes through `_evidence_status`, and each rule's
`counts` must agree with how `assess` uses what comes out.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

from fieldclub.services.confidence import (
    DESK_STRANDS,
    FIELD_STRANDS,
    STEP_RULES,
    VERIFIER_ROLES,
    EvidenceFacts,
    EvidenceInput,
    EvidenceStatus,
    MetBy,
    Thresholds,
    VoteInput,
    _evidence_status,
)
from fieldclub.vocab import (
    TRUSTED_ROLES,
    EvidenceKind,
    NextStepCode,
    Outcome,
    Relation,
    Role,
    Stance,
    Strand,
    role_weight,
)

FINDER, CONTRIBUTOR, VOTER, OTHER_VOTER, VERIFIER = 1, 2, 3, 4, 5
T = Thresholds()

# How `assess` reads each status for the step it meets.
ENGINE: dict[NextStepCode, Callable[[EvidenceStatus], bool]] = {
    NextStepCode.NEED_STRAND: lambda e: (
        e.strand in DESK_STRANDS and e.standing and e.independent and e.direction is Stance.SUPPORTS
    ),
    NextStepCode.NEED_GROUND: lambda e: e.checks_ground,
    NextStepCode.NEED_OFFICIAL: lambda e: e.puts_on_record,
}

# Votes, by who casts them: the finder's and the contributor's own don't count.
VOTES: tuple[tuple[VoteInput, ...], ...] = (
    (),
    (VoteInput(VOTER, Role.MEMBER, 1),),
    (VoteInput(VOTER, Role.EXPERT, 1),),
    (VoteInput(FINDER, Role.MEMBER, 1),),
    (VoteInput(CONTRIBUTOR, Role.MEMBER, 1),),
    (VoteInput(VOTER, Role.MEMBER, -1),),
    (VoteInput(VOTER, Role.MEMBER, 1), VoteInput(OTHER_VOTER, Role.MEMBER, -1)),
    (VoteInput(VOTER, Role.MEMBER, 1), VoteInput(OTHER_VOTER, Role.EXPERT, -1)),
)
# Who verified it, if anyone, and with what role.
VERIFICATIONS: tuple[tuple[int | None, Role | None], ...] = (
    (None, None),
    (VERIFIER, Role.MEMBER),
    (VERIFIER, Role.TRUSTED),
    (VERIFIER, Role.EXPERT),
    (VERIFIER, Role.MODERATOR),
    (FINDER, Role.EXPERT),
    (CONTRIBUTOR, Role.EXPERT),
)


def _facts(item: EvidenceInput) -> EvidenceFacts:
    """The facts about an item, worked out from its inputs and the documented definitions."""
    counted = [vote for vote in item.votes if vote.user_id not in (FINDER, item.user_id)]
    up = sum(role_weight(vote.role) for vote in counted if vote.value > 0)
    total = sum(role_weight(vote.role) * vote.value for vote in counted)
    return EvidenceFacts(
        kind=item.kind,
        relation=item.relation,
        stance=item.stance,
        outcome=item.outcome,
        by_finder=item.user_id == FINDER,
        trusted=item.role in TRUSTED_ROLES,
        endorsed=up >= T.endorsement_weight,
        standing=total >= 0,
        verified=(
            item.verified_by is not None
            and item.verified_by not in (FINDER, item.user_id)
            and item.verifier_role in VERIFIER_ROLES
        ),
    )


def _items() -> list[EvidenceInput]:
    items = []
    for kind, stance, outcome, by, role, votes, (verifier, verifier_role) in itertools.product(
        EvidenceKind,
        Stance,
        (None, *Outcome),
        (FINDER, CONTRIBUTOR),
        Role,
        VOTES,
        VERIFICATIONS,
    ):
        relations = (None, *Relation) if kind is EvidenceKind.RECORD_LINK else (None,)
        for relation in relations:
            items.append(
                EvidenceInput(
                    id=len(items) + 1,
                    user_id=by,
                    role=role,
                    kind=kind,
                    stance=stance,
                    outcome=outcome,
                    relation=relation,
                    verified_by=verifier,
                    verifier_role=verifier_role,
                    votes=votes,
                )
            )
    return items


def test_every_rule_met_by_evidence_is_read_by_the_engine() -> None:
    assert {rule.code for rule in STEP_RULES if rule.met_by is MetBy.EVIDENCE} == set(ENGINE)
    assert Strand.OFFICIAL not in DESK_STRANDS | FIELD_STRANDS


def test_each_rule_counts_exactly_what_the_engine_counts() -> None:
    rules = [rule for rule in STEP_RULES if rule.met_by is MetBy.EVIDENCE]
    mismatches: list[str] = []
    counted = dict.fromkeys(ENGINE, 0)
    items = _items()
    for item in items:
        status = _evidence_status(item, FINDER, T)
        facts = _facts(item)
        for rule in rules:
            engine = ENGINE[rule.code](status)
            counted[rule.code] += engine
            if rule.counts(facts) != engine:
                mismatches.append(f"{rule.code}: rule {rule.counts(facts)}, engine {engine}: {item}")
    assert not mismatches, f"{len(mismatches)} of {len(items)}, first: {mismatches[0]}"
    # Every rule is met by something, and refuses something, or the test proves little.
    assert all(0 < n < len(items) for n in counted.values()), counted
