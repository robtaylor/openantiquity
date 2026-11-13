"""An investigation as GeoJSON, as a spreadsheet and as a printable report.

Positions: each finding is written by `services.exports`, so a download
carries the generalised position of a protected finding unless the person
downloading is its finder or trusted (Decision 0005, rule 8). A
finding the viewer may not see because it is hidden, and a withdrawn
finding, are left out of the GeoJSON and the spreadsheet. The report keeps a
line saying an item is no longer available, with nothing of it. Everything
else people wrote and drew goes through the investigation's `PositionGuard`
for that download rule (`services.investigations.position_guard`): when a
finding it holds is carried at its square, the title, summary, notes and
every item's text lose the positions written in them, a saved view or
height profile near that finding goes without its place, and a reference's
link that holds a position is dropped.

Licences: every record carries its source's licence and attribution
(Decision 0004). Findings, notes and everything else people wrote are under
the contribution licence.

The report is one HTML page with no scripts, no external requests and every
piece of text escaped. The investigation's notes and each item's note are
read as the notebook reads them (`services.notes_markdown`): headings,
paragraphs, lists, strong, emphasis and links, and never HTML or an image.
Links are written only for `http` and `https` addresses. The route serves
it with a sandboxing Content-Security-Policy as well, so even a slip here
could not run anything.
"""

from __future__ import annotations

import html
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.config import get_settings
from fieldclub.models import Investigation, User
from fieldclub.schemas.common import GeoJSONFeature, GeoJSONGeometry, PublicUser, geojson_point
from fieldclub.schemas.records import record_feature
from fieldclub.services import exports, investigations, notes_markdown
from fieldclub.services.investigations import ItemView, MemberView, Unavailable
from fieldclub.services.records import RecordResult
from fieldclub.vocab import CONTRIBUTION_LICENCE, FEATURE_CLASSES, PERIODS, InvestigationItemKind, Visibility

# The spreadsheet's columns: the findings export's, then what an investigation adds.
CSV_COLUMNS: tuple[str, ...] = (*exports.COLUMNS, "attribution", "source", "item_kind", "item_note")

_CLASS_LABELS = {info.id.value: info.label for info in FEATURE_CLASSES}
_PERIOD_LABELS = {info.id.value: info.label for info in PERIODS}

_UNAVAILABLE_TEXT = {
    (InvestigationItemKind.FINDING, Unavailable.HIDDEN): "A finding that a moderator has hidden.",
    (InvestigationItemKind.FINDING, Unavailable.WITHDRAWN): "A finding that its finder has withdrawn.",
    (InvestigationItemKind.FINDING, Unavailable.GONE): "A finding that no longer exists.",
    (InvestigationItemKind.RECORD, Unavailable.GONE): "A record that is no longer in the index.",
}


@dataclass(frozen=True)
class Entry:
    view: ItemView
    # The item's title and note as the download may carry them (`services.investigations.item_text`).
    title: str | None
    note: str | None
    # The download's row for a finding the viewer may see.
    finding: exports.Exported | None = None
    # A view's, reference's or profile's content as the download may carry it, None
    # for a view or profile held back near a finding carried at its square.
    data: dict[str, Any] | None = None

    @property
    def kind(self) -> InvestigationItemKind:
        return InvestigationItemKind(self.view.item.kind)


@dataclass(frozen=True)
class InvestigationExport:
    investigation: Investigation
    # The investigation's own text as the download may carry it.
    title: str
    summary: str | None
    notes: str | None
    owner: User
    members: list[MemberView]
    entries: list[Entry]
    exported_at: datetime
    url: str


