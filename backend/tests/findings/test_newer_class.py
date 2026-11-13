"""A class a newer version stored and this one has no name for is read as "Not sure", not a 500.

A deploy changes the schema first and swaps the machines after, so for some
minutes this version serves beside a newer one, and going back to this
version leaves the newer one's findings in the database. A finding can't be
left out of its own page the way an activity row of an unknown kind is, so
this version reads the class as `unknown` wherever it serves, lists, searches,
assesses, exports or matches a finding, and never writes "Not sure" over it
behind its finder's back.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import AddConstraint, CreateTable, DropConstraint

from fieldclub.db import Base
from fieldclub.models import Finding, Observation, User
from fieldclub.schemas.activity import ActivityFinding
from fieldclub.schemas.mentions import MentionedFinding
from fieldclub.services import findings, sensitivity
from fieldclub.services.confidence import load_assessment
from fieldclub.vocab import (
    EvidenceKind,
    FeatureClass,
    InvestigationItemKind,
    Relation,
    Sensitivity,
    Visibility,
    Visible,
)
from tests.findings.support import API, answer, create
from tests.helpers import ClientAs, MakeUser, add_record, add_source
from tests.investigations.support import add, make, url

LATER_CLASS = "added_by_a_later_version"
assert LATER_CLASS not in set(FeatureClass), "the class has to be one this version has no name for"

# Every check that keeps a stored class inside this version's classes.
_CLASS_CHECKS = {
    Finding.__tablename__: ("ck_findings_feature_class_valid", "ck_findings_community_class_valid"),
    Observation.__tablename__: ("ck_observations_feature_class_valid",),
}


def _checks() -> list[Any]:
    found = []
    for table_name, names in _CLASS_CHECKS.items():
        table = Base.metadata.tables[table_name]
        for name in names:
            (check,) = (c for c in table.constraints if c.name == name)
            found.append(check)
    return found


@contextmanager
def class_check_lifted(db: Session, database: Engine) -> Iterator[None]:
    """Lift the checks on stored classes in this database, and put them back on the way out.

    On the way out the later class is taken off every row, so the checks can
    be made again. Adding a check back is told not to set it apart from its
    table, or every schema built later in the run would be made without it.
    """
    checks = _checks()
    with database.begin() as conn:
        for check in checks:
            conn.execute(DropConstraint(check))
    try:
        yield
    finally:
        db.rollback()
        with database.begin() as conn:
            conn.execute(
                update(Finding)
                .where(Finding.feature_class == LATER_CLASS)
                .values(feature_class=FeatureClass.UNKNOWN.value)
            )
            conn.execute(
                update(Finding).where(Finding.community_class == LATER_CLASS).values(community_class=None)
            )
            conn.execute(
                update(Observation).where(Observation.feature_class == LATER_CLASS).values(feature_class=None)
            )
            for check in checks:
                conn.execute(AddConstraint(check, isolate_from_table=False))


@pytest.fixture
def later_schema(db: Session, database: Engine) -> Iterator[None]:
    """The checks on stored classes lifted, as a later version's schema would have widened them."""
    with class_check_lifted(db, database):
        yield


def test_lifting_the_checks_leaves_them_in_every_schema_built_afterwards(
    db: Session, database: Engine
) -> None:
    with class_check_lifted(db, database):
        pass

    for table_name, names in _CLASS_CHECKS.items():
        made = str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=postgresql.dialect()))
        for name in names:
            assert name in made, f"{name} is no longer made with {table_name}"


def store_later_class(db: Session, finding: Finding) -> None:
    """Give `finding` the later class, as finder's class and community's, as the later version would store it.

    Written with a bulk update, which no ORM hook sees, as the later version's
    rows reach this one: straight from the database. The stored assessment
    names the later class where the later version's engine would.
    """
    assessment = dict(finding.assessment)
    known = finding.feature_class
    assessment["class_support"] = {LATER_CLASS: assessment["class_support"][known]}
    assessment["class_leader"] = LATER_CLASS
    assessment["community_class"] = LATER_CLASS
    assert known not in assessment["class_support"], "the finder's class is now the later one"
    db.execute(
        update(Finding)
        .where(Finding.id == finding.id)
        .values(feature_class=LATER_CLASS, community_class=LATER_CLASS, assessment=assessment)
    )
    db.commit()
    db.refresh(finding)


@pytest.fixture
def finder(make_user: MakeUser) -> User:
    return make_user()


@pytest.fixture
def later(db: Session, finder: User, later_schema: None) -> Finding:
    """An open finding saved with the later class."""
    finding = create(db, finder)
    assert finding.sensitivity == Sensitivity.OPEN.value
    store_later_class(db, finding)
    return finding


def test_its_page_says_not_sure(
    later: Finding, finder: User, client: TestClient, client_as: ClientAs
) -> None:
    for reader in (client, client_as(finder)):
        page = reader.get(f"{API}/findings/{later.public_id}")

        assert page.status_code == 200, page.text
        assert page.json()["feature_class"] == "unknown"
        assert LATER_CLASS not in page.text
    tallies = client_as(finder).get(f"{API}/findings/{later.public_id}").json()["assessment"]["tallies"]
    assert tallies["community_class"] == "unknown"


