"""Reports: who may report what, the queue, and resolving."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import vocab
from fieldclub.models import Report
from fieldclub.services import moderation
from fieldclub.vocab import ReportReason, ReportStatus, ReportTarget, Role
from tests.findings.support import add_desk_evidence
from tests.helpers import WEB, ClientAs, MakeFinding, MakeUser, count, error_code
from tests.moderation.support import API, comment, log_entries, mention, photo


def report(client, kind: str, ref: object, reason: str = "abuse", **extra):
    return client.post(
        f"{API}/reports", json={"target_kind": kind, "target_id": str(ref), "reason": reason, **extra}
    )


def test_a_member_reports_each_kind_of_thing(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user(handle="Owner")
    finding = make_finding(owner)
    evidence, _ = add_desk_evidence(db, finding, make_user())
    targets = {
        "finding": finding.public_id,
        "comment": comment(db, finding, owner).id,
        "evidence": evidence.id,
        "mention": mention(db, finding, owner).id,
        "photo": photo(db, owner, approved_by=make_user(Role.MODERATOR)).id,
        "user": "Owner",
    }
    client = client_as(make_user())
    for kind, ref in targets.items():
        response = report(client, kind, ref, note="Look at this.")
        assert response.status_code == 201, (kind, response.text)
        body = response.json()
        assert (body["target_kind"], body["target_id"], body["reason"]) == (kind, str(ref), "abuse")
        # The reporter learns nothing about what happens next.
        assert set(body) == {"id", "target_kind", "target_id", "reason", "created_at"}
    assert count(db, Report) == len(targets)


def test_one_open_report_per_reporter_and_target(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding()
    client = client_as(make_user())
    assert report(client, "finding", finding.public_id).status_code == 201
    again = report(client, "finding", finding.public_id, reason="spam")
    assert (again.status_code, error_code(again)) == (409, "already_reported")
    # Someone else may report it too, and once it is upheld the first reporter may again at once.
    assert report(client_as(make_user()), "finding", finding.public_id).status_code == 201
    first = db.query(Report).order_by(Report.id).first()
    assert first is not None
    moderation.resolve_report(db, first.id, make_user(Role.MODERATOR), ReportStatus.UPHELD, "Hidden.")
    db.commit()
    assert report(client, "finding", finding.public_id).status_code == 201


def test_a_dismissed_report_is_not_made_again_for_a_day(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding()
    reporter = make_user()
    client = client_as(reporter)
    moderator = make_user(Role.MODERATOR)

    assert report(client, "finding", finding.public_id).status_code == 201
    first = db.scalar(select(Report))
    assert first is not None
    moderation.resolve_report(db, first.id, moderator, ReportStatus.DISMISSED, "Fine.")
    db.commit()
    for reason in ("abuse", "spam"):
        again = report(client, "finding", finding.public_id, reason=reason)
        assert (again.status_code, error_code(again)) == (409, "recently_dismissed")
    # Somebody else still can, and so can the same person about something else.
    assert report(client_as(make_user()), "finding", finding.public_id).status_code == 201
    assert report(client, "finding", make_finding().public_id).status_code == 201
    assert count(db, Report) == 3

    # A day after the dismissal they may report it again.
    a_day_on = datetime.now(UTC) + moderation.REPORT_COOLING_OFF + timedelta(minutes=1)
    moderation.create_report(
        db, reporter, ReportTarget.FINDING, finding.public_id, ReportReason.ABUSE, None, now=a_day_on
    )


def test_nobody_reports_what_they_cannot_see(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user()
    finding = make_finding(owner)
    hidden_finding = make_finding(owner)
    moderation.set_hidden(
        db, ReportTarget.FINDING, hidden_finding.public_id, make_user(Role.MODERATOR), hidden=True, reason="x"
    )
    waiting = photo(db, owner)
    db.commit()
    client = client_as(make_user())
    for kind, ref in [
        ("finding", hidden_finding.public_id),
        ("finding", "ZZZZZZ"),
        ("comment", 999),
        ("comment", "not-a-number"),
        ("evidence", 10**30),
        ("photo", waiting.id),
        ("user", "Nobody"),
        ("mention", finding.id),
    ]:
        response = report(client, kind, ref)
        assert (response.status_code, error_code(response)) == (404, "target_not_found"), (kind, ref)


def test_nobody_reports_themselves(client_as: ClientAs, make_user: MakeUser) -> None:
    me = make_user(handle="Me")
    response = report(client_as(me), "user", "Me")
    assert (response.status_code, error_code(response)) == (422, "cannot_report_self")


def test_reports_check_their_input(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding()
    client = client_as(make_user())
    for bad in [
        {"reason": "boring"},
        {"note": "x" * 2001},
        {"target_id": ""},
        {"target_id": "x" * 65},
        {"target_kind": "investigation"},
        {"extra": True},
    ]:
        body = {"target_kind": "finding", "target_id": finding.public_id, "reason": "spam"} | bad
        response = client.post(f"{API}/reports", json=body)
        assert (response.status_code, error_code(response)) == (422, "validation_error"), bad


def test_reporting_is_rate_limited(
    limits_on: None, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    client = client_as(make_user())
    findings_ = [make_finding() for _ in range(31)]
    codes = [report(client, "finding", f.public_id).status_code for f in findings_]
    assert codes[:30] == [201] * 30
    assert codes[30] == 429


def test_the_queue_is_oldest_first_with_enough_of_each_target_to_decide(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user(handle="Owner")
    finding = make_finding(owner, title="A barrow by the road")
    said = comment(db, finding, owner, "Come and dig here at night.")
    first, second = make_user(handle="First"), make_user(handle="Second")
    report(client_as(first), "comment", said.id, "illegal", note="Inciting nighthawking.")
    report(client_as(second), "comment", said.id, "location_risk")
    report(client_as(second), "user", "Owner", "intimate_image")
    moderator = client_as(make_user(Role.MODERATOR))

    response = moderator.get(f"{API}/mod/reports")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["reporter"]["handle"] for item in items] == ["First", "Second", "Second"]
    top = items[0]
    assert top["note"] == "Inciting nighthawking."
    assert top["open_on_target"] == 2
    assert top["due_at"] is None
    target = top["target"]
    assert target["kind"] == "comment"
    assert target["ref"] == str(said.id)
    assert target["body"] == "Come and dig here at night."
    assert target["owner"]["handle"] == "Owner"
    assert target["finding"] == {
        "public_id": finding.public_id,
        "title": "A barrow by the road",
        "hidden": False,
    }
    assert (target["exists"], target["hidden"], target["removed"]) == (True, False, False)
    person = items[2]
    assert person["target"]["owner"]["handle"] == "Owner"
    created = person["created_at"]
    assert person["due_at"] is not None
    assert datetime.fromisoformat(person["due_at"]) - datetime.fromisoformat(created) == timedelta(hours=48)

    only = moderator.get(f"{API}/mod/reports", params={"reason": "intimate_image"}).json()["items"]
    assert [item["reason"] for item in only] == ["intimate_image"]
    paged = moderator.get(f"{API}/mod/reports", params={"limit": 2}).json()
    rest = moderator.get(f"{API}/mod/reports", params={"limit": 2, "cursor": paged["next_cursor"]}).json()
    assert [i["id"] for i in paged["items"] + rest["items"]] == [i["id"] for i in items]
    assert rest["next_cursor"] is None


def test_resolving_closes_every_open_report_on_the_target_and_is_logged(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding()
    for _ in range(3):
        report(client_as(make_user()), "finding", finding.public_id, "spam")
    moderator = make_user(Role.MODERATOR, handle="Mod")
    client = client_as(moderator)
    first = client.get(f"{API}/mod/reports").json()["items"][0]["id"]

    response = client.post(f"{API}/mod/reports/{first}/resolve", json={"outcome": "upheld", "note": "Spam."})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved"] == 3
    assert body["report"]["status"] == "upheld"
    assert body["report"]["resolved_by"]["handle"] == "Mod"
    assert client.get(f"{API}/mod/reports").json()["items"] == []
    upheld = client.get(f"{API}/mod/reports", params={"status": "upheld"}).json()["items"]
    assert len(upheld) == 3

    again = client.post(f"{API}/mod/reports/{first}/resolve", json={"outcome": "dismissed", "note": "x"})
    assert (again.status_code, error_code(again)) == (409, "report_already_resolved")
    missing = client.post(f"{API}/mod/reports/999999/resolve", json={"outcome": "dismissed", "note": "x"})
    assert (missing.status_code, error_code(missing)) == (404, "report_not_found")
    (entry,) = log_entries(db)
    assert (entry.action, entry.target_kind, entry.target_id, entry.reason) == (
        "resolve_report",
        "finding",
        finding.id,
        "Spam.",
    )
    assert entry.data == {"outcome": "upheld", "reports": sorted(r["id"] for r in upheld)}


@pytest.mark.parametrize(
    "whose",
    ["reported_by_them", "about_their_work", "about_their_comment", "about_their_photo", "about_them"],
)
def test_a_moderator_does_not_resolve_a_report_on_themselves(
    whose: str, db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    moderator = make_user(Role.MODERATOR, handle="Mod")
    client = client_as(moderator)
    # Someone else's report on someone else's comment stays in their queue.
    report(client_as(make_user()), "comment", comment(db, make_finding(), make_user()).id)
    if whose == "reported_by_them":
        report(client, "finding", make_finding().public_id)
    elif whose == "about_their_work":
        report(client_as(make_user()), "finding", make_finding(moderator).public_id)
    elif whose == "about_their_comment":
        report(client_as(make_user()), "comment", comment(db, make_finding(), moderator).id)
    elif whose == "about_their_photo":
        report(client_as(make_user()), "photo", photo(db, moderator, approved_by=make_user(Role.ADMIN)).id)
    else:
        report(client_as(make_user()), "user", "Mod")
    # The queue leaves it out for them, with its reporter and note, and resolving it is refused.
    assert [i["target"]["kind"] for i in client.get(f"{API}/mod/reports").json()["items"]] == ["comment"]
    other = client_as(make_user(Role.ADMIN))
    _, item = other.get(f"{API}/mod/reports").json()["items"]
    response = client.post(
        f"{API}/mod/reports/{item['id']}/resolve", json={"outcome": "dismissed", "note": "x"}
    )
    assert (response.status_code, error_code(response)) == (403, "own_report")
    # Another moderator can.
    resolved = other.post(
        f"{API}/mod/reports/{item['id']}/resolve", json={"outcome": "dismissed", "note": "x"}
    )
    assert resolved.status_code == 200


def test_the_queue_shows_a_target_that_has_since_gone(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user()
    finding = make_finding(owner)
    said = comment(db, finding, owner)
    report(client_as(make_user()), "comment", said.id)
    client_as(owner).delete(f"{API}/comments/{said.id}", headers=WEB)
    (item,) = client_as(make_user(Role.MODERATOR)).get(f"{API}/mod/reports").json()["items"]
    assert (item["target"]["exists"], item["target"]["removed"]) == (True, True)


def test_report_reasons_are_in_meta_with_their_deadlines(client) -> None:
    reasons = client.get(f"{API}/meta").json()["vocab"]["report_reasons"]
    assert [r["id"] for r in reasons] == [r.value for r in ReportReason]
    for item in reasons:
        assert list(item) == ["id", "label", "hint", "due_hours"]
        assert item["hint"].endswith(".")
    due = {r["id"]: r["due_hours"] for r in reasons if r["due_hours"] is not None}
    assert due == {"intimate_image": 48, "defamation": 48}
    assert len(vocab.REPORT_REASONS) == len(ReportReason)
