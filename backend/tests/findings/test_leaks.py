"""No route returns an exact position to a viewer who shouldn't have it (WS4 exit criterion).

Every route this track owns that returns a finding, or anything derived from
its position, is called as a signed-out visitor, a member, the finder, a
trusted member and a moderator, against an open, a protected and a
restricted finding. Each finding sits at its own point, so a response that
holds several can be checked for each one separately. The check searches the
whole response body for the exact position in every form it could take:
degrees, both grid references, and easting and northing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Activity, Finding, Notification, User
from fieldclub.services import findings, sensitivity
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Outcome, Sensitivity, Visible
from tests.findings.support import API, answer, create
from tests.helpers import MakeUser, lon_lat

VIEWERS = ("signed_out", "member", "finder", "trusted", "moderator")
LEVELS = (Sensitivity.OPEN, Sensitivity.PROTECTED, Sensitivity.RESTRICTED)

# Each level's finding has its own point, with decimals nothing else produces.
POINTS = {
    Sensitivity.OPEN: (-1.854173, 51.428637),
    Sensitivity.PROTECTED: (-1.812947, 51.402583),
    Sensitivity.RESTRICTED: (-1.776491, 51.384219),
}

# What each viewer sees on a page or the map (Decision 0005).
SEES = {
    "signed_out": {Sensitivity.OPEN},
    "member": {Sensitivity.OPEN, Sensitivity.PROTECTED},
    "finder": set(LEVELS),
    "trusted": set(LEVELS),
    "moderator": set(LEVELS),
}
# What each viewer's downloads carry: only the finder and trusted people get protected positions.
DOWNLOADS = {**SEES, "member": {Sensitivity.OPEN}}


def exact_strings(level: Sensitivity) -> list[str]:
    lon, lat = POINTS[level]
    _, easting, northing = gridref.to_grid(lon, lat)
    return [
        f"{abs(lon):.6f}",
        f"{lat:.6f}",
        gridref.to_gridref(lon, lat),
        gridref.to_gridref(lon, lat, compact=True),
        gridref.to_gridref(lon, lat, 6),
        gridref.to_gridref(lon, lat, 10),
        str(round(easting)),
        str(round(northing)),
    ]


def check(
    text: str, allowed: set[Sensitivity], present: set[Sensitivity] | None = None, *, where: str
) -> None:
    """Every level's exact position is absent unless allowed, and present where it must be."""
    for level in LEVELS:
        leaked = [s for s in exact_strings(level) if s in text]
        if level not in allowed:
            assert not leaked, f"{where}: the {level} finding's exact position leaks as {leaked}"
        elif present is not None and level in present:
            assert leaked, f"{where}: the {level} finding's exact position should be there"


