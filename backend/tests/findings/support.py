"""Helpers for the findings tests. Import as `from tests.findings.support import ...`."""

from __future__ import annotations

import math
from typing import Any

from geoalchemy2.shape import to_shape
from pyproj import Geod
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Finding, FindingShapeChange, User
from fieldclub.services import findings, review, shapes
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


# --------------------------------------------------------------------------
# Lines and shapes
# --------------------------------------------------------------------------

GEOD = Geod(ellps="WGS84")
# Degrees of longitude per degree of latitude at LAT, near enough.
K = math.cos(math.radians(LAT))


def path(*points: tuple[float, float], kind: str = "corner", closed: bool = False) -> shapes.Path:
    return shapes.read_path(
        {"closed": closed, "points": [{"lon": lon, "lat": lat, "kind": kind} for lon, lat in points]}
    )


def meridian(*lats: float, lon: float = LON) -> shapes.Path:
    """Corners up a meridian at these offsets from LAT."""
    return path(*((lon, LAT + offset) for offset in lats))


def east(metres: float, lon: float = LON, lat: float = LAT) -> float:
    lon_east, _, _ = GEOD.fwd(lon, lat, 90, metres)
    return lon_east


def drawn(db: Session, author: Any, shape: shapes.Path, **kwargs: Any) -> Finding:
    finding = findings.create_finding(db, author, path=shape, feature_class="linear", **kwargs)
    db.commit()
    return finding


def edit(db: Session, finding: Finding, actor: Any, **changes: Any) -> Finding:
    findings.update_finding(db, findings.lock(db, finding), actor, changes)
    db.commit()
    db.expire_all()
    return finding


def outline_of(finding: Finding) -> BaseGeometry:
    assert finding.outline is not None, f"{finding.public_id} has no outline"
    return to_shape(finding.outline)


def changes_of(db: Session, finding: Finding) -> list[FindingShapeChange]:
    return list(
        db.scalars(
            select(FindingShapeChange)
            .where(FindingShapeChange.finding_id == finding.id)
            .order_by(FindingShapeChange.revision)
        )
    )
