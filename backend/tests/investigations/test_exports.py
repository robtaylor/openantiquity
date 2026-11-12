"""Investigation exports: what each format holds, licences, and a report that hostile text can't break."""

from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import Investigation, User
from fieldclub.services import exports, investigation_exports
from fieldclub.vocab import FindingState, InvestigationItemKind, Visibility
from tests.helpers import ClientAs, MakeFinding, MakeUser, add_record, add_source
from tests.investigations.support import PROFILE, REFERENCE, VIEW, add, make, url

KIND = InvestigationItemKind


@pytest.fixture
def notebook(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> tuple[Investigation, User]:
    owner = make_user(handle="Owner", display_name="Ann Owner")
    investigation = make(db, owner, Visibility.PUBLIC, summary="Round the henge", notes="Start at the bank.")
    finding = make_finding(title="Ring ditch")
    hidden = make_finding(title="Hidden barrow")
    withdrawn = make_finding(title="Withdrawn enclosure")
    open_source = add_source(db)
    restricted_source = add_source(
        db,
        "nc-source",
        name="Lost villages",
        licence="CC BY-NC-SA 4.0",
        licence_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        attribution="Beresford's Lost Villages",
        reuse="non_commercial",
        homepage="https://example.org/villages",
    )
    henge = add_record(
        db, open_source, "Avebury henge", -1.8542, 51.4286, monument_types=["HENGE"], periods=["NEOLITHIC"]
    )
    village = add_record(db, restricted_source, "West Kennet village", -1.84, 51.41, precision_m=1000)
    db.commit()
    add(db, investigation, owner, kind=KIND.FINDING, finding=finding.public_id, note="Clear on slope")
    add(db, investigation, owner, kind=KIND.FINDING, finding=hidden.public_id)
    add(db, investigation, owner, kind=KIND.FINDING, finding=withdrawn.public_id)
    add(db, investigation, owner, kind=KIND.RECORD, record_id=henge.id)
    add(db, investigation, owner, kind=KIND.RECORD, record_id=village.id, note="Deserted")
    add(db, investigation, owner, kind=KIND.VIEW, title="South view", data=VIEW)
    add(db, investigation, owner, kind=KIND.NOTE, note="Ask the landowner.")
    add(db, investigation, owner, kind=KIND.REFERENCE, title="Avebury", data=REFERENCE)
    add(db, investigation, owner, kind=KIND.PROFILE, data=PROFILE)
    hidden.hidden_at = datetime(2026, 11, 10, tzinfo=UTC)
    withdrawn.state = FindingState.WITHDRAWN.value
    db.commit()
    return investigation, owner


def test_geojson_holds_every_available_item_with_its_licence(
    notebook: tuple[Investigation, User], client: TestClient
) -> None:
    investigation, _ = notebook
    response = client.get(url(investigation, "/export"), params={"format": "geojson"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geo+json"
    name = f"openantiquity-investigation-{investigation.public_id}.geojson"
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'
    body = response.json()
    assert body["investigation"]["title"] == "Parish survey"
    assert body["investigation"]["licence"] == "CC BY 4.0"
    features = body["features"]
    assert [f["properties"]["item_kind"] for f in features] == [
        "finding",
        "record",
        "record",
        "view",
        "note",
        "reference",
        "profile",
    ]
    finding, henge, village, view, note, reference, profile = features
    assert finding["properties"]["name"] == "Ring ditch"
    assert finding["properties"]["licence"] == "CC BY 4.0"
    assert finding["properties"]["item_note"] == "Clear on slope"
    assert (henge["properties"]["licence"], henge["properties"]["attribution"]) == (
        "Open Government Licence v3.0",
        "© The test suite 2026",
    )
    assert village["properties"]["licence"] == "CC BY-NC-SA 4.0"
    assert village["properties"]["reuse"] == "non_commercial"
    assert village["properties"]["attribution"] == "Beresford's Lost Villages"
    assert view["geometry"] == {"type": "Point", "coordinates": VIEW["centre"]}
    assert note["geometry"] is None
    assert note["properties"]["item_note"] == "Ask the landowner."
    assert reference["properties"]["citation"] == REFERENCE["citation"]
    assert profile["geometry"]["type"] == "LineString"
    assert "Hidden barrow" not in response.text
    assert "Withdrawn enclosure" not in response.text


def test_the_spreadsheet_uses_her_field_names_and_states_each_licence(
    notebook: tuple[Investigation, User], client: TestClient
) -> None:
    investigation, _ = notebook
    response = client.get(url(investigation, "/export"), params={"format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert list(rows[0]) == list(investigation_exports.CSV_COLUMNS)
    assert set(exports.COLUMNS) <= set(rows[0])
    assert [row["name"] for row in rows] == ["Ring ditch", "Avebury henge", "West Kennet village"]
    finding, henge, village = rows
    assert finding["licence"] == "CC BY 4.0"
    assert finding["monument_type"] == "ENCLOSURE"
    assert finding["item_note"] == "Clear on slope"
    assert henge["licence"] == "Open Government Licence v3.0"
    assert henge["attribution"] == "© The test suite 2026"
    assert henge["monument_type"] == "HENGE"
    assert henge["grid_reference"].startswith("SU ")
    assert len(henge["grid_reference"].replace(" ", "")) == 10
    assert village["licence"] == "CC BY-NC-SA 4.0"
    assert village["source"] == "Lost villages"
    # Published to a 1 km square, so written as one.
    assert len(village["grid_reference"].replace(" ", "")) == 6
    assert village["position_precision_m"] == "1000"


def test_a_spreadsheet_cell_that_would_run_as_a_formula_is_escaped(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs
) -> None:
    owner = make_user()
    investigation = make(db, owner)
    finding = make_finding(title='=HYPERLINK("https://evil.example")')
    add(db, investigation, owner, kind=KIND.FINDING, finding=finding.public_id, note="+SUM(A1)")
    rows = list(
        csv.DictReader(io.StringIO(client_as(owner).get(url(investigation, "/export?format=csv")).text))
    )
    assert rows[0]["name"].startswith("'=")
    assert rows[0]["item_note"] == "'+SUM(A1)"


def test_the_report_is_one_page_with_every_item(
    notebook: tuple[Investigation, User], client: TestClient
) -> None:
    investigation, _ = notebook
    response = client.get(url(investigation, "/export"), params={"format": "html"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "OpenAntiquity" in response.text
    assert "Field Club" not in response.text
    page = response.text
    for text in (
        "Parish survey",
        "Round the henge",
        "Start at the bank.",
        "Ring ditch",
        "Avebury henge",
        "Ask the landowner.",
        "Smith, J. 1888",
        "A finding that a moderator has hidden.",
        "A finding that its finder has withdrawn.",
        "CC BY-NC-SA 4.0",
        "Beresford&#x27;s Lost Villages",
        "By Ann Owner",
    ):
        assert text in page, text
    assert "Hidden barrow" not in page
    assert "Withdrawn enclosure" not in page


# --------------------------------------------------------------------------
# Hostile text
# --------------------------------------------------------------------------

HOSTILE = [
    '<script>alert("title")</script>',
    '"><img src=x onerror=alert(1)>',
    "</style><script>alert(2)</script>",
    "<iframe src=//evil.example></iframe>",
    "<a href=javascript:alert(3)>click</a>",
    "' onmouseover='alert(4)",
]

ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "header", "section", "h1", "h2", "h3", "p",
    "ol", "li", "dl", "dt", "dd", "span", "div", "a", "table", "thead", "tbody", "tr", "th", "td",
}  # fmt: skip


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str | None]] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.extend(attrs)
        self.hrefs.extend(value or "" for name, value in attrs if name == "href")


def test_the_report_escapes_hostile_titles_and_notes(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs
) -> None:
    owner = make_user()
    investigation = make(
        db, owner, Visibility.PUBLIC, title=HOSTILE[0], summary=HOSTILE[1], notes="\n".join(HOSTILE)
    )
    finding = make_finding(title=HOSTILE[2], description=HOSTILE[3])
    record = add_record(
        db, add_source(db, attribution=HOSTILE[4], licence=HOSTILE[5]), HOSTILE[1], -1.85, 51.43
    )
    db.commit()
    add(
        db,
        investigation,
        owner,
        kind=KIND.FINDING,
        finding=finding.public_id,
        title=HOSTILE[4],
        note=HOSTILE[0],
    )
    add(db, investigation, owner, kind=KIND.RECORD, record_id=record.id, note=HOSTILE[3])
    add(db, investigation, owner, kind=KIND.NOTE, title=HOSTILE[5], note="\n".join(HOSTILE))
    hostile_ref = {"url": "https://example.org/?q=%22%3E%3Cscript%3E", "citation": HOSTILE[2]}
    add(db, investigation, owner, kind=KIND.REFERENCE, title=HOSTILE[1], data=hostile_ref)
    add(db, investigation, owner, kind=KIND.VIEW, title=HOSTILE[0], data=VIEW | {"layer": "composite"})
    page = client_as(owner).get(url(investigation, "/export"), params={"format": "html"}).text

    parser = Tags()
    parser.feed(page)
    assert set(parser.tags) <= ALLOWED_TAGS, set(parser.tags) - ALLOWED_TAGS
    assert parser.tags.count("style") == 1
    assert not [name for name, _ in parser.attributes if name.startswith("on")]
    assert all(href.startswith(("https://", "http://")) for href in parser.hrefs), parser.hrefs
    lowered = page.lower()
    assert "<script" not in lowered
    assert "<iframe" not in lowered
    assert "<img" not in lowered
    assert "javascript:" not in [href.lower()[:11] for href in parser.hrefs]
    assert "&lt;script&gt;alert(&quot;title&quot;)&lt;/script&gt;" in page
    assert "&lt;/style&gt;" in page


# --------------------------------------------------------------------------
# Notes in Markdown
# --------------------------------------------------------------------------

MARKDOWN_NOTES = """# The parish

A **bank** with a *faint* ditch. See [the HER](https://example.org/her?id=1&x=2).

- first
- second

1. one
2. two

[a script](javascript:alert(1)) ![a photo](https://example.org/photo.jpg) <b onclick=alert(2)>bold</b>
"""


def test_the_report_reads_notes_as_the_notebook_does(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs
) -> None:
    owner = make_user()
    investigation = make(db, owner, Visibility.PUBLIC, notes=MARKDOWN_NOTES)
    add(db, investigation, owner, kind=KIND.NOTE, note="## Later\n\nAsk **again**.")
    response = client_as(owner).get(url(investigation, "/export"), params={"format": "html"})
    page = response.text
    # The page keeps its policy: no scripts, no requests, no images, in a sandbox.
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "sandbox" in policy
    assert html.escape(investigation_exports.REPORT_CSP, quote=True) in page
    # Notes sit under the section's h2, an item's note under the item's h3.
    assert "<h3>The parish</h3>" in page
    assert "<h5>Later</h5>" in page
    assert "A <strong>bank</strong> with a <em>faint</em> ditch." in page
    assert (
        '<a href="https://example.org/her?id=1&amp;x=2" '
        'rel="noopener noreferrer external nofollow">the HER</a>' in page
    )
    assert "<ul><li>first</li><li>second</li></ul><ol><li>one</li><li>two</li></ol>" in page
    assert "Ask <strong>again</strong>." in page
    parser = Tags()
    parser.feed(page)
    assert set(parser.tags) <= ALLOWED_TAGS | {"h4", "h5", "ul", "strong", "em"}, (
        set(parser.tags) - ALLOWED_TAGS
    )
    assert "img" not in parser.tags
    assert "b" not in parser.tags
    assert not [name for name, _ in parser.attributes if name.startswith("on")]
    assert all(href.startswith(("https://", "http://")) for href in parser.hrefs), parser.hrefs
    assert "&lt;b onclick=alert(2)&gt;bold&lt;/b&gt;" in page


def test_markup_in_an_item_note_cannot_show_a_hidden_position(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client: TestClient
) -> None:
    """Redaction reads the note as typed, so markup that joins figures into a position falls back to text."""
    owner = make_user()
    finding = make_finding(sensitivity="protected", title="Barrow")
    investigation = make(db, owner, Visibility.PUBLIC)
    add(
        db,
        investigation,
        owner,
        kind=KIND.FINDING,
        finding=finding.public_id,
        note="Typed SU 1234 5678 here, and *also* SU 123**456**.",
    )
    page = client.get(url(investigation, "/export"), params={"format": "html"}).text
    assert "SU 1234 5678" not in page
    assert "[position hidden] here, and *also* SU 123**456**." in page
    assert "<strong>456</strong>" not in page
