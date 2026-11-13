"""A level an earlier version stored and this one has dropped (Decision 0032).

A finding is `open` or `protected`. An earlier version had a third level,
and a database it served can still hold a finding at it, and moderation log
entries that name it. A deploy runs `create_schema` while the earlier version
still serves, so the schema step moves such a finding to `protected` before it
makes the check on `findings.sensitivity` again, and leaves the log as it was
written. The finding's page, the feed and the log then answer as for any
protected finding.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint, Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub.db import Base, create_schema
from fieldclub.models import Finding
from fieldclub.vocab import FeatureClass, Role, Sensitivity
from tests.findings.support import create
from tests.helpers import ClientAs, MakeFinding, MakeUser

API = "/api/v1"
CHECK = "ck_findings_sensitivity_valid"
# The level an earlier version stored, which this version has no name for.
DROPPED = "restricted"
assert DROPPED not in set(Sensitivity), "the level has to be one this version has no name for"
EARLIER_LEVELS = ("open", "protected", DROPPED)


def _check(engine: Engine) -> tuple[str, bool]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT pg_get_constraintdef(oid), convalidated FROM pg_constraint WHERE conname = :name"),
            {"name": CHECK},
        ).one()
    return row[0], row[1]


def _earlier_check(engine: Engine) -> None:
    """Put back the check as the earlier version built it, with the dropped level in it."""
    levels = ", ".join(f"'{level}'" for level in EARLIER_LEVELS)
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE findings DROP CONSTRAINT {CHECK}"))
        conn.execute(text(f"ALTER TABLE findings ADD CONSTRAINT {CHECK} CHECK (sensitivity IN ({levels}))"))


@pytest.fixture
def earlier_schema(db: Session, database: Engine) -> Iterator[None]:
    """The check on `findings.sensitivity` as the earlier version made it, and this version's after."""
    _earlier_check(database)
    try:
        yield
    finally:
        db.rollback()
        with database.begin() as conn:
            conn.execute(
                text("UPDATE findings SET sensitivity = 'protected' WHERE sensitivity = :level"),
                {"level": DROPPED},
            )
        create_schema(database)
        assert DROPPED not in _check(database)[0]


def _store_the_earlier_version_s_rows(database: Engine, finding: Finding, moderator_id: int) -> None:
    """The finding at the dropped level, and the history an earlier version wrote of it."""
    with database.begin() as conn:
        conn.execute(
            text("UPDATE findings SET sensitivity = :level WHERE id = :id"),
            {
                "level": DROPPED,
                "id": finding.id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO moderation_actions (actor_id, action, target_kind, target_id, reason, data) "
                "VALUES (:actor, 'change_sensitivity', 'finding', :id, 'Damage.', CAST(:data AS jsonb))"
            ),
            {
                "actor": moderator_id,
                "id": finding.id,
                "data": json.dumps({"from": "protected", "to": DROPPED}),
            },
        )


@pytest.mark.usefixtures("earlier_schema")
def test_the_schema_step_makes_a_finding_at_the_dropped_level_protected_and_keeps_the_log(
    db: Session,
    database: Engine,
    client: TestClient,
    client_as: ClientAs,
    make_user: MakeUser,
) -> None:
    finder = make_user(handle="Finder")
    moderator = make_user(Role.MODERATOR, handle="Mod")
    # Made through the service, so it has its assessment and its line in the feed.
    barrow = create(db, finder, feature_class=FeatureClass.ROUND_BARROW, title="A barrow")
    _store_the_earlier_version_s_rows(database, barrow, moderator.id)
    with database.connect() as conn:
        public_before = conn.scalar(
            text("SELECT ST_AsText(location_public) FROM findings WHERE id = :id"), {"id": barrow.id}
        )

    create_schema(database)
    once = _check(database)
    create_schema(database)

    definition, validated = _check(database)
    assert (definition, validated) == once, "a second run changed the check"
    assert validated
    assert "'open'" in definition
    assert "'protected'" in definition
    assert f"'{DROPPED}'" not in definition
    with database.connect() as conn:
        stored, public_after = conn.execute(
            text("SELECT sensitivity, ST_AsText(location_public) FROM findings WHERE id = :id"),
            {"id": barrow.id},
        ).one()
        logged = conn.scalar(
            text("SELECT data FROM moderation_actions WHERE target_id = :id"), {"id": barrow.id}
        )
    assert stored == Sensitivity.PROTECTED.value
    # Both levels show the square's centre to the public, so the public position stays.
    assert public_after == public_before
    assert logged == {"from": "protected", "to": DROPPED}, "the log is history and stays as written"

    # The finding answers as a protected one: exact to a member, the square to everyone else.
    signed_out = client.get(f"{API}/findings/{barrow.public_id}")
    assert signed_out.status_code == 200, signed_out.text
    assert signed_out.json()["sensitivity"] == "protected"
    assert signed_out.json()["location"]["obscured"] is True
    member = client_as(make_user())
    seen = member.get(f"{API}/findings/{barrow.public_id}")
    assert seen.status_code == 200, seen.text
    assert seen.json()["location"]["obscured"] is False

    feed = member.get(f"{API}/activity")
    assert feed.status_code == 200, feed.text
    assert [item["finding"]["public_id"] for item in feed.json()["items"]] == [barrow.public_id]

    log = client_as(moderator).get(f"{API}/mod/actions")
    assert log.status_code == 200, log.text
    assert [(item["action"], item["data"]) for item in log.json()["items"]] == [
        ("change_sensitivity", {"from": "protected", "to": DROPPED})
    ]

    # No version can store the dropped level any more.
    with pytest.raises(IntegrityError, match=CHECK), database.begin() as conn:
        conn.execute(
            text("UPDATE findings SET sensitivity = :level WHERE id = :id"),
            {
                "level": DROPPED,
                "id": barrow.id,
            },
        )


@pytest.mark.usefixtures("earlier_schema")
def test_going_back_to_the_earlier_version_s_schema_keeps_every_finding(
    database: Engine, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The earlier version's schema step, run after this one's, widens the check again and validates it."""
    make_finding(feature_class=FeatureClass.ROUND_BARROW)
    create_schema(database)
    (check,) = [
        constraint
        for constraint in Base.metadata.tables["findings"].constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == CHECK
    ]
    assert check.info["enum"] is Sensitivity
    earlier = StrEnum("EarlierSensitivity", {level: level for level in EARLIER_LEVELS})
    monkeypatch.setitem(check.info, "enum", earlier)

    create_schema(database)

    definition, validated = _check(database)
    assert f"'{DROPPED}'" in definition
    assert validated
    monkeypatch.undo()
