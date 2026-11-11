"""An answer stays independent after the reveal (Decision 0008).

Answering shows the finding in full and everyone else's answers, so the
answer can't change afterwards, can't be taken back and given again
differently, and nothing in activity or notifications says how anyone
answered.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Notification, User
from fieldclub.services import findings, review, sensitivity
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Outcome, Role, Visible
from tests.findings.support import API, add_desk_evidence, answer, create
from tests.helpers import ClientAs, MakeUser, error_code


def _tallies(client_as: ClientAs, finder: User, public_id: str) -> dict:
    return client_as(finder).get(f"{API}/findings/{public_id}").json()["assessment"]["tallies"]


def test_an_answer_cannot_change_after_the_reveal(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, reviewer = make_user(), make_user()
    finding = create(db, finder, feature_class=FeatureClass.ENCLOSURE)
    for _ in range(2):
        answer(db, finding, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    path = f"{API}/findings/{finding.public_id}/observation"
    client = client_as(reviewer)

    peek = client.put(path, json={"visible": "unsure"})
    assert peek.status_code == 200
    assert peek.json()["comparison"]["others"]["yes"] == 2
    before = _tallies(client_as, finder, finding.public_id)

    changed = client.put(path, json={"visible": "yes", "feature_class": "enclosure"})
    assert changed.status_code == 409
    assert error_code(changed) == "answer_final"
    assert _tallies(client_as, finder, finding.public_id) == before
    assert before["seen"] == 2.0

    # The note alone can change.
    noted = client.put(path, json={"visible": "unsure", "note": "Hard to tell in this light"})
    assert noted.status_code == 200
    assert noted.json()["observation"]["note"] == "Hard to tell in this light"
    assert _tallies(client_as, finder, finding.public_id) == before


def test_the_comparison_counts_only_other_people_s_standing_answers(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    answer(db, finding, make_user(), Visible.YES)
    answer(db, finding, make_user(), Visible.NO)
    taken_back = make_user()
    answer(db, finding, taken_back, Visible.YES)
    review.delete_observation(db, finding, taken_back)
    db.commit()

    result = answer(db, finding, make_user(), Visible.UNSURE)
    assert result.comparison is not None
    assert result.comparison.others == {Visible.YES: 1, Visible.NO: 1, Visible.UNSURE: 0}


def test_taking_an_answer_back_cannot_reset_it(db: Session, client_as: ClientAs, make_user: MakeUser) -> None:
    finder, reviewer = make_user(), make_user()
    finding = create(db, finder)
    for _ in range(2):
        answer(db, finding, make_user(), Visible.YES)
    path = f"{API}/findings/{finding.public_id}/observation"
    client = client_as(reviewer)

    assert client.put(path, json={"visible": "no"}).status_code == 200
    assert _tallies(client_as, finder, finding.public_id)["unseen"] == 1.0
    assert client.delete(path).status_code == 204
    after = _tallies(client_as, finder, finding.public_id)
    assert (after["unseen"], after["observation_count"]) == (0.0, 2)
    assert error_code(client.delete(path)) == "observation_not_found"

    again = client.put(path, json={"visible": "yes"})
    assert error_code(again) == "answer_final"
    assert _tallies(client_as, finder, finding.public_id) == after
    listed = client_as(finder).get(f"{API}/findings/{finding.public_id}/observations").json()["items"]
    assert [item["visible"] for item in listed] == ["yes", "yes"]
    # Still out of the queue: they've seen the answers.
    assert client.get(f"{API}/review/next").json()["items"] == []

    # The same answer given again restores it.
    restored = client.put(path, json={"visible": "no"})
    assert restored.status_code == 200
    assert restored.json()["observation"]["withdrawn"] is False
    assert _tallies(client_as, finder, finding.public_id)["unseen"] == 1.0


def test_an_answer_cannot_say_a_check_and_its_explanation_together(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = create(db, make_user())
    path = f"{API}/findings/{finding.public_id}/observation"
    client = client_as(make_user())
    refused = client.put(path, json={"visible": "no", "explanation": "modern", "not_modern": True})
    assert refused.status_code == 422
    assert error_code(refused) == "validation_error"
    assert (
        client.put(path, json={"visible": "no", "explanation": "modern", "not_natural": True}).status_code
        == 200
    )


def _notifications(db: Session, user: User) -> list[tuple[str, int | None]]:
    rows = db.execute(
        select(Notification.kind, Notification.actor_id).where(Notification.user_id == user.id)
    ).all()
    return sorted((kind, actor) for kind, actor in rows)


def test_activity_and_notifications_do_not_say_who_answered_or_how(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, commenter = make_user(), make_user()
    seen_one = create(db, finder)
    ruled_out = create(db, finder)
    for finding in (seen_one, ruled_out):
        assert (
            client_as(commenter)
            .post(f"{API}/findings/{finding.public_id}/comments", json={"body": "What is it?"})
            .status_code
            == 201
        )
    for _ in range(2):
        answer(db, seen_one, make_user(), Visible.YES)
    for _ in range(3):
        answer(db, ruled_out, make_user(), Visible.NO)
    assert (seen_one.tier, ruled_out.state) == ("seen", "ruled_out")

    page = client_as(commenter).get(f"{API}/findings/{seen_one.public_id}").json()
    assert page["answers_visible"] is False
    kinds = {"observation_added", "tier_changed", "state_changed"}
    assert {kind for kind, _ in _notifications(db, commenter)} == kinds
    assert all(actor is None for kind, actor in _notifications(db, commenter) if kind in kinds)
    rows = db.execute(select(Activity.kind, Activity.actor_id).where(Activity.kind.in_(kinds))).all()
    assert rows
    assert all(actor is None for _, actor in rows), rows


def test_a_change_caused_by_evidence_is_still_credited(db: Session, make_user: MakeUser) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    for _ in range(2):
        answer(db, finding, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    add_desk_evidence(db, finding, helper, EvidenceKind.AERIAL)
    add_desk_evidence(db, finding, helper, EvidenceKind.HISTORIC_MAP, title="OS 6-inch")
    assert finding.tier == "corroborated"
    actors = db.scalars(
        select(Activity.actor_id).where(Activity.kind == "tier_changed").order_by(Activity.id)
    ).all()
    assert actors == [None, helper.id]


def test_next_steps_carry_no_numbers_for_someone_who_has_not_answered(
    db: Session, client, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    for _ in range(2):
        answer(db, finding, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    add_desk_evidence(db, finding, helper, EvidenceKind.AERIAL)
    add_desk_evidence(db, finding, helper, EvidenceKind.HISTORIC_MAP, title="OS 6-inch")
    path = f"{API}/findings/{finding.public_id}"

    for viewer in (client, client_as(make_user())):
        steps = viewer.get(path).json()["assessment"]["next_steps"]
        assert {step["code"] for step in steps} == {"need_check", "need_trusted_review"}
        for step in steps:
            assert (step["people"], step["weight_needed"]) == (None, None)
            assert not any(ch.isdigit() for ch in step["prompt"])
            assert not {"one", "five"} & set(step["prompt"].split())
        assert {step["check"] for step in steps if step["code"] == "need_check"} == {
            "not_modern",
            "not_natural",
            "not_artefact",
        }

    review_step = next(
        step
        for step in client_as(finder).get(path).json()["assessment"]["next_steps"]
        if step["code"] == "need_trusted_review"
    )
    assert review_step["weight_needed"] == 5.0


def test_three_accounts_cannot_farm_their_way_to_restricted_positions(
    db: Session, make_user: MakeUser
) -> None:
    finder, helper, endorser = make_user(), make_user(), make_user()
    for n in range(2):
        finding = create(db, finder, lon=-1.85 + 0.01 * n)
        answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
        answer(db, finding, endorser, Visible.YES)
        add_desk_evidence(db, finding, helper, EvidenceKind.AERIAL)
        add_desk_evidence(db, finding, endorser, EvidenceKind.HISTORIC_MAP, title="OS 6-inch")
        visit, _ = findings.add_evidence(
            db,
            findings.lock(db, finding),
            helper,
            EvidenceFields(
                kind=EvidenceKind.FIELD_VISIT, outcome=Outcome.SUPPORTS, occurred_on=date(2026, 10, 1)
            ),
        )
        findings.vote(db, visit.id, endorser, 1)
        db.commit()
        assert finding.tier == "ground_checked"
    db.expire_all()
    farmed = db.get(User, finder.id)
    assert farmed is not None
    assert farmed.reputation >= 50
    assert farmed.role == Role.MEMBER.value
    restricted = create(db, make_user(), requested_sensitivity="restricted")
    assert not sensitivity.sees_exact(restricted, farmed)
