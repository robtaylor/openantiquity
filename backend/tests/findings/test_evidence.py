"""Evidence of every kind, votes on it, and verification of official evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Evidence, Follow, Media, Record, Source, User
from fieldclub.models.common import db_point
from fieldclub.services import findings
from fieldclub.services.findings import EvidenceFields, InvalidEvidenceError
from fieldclub.vocab import EvidenceKind, Outcome, Relation, Stance
from tests.findings.support import API, add_desk_evidence, create
from tests.helpers import ClientAs, MakeUser, error_code

VISIT = date(2026, 10, 1)


def _media(db: Session, owner: User) -> Media:
    media = Media(
        user_id=owner.id, storage_key=f"m/{owner.id}.jpg", content_type="image/jpeg", bytes=1, sha256="x"
    )
    db.add(media)
    db.commit()
    return media


def _record(db: Session) -> Record:
    db.add(
        Source(
            key="test-source",
            name="Test",
            publisher="Test",
            licence="OGL",
            attribution="Test",
            reuse="open",
            category="monument",
            access="bulk",
        )
    )
    db.flush()
    record = Record(
        source_key="test-source",
        external_id="1",
        name="Barrow",
        category="monument",
        geom=db_point(-1.85, 51.43),
        centroid=db_point(-1.85, 51.43),
        ingested_at=datetime.now(UTC),
    )
    db.add(record)
    db.commit()
    return record


def _valid_cases(db: Session, user: User) -> list[dict[str, Any]]:
    media = _media(db, user)
    record = _record(db)
    return [
        {"kind": EvidenceKind.LIDAR_VIEW, "view": {"layer": "slope", "zoom": 17}},
        {"kind": EvidenceKind.AERIAL, "url": "https://example.org/photo"},
        {"kind": EvidenceKind.AERIAL, "media_id": media.id},
        {"kind": EvidenceKind.HISTORIC_MAP, "title": "OS 6-inch, 1888"},
        {"kind": EvidenceKind.RECORD_LINK, "record_id": record.id, "relation": Relation.SAME_AS},
        # Decision 0007: a record we don't store is kept as its identifier and address only.
        {
            "kind": EvidenceKind.RECORD_LINK,
            "reference": "ADS-12345",
            "url": "https://example.org/record/12345",
            "source_key": "test-source",
            "relation": Relation.RELATED,
        },
        {"kind": EvidenceKind.DOCUMENT, "reference": "WANHM 1923, 41"},
        {"kind": EvidenceKind.PHOTO, "media_id": media.id, "outcome": Outcome.SUPPORTS},
        {"kind": EvidenceKind.FIELD_VISIT, "occurred_on": VISIT, "outcome": Outcome.INCONCLUSIVE},
        {
            "kind": EvidenceKind.GEOPHYSICS,
            "occurred_on": VISIT,
            "outcome": Outcome.SUPPORTS,
            "organisation": "Unit",
        },
        {"kind": EvidenceKind.EXCAVATION, "occurred_on": VISIT, "outcome": Outcome.CONTRADICTS},
        {"kind": EvidenceKind.HER_RECORD, "reference": "MWI1234", "organisation": "Wiltshire HER"},
        {"kind": EvidenceKind.DESIGNATION, "record_id": record.id},
        {"kind": EvidenceKind.PUBLICATION, "title": "A new enclosure near Avebury"},
    ]


def test_every_kind_can_be_added_with_what_it_needs(db: Session, make_user: MakeUser) -> None:
    helper = make_user()
    finding = create(db, make_user())
    cases = _valid_cases(db, helper)
    assert {case["kind"] for case in cases} == set(EvidenceKind)
    for case in cases:
        evidence, _ = findings.add_evidence(db, findings.lock(db, finding), helper, EvidenceFields(**case))
        db.commit()
        assert evidence.kind == case["kind"].value
    assert finding.evidence_count == len(cases)
    external = db.scalars(select(Evidence).where(Evidence.reference == "ADS-12345")).one()
    assert (external.record_id, external.title, external.data) == (None, None, {"source_key": "test-source"})


@pytest.mark.parametrize(
    "case",
    [
        {"kind": EvidenceKind.LIDAR_VIEW},
        {"kind": EvidenceKind.AERIAL, "view": {"layer": "slope"}},
        {"kind": EvidenceKind.AERIAL},
        {"kind": EvidenceKind.HISTORIC_MAP},
        {"kind": EvidenceKind.RECORD_LINK, "reference": "X1", "url": "https://example.org"},
        {"kind": EvidenceKind.RECORD_LINK, "relation": Relation.SAME_AS},
        {"kind": EvidenceKind.RECORD_LINK, "relation": Relation.SAME_AS, "reference": "X1"},
        {
            "kind": EvidenceKind.RECORD_LINK,
            "relation": Relation.SAME_AS,
            "reference": "X1",
            "url": "https://example.org",
            "title": "Copied name",
        },
        {"kind": EvidenceKind.RECORD_LINK, "relation": Relation.SAME_AS, "record_id": 999_999},
        {
            "kind": EvidenceKind.RECORD_LINK,
            "relation": Relation.SAME_AS,
            "reference": "X1",
            "url": "https://example.org",
            "source_key": "no-such-source",
        },
        {"kind": EvidenceKind.DOCUMENT, "relation": Relation.RELATED, "title": "Book"},
        {"kind": EvidenceKind.DOCUMENT, "title": "Book", "outcome": Outcome.SUPPORTS},
        {"kind": EvidenceKind.DOCUMENT, "title": "Book", "record_id": 1},
        {"kind": EvidenceKind.DOCUMENT, "title": "Book", "source_key": "test-source"},
        {"kind": EvidenceKind.DOCUMENT, "title": "Book", "media_id": 1},
        {"kind": EvidenceKind.PHOTO, "outcome": Outcome.SUPPORTS},
        {"kind": EvidenceKind.FIELD_VISIT, "outcome": Outcome.SUPPORTS},
        {"kind": EvidenceKind.FIELD_VISIT, "occurred_on": VISIT},
        {
            "kind": EvidenceKind.EXCAVATION,
            "occurred_on": datetime.now(UTC).date() + timedelta(days=2),
            "outcome": Outcome.SUPPORTS,
        },
        {"kind": EvidenceKind.HER_RECORD},
        {"kind": EvidenceKind.PUBLICATION},
    ],
)
def test_evidence_missing_what_its_kind_needs_is_refused(
    db: Session, make_user: MakeUser, case: dict[str, Any]
) -> None:
    finding = create(db, make_user())
    with pytest.raises(InvalidEvidenceError):
        findings.add_evidence(db, findings.lock(db, finding), make_user(), EvidenceFields(**case))


def test_you_attach_only_photos_you_uploaded(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    someone_elses = _media(db, make_user())
    with pytest.raises(InvalidEvidenceError, match="you uploaded"):
        findings.add_evidence(
            db,
            findings.lock(db, finding),
            make_user(),
            EvidenceFields(kind=EvidenceKind.PHOTO, media_id=someone_elses.id),
        )


def test_votes_count_from_others_but_not_from_the_contributor_or_finder(
    db: Session, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    evidence, _ = add_desk_evidence(db, finding, helper)
    for voter in (helper, finder):
        with pytest.raises(findings.VoteNotAllowedError):
            findings.vote(db, evidence.id, voter, 1)
    voter = make_user()
    findings.vote(db, evidence.id, voter, -1)
    db.commit()
    status = next(s for s in finding.assessment["evidence"] if s["id"] == evidence.id)
    assert (status["vote_total"], status["standing"]) == (-1.0, False)
    assert db.scalar(select(Follow).where(Follow.user_id == voter.id))
    findings.vote(db, evidence.id, voter, 0)
    db.commit()
    status = next(s for s in finding.assessment["evidence"] if s["id"] == evidence.id)
    assert (status["vote_total"], status["standing"]) == (0.0, True)


def test_evidence_endorsed_by_two_others_earns_its_contributor_a_point(
    db: Session, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    evidence, _ = add_desk_evidence(db, finding, helper)
    findings.vote(db, evidence.id, make_user(), 1)
    findings.vote(db, evidence.id, make_user(), 1)
    db.commit()
    db.refresh(helper)
    assert helper.reputation == 1.0


def test_verification_puts_a_finding_on_record(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    entry, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        make_user(),
        EvidenceFields(kind=EvidenceKind.HER_RECORD, reference="MWI1234"),
    )
    map_item, _ = add_desk_evidence(db, finding, make_user(), EvidenceKind.HISTORIC_MAP, title="1888")
    for who in (make_user(), make_user("trusted")):
        with pytest.raises(findings.VerifyNotAllowedError):
            findings.verify(db, entry.id, who)
    with pytest.raises(InvalidEvidenceError, match="Only an HER entry"):
        findings.verify(db, map_item.id, make_user("expert"))
    result = findings.verify(db, entry.id, make_user("expert"))
    db.commit()
    assert result.tier_after.value == "confirmed"
    assert finding.tier == "confirmed"


def test_an_archaeologist_cannot_verify_on_their_own_finding(db: Session, make_user: MakeUser) -> None:
    expert = make_user("expert")
    finding = create(db, expert)
    entry, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        make_user(),
        EvidenceFields(kind=EvidenceKind.DESIGNATION, reference="1012345"),
    )
    with pytest.raises(findings.VerifyNotAllowedError):
        findings.verify(db, entry.id, expert)


def test_deleting_evidence_reassesses(db: Session, make_user: MakeUser) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    evidence, _ = add_desk_evidence(db, finding, helper)
    with pytest.raises(findings.EvidenceForbiddenError):
        findings.delete_evidence(db, evidence.id, make_user())
    findings.delete_evidence(db, evidence.id, helper)
    db.commit()
    assert finding.evidence_count == 0
    with pytest.raises(findings.EvidenceNotFoundError):
        findings.delete_evidence(db, evidence.id, helper)
    other, _ = add_desk_evidence(db, finding, helper)
    findings.delete_evidence(db, other.id, make_user("moderator"))
    db.commit()
    assert finding.evidence_count == 0


def test_no_evidence_on_a_withdrawn_finding(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    evidence, _ = add_desk_evidence(db, finding, make_user())
    findings.withdraw_finding(db, findings.lock(db, finding), finder)
    db.commit()
    with pytest.raises(findings.FindingClosedError):
        add_desk_evidence(db, finding, make_user())
    with pytest.raises(findings.FindingClosedError):
        findings.vote(db, evidence.id, make_user(), 1)


# --------------------------------------------------------------------------
# Over HTTP
# --------------------------------------------------------------------------


def test_evidence_over_http(db: Session, client_as: ClientAs, make_user: MakeUser) -> None:
    finder, helper, voter = make_user(), make_user(), make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/evidence"
    added = client_as(helper).post(
        path, json={"kind": "lidar_view", "view": {"layer": "sky_view", "zoom": 17}, "note": "Clearer here"}
    )
    assert added.status_code == 201, added.text
    (item,) = added.json()["evidence"]
    assert item["view"]["layer"] == "sky_view"
    assert item["contributor"]["handle"] == helper.handle
    assert item["independent"] is True

    refused = client_as(helper).post(path, json={"kind": "record_link", "relation": "same_as"})
    assert error_code(refused) == "invalid_evidence"
    assert error_code(
        client_as(helper).post(path, json={"kind": "aerial", "url": "javascript:alert(1)"})
    ) == ("validation_error")

    vote = client_as(voter).put(f"{API}/evidence/{item['id']}/vote", json={"value": 1})
    assert vote.json() == {"evidence_id": item["id"], "value": 1}
    assert error_code(client_as(helper).put(f"{API}/evidence/{item['id']}/vote", json={"value": 1})) == (
        "vote_not_allowed"
    )
    assert client_as(voter).put(f"{API}/evidence/{item['id']}/vote", json={"value": 2}).status_code == 422
    page = client_as(voter).get(f"{API}/findings/{finding.public_id}").json()
    assert page["evidence"][0]["my_vote"] == 1
    assert page["evidence"][0]["vote_total"] == 1.0

    official = client_as(helper).post(path, json={"kind": "her_record", "reference": "MWI1"}).json()
    entry_id = next(e["id"] for e in official["evidence"] if e["kind"] == "her_record")
    verified = client_as(make_user("moderator")).post(f"{API}/evidence/{entry_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["tier"] == "confirmed"

    assert client_as(make_user()).delete(f"{API}/evidence/{item['id']}").status_code == 403
    assert client_as(helper).delete(f"{API}/evidence/{item['id']}").status_code == 204
    assert error_code(client_as(helper).delete(f"{API}/evidence/{item['id']}")) == "evidence_not_found"


def test_an_unapproved_photo_is_not_shown_to_others(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    media = _media(db, helper)
    findings.add_evidence(
        db,
        findings.lock(db, finding),
        helper,
        EvidenceFields(kind=EvidenceKind.PHOTO, media_id=media.id, stance=Stance.SUPPORTS),
    )
    db.commit()
    path = f"{API}/findings/{finding.public_id}"
    assert client_as(make_user()).get(path).json()["evidence"][0]["media_id"] is None
    assert client_as(helper).get(path).json()["evidence"][0]["media_id"] == media.id
    media.approved_at = datetime.now(UTC)
    db.commit()
    assert client_as(make_user()).get(path).json()["evidence"][0]["media_id"] == media.id


def test_evidence_and_votes_need_the_exact_position(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, trusted, member = make_user(), make_user("trusted"), make_user()
    finding = create(db, finder, requested_sensitivity="restricted")
    assert client_as(member).get(f"{API}/findings/{finding.public_id}").json()["location"]["obscured"]
    evidence, _ = add_desk_evidence(db, finding, trusted)
    path = f"{API}/findings/{finding.public_id}/evidence"
    for outcome in ("supports", "contradicts"):
        visit = {"kind": "field_visit", "outcome": outcome, "occurred_on": VISIT.isoformat()}
        refused = client_as(member).post(path, json=visit)
        assert (refused.status_code, error_code(refused)) == (403, "location_hidden")
    voted = client_as(member).put(f"{API}/evidence/{evidence.id}/vote", json={"value": -1})
    assert (voted.status_code, error_code(voted)) == (403, "location_hidden")
    db.expire_all()
    assert (finding.state, finding.evidence_count) == ("open", 1)
    assert (
        client_as(make_user("trusted"))
        .put(f"{API}/evidence/{evidence.id}/vote", json={"value": 1})
        .status_code
        == 200
    )


def test_an_archaeologist_cannot_verify_evidence_they_added(db: Session, make_user: MakeUser) -> None:
    expert = make_user("expert")
    finding = create(db, make_user())
    entry, _ = findings.add_evidence(
        db, findings.lock(db, finding), expert, EvidenceFields(kind=EvidenceKind.HER_RECORD, reference="MWI9")
    )
    db.commit()
    with pytest.raises(findings.VerifyNotAllowedError):
        findings.verify(db, entry.id, expert)
    db.rollback()
    assert findings.verify(db, entry.id, make_user("moderator")).tier_after.value == "confirmed"
