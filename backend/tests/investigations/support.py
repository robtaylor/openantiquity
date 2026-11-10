"""Helpers for the investigation tests. Import as `from tests.investigations.support import ...`."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Investigation, InvestigationItem, User
from fieldclub.services import investigations
from fieldclub.services.investigations import Need, NewItem
from fieldclub.vocab import InvestigationItemKind, InvestigationRole, Visibility

API = "/api/v1"

VIEW = {"centre": [-1.8542, 51.4286], "zoom": 16, "layer": "composite"}
REFERENCE = {"url": "https://example.org/avebury", "citation": "Smith, J. 1888. Avebury. London."}
PROFILE = {"line": {"type": "LineString", "coordinates": [[-1.855, 51.428], [-1.853, 51.429]]}, "samples": 50}


def url(investigation: Investigation, suffix: str = "") -> str:
    return f"{API}/investigations/{investigation.public_id}{suffix}"


def make(
    db: Session,
    owner: User,
    visibility: Visibility | str = Visibility.PUBLIC,
    *,
    members: dict[InvestigationRole, list[User]] | None = None,
    **columns: Any,
) -> Investigation:
    """A committed investigation, with the members given."""
    columns.setdefault("title", "Parish survey")
    investigation = investigations.create_investigation(db, owner, visibility=visibility, **columns)
    for role, people in (members or {}).items():
        for person in people:
            investigations.add_member(db, investigation, person, role)
    db.commit()
    return investigation


def add(db: Session, investigation: Investigation, user: User, **fields: Any) -> InvestigationItem:
    """A committed item added through the service. A note unless told otherwise."""
    fields.setdefault("kind", InvestigationItemKind.NOTE)
    if fields["kind"] is InvestigationItemKind.NOTE:
        fields.setdefault("note", "A line of notes.")
    access = investigations.load(db, investigation.public_id, user, Need.EDIT, lock=True)
    item = investigations.add_item(db, access, user, NewItem(**fields))
    db.commit()
    return item


def order(db: Session, investigation: Investigation) -> list[int]:
    """Item ids in their order."""
    db.expire_all()
    return list(
        db.scalars(
            select(InvestigationItem.id)
            .where(InvestigationItem.investigation_id == investigation.id)
            .order_by(InvestigationItem.position, InvestigationItem.id)
        )
    )


def positions(db: Session, investigation: Investigation) -> list[int]:
    db.expire_all()
    return list(
        db.scalars(
            select(InvestigationItem.position)
            .where(InvestigationItem.investigation_id == investigation.id)
            .order_by(InvestigationItem.position)
        )
    )
