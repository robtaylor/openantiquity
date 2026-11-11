"""A `tier_changed` event names the evidence that caused it, except a vote's and a second look's.

The timeline puts a step up the ladder down to the follow-up that made it.
It reads `details.evidence_id` on the step instead of matching the step to a
follow-up by actor and time. A step caused by a second look must say nothing
new (Decision 0008): no item, no actor, and nothing that orders or counts
the people who answered, in the feed, in notifications or on the event stream.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding
from fieldclub.services import activity, findings
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Outcome, Role, Stance, Visible
from tests.activity.support import API, follow, items
from tests.findings.support import answer, create
from tests.helpers import ClientAs, MakeUser

# What a step's details may carry besides the move itself.
MOVE = {"tier_from", "tier_to"}


@pytest.fixture
def payloads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every payload sent on the event bus, as `activity.record` sends it."""
    sent: list[dict[str, Any]] = []
    real = activity.event_payload

    def spy(*args: Any) -> str:
        payload = real(*args)
        sent.append(json.loads(payload))
        return payload

    monkeypatch.setattr(activity, "event_payload", spy)
    return sent


def _visit(db: Session, finding: Finding, user: Any) -> int:
    evidence, result = findings.add_evidence(
        db,
        findings.lock(db, finding),
        user,
        EvidenceFields(
            kind=EvidenceKind.FIELD_VISIT,
            stance=Stance.SUPPORTS,
            outcome=Outcome.SUPPORTS,
            occurred_on=date(2026, 10, 1),
            note="Walked the bank with the farmer's permission.",
        ),
    )
    db.commit()
    assert result.moved_up
    return evidence.id


def _steps(listed: list[dict[str, Any]], finding: Finding) -> list[dict[str, Any]]:
    return [
        item
        for item in listed
        if item["kind"] == "tier_changed" and item["finding"]["public_id"] == finding.public_id
    ]


def test_a_step_a_follow_up_made_names_it(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs, payloads: list[dict[str, Any]]
) -> None:
    finder, follower = make_user(handle="Finder"), make_user(handle="Follower")
    visitor = make_user(Role.TRUSTED, handle="Visitor")
    finding = create(db, finder, title="Bank and ditch")
    follow(db, finding, follower)
    visit = _visit(db, finding, visitor)
    db.refresh(finding)
    assert finding.tier == "ground_checked"

    for viewer in (client, client_as(follower)):
        (step,) = _steps(items(viewer.get(f"{API}/activity", params={"limit": 200})), finding)
        assert step["actor"]["handle"] == "Visitor"
        assert step["details"]["evidence_id"] == visit
        assert (step["details"]["tier_from"], step["details"]["tier_to"]) == ("spotted", "ground_checked")
        logged = [
            item
            for item in items(viewer.get(f"{API}/activity", params={"limit": 200}))
            if item["kind"] == "followup_logged"
        ]
        assert [item["details"]["evidence_id"] for item in logged] == [visit]
    notes = client_as(follower).get(f"{API}/notifications", params={"limit": 200}).json()["items"]
    (noted,) = [note for note in notes if note["kind"] == "tier_changed"]
    assert noted["details"]["evidence_id"] == visit
    # The stream carries ids and kinds only, so the client fetches the step through the feed.
    step_payloads = [payload for payload in payloads if payload["kind"] == "tier_changed"]
    assert step_payloads == [
        {
            "id": step_payloads[0]["id"],
            "kind": "tier_changed",
            "finding": finding.public_id,
            "investigation": None,
            "actor": "Visitor",
        }
    ]


def test_a_step_a_verification_made_names_the_item_verified(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    finder, adder = make_user(handle="Finder"), make_user(handle="Adder")
    expert = make_user(Role.EXPERT, handle="Archaeologist")
    finding = create(db, finder, title="Ring ditch")
    entry, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        adder,
        EvidenceFields(kind=EvidenceKind.HER_RECORD, stance=Stance.SUPPORTS, reference="MWI1234"),
    )
    db.commit()
    findings.verify(db, entry.id, expert)
    db.commit()
    db.refresh(finding)
    assert finding.tier == "confirmed"
    (step,) = _steps(items(client.get(f"{API}/activity", params={"limit": 200})), finding)
    assert (step["actor"]["handle"], step["details"]["evidence_id"]) == ("Archaeologist", entry.id)