def gather(
    db: Session, investigation: Investigation, viewer: User | None, *, now: datetime | None = None
) -> InvestigationExport:
    """Everything an export of `investigation` for `viewer` holds, in the notebook's order."""
    views = investigations.item_views(db, investigations.all_items(db, investigation), viewer)
    shown = [view.finding for view in views if view.finding is not None]
    rows = {item.row.openantiquity_id: item for item in exports.export_rows(db, shown, viewer)}
    guard = investigations.position_guard(db, investigation, viewer, download=True)
    entries = [
        Entry(
            view,
            *investigations.item_text(view, _reader(view, viewer), guard),
            rows[view.finding.public_id] if view.finding is not None else None,
            investigations.item_content(view.item, guard) if view.item.data is not None else None,
        )
        for view in views
    ]
    members, _ = investigations.list_members(db, investigation, limit=investigations.MAX_MEMBERS)
    owner = next(member.user for member in members if member.user.has_id(investigation.owner_id))
    base = get_settings().public_url.rstrip("/")
    return InvestigationExport(
        investigation=investigation,
        title=guard.text(investigation.title) or investigation.title,
        summary=guard.text(investigation.summary),
        notes=guard.text(investigation.notes),
        owner=owner,
        # Invitations nobody has accepted aren't part of the work.
        members=[member for member in members if member.accepted],
        entries=entries,
        exported_at=now or datetime.now(UTC),
        url=f"{base}/i/{investigation.public_id}",
    )


def _reader(view: ItemView, viewer: User | None) -> User | None:
    """Whose view of a finding item's text the download takes: stricter than the page's (Decision 0005)."""
    if view.finding is None or exports.downloads_exact(view.finding, viewer):
        return viewer
    return None


def _available(export: InvestigationExport) -> Iterator[Entry]:
    return (entry for entry in export.entries if entry.view.unavailable is None)


def _item_properties(entry: Entry) -> dict[str, Any]:
    item = entry.view.item
    return {
        "item_id": item.id,
        "item_kind": item.kind,
        "item_position": item.position,
        "item_title": entry.title,
        "item_note": entry.note,
        "item_added_by": PublicUser.from_user(entry.view.added_by).display_name,
    }


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------


def _feature(entry: Entry) -> GeoJSONFeature:
    item, view = entry.view.item, entry.view
    properties = _item_properties(entry)
    if entry.finding is not None:
        feature = exports.to_feature_collection([entry.finding]).features[0]
        feature.properties = {**feature.properties, **properties}
        return feature
    if view.record is not None:
        feature = record_feature(view.record)
        feature.properties = {**feature.properties, **properties}
        return feature
    data = entry.data or {}
    properties["licence"] = CONTRIBUTION_LICENCE
    kind = entry.kind
    if _withheld(entry):
        return GeoJSONFeature(
            id=f"item-{item.id}", geometry=None, properties={**properties, "withheld": WITHHELD}
        )
    if kind is InvestigationItemKind.VIEW:
        lon, lat = data["centre"]
        return GeoJSONFeature(
            id=f"item-{item.id}",
            geometry=geojson_point(lon, lat),
            properties={**properties, **{key: value for key, value in data.items() if key != "centre"}},
        )
    if kind is InvestigationItemKind.PROFILE:
        line = data["line"]
        return GeoJSONFeature(
            id=f"item-{item.id}",
            geometry=GeoJSONGeometry(type="LineString", coordinates=line["coordinates"]),
            properties={**properties, "samples": data.get("samples")},
        )
    return GeoJSONFeature(id=f"item-{item.id}", geometry=None, properties={**properties, **data})


# What a download says of a view or profile it leaves out.
WITHHELD = "Near a protected finding, so where it is isn't in this download."


def _withheld(entry: Entry) -> bool:
    return entry.kind in (InvestigationItemKind.VIEW, InvestigationItemKind.PROFILE) and entry.data is None


def to_geojson(export: InvestigationExport) -> dict[str, Any]:
    """A FeatureCollection of every available item in order, with the investigation as a foreign member."""
    investigation = export.investigation
    return {
        "type": "FeatureCollection",
        "investigation": {
            "public_id": investigation.public_id,
            "title": export.title,
            "summary": export.summary,
            "notes": export.notes,
            "url": export.url,
            "owner": PublicUser.from_user(export.owner).display_name,
            "exported_at": export.exported_at.isoformat(),
            "licence": CONTRIBUTION_LICENCE,
            "licence_note": (
                "Findings, notes and other contributions are under "
                f"{CONTRIBUTION_LICENCE}. Each record carries its own source's licence and attribution."
            ),
        },
        "features": [_feature(entry).model_dump(mode="json") for entry in _available(export)],
    }