def test_the_list_the_map_and_a_search_say_not_sure(later: Finding, client: TestClient) -> None:
    listed = client.get(f"{API}/findings")
    mapped = client.get(f"{API}/findings", params={"format": "geojson"})
    unsure = client.get(f"{API}/findings", params={"feature_class": "unknown"})
    enclosures = client.get(f"{API}/findings", params={"feature_class": "enclosure"})

    assert listed.status_code == 200, listed.text
    assert [item["feature_class"] for item in listed.json()["items"]] == ["unknown"]
    assert mapped.status_code == 200, mapped.text
    assert [f["properties"]["feature_class"] for f in mapped.json()["features"]] == ["unknown"]
    assert [item["public_id"] for item in unsure.json()["items"]] == [later.public_id]
    assert enclosures.json()["items"] == []


def test_the_feed_and_a_mention_say_not_sure(
    db: Session, later: Finding, finder: User, client: TestClient
) -> None:
    feed = client.get(f"{API}/activity")

    assert feed.status_code == 200, feed.text
    assert [item["finding"]["feature_class"] for item in feed.json()["items"]] == ["unknown"]
    assert ActivityFinding.build(later, None).feature_class is FeatureClass.UNKNOWN
    assert MentionedFinding.build(later, finder, None).feature_class is FeatureClass.UNKNOWN


def test_the_review_queue_a_card_and_the_reveal_say_not_sure(
    later: Finding, make_user: MakeUser, client_as: ClientAs
) -> None:
    helper = client_as(make_user())

    tasks = helper.get(f"{API}/review/tasks")
    cards = helper.get(f"{API}/review/next")
    answered = helper.put(
        f"{API}/findings/{later.public_id}/observation",
        json={"visible": "yes", "feature_class": "unknown", "shape_revision": 0},
    )

    assert tasks.status_code == 200, tasks.text
    assert later.public_id in tasks.text
    assert cards.status_code == 200, cards.text
    assert [card["public_id"] for card in cards.json()["items"]] == [later.public_id]
    assert answered.status_code == 200, answered.text
    reveal = answered.json()
    assert reveal["comparison"]["finder_class"] == "unknown"
    assert reveal["finding"]["feature_class"] == "unknown"
    assert LATER_CLASS not in answered.text


def test_the_downloads_say_not_sure(db: Session, later: Finding, finder: User, client: TestClient) -> None:
    investigation = make(db, finder, Visibility.PUBLIC)
    add(db, investigation, finder, kind=InvestigationItemKind.FINDING, finding=later.public_id)

    one = client.get(f"{API}/findings/{later.public_id}/export", params={"format": "csv"})
    mapped = client.get(f"{API}/findings/{later.public_id}/export")
    many = client.get(f"{API}/findings/export", params={"format": "csv"})
    page = client.get(url(investigation, "/export"), params={"format": "html"})
    table = client.get(url(investigation, "/export"), params={"format": "csv"})

    for response in (one, mapped, many, page, table):
        assert response.status_code == 200, response.text
        assert LATER_CLASS not in response.text
    # "SITE" is the monument type of a finding not yet classified.
    assert [row["monument_type"] for row in csv.DictReader(io.StringIO(one.text))] == ["SITE"]
    assert [row["monument_type"] for row in csv.DictReader(io.StringIO(many.text))] == ["SITE"]
    assert [f["properties"]["monument_type"] for f in mapped.json()["features"]] == ["SITE"]
    assert "Not sure" in page.text


def test_the_suggested_records_and_a_record_s_findings_answer(
    db: Session, later: Finding, finder: User, client: TestClient, client_as: ClientAs
) -> None:
    lon, lat = -1.854173, 51.428637
    record = add_record(db, add_source(db), "Bowl barrow", lon, lat)
    db.commit()
    findings.add_evidence(
        db,
        findings.lock(db, later),
        finder,
        findings.EvidenceFields(
            kind=EvidenceKind.RECORD_LINK, record_id=record.id, relation=Relation.RELATED
        ),
    )
    db.commit()

    suggested = client_as(finder).get(f"{API}/findings/{later.public_id}/suggested-records")
    linked = client.get(f"{API}/records/{record.id}/findings")

    assert suggested.status_code == 200, suggested.text
    assert linked.status_code == 200, linked.text
    assert [item["feature_class"] for item in linked.json()["items"]] == ["unknown"]


def test_a_reassessment_reads_it_as_not_sure_and_leaves_it_stored(
    db: Session, later: Finding, make_user: MakeUser
) -> None:
    answer(db, later, make_user(), Visible.YES)

    db.refresh(later)
    assessment = load_assessment(later.assessment)
    assert assessment is not None
    assert assessment.class_support == {}
    assert later.feature_class == LATER_CLASS, "a reassessment never writes the class"