@dataclass
class World:
    people: dict[str, User]
    findings: dict[Sensitivity, Finding]
    client: Callable[[str], TestClient]


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]) -> World:
    finder = make_user(handle="Finder")
    people = {
        "finder": finder,
        "member": make_user(handle="Member"),
        "trusted": make_user("trusted", handle="Trusted"),
        "moderator": make_user("moderator", handle="Moderator"),
    }
    # Two trusted helpers lift every finding to Seen, so the help-wanted list
    # offers evidence tasks, which show obscured positions.
    helpers = [make_user("trusted", handle=f"Helper{n}") for n in (1, 2)]
    made = {}
    for level, (lon, lat) in POINTS.items():
        finding = create(
            db,
            finder,
            lon=lon,
            lat=lat,
            feature_class=FeatureClass.ENCLOSURE,
            requested_sensitivity=level,
            outline=box(lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005),
            title=f"A {level} enclosure",
        )
        for helper in helpers:
            answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
        findings.add_evidence(
            db,
            findings.lock(db, finding),
            helpers[0],
            EvidenceFields(
                kind=EvidenceKind.HISTORIC_MAP,
                title="First edition map",
                url=f"https://maps.example/view?lat={lat:.6f}&lon={lon:.6f}",
            ),
        )
        findings.add_evidence(
            db,
            findings.lock(db, finding),
            helpers[1],
            EvidenceFields(
                kind=EvidenceKind.FIELD_VISIT,
                # Inconclusive, so the finding stays at Seen and asks for desk evidence.
                outcome=Outcome.INCONCLUSIVE,
                occurred_on=date(2026, 10, 1),
                reference=gridref.to_gridref(lon, lat, 10),
                note="Bank clear on the ground.",
            ),
        )
        findings.add_comment(db, finding, helpers[0], "Lovely crisp bank on the slope view.")
        db.commit()
        assert finding.sensitivity == level.value
        assert finding.tier == "seen"
        made[level] = finding

    def client(viewer: str) -> TestClient:
        return client_for(app, None if viewer == "signed_out" else people[viewer])

    return World(people, made, client)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_lists_and_the_map(world: World, viewer: str) -> None:
    client = world.client(viewer)
    page = client.get(f"{API}/findings")
    assert page.status_code == 200
    check(page.text, SEES[viewer], SEES[viewer], where="GET /findings")
    by_id = {item["public_id"]: item for item in page.json()["items"]}
    for level, finding in world.findings.items():
        item = by_id[finding.public_id]
        assert item["location"]["obscured"] is (level not in SEES[viewer])
        assert (item["location"]["outline"] is None) is (level not in SEES[viewer])

    geojson = client.get(f"{API}/findings", params={"bbox": "-1.9,51.35,-1.7,51.45", "format": "geojson"})
    assert geojson.status_code == 200
    check(geojson.text, SEES[viewer], SEES[viewer], where="GET /findings?format=geojson")
    features = {f["id"]: f for f in geojson.json()["features"]}
    assert set(features) == {f.public_id for f in world.findings.values()}
    for level, finding in world.findings.items():
        props = features[finding.public_id]["properties"]
        assert props["obscured"] is (level not in SEES[viewer])
        assert (props["square"] is None) is (level in SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
def test_a_box_round_the_exact_point_finds_only_what_the_viewer_may_see(
    world: World, viewer: str, level: Sensitivity
) -> None:
    """Narrowing the box on an exact point must not reveal a generalised finding."""
    lon, lat = POINTS[level]
    finding = world.findings[level]
    centre = lon_lat(finding.location_public)
    if level is not Sensitivity.OPEN:
        assert abs(centre[0] - lon) > 0.0006 or abs(centre[1] - lat) > 0.0006, (
            "the point is too near its centre"
        )
    tight = f"{lon - 0.0005},{lat - 0.0005},{lon + 0.0005},{lat + 0.0005}"
    found = world.client(viewer).get(f"{API}/findings", params={"bbox": tight, "format": "geojson"})
    ids = {f["id"] for f in found.json()["features"]}
    assert (finding.public_id in ids) is (level in SEES[viewer])
    # The square's centre finds it for everyone.
    around_centre = f"{centre[0] - 0.0005},{centre[1] - 0.0005},{centre[0] + 0.0005},{centre[1] + 0.0005}"
    found = world.client(viewer).get(f"{API}/findings", params={"bbox": around_centre, "format": "geojson"})
    ids = {f["id"] for f in found.json()["features"]}
    assert (finding.public_id in ids) is (level not in SEES[viewer] or level is Sensitivity.OPEN)


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
def test_a_finding_page(world: World, viewer: str, level: Sensitivity) -> None:
    finding = world.findings[level]
    response = world.client(viewer).get(f"{API}/findings/{finding.public_id}")
    assert response.status_code == 200
    allowed = {level} & SEES[viewer]
    check(response.text, allowed, allowed, where=f"GET /findings/{{id}} ({level})")
    body = response.json()
    assert body["location"]["obscured"] is (level not in SEES[viewer])
    for item in body["evidence"]:
        assert item["redacted"] is (level not in SEES[viewer])
        if item["redacted"]:
            assert item["url"] is item["reference"] is item["record_id"] is item["view"] is None


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("fmt", ["csv", "geojson"])
def test_downloads_of_one_finding(world: World, viewer: str, level: Sensitivity, fmt: str) -> None:
    finding = world.findings[level]
    response = world.client(viewer).get(f"{API}/findings/{finding.public_id}/export", params={"format": fmt})
    assert response.status_code == 200
    allowed = {level} & DOWNLOADS[viewer]
    check(response.text, allowed, allowed, where=f"export {fmt} ({level})")


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("fmt", ["csv", "geojson"])
def test_downloads_of_a_filtered_set(world: World, viewer: str, fmt: str) -> None:
    response = world.client(viewer).get(
        f"{API}/findings/export", params={"format": fmt, "bbox": "-1.9,51.35,-1.7,51.45"}
    )
    assert response.status_code == 200
    check(response.text, DOWNLOADS[viewer], DOWNLOADS[viewer], where=f"filtered export {fmt}")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "private, no-cache"


@pytest.mark.parametrize("viewer", VIEWERS)
def test_review_cards_are_only_for_findings_the_viewer_sees_exactly(world: World, viewer: str) -> None:
    response = world.client(viewer).get(f"{API}/review/next")
    assert response.status_code == 200
    offered = {card["public_id"] for card in response.json()["items"]}
    own = set(LEVELS) if viewer == "finder" else set()
    expected = {world.findings[level].public_id for level in SEES[viewer] - own}
    assert offered == expected
    check(response.text, SEES[viewer] - own, where="GET /review/next")


@pytest.mark.parametrize("viewer", VIEWERS)
def test_help_wanted(world: World, viewer: str) -> None:
    response = world.client(viewer).get(f"{API}/review/tasks")
    assert response.status_code == 200
    check(response.text, SEES[viewer], where="GET /review/tasks")
    strand = next(group for group in response.json()["groups"] if group["code"] == "need_strand")
    assert strand["total"] == 3
    for item in strand["items"]:
        level = next(lv for lv, f in world.findings.items() if f.public_id == item["public_id"])
        assert item["place"]["obscured"] is (level not in SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
def test_comments_and_answers_carry_no_position(world: World, viewer: str, level: Sensitivity) -> None:
    finding = world.findings[level]
    client = world.client(viewer)
    comments = client.get(f"{API}/findings/{finding.public_id}/comments")
    assert comments.status_code == 200
    check(comments.text, set(), where="comments")
    answers = client.get(f"{API}/findings/{finding.public_id}/observations")
    assert answers.status_code == (200 if viewer == "finder" else 403)
    check(answers.text, set(), where="observations")


@pytest.mark.parametrize("viewer", ["member", "trusted", "moderator"])
@pytest.mark.parametrize("level", LEVELS)
def test_writes_answer_with_what_the_writer_may_see(world: World, viewer: str, level: Sensitivity) -> None:
    finding = world.findings[level]
    client = world.client(viewer)
    allowed = {level} & SEES[viewer]

    comment = client.post(f"{API}/findings/{finding.public_id}/comments", json={"body": "Interesting."})
    assert comment.status_code == 201
    check(comment.text, set(), where="POST comment")

    evidence = client.post(
        f"{API}/findings/{finding.public_id}/evidence",
        json={"kind": "document", "title": "Parish history, page 12"},
    )
    if level in SEES[viewer]:
        assert evidence.status_code == 201
        check(evidence.text, allowed, allowed, where=f"POST evidence ({level})")
    else:
        assert evidence.status_code == 403
        assert evidence.json()["error"]["code"] == "location_hidden"
        check(evidence.text, set(), where="refused evidence")

    looked = client.put(f"{API}/findings/{finding.public_id}/observation", json={"visible": "yes"})
    if level in SEES[viewer]:
        assert looked.status_code == 200
        check(looked.text, allowed, allowed, where="reveal")
    else:
        assert looked.status_code == 403
        assert looked.json()["error"]["code"] == "location_hidden"
        check(looked.text, set(), where="refused answer")


def test_activity_and_notifications_never_hold_an_exact_position(world: World, db: Session) -> None:
    rows = db.scalars(select(Activity)).all()
    assert rows
    for row in rows:
        finding = next(f for f in world.findings.values() if f.id == row.finding_id)
        assert row.location is not None
        assert lon_lat(row.location) == pytest.approx(sensitivity.square_centre(finding), abs=1e-9)
        check(str(row.data), set(), where=f"activity {row.kind}")
    for note in db.scalars(select(Notification)).all():
        check(str(note.data), set(), where=f"notification {note.kind}")


def test_a_banned_account_sees_what_the_public_sees(world: World, db: Session) -> None:
    trusted = world.people["trusted"]
    trusted.banned_at = datetime.now(UTC)
    db.commit()
    response = world.client("trusted").get(f"{API}/findings")
    check(response.text, SEES["signed_out"], where="banned viewer")


def test_the_sql_visibility_clause_agrees_with_sees_exact(world: World, db: Session) -> None:
    """`findings.exact_clause` restates `sensitivity.sees_exact` in SQL. They must agree on every row."""
    for viewer in [None, *world.people.values()]:
        clause = findings.as_sql(findings.exact_clause(viewer))
        in_sql = set(db.scalars(select(Finding.id).where(clause)))
        in_python = {f.id for f in world.findings.values() if sensitivity.sees_exact(f, viewer)}
        assert in_sql == in_python, f"viewer {viewer}"