# --------------------------------------------------------------------------
# Spreadsheet
# --------------------------------------------------------------------------


def _record_row(result: RecordResult) -> dict[str, Any]:
    record, source = result.record, result.source
    precision = record.precision_m
    digits = 4 if precision is not None and precision >= 1000 else 8
    try:
        system, easting, northing = gridref.to_grid(result.lon, result.lat)
        reference: str | None = gridref.to_gridref(result.lon, result.lat, digits)
    except gridref.GridRefError:
        system, easting, northing, reference = None, None, None, None
    when = record.source_updated_at or record.ingested_at
    return {
        "name": record.name,
        "grid_reference": reference,
        "easting": round(easting) if easting is not None else None,
        "northing": round(northing) if northing is not None else None,
        "grid": system.value if system is not None else None,
        "monument_type": "; ".join(record.monument_types or []) or record.record_type or "",
        "period": "; ".join(record.periods or []),
        "description": record.summary or "",
        "evidence_summary": "",
        "compiler": source.publisher,
        "date": when.date().isoformat(),
        "licence": source.licence,
        "openantiquity_id": f"{record.source_key}:{record.external_id}",
        "url": record.url or "",
        "tier": "",
        "position_precision_m": round(precision) if precision is not None else None,
        "shape_kind": None,
        "shape_length_m": None,
        "attribution": source.attribution,
        "source": source.name,
    }


def _csv_row(entry: Entry) -> list[Any] | None:
    item = entry.view.item
    if entry.finding is not None:
        row = asdict(entry.finding.row)
        row |= {"attribution": f"{row['compiler']}, OpenAntiquity", "source": "OpenAntiquity"}
    elif entry.view.record is not None:
        row = _record_row(entry.view.record)
    else:
        return None
    row |= {"item_kind": item.kind, "item_note": entry.note}
    assert set(row) == set(CSV_COLUMNS), f"columns differ: {set(row) ^ set(CSV_COLUMNS)}"
    return [row[column] for column in CSV_COLUMNS]


def to_csv(export: InvestigationExport) -> str:
    """One row per finding and record, in the notebook's order, with HER field names."""
    rows = (row for entry in _available(export) if (row := _csv_row(entry)) is not None)
    return exports.csv_table(CSV_COLUMNS, rows)


# --------------------------------------------------------------------------
# The printable report
# --------------------------------------------------------------------------

# The page may load nothing and run nothing. Inline styles only.
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

_STYLE = """
body { font: 11pt/1.45 Georgia, "Times New Roman", serif; color: #1f1d1a; background: #fff;
  max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.8rem; margin: 0.2rem 0 0.4rem; }
h2 { font-size: 1.2rem; border-bottom: 1px solid #c9c2b6; padding-bottom: 0.2rem; margin-top: 2rem; }
h3 { font-size: 1.05rem; margin: 0 0 0.3rem; }
.kicker, .meta, .kind { font: 0.8rem/1.4 system-ui, sans-serif; color: #5c574f; }
.kind { text-transform: uppercase; letter-spacing: 0.05em; }
.text { white-space: pre-wrap; }
.notes > :first-child, .note > :first-child { margin-top: 0; }
.notes h3, .notes h4, .notes h5, .note h4, .note h5, .note h6 { font-size: 1rem; margin: 0.8rem 0 0.2rem; }
ol.items { list-style: none; padding: 0; }
ol.items > li { border-top: 1px solid #e3ded5; padding: 0.8rem 0; break-inside: avoid; }
.unavailable { color: #5c574f; font-style: italic; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.1rem 0.8rem; margin: 0.3rem 0; }
dt { color: #5c574f; }
dd { margin: 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; border-bottom: 1px solid #e3ded5; padding: 0.25rem 0.4rem; vertical-align: top; }
a { color: #2d4f7c; }
@media print { body { margin: 0; } a { color: inherit; } }
"""


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _link(url: str | None, label: str | None = None) -> str:
    """A link for an http or https address, otherwise the text alone."""
    if not url:
        return _e(label)
    if not url.lower().startswith(("https://", "http://")):
        return _e(label or url)
    return f'<a href="{_e(url)}">{_e(label or url)}</a>'


