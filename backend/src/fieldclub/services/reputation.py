"""Reputation: itemised points for findings that climb and for help that turned out right.

The rules are the "Reputation" paragraph of `docs/ARCHITECTURE.md`. Points
are written to `reputation_events`, one row per award, so a person can see
where each point came from. There are no penalties.

Interface
=========

    from fieldclub.services.confidence import assess, load_assessment
    from fieldclub.services.reputation import awards, record_awards

    old = load_assessment(finding.assessment)    # before the change, or None
    new = assess(inputs)                          # after it
    recorded = record_awards(db, finding.id, awards(old, new))

`awards(old, new)` is pure. It reads who did what from the two assessments:
the finder, the answers, the evidence and its endorsers. `record_awards`
writes the awards, adds them to each person's `users.reputation`, and
reports the members who have just reached fifty points. It flushes and
never commits.

Fifty points makes a member eligible for trusted. It doesn't promote them:
a moderator does that. Trusted users see the exact position of restricted
findings (Decision 0005), and points can be farmed. Three colluding
accounts can take a finding to Checked on the ground (two answers, two desk
items, one site report and one endorsement), which pays its finder 27
points, so two such findings would cross fifty. Automatic promotion would
hand restricted positions to anyone willing to run three accounts.

Each award has a stable `reason`, and `reputation_events` is unique on
(user, finding, reason). `record_awards` skips an award already written, so
a finding that drops a tier and climbs back pays nothing twice, and calling
it again with the same awards is harmless. That also makes `old = None` safe
when the stored assessment is empty or from an older version.

Decisions where the contract is silent
======================================

1. A finding earns its finder the points for each tier whose rule it newly
   meets (`Assessment.satisfied`), not only for the tier it lands on. A
   finding confirmed on record that later gets two observers earns the
   points for Seen too.
2. While a finding is ruled out or withdrawn it earns no tier points and no
   known-record point. It earns them if it comes back.
3. An observation "matches the outcome" of Corroborated when it counts as
   seeing it, and of ruled out when it says "no" or gives an explanation.
   Only the answers given when the finding reaches that outcome earn.
4. "Endorsed by two other people" counts the endorsers the engine counts:
   people other than the contributor and the finder, on an item that stands.
5. Nothing is awarded on a withdrawn finding.
6. Only an active member becomes eligible. Experts, moderators, admins and
   trusted users are never reported, and nobody's role changes here.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub.models import ReputationEvent, User
from fieldclub.services.confidence import Assessment, EvidenceStatus
from fieldclub.vocab import FindingState, Role, Tier, Visible

logger = logging.getLogger(__name__)

TIER_POINTS: dict[Tier, float] = {
    Tier.SEEN: 2,
    Tier.CORROBORATED: 5,
    Tier.PROBABLE: 10,
    Tier.GROUND_CHECKED: 20,
    Tier.CONFIRMED: 30,
}
MATCHING_OBSERVATION_POINTS = 1.0
ENDORSED_EVIDENCE_POINTS = 1.0
ENDORSERS_NEEDED = 2
KNOWN_RECORD_POINTS = 1.0
TRUSTED_AT = 50.0

KNOWN_RECORD = "known_record"
OBSERVATION_CORROBORATED = "observation_corroborated"
OBSERVATION_RULED_OUT = "observation_ruled_out"

_NOT_EARNING = frozenset({FindingState.RULED_OUT, FindingState.WITHDRAWN})


def tier_reason(tier: Tier) -> str:
    return f"tier_{tier.value}"


def evidence_reason(evidence_id: int) -> str:
    return f"evidence_endorsed_{evidence_id}"


@dataclass(frozen=True)
class Award:
    user_id: int
    points: float
    reason: str


@dataclass(frozen=True)
class RecordedAwards:
    awards: tuple[Award, ...]  # the ones written now, without those already held
    eligible: tuple[int, ...]  # members who have just reached `TRUSTED_AT`, for a moderator to promote


def _earned_tiers(assessment: Assessment | None) -> frozenset[Tier]:
    if assessment is None or assessment.state in _NOT_EARNING:
        return frozenset({Tier.SPOTTED})
    return assessment.satisfied


def _earns_known(assessment: Assessment | None) -> bool:
    return assessment is not None and assessment.known and assessment.state not in _NOT_EARNING


def _endorsed(status: EvidenceStatus | None) -> bool:
    return status is not None and status.standing and len(status.endorsers) >= ENDORSERS_NEEDED


def awards(old: Assessment | None, new: Assessment) -> list[Award]:
    """The points a change to a finding earns, from its assessment before and after."""
    if old is not None:
        assert old.finder_id == new.finder_id, "both assessments must be of the same finding"
    if new.state is FindingState.WITHDRAWN:
        return []
    found: list[Award] = []
    reached = _earned_tiers(new) - _earned_tiers(old)
    found += [
        Award(new.finder_id, TIER_POINTS[tier], tier_reason(tier)) for tier in reached if tier in TIER_POINTS
    ]

    if Tier.CORROBORATED in reached:
        found += [
            Award(obs.user_id, MATCHING_OBSERVATION_POINTS, OBSERVATION_CORROBORATED)
            for obs in new.observations
            if obs.counts_as_seen
        ]
    if new.state is FindingState.RULED_OUT and (old is None or old.state is not FindingState.RULED_OUT):
        found += [
            Award(obs.user_id, MATCHING_OBSERVATION_POINTS, OBSERVATION_RULED_OUT)
            for obs in new.observations
            if obs.visible is Visible.NO or obs.explanation is not None
        ]

    before = {status.id: status for status in old.evidence} if old is not None else {}
    found += [
        Award(status.user_id, ENDORSED_EVIDENCE_POINTS, evidence_reason(status.id))
        for status in new.evidence
        if _endorsed(status) and not _endorsed(before.get(status.id))
    ]

    if _earns_known(new) and not _earns_known(old):
        found.append(Award(new.finder_id, KNOWN_RECORD_POINTS, KNOWN_RECORD))
    return sorted(found, key=lambda award: (award.user_id, award.reason))


def record_awards(db: Session, finding_id: int, found: Iterable[Award]) -> RecordedAwards:
    """Write awards not already held, add them to reputations, and report members who reach fifty.

    Flushes and never commits. Rows are written in user order, so two
    transactions awarding the same people lock them in the same order.
    """
    rows = [
        {"user_id": award.user_id, "delta": award.points, "reason": award.reason, "finding_id": finding_id}
        for award in sorted(found, key=lambda award: (award.user_id, award.reason))
    ]
    assert len({(row["user_id"], row["reason"]) for row in rows}) == len(rows), "an award is listed twice"
    assert all(row["delta"] > 0 for row in rows), "there are no penalties"
    if not rows:
        return RecordedAwards((), ())

    written = db.execute(
        insert(ReputationEvent)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["user_id", "finding_id", "reason"])
        .returning(ReputationEvent.user_id, ReputationEvent.delta, ReputationEvent.reason)
    ).all()
    totals: dict[int, float] = defaultdict(float)
    for user_id, delta, _ in written:
        totals[user_id] += delta
    for user_id, total in sorted(totals.items()):
        db.execute(update(User).where(User.id == user_id).values(reputation=User.reputation + total))

    eligible: tuple[int, ...] = ()
    if totals:
        reached = db.execute(
            select(User.id, User.reputation).where(
                User.id.in_(totals),
                User.role == Role.MEMBER.value,
                User.reputation >= TRUSTED_AT,
                User.banned_at.is_(None),
                User.deleted_at.is_(None),
            )
        ).all()
        eligible = tuple(sorted(uid for uid, points in reached if points - totals[uid] < TRUSTED_AT))
    for user_id in eligible:
        logger.info("user %s reached %s points and can be made trusted by a moderator", user_id, TRUSTED_AT)
    db.flush()
    return RecordedAwards(
        awards=tuple(Award(user_id, delta, reason) for user_id, delta, reason in written),
        eligible=eligible,
    )
