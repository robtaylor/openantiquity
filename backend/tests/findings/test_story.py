"""Three accounts take a finding from spotted to seen to corroborated (WS4 exit criterion).

Each change notifies the right people, and reputation is paid once however
often the finding is reassessed afterwards.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Notification, ReputationEvent, User
from fieldclub.services import findings
from fieldclub.vocab import EvidenceKind, FeatureClass, Visible
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import MakeUser


def _notified(db: Session, kind: str) -> dict[int, list[dict]]:
    rows = db.execute(
        select(Notification.user_id, Notification.data)
        .where(Notification.kind == kind)
        .order_by(Notification.id)
    ).all()
    found: dict[int, list[dict]] = {}
    for user_id, data in rows:
        assert data is not None, "tier changes always say from and to"
        found.setdefault(user_id, []).append(data)
    return found


def _points(db: Session) -> list[tuple[int, str, float]]:
    return sorted(
        (row.user_id, row.reason, row.delta)
        for row in db.execute(select(ReputationEvent.user_id, ReputationEvent.reason, ReputationEvent.delta))
    )


def test_spotted_to_seen_to_corroborated(db: Session, make_user: MakeUser) -> None:
    ann, ben, cat = make_user(handle="Ann"), make_user(handle="Ben"), make_user(handle="Cat")

    finding = create(db, ann, feature_class=FeatureClass.ENCLOSURE)
    assert finding.tier == "spotted"

    # Ben can see it. One person isn't enough.
    first = answer(db, finding, ben, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    assert (first.reassessment.tier_before.value, first.reassessment.tier_after.value) == (
        "spotted",
        "spotted",
    )
    assert not first.reassessment.moved_up
    assert finding.answers_to_next == 1

    # Cat can too: Seen by others.
    second = answer(db, finding, cat, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    assert second.reassessment.moved_up
    assert finding.tier == "seen"
    seen = _notified(db, "tier_changed")
    # Ann (the finder) and Ben (who helped) are told. Cat made the change.
    assert seen == {ann.id: [{"from": "spotted", "to": "seen"}], ben.id: [{"from": "spotted", "to": "seen"}]}
    assert _points(db) == [(ann.id, "tier_seen", 2.0)]

    # Two independent kinds of desk evidence, from two people who aren't the finder.
    add_desk_evidence(db, finding, ben, EvidenceKind.AERIAL)
    assert finding.tier == "seen"
    _, result = add_desk_evidence(db, finding, cat, EvidenceKind.HISTORIC_MAP, title="OS 6-inch, 1888")
    assert result.moved_up
    assert finding.tier == "corroborated"
    assert finding.community_class == "enclosure"

    corroborated = {
        user: [data for data in items if data["to"] == "corroborated"]
        for user, items in _notified(db, "tier_changed").items()
    }
    assert corroborated == {
        ann.id: [{"from": "seen", "to": "corroborated"}],
        ben.id: [{"from": "seen", "to": "corroborated"}],
    }
    expected = sorted(
        [
            (ann.id, "tier_seen", 2.0),
            (ann.id, "tier_corroborated", 5.0),
            (ben.id, "observation_corroborated", 1.0),
            (cat.id, "observation_corroborated", 1.0),
        ]
    )
    assert _points(db) == expected
    db.expire_all()
    reputations = {user.handle: user.reputation for user in db.scalars(select(User))}
    assert reputations == {"Ann": 7.0, "Ben": 1.0, "Cat": 1.0}

    # Everything that happened is in the activity log, in order.
    assert db.scalars(select(Activity.kind).order_by(Activity.id)).all() == [
        "finding_created",
        "observation_added",
        "observation_added",
        "tier_changed",
        "evidence_added",
        "evidence_added",
        "tier_changed",
    ]

    # Reassessing again, or a change that moves nothing, pays nothing twice.
    findings.reassess(db, findings.lock(db, finding), None)
    answer(db, finding, ben, Visible.YES, feature_class=FeatureClass.ENCLOSURE, note="Still see it")
    db.commit()
    assert _points(db) == expected
    db.expire_all()
    assert {user.handle: user.reputation for user in db.scalars(select(User))} == reputations


def test_a_tier_that_falls_and_climbs_again_pays_once_and_notifies_each_time(
    db: Session, make_user: MakeUser
) -> None:
    ann, ben, cat, dan = (make_user() for _ in range(4))
    finding = create(db, ann)
    answer(db, finding, ben)
    answer(db, finding, cat)
    assert finding.tier == "seen"
    answer(db, finding, cat, Visible.NO)
    assert finding.tier == "spotted"
    answer(db, finding, dan)
    answer(db, finding, cat)
    assert finding.tier == "seen"
    awards = db.scalars(select(ReputationEvent.reason).where(ReputationEvent.user_id == ann.id)).all()
    assert awards == ["tier_seen"]
    moves = [data["to"] for data in _notified(db, "tier_changed")[ann.id]]
    assert moves == ["seen", "spotted", "seen"]