def _place(lon: float, lat: float) -> str:
    try:
        return gridref.to_gridref(lon, lat)
    except gridref.GridRefError:
        return f"{lat:.5f}, {lon:.5f}"


def _pairs(pairs: list[tuple[str, str]]) -> str:
    """A definition list. Values are HTML already escaped by the caller."""
    rows = "".join(f"<dt>{_e(name)}</dt><dd>{value}</dd>" for name, value in pairs if value)
    return f"<dl>{rows}</dl>" if rows else ""


def _finding_html(entry: Entry) -> tuple[str, str]:
    assert entry.finding is not None, "only a finding the viewer may see has a row"
    assert entry.view.finding is not None
    row, where, finding = entry.finding.row, entry.finding.location, entry.view.finding
    position = row.grid_reference or _place(where.lon, where.lat)
    if where.obscured:
        position += " (the 1 km square only: the exact position isn't in this download)"
    body = _pairs(
        [
            ("Feature", _e(_CLASS_LABELS[finding.feature_class])),
            ("Period", _e(_PERIOD_LABELS[finding.period])),
            ("Confidence", _e(row.tier)),
            ("Position", _e(position)),
            ("Marked by", _e(row.compiler)),
            ("Description", f'<span class="text">{_e(row.description)}</span>' if row.description else ""),
            ("Evidence", _e(row.evidence_summary)),
            ("Page", _link(row.url)),
            ("Licence", _e(row.licence)),
        ]
    )
    return row.name, body


def _record_html(result: RecordResult) -> tuple[str, str]:
    record, source = result.record, result.source
    body = _pairs(
        [
            ("Type", _e(record.record_type or "; ".join(record.monument_types or []))),
            ("Periods", _e("; ".join(record.periods or []))),
            ("Position", _e(_place(result.lon, result.lat))),
            ("Summary", f'<span class="text">{_e(record.summary)}</span>' if record.summary else ""),
            ("Source", _link(source.homepage, source.name)),
            ("Record", _link(record.url, record.external_id)),
            ("Licence", _link(source.licence_url, source.licence)),
            ("Attribution", _e(source.attribution)),
        ]
    )
    return record.name, body


def _other_html(entry: Entry) -> tuple[str, str]:
    data = entry.data or {}
    kind = entry.kind
    default = {InvestigationItemKind.VIEW: "Saved map view", InvestigationItemKind.PROFILE: "Height profile"}
    if _withheld(entry):
        return default[kind], f'<p class="unavailable">{_e(WITHHELD)}</p>'
    if kind is InvestigationItemKind.VIEW:
        lon, lat = data["centre"]
        layers = " compared with ".join(_e(data[key]) for key in ("layer", "compare_layer") if data.get(key))
        return "Saved map view", _pairs(
            [("Centre", _e(_place(lon, lat))), ("Zoom", _e(data.get("zoom"))), ("Layer", layers)]
        )
    if kind is InvestigationItemKind.PROFILE:
        points = data["line"]["coordinates"]
        return "Height profile", _pairs(
            [("From", _e(_place(*points[0]))), ("To", _e(_place(*points[-1]))), ("Points", _e(len(points)))]
        )
    if kind is InvestigationItemKind.REFERENCE:
        return "Reference", _pairs([("Citation", _e(data.get("citation"))), ("Link", _link(data.get("url")))])
    return "Note", ""


