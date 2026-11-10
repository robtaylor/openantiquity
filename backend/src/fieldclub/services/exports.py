"""Findings as GeoJSON and as CSV in the shape a Historic Environment Record expects.

Positions: a download carries the generalised position of a protected or
restricted finding unless the person downloading is its finder or trusted
(Decision 0005, rule 8). That is stricter than the page, where any member
sees a protected finding exactly. `sensitivity.downloads_exact` is the rule,
beside the other viewer rules, and `export_location` applies it
by asking `sensitivity.visible_location` either as the viewer or as the
public, so the position itself still comes from the one function that
generalises.

The columns follow what HER officers import: a name, a grid reference with
easting and northing, the monument type as a FISH thesaurus term, the
period, a description, a summary of the evidence, who compiled it, when, and
the licence. Field Club adds its own id, address, tier and how precise the
position is.
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.config import get_settings
from fieldclub.models import Evidence, Finding, User
from fieldclub.schemas.common import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    PublicUser,
    geojson_point,
    to_geojson,
)
from fieldclub.services import findings, sensitivity
from fieldclub.services.sensitivity import downloads_exact as downloads_exact
from fieldclub.vocab import (
    CONTRIBUTION_LICENCE,
    EVIDENCE_KINDS,
    FEATURE_CLASSES,
    PERIODS,
    TIERS,
)

_FISH = {info.id.value: info.fish_term for info in FEATURE_CLASSES}
_PERIODS = {info.id.value: info.label for info in PERIODS}
_KINDS = {info.id.value: info.label for info in EVIDENCE_KINDS}
_TIERS = {info.id.value: info.label for info in TIERS}

# A spreadsheet runs a cell that starts with one of these as a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

# The most findings one download holds.
MAX_EXPORT = 5000


def export_location(finding: Finding, viewer: User | None) -> sensitivity.VisibleLocation:
    """The position a download for `viewer` carries."""
    return sensitivity.visible_location(finding, viewer if downloads_exact(finding, viewer) else None)


@dataclass(frozen=True)
class ExportRow:
    name: str
    grid_reference: str | None
    easting: int | None
    northing: int | None
    grid: str | None
    monument_type: str
    period: str
    description: str
    evidence_summary: str
    compiler: str
    date: str
    licence: str
    fieldclub_id: str
    url: str
    tier: str
    position_precision_m: int


COLUMNS: tuple[str, ...] = tuple(ExportRow.__dataclass_fields__)


@dataclass(frozen=True)
class Exported:
    row: ExportRow
    location: sensitivity.VisibleLocation


def _evidence_summary(items: Sequence[Evidence]) -> str:
    """`Aerial photo (2); Old map: OS 6-inch 1888`, counting standing items by kind."""
    counted = Counter(item.kind for item in items)
    parts = []
    for kind, number in sorted(counted.items(), key=lambda pair: _KINDS[pair[0]]):
        titled = [item.title for item in items if item.kind == kind and item.title]
        label = _KINDS[kind] + (f" ({number})" if number > 1 else "")
        parts.append(f"{label}: {', '.join(titled)}" if titled else label)
    return "; ".join(parts)


def export_rows(db: Session, chosen: Sequence[Finding], viewer: User | None) -> list[Exported]:
    """One row per finding, with the position this viewer's download may carry."""
    ids = [finding.id for finding in chosen]
    evidence: dict[int, list[Evidence]] = defaultdict(list)
    if ids:
        for item in db.scalars(
            select(Evidence)
            .where(Evidence.finding_id.in_(ids), Evidence.deleted_at.is_(None))
            .order_by(Evidence.id)
        ):
            evidence[item.finding_id].append(item)
    authors = findings.users_by_id(db, (finding.author_id for finding in chosen))
    base = get_settings().public_url.rstrip("/")
    exported = []
    for finding in chosen:
        where = export_location(finding, viewer)
        system, easting, northing = gridref.to_grid(where.lon, where.lat)
        row = ExportRow(
            name=finding.title,
            grid_reference=where.grid_ref,
            # Rounded, not truncated: a square's centre is a whole number of metres.
            easting=round(easting),
            northing=round(northing),
            grid=system.value,
            monument_type=_FISH[finding.feature_class],
            period=_PERIODS[finding.period],
            description=finding.description or "",
            evidence_summary=_evidence_summary(evidence[finding.id]),
            compiler=PublicUser.from_user(authors[finding.author_id]).display_name,
            date=finding.created_at.date().isoformat(),
            licence=CONTRIBUTION_LICENCE,
            fieldclub_id=finding.public_id,
            url=f"{base}/f/{finding.public_id}",
            tier=_TIERS[finding.tier],
            position_precision_m=1000 if where.obscured else 10,
        )
        exported.append(Exported(row, where))
    return exported


def _safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


def to_csv(rows: Sequence[Exported]) -> str:
    """A CSV with a header row. Cells that a spreadsheet would run as formulas are escaped."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for item in rows:
        writer.writerow([_safe(value) if value is not None else "" for value in asdict(item.row).values()])
    return buffer.getvalue()


def to_feature_collection(rows: Sequence[Exported]) -> GeoJSONFeatureCollection:
    """A GeoJSON FeatureCollection with the CSV's columns as properties.

    The geometry is the point the download may carry. An exact outline is
    added as the `outline` property, and never for a generalised position.
    """
    return GeoJSONFeatureCollection(
        features=[
            GeoJSONFeature(
                id=item.row.fieldclub_id,
                geometry=geojson_point(item.location.lon, item.location.lat),
                properties={
                    **asdict(item.row),
                    "obscured": item.location.obscured,
                    "outline": to_geojson(item.location.outline),
                },
            )
            for item in rows
        ]
    )