def test_a_step_a_vote_made_names_no_item(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    """An item gives its votes only as counts, so a step a vote caused can't name the item.

    With the voter as actor, the item and the step's direction would say who
    voted on which item and how.
    """
    finder, follower = make_user(handle="Finder"), make_user(handle="Follower")
    voter = make_user(handle="Voter")
    finding = create(db, finder, title="Bank")
    follow(db, finding, follower)
    visit, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        finder,
        EvidenceFields(
            kind=EvidenceKind.FIELD_VISIT,
            stance=Stance.SUPPORTS,
            outcome=Outcome.SUPPORTS,
            occurred_on=date(2026, 10, 1),
            note="Walked it.",
        ),
    )
    db.commit()
    db.refresh(finding)
    assert finding.tier == "spotted", "the finder's own visit needs an endorsement to count"
    moves = []
    for value in (1, -1):
        response = client_as(voter).put(f"{API}/evidence/{visit.id}/vote", json={"value": value})
        assert response.status_code == 200, response.text
        db.refresh(finding)
        moves.append(finding.tier)
    assert moves == ["ground_checked", "spotted"], "both votes moved the finding"

    for viewer in (client, client_as(follower)):
        steps = _steps(items(viewer.get(f"{API}/activity", params={"limit": 200})), finding)
        assert len(steps) == 2
        assert all(step["details"].get("evidence_id") is None for step in steps), steps
    notes = client_as(follower).get(f"{API}/notifications", params={"limit": 200}).json()["items"]
    noted = [note for note in notes if note["kind"] == "tier_changed"]
    assert len(noted) == 2
    assert all(note["details"].get("evidence_id") is None for note in noted), noted
    rows = db.scalars(
        select(Activity)
        .where(Activity.kind == "tier_changed", Activity.finding_id == finding.id)
        .order_by(Activity.id)
    ).all()
    assert [row.data for row in rows] == [
        {"from": "spotted", "to": "ground_checked"},
        {"from": "ground_checked", "to": "spotted"},
    ]


def test_a_step_a_second_look_made_names_nothing(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs, payloads: list[dict[str, Any]]
) -> None:
    finder, follower = make_user(handle="Finder"), make_user(handle="Follower")
    finding = create(db, finder, title="Enclosure")
    follow(db, finding, follower)
    for handle in ("First", "Second"):
        answer(db, finding, make_user(handle=handle), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    db.refresh(finding)
    assert finding.tier == "seen"

    (row,) = db.scalars(
        select(Activity).where(Activity.kind == "tier_changed", Activity.finding_id == finding.id)
    ).all()
    # The row itself holds the move and nothing else, so no later reader can learn more.
    assert (row.actor_id, row.data) == (None, {"from": "spotted", "to": "seen"})

    def assert_names_nothing(step: dict[str, Any], where: str) -> None:
        assert step["actor"] is None, where
        named = {key for key, value in step["details"].items() if value is not None}
        assert named == MOVE, f"{where} says more than the move: {named - MOVE}"

    for viewer in (client, client_as(follower)):
        (step,) = _steps(items(viewer.get(f"{API}/activity", params={"limit": 200})), finding)
        assert_names_nothing(step, "the feed")
    notes = client_as(follower).get(f"{API}/notifications", params={"limit": 200}).json()["items"]
    (noted,) = [note for note in notes if note["kind"] == "tier_changed"]
    assert_names_nothing(noted, "a notification")
    step_payloads = [payload for payload in payloads if payload["kind"] == "tier_changed"]
    assert len(step_payloads) == 1
    assert step_payloads[0] == {
        "id": row.id,
        "kind": "tier_changed",
        "finding": finding.public_id,
        "investigation": None,
        "actor": None,
    }


def test_a_change_a_second_look_caused_cannot_name_evidence(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user(), title="Mound")
    with pytest.raises(AssertionError, match="names no evidence"):
        findings.reassess(db, findings.lock(db, finding), None, evidence_id=1)