_KIND_LABELS = {
    InvestigationItemKind.FINDING: "Finding",
    InvestigationItemKind.RECORD: "Record",
    InvestigationItemKind.VIEW: "Map view",
    InvestigationItemKind.NOTE: "Note",
    InvestigationItemKind.REFERENCE: "Reference",
    InvestigationItemKind.PROFILE: "Height profile",
}


def _item_html(entry: Entry) -> str:
    view = entry.view
    label = f'<p class="kind">{_e(_KIND_LABELS[entry.kind])}</p>'
    if view.unavailable is not None:
        title = f"<h3>{_e(entry.title)}</h3>" if entry.title else ""
        why = _UNAVAILABLE_TEXT[entry.kind, view.unavailable]
        return f'<li>{label}{title}<p class="unavailable">{_e(why)}</p></li>'
    if entry.finding is not None:
        default, body = _finding_html(entry)
    elif view.record is not None:
        default, body = _record_html(view.record)
    else:
        default, body = _other_html(entry)
    heading = entry.title or default
    # Under the item's h3, so a note's own headings start at h4, as on the notebook's page.
    note = f'<div class="note">{notes_markdown.render(entry.note, 4)}</div>' if entry.note else ""
    added = PublicUser.from_user(view.added_by).display_name
    return f'<li>{label}<h3>{_e(heading)}</h3>{body}{note}<p class="meta">Added by {_e(added)}</p></li>'


def _licences_html(export: InvestigationExport) -> str:
    sources = {}
    for entry in _available(export):
        if entry.view.record is not None:
            sources[entry.view.record.source.key] = entry.view.record.source
    rows = "".join(
        f"<tr><td>{_e(source.name)}</td><td>{_link(source.licence_url, source.licence)}</td>"
        f"<td>{_e(source.attribution)}</td></tr>"
        for source in sorted(sources.values(), key=lambda source: source.name)
    )
    table = (
        "<table><thead><tr><th>Source</th><th>Licence</th><th>Attribution</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        if rows
        else ""
    )
    return (
        "<section><h2>Licences and attribution</h2>"
        "<p>Findings, notes and everything else contributed to OpenAntiquity are under "
        f"{_e(CONTRIBUTION_LICENCE)}. "
        "Records keep their own source's licence and attribution, listed here.</p>"
        f"{table}</section>"
    )


def to_html(export: InvestigationExport) -> str:
    """The investigation as one printable, self-contained HTML page."""
    investigation = export.investigation
    others = [member for member in export.members if not member.user.has_id(investigation.owner_id)]
    people = PublicUser.from_user(export.owner).display_name
    if others:
        people += ", with " + ", ".join(PublicUser.from_user(member.user).display_name for member in others)
    visibility = {
        Visibility.PUBLIC: "Public",
        Visibility.UNLISTED: "Unlisted",
        Visibility.PRIVATE: "Private",
    }[Visibility(investigation.visibility)]
    summary = f'<p class="text">{_e(export.summary)}</p>' if export.summary else ""
    notes = (
        # Under the section's h2, so a note's own headings start at h3.
        f'<section><h2>Notes</h2><div class="notes">{notes_markdown.render(export.notes, 3)}</div></section>'
        if export.notes
        else ""
    )
    items = "".join(_item_html(entry) for entry in export.entries)
    items_html = f'<section><h2>Items</h2><ol class="items">{items}</ol></section>' if items else ""
    return (
        "<!doctype html>"
        '<html lang="en-GB"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{_e(REPORT_CSP)}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        f"<title>{_e(export.title)} - OpenAntiquity</title>"
        f"<style>{_STYLE}</style></head><body>"
        '<header><p class="kicker">OpenAntiquity investigation</p>'
        f"<h1>{_e(export.title)}</h1>{summary}"
        f'<p class="meta">By {_e(people)}. {_e(visibility)}. '
        f"Exported {_e(export.exported_at.strftime('%d %B %Y'))} from {_link(export.url)}.</p></header>"
        f"{notes}{items_html}{_licences_html(export)}"
        "</body></html>"
    )
