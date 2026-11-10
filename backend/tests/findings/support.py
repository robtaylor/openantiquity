"""Helpers for the findings tests. Import as `from tests.findings.support import ...`."""

from __future__ import annotations

from typing import Any

from shapely.geometry import Point
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.services import findings, review
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Relation, Stance, Visible

API = "/api/v1"

# A point near Avebury.
LON, LAT = -1.854173, 51.428637


def point(lon: float = LON, lat: float = LAT) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [lon, lat]}


def square_around(lon: float = LON, lat: float = LAT, half: float = 0.0004) -> dict[str, Any]:
    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
    ]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def create(
    db: Session,
    author: User,
    *,
    lon: float = LON,
    lat: float = LAT,
    feature_class: FeatureClass | str = FeatureClass.ENCLOSURE,
    **kwargs: Any,
) -> Finding:
    """A finding made through the service, committed."""
    finding = findings.create_finding(
        db, author, location=Point(lon, lat), feature_class=feature_class, **kwargs
    )
    db.commit()
    return finding


def answer(db: Session, finding: Finding, user: User, visible: Visible | str = Visible.YES, **kwargs: Any):
    """A second look through the service, committed."""
    result = review.put_observation(db, finding, user, review.Answer(visible=Visible(visible), **kwargs))
    db.commit()
    return result


def add_desk_evidence(
    db: Session, finding: Finding, user: User, kind: EvidenceKind = EvidenceKind.AERIAL, **kwargs: Any
):
    """Supporting desk evidence of a kind that needs only a link."""
    fields: dict[str, Any] = {"url": "https://example.org/evidence"}
    if kind is EvidenceKind.RECORD_LINK:
        fields = {"reference": "MWI1234", "url": "https://example.org/record", "relation": Relation.RELATED}
    if kind is EvidenceKind.LIDAR_VIEW:
        fields = {"view": {"layer": "slope", "zoom": 16}}
    fields.update(kwargs)
    evidence, result = findings.add_evidence(
        db, findings.lock(db, finding), user, EvidenceFields(kind=kind, stance=Stance.SUPPORTS, **fields)
    )
    db.commit()
    return evidence, result