def test_a_stored_assessment_naming_the_later_class_reads_as_not_sure(later: Finding) -> None:
    assessment = load_assessment(later.assessment)

    assert assessment is not None
    assert assessment.class_leader is FeatureClass.UNKNOWN
    assert assessment.community_class is FeatureClass.UNKNOWN
    assert assessment.class_support == {}, "support for a class this version can't name isn't shown"


def test_a_second_look_naming_the_later_class_reads_as_not_sure(
    db: Session, finder: User, make_user: MakeUser, client_as: ClientAs, later_schema: None
) -> None:
    finding = create(db, finder)
    helper = make_user()
    answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.MOAT)
    db.execute(update(Observation).where(Observation.user_id == helper.id).values(feature_class=LATER_CLASS))
    db.commit()

    listed = client_as(finder).get(f"{API}/findings/{finding.public_id}/observations")
    findings.reassess(db, findings.lock(db, finding), None)
    db.commit()

    assert listed.status_code == 200, listed.text
    assert [item["feature_class"] for item in listed.json()["items"]] == ["unknown"]
    assessment = load_assessment(finding.assessment)
    assert assessment is not None
    assert [obs.feature_class for obs in assessment.observations] == [FeatureClass.UNKNOWN]


# --------------------------------------------------------------------------
# Not writing over it
# --------------------------------------------------------------------------


def test_an_edit_sending_back_the_not_sure_it_was_shown_keeps_the_stored_class(
    db: Session, later: Finding, finder: User, client_as: ClientAs
) -> None:
    shown = client_as(finder).get(f"{API}/findings/{later.public_id}").json()

    edited = client_as(finder).patch(
        f"{API}/findings/{later.public_id}",
        json={"title": "Footings by the lane", "feature_class": shown["feature_class"]},
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["feature_class"] == "unknown"
    db.refresh(later)
    assert (later.title, later.feature_class) == ("Footings by the lane", LATER_CLASS)


def test_an_edit_choosing_another_class_saves_it(
    db: Session, later: Finding, finder: User, client_as: ClientAs
) -> None:
    edited = client_as(finder).patch(f"{API}/findings/{later.public_id}", json={"feature_class": "moat"})

    assert edited.status_code == 200, edited.text
    assert edited.json()["feature_class"] == "moat"
    db.refresh(later)
    assert later.feature_class == "moat"


def test_a_note_saved_on_a_second_look_naming_the_later_class_keeps_the_class(
    db: Session, finder: User, make_user: MakeUser, client_as: ClientAs, later_schema: None
) -> None:
    finding = create(db, finder)
    helper = make_user()
    answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.MOAT)
    db.execute(update(Observation).where(Observation.user_id == helper.id).values(feature_class=LATER_CLASS))
    db.commit()
    shown = client_as(helper).get(f"{API}/findings/{finding.public_id}").json()["my_observation"]

    saved = client_as(helper).put(
        f"{API}/findings/{finding.public_id}/observation",
        json={
            "visible": shown["visible"],
            "feature_class": shown["feature_class"],
            "note": "Clearer at dusk",
        },
    )

    assert shown["feature_class"] == "unknown"
    assert saved.status_code == 200, saved.text
    stored = db.scalars(select(Observation).where(Observation.user_id == helper.id)).one()
    db.refresh(stored)
    assert (stored.note, stored.feature_class) == ("Clearer at dusk", LATER_CLASS)


# --------------------------------------------------------------------------
# Protection
# --------------------------------------------------------------------------


def test_the_later_class_starts_at_the_level_of_not_sure() -> None:
    assert sensitivity.default_sensitivity(LATER_CLASS) is sensitivity.default_sensitivity(
        FeatureClass.UNKNOWN
    )


@pytest.mark.parametrize("level", list(Sensitivity))
def test_the_later_class_never_changes_a_level(level: Sensitivity) -> None:
    for new in FeatureClass:
        expected = sensitivity.level_after_class_change(level, FeatureClass.UNKNOWN, new)
        assert sensitivity.level_after_class_change(level, LATER_CLASS, new) is expected
    assert sensitivity.level_after_class_change(level, FeatureClass.UNKNOWN, LATER_CLASS) is level


def test_a_protected_finding_of_the_later_class_stays_protected_through_an_edit(
    db: Session, finder: User, client_as: ClientAs, later_schema: None
) -> None:
    finding = create(db, finder, feature_class=FeatureClass.ROUND_BARROW)
    assert finding.sensitivity == Sensitivity.PROTECTED.value
    store_later_class(db, finding)

    edited = client_as(finder).patch(
        f"{API}/findings/{finding.public_id}", json={"feature_class": "enclosure"}
    )

    assert edited.status_code == 200, edited.text
    db.refresh(finding)
    assert (finding.feature_class, finding.sensitivity) == ("enclosure", Sensitivity.PROTECTED.value)
    assert db.scalar(select(Finding.sensitivity).where(Finding.id == finding.id)) == "protected"
