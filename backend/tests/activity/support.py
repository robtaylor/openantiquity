"""Helpers for the activity and people tests. Import as `from tests.activity.support import ...`."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, Investigation, Notification, User
from fieldclub.services import findings, investigations
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, Stance, Visibility

API = "/api/v1"


def follow(db: Session, finding: Finding, *users: User) -> None:
    for user in users:
        findings.follow(db, user, finding)
    db.commit()


def add_map(db: Session, finding: Finding, user: User, **fields: Any) -> int:
    """A historic map as evidence, through the service, committed. Returns its id."""
    evidence, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        user,
        EvidenceFields(
            kind=EvidenceKind.HISTORIC_MAP,
            stance=Stance.SUPPORTS,
            url=fields.pop("url", "https://maps.example/first-edition"),
            **fields,
        ),
    )
    db.commit()
    return evidence.id


def comment(db: Session, finding: Finding, user: User, body: str = "A crisp bank on the slope view.") -> int:
    made = findings.add_comment(db, finding, user, body)
    db.commit()
    return made.id


def investigation(db: Session, owner: User, visibility: Visibility = Visibility.PUBLIC) -> Investigation:
    made = investigations.create_investigation(
        db, owner, title=f"A {visibility} survey", visibility=visibility
    )
    db.commit()
    return made


def notifications_of(db: Session, user: User) -> list[Notification]:
    db.expire_all()
    return list(
        db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id))
    )


def kinds_of(rows: list[Notification] | list[Activity]) -> list[str]:
    return [row.kind for row in rows]


def items(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.text
    return response.json()["items"]


def walk(value: Any) -> Iterator[tuple[str, Any]]:
    """Every key and value in a JSON document, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


# --------------------------------------------------------------------------
# The event stream over HTTP
# --------------------------------------------------------------------------

# How long a test waits on a real server or a stream.
TIMEOUT_S = 10.0


def read_event(lines: Iterator[str]) -> dict[str, str]:
    """The next SSE event, as its fields. Comment lines come back as `comment`."""
    fields: dict[str, str] = {}
    for line in lines:
        if line == "":
            if fields:
                return fields
            continue
        name, _, value = line.partition(":")
        fields["comment" if name == "" else name] = value.strip()
    raise AssertionError("the stream ended")


def next_activity(lines: Iterator[str]) -> dict[str, Any]:
    while True:
        fields = read_event(lines)
        if fields.get("event") == "activity":
            return {"id": fields["id"], **json.loads(fields["data"])}
