"""No route returns an exact position to a viewer who shouldn't have it (WS4 exit criterion).

Every route that returns a finding, or anything derived from its position,
is called as a signed-out visitor, a member, the finder, a
trusted member and a moderator, against an open, a protected and a
restricted finding drawn as an area, and one drawn as a line and extended.
Each finding sits at its own point, so a response that holds several can be
checked for each one separately. The check searches the whole response body
for the exact position in every form it could take: degrees, both grid
references, and easting and northing, and for a line every point it was
drawn through, the view framing its extension and its length.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Activity, Finding, Notification, User
from fieldclub.models.common import db_point
from fieldclub.services import findings, sensitivity, shapes
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Outcome, Relation, Sensitivity, Stance, Visible
from tests import leak_record
from tests.findings.support import API, answer, create, outline_of
from tests.helpers import MakeUser, add_record, add_source, lon_lat

VIEWERS = ("signed_out", "member", "finder", "trusted", "moderator")
LEVELS = (Sensitivity.OPEN, Sensitivity.PROTECTED, Sensitivity.RESTRICTED)

# Each level's finding has its own point, with decimals nothing else produces.
POINTS = {
    Sensitivity.OPEN: (-1.854173, 51.428637),
    Sensitivity.PROTECTED: (-1.812947, 51.402583),
    Sensitivity.RESTRICTED: (-1.776491, 51.384219),
}

# Each level's line: three points drawn first, with the anchor half way along
# them (`ANCHORS`), and a fourth added later. None is near anything else in the tests.
LINES = {
    Sensitivity.OPEN: (
        (-1.887412, 51.437218), (-1.871936, 51.431574), (-1.856283, 51.425961), (-1.840617, 51.420337),
    ),
    Sensitivity.PROTECTED: (
        (-1.846159, 51.415382), (-1.830694, 51.409741), (-1.815228, 51.404107), (-1.799763, 51.398462),
    ),
    Sensitivity.RESTRICTED: (
        (-1.790384, 51.396152), (-1.774917, 51.390518), (-1.759452, 51.384873), (-1.743986, 51.379238),
    ),
}  # fmt: skip


def line_path(level: Sensitivity, *, extended: bool) -> shapes.Path:
    points = LINES[level] if extended else LINES[level][:3]
    return shapes.read_path({"points": [{"lon": lon, "lat": lat, "kind": "corner"} for lon, lat in points]})


def _anchor(level: Sensitivity) -> tuple[float, float]:
    anchor = shapes.derived_anchor(shapes.shape_of(line_path(level, extended=False)))
    return anchor.x, anchor.y


# Where the server places each level's line when it is drawn, half way along its first three points.
ANCHORS = {level: _anchor(level) for level in LINES}


def draw_line(db: Session, finder: User, level: Sensitivity) -> Finding:
    """The level's line, drawn by `finder` with no point, so the server places its anchor. Committed."""
    finding = findings.create_finding(
        db,
        finder,
        path=line_path(level, extended=False),
        feature_class=FeatureClass.ROAD,
        requested_sensitivity=level,
        title=f"A {level} road",
    )
    db.commit()
    assert lon_lat(finding.location) == ANCHORS[level], "the anchor is half way along"
    leak_record.built(finding.public_id)
    return finding


def extend_line(db: Session, finder: User, finding: Finding, level: Sensitivity) -> None:
    findings.update_finding(
        db, findings.lock(db, finding), finder, {"path": line_path(level, extended=True), "path_revision": 0}
    )
    db.commit()
    assert lon_lat(finding.location) == ANCHORS[level], "extending keeps the anchor"
    if finding.added_view is not None:
        ADDED_VIEWS[level] = finding.added_view


# The view that frames what each level's line added beyond its second looks, once it is extended.
ADDED_VIEWS: dict[Sensitivity, dict] = {}


def _line_strings(level: Sensitivity) -> list[str]:
    """What only someone who sees the level's line exactly may read of it, beyond its anchor."""
    drawn, extended = (shapes.shape_of(line_path(level, extended=e)) for e in (False, True))
    view = shapes.added_view(drawn.path, extended.path)
    assert view is not None, "the fourth point extends the line"
    found = [f"{abs(lon):.6f}" for lon, _ in LINES[level]] + [f"{lat:.6f}" for _, lat in LINES[level]]
    found += [f"{abs(view['lon'])}", f"{view['lat']}"]
    if (beyond := ADDED_VIEWS.get(level)) is not None:
        found += [f"{abs(beyond['lon'])}", f"{beyond['lat']}"]
    # Its length, and what the extension added, as whole metres and the point after them.
    found += [f"{int(extended.length_m)}.", f"{int(extended.length_m - drawn.length_m)}."]
    return found


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


def _point_strings(lon: float, lat: float) -> list[str]:
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


def exact_strings(level: Sensitivity) -> list[str]:
    """The level's area finding's exact point, and its line's anchor, points, view and length."""
    return [*_point_strings(*POINTS[level]), *_point_strings(*ANCHORS[level]), *_line_strings(level)]


# The time of day in an ISO timestamp, down to its fraction of a second.
_TIMES = re.compile(r"\d{2}:\d{2}:\d{2}\.\d+")


def check(
    text: str, allowed: set[Sensitivity], present: set[Sensitivity] | None = None, *, where: str
) -> None:
    """Every level's exact position is absent unless allowed, and present where it must be.

    Times are taken out first: a timestamp such as `11:07:51.776491` carries no
    position, but its seconds can spell one, which made this check fail at random.
    """
    leak_record.checked(text, {level.value for level in LEVELS if level not in allowed})
    text = _TIMES.sub("", text)
    for level in LEVELS:
        leaked = [s for s in exact_strings(level) if s in text]
        if level not in allowed:
            assert not leaked, f"{where}: the {level} finding's exact position leaks as {leaked}"
        elif present is not None and level in present:
            assert leaked, f"{where}: the {level} finding's exact position should be there"


def checked_unlisted(response: object, world: World, seen: set[Sensitivity]) -> None:
    """Say that `response`, already checked, was checked against each line it leaves out.

    For a response that lists only what the viewer sees exactly, so it never
    names a line seen only as its square (`tests.leak_record.checked_response`).
    """
    for level, line in world.lines.items():
        if level not in seen:
            leak_record.checked_response(response, line.public_id)


KINDS = ("area", "line")


@dataclass
class World:
    people: dict[str, User]
    # Each level's finding drawn as an area.
    findings: dict[Sensitivity, Finding]
    client: Callable[[str], TestClient]
    # Each level's finding drawn as a line, answered and then extended.
    lines: dict[Sensitivity, Finding] = field(default_factory=dict)

    def of(self, kind: str, level: Sensitivity) -> Finding:
        return (self.findings if kind == "area" else self.lines)[level]

    def every(self) -> list[tuple[Sensitivity, Finding]]:
        return [*self.findings.items(), *self.lines.items()]


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
    made, lines = {}, {}
    for level, (lon, lat) in POINTS.items():
        made[level] = create(
            db,
            finder,
            lon=lon,
            lat=lat,
            feature_class=FeatureClass.ENCLOSURE,
            requested_sensitivity=level,
            outline=box(lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005),
            title=f"A {level} enclosure",
        )
        lines[level] = draw_line(db, finder, level)
    for level, finding in [*made.items(), *lines.items()]:
        lon, lat = lon_lat(finding.location)
        for helper in helpers:
            answer(db, finding, helper, Visible.YES, feature_class=FeatureClass(finding.feature_class))
        mapped, _ = findings.add_evidence(
            db,
            findings.lock(db, finding),
            helpers[0],
            EvidenceFields(
                kind=EvidenceKind.HISTORIC_MAP, title="First edition map", url="https://maps.example/"
            ),
        )
        # A link that gives the position is refused on a finding that isn't open, so this is one
        # added while it was open, before it was raised: those who see only the square never get it.
        mapped.url = f"https://maps.example/view?lat={lat:.6f}&lon={lon:.6f}"
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
    # Extended after the second looks, so each line asks for a look at its new part.
    for level, line in lines.items():
        extend_line(db, finder, line, level)
        assert line.tier == "seen"
        assert "look_at_new_part" in line.open_steps
        assert line.added_view is not None
        assert ADDED_VIEWS[level] == line.added_view

    def client(viewer: str) -> TestClient:
        return client_for(app, None if viewer == "signed_out" else people[viewer])

    return World(people, made, client, lines)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_lists_and_the_map(world: World, viewer: str) -> None:
    client = world.client(viewer)
    page = client.get(f"{API}/findings")
    assert page.status_code == 200
    check(page.text, SEES[viewer], SEES[viewer], where="GET /findings")
    by_id = {item["public_id"]: item for item in page.json()["items"]}
    for level, finding in world.every():
        item = by_id[finding.public_id]
        assert item["location"]["obscured"] is (level not in SEES[viewer])
        # A list carries no shape for anyone, and says what kind it is only to exact viewers.
        assert item["location"]["outline"] is None
        seen = level in SEES[viewer]
        assert item["location"]["shape_kind"] == (finding.shape_kind if seen else None)

    for zoom in (9, 13, 16):
        geojson = client.get(
            f"{API}/findings", params={"bbox": "-1.9,51.35,-1.7,51.45", "format": "geojson", "zoom": zoom}
        )
        assert geojson.status_code == 200
        check(geojson.text, SEES[viewer], SEES[viewer], where=f"GET /findings?format=geojson&zoom={zoom}")
        features = {f["id"]: f for f in geojson.json()["features"]}
        assert set(features) == {f.public_id for _, f in world.every()}
        for level, finding in world.every():
            props = features[finding.public_id]["properties"]
            assert props["obscured"] is (level not in SEES[viewer])
            assert (props["square"] is None) is (level in SEES[viewer])
            assert (props["shape"] is None) is (level not in SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
def test_a_box_on_a_line_s_far_end_finds_it_only_for_those_who_see_it_exactly(
    world: World, viewer: str, level: Sensitivity
) -> None:
    """A box matches a line by its shape only for exact viewers: for anyone else, by its square."""
    lon, lat = LINES[level][-1]
    line = world.lines[level]
    assert gridref.gridref_at(lon, lat, 4) != gridref.gridref_at(*ANCHORS[level], 4), (
        "the end is in another square"
    )
    tight = f"{lon - 0.0005},{lat - 0.0005},{lon + 0.0005},{lat + 0.0005}"
    for fmt in ("geojson", "json"):
        found = world.client(viewer).get(f"{API}/findings", params={"bbox": tight, "format": fmt})
        assert found.status_code == 200
        body = found.json()
        ids = {
            item["id"] if fmt == "geojson" else item["public_id"]
            for item in body.get("features", body.get("items", []))
        }
        assert (line.public_id in ids) is (level in SEES[viewer]), fmt
        check(found.text, SEES[viewer], where=f"a box on the {level} line's end")


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
@pytest.mark.parametrize("kind", KINDS)
def test_a_finding_page(world: World, viewer: str, level: Sensitivity, kind: str) -> None:
    finding = world.of(kind, level)
    response = world.client(viewer).get(f"{API}/findings/{finding.public_id}")
    assert response.status_code == 200
    allowed = {level} & SEES[viewer]
    check(response.text, allowed, allowed, where=f"GET /findings/{{id}} ({level} {kind})")
    body = response.json()
    assert body["location"]["obscured"] is (level not in SEES[viewer])
    shape = body["location"]["shape"]
    if level not in SEES[viewer]:
        # That the shape changed, and when, and nothing of its kind, size, place or what was added.
        assert (body["location"]["outline"], body["location"]["path"], body["location"]["shape_kind"]) == (
            None,
            None,
            None,
        )
        assert shape == {
            "kind": None,
            "length_m": None,
            "revision": None,
            "extent": None,
            "changes": [
                {"kind": "changed", "on": c["on"], "added_length_m": None, "added_view": None}
                for c in shape["changes"]
            ],
            "added_since_looked_m": None,
            "added_view": None,
            "looked_at": None,
        }
        assert "look_at_new_part" not in [step["code"] for step in body["assessment"]["next_steps"]]
        assert '"line"' not in response.text
    else:
        assert shape["kind"] == kind
        assert (shape["looked_at"] is not None) is (viewer == "finder")
    for item in body["evidence"]:
        assert item["redacted"] is (level not in SEES[viewer])
        if item["redacted"]:
            assert item["url"] is item["reference"] is item["record_id"] is item["view"] is None


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("fmt", ["csv", "geojson"])
@pytest.mark.parametrize("kind", KINDS)
def test_downloads_of_one_finding(world: World, viewer: str, level: Sensitivity, fmt: str, kind: str) -> None:
    finding = world.of(kind, level)
    response = world.client(viewer).get(f"{API}/findings/{finding.public_id}/export", params={"format": fmt})
    assert response.status_code == 200
    allowed = {level} & DOWNLOADS[viewer]
    check(response.text, allowed, allowed, where=f"export {fmt} ({level} {kind})")
    if fmt == "geojson":
        (feature,) = response.json()["features"]
        exact = level in DOWNLOADS[viewer]
        assert (feature["properties"]["outline"] is not None) is exact
        assert feature["properties"]["shape_kind"] == (kind if exact else None)
        assert (feature["properties"]["shape_length_m"] is not None) is exact


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
    expected = {f.public_id for level, f in world.every() if level in SEES[viewer] - own}
    assert offered == expected
    check(response.text, SEES[viewer] - own, where="GET /review/next")
    # A line the viewer sees only as its square is left out, so the response doesn't name it.
    checked_unlisted(response, world, SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
def test_help_wanted(world: World, viewer: str) -> None:
    response = world.client(viewer).get(f"{API}/review/tasks")
    assert response.status_code == 200
    check(response.text, SEES[viewer], where="GET /review/tasks")
    groups = {group["code"]: group for group in response.json()["groups"]}
    strand = groups["need_strand"]
    assert strand["total"] == 6
    for item in strand["items"]:
        level = next(lv for lv, f in world.every() if f.public_id == item["public_id"])
        assert item["place"]["obscured"] is (level not in SEES[viewer])
        assert item["place"]["outline"] is None
    # The new part of a line is shape, so it is offered only where the line is seen exactly.
    new_part = {item["public_id"] for item in groups["look_at_new_part"]["items"]}
    own = set(LEVELS) if viewer == "finder" else set()
    assert new_part == {world.lines[level].public_id for level in SEES[viewer] - own}


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_comments_and_answers_carry_no_position(
    world: World, viewer: str, level: Sensitivity, kind: str
) -> None:
    finding = world.of(kind, level)
    client = world.client(viewer)
    comments = client.get(f"{API}/findings/{finding.public_id}/comments")
    assert comments.status_code == 200
    check(comments.text, set(), where="comments")
    answers = client.get(f"{API}/findings/{finding.public_id}/observations")
    assert answers.status_code == (200 if viewer == "finder" else 403)
    check(answers.text, set(), where="observations")


@pytest.mark.parametrize("viewer", ["member", "trusted", "moderator"])
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_writes_answer_with_what_the_writer_may_see(
    world: World, viewer: str, level: Sensitivity, kind: str
) -> None:
    finding = world.of(kind, level)
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

    path = f"{API}/findings/{finding.public_id}/observation"
    held = client.put(path, json={"visible": "yes", "detail_follows": True})
    revealed = client.post(f"{path}/reveal", json={"feature_class": "enclosure"})
    looked = client.put(path, json={"visible": "yes", "feature_class": "enclosure"})
    if level in SEES[viewer]:
        assert held.status_code == 200
        check(held.text, set(), where="answer whose detail follows")
        assert revealed.status_code == 200
        check(revealed.text, allowed, allowed, where="reveal after the detail")
        assert looked.status_code == 200
        check(looked.text, allowed, allowed, where="reveal")
    else:
        for refused in (held, looked):
            assert refused.status_code == 403
            assert refused.json()["error"]["code"] == "location_hidden"
            check(refused.text, set(), where="refused answer")
        assert revealed.json()["error"]["code"] == "observation_not_found"
        check(revealed.text, set(), where="refused reveal")

    # A finding marked about 400 m from this one's anchor, which sends back nothing of it.
    lon, lat = lon_lat(finding.location)
    beside = {"type": "Point", "coordinates": [round(lon + 0.0043, 6), round(lat + 0.0021, 6)]}
    marked = client.post(f"{API}/findings", json={"location": beside, "feature_class": "enclosure"})
    assert marked.status_code == 201
    check(marked.text, set(), where=f"POST /findings beside the {level} {kind}")
    leak_record.checked_response(marked, finding.public_id)


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_changes_to_a_finding_answer_with_what_the_writer_may_see(
    world: World, db: Session, viewer: str, level: Sensitivity, kind: str
) -> None:
    """A change answers with the finding's page, so only to someone who sees it exactly.

    The finder renames and withdraws it, a trusted member raises it, and a
    moderator verifies an HER record added to it. Everyone else is refused, and
    a refusal says nothing of where it is.
    """
    finding = world.of(kind, level)
    official, _ = findings.add_evidence(
        db,
        findings.lock(db, finding),
        world.people["trusted"],
        EvidenceFields(kind=EvidenceKind.HER_RECORD, stance=Stance.SUPPORTS, reference="MWI1234"),
    )
    db.commit()
    client = world.client(viewer)
    allowed = {level} & SEES[viewer]
    page = f"{API}/findings/{finding.public_id}"
    answered = {
        "PATCH": client.patch(page, json={"title": f"A {level} {kind}, renamed"}),
        # The address names the record, not the finding.
        "verify": client.post(f"{API}/evidence/{official.id}/verify"),
        "raise": client.put(f"{page}/sensitivity", json={"level": "protected"}),
        "withdraw": client.post(f"{page}/withdraw"),
    }
    for change, response in answered.items():
        where = f"{change} of the {level} {kind} as {viewer}"
        assert response.status_code < 500, where
        if viewer == "signed_out":
            assert response.status_code == 401, where
        check(response.text, allowed, where=where)
        leak_record.checked_response(response, finding.public_id)
    if viewer == "finder":
        assert answered["PATCH"].status_code == answered["withdraw"].status_code == 200
    if viewer == "moderator":
        assert answered["verify"].status_code == 200


def test_activity_and_notifications_never_hold_an_exact_position(world: World, db: Session) -> None:
    rows = db.scalars(select(Activity)).all()
    assert rows
    assert {row.finding_id for row in rows if row.kind == "shape_extended"} == {
        f.id for f in world.lines.values()
    }
    for row in rows:
        finding = next(f for _, f in world.every() if f.id == row.finding_id)
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
    """`sensitivity.sees_exact_clause` restates `sees_exact` in SQL. They must agree on every row."""
    for viewer in [None, *world.people.values()]:
        clause = sensitivity.as_sql(sensitivity.sees_exact_clause(viewer))
        in_sql = set(db.scalars(select(Finding.id).where(clause)))
        in_python = {f.id for _, f in world.every() if sensitivity.sees_exact(f, viewer)}
        assert in_sql == in_python, f"viewer {viewer}"


# --------------------------------------------------------------------------
# Routes outside the findings track that take a finding's position
# --------------------------------------------------------------------------


def _records_around(db: Session) -> None:
    """Records at each exact point, round it, and at each square's centre, so distances have work to do."""
    source = add_source(db)
    for level, (lon, lat) in POINTS.items():
        add_record(db, source, f"Enclosure by the {level} point", lon + 0.00013, lat + 0.00011)
        for step in range(1, 4):
            add_record(db, source, f"Bank {level} {step}", lon + 0.0007 * step, lat - 0.0004 * step)
        centre = gridref.gridref_at(lon, lat, 4).centre()
        add_record(db, source, f"Camp at the {level} square", *centre)
    db.commit()


def _move_within_square(db: Session, finding: Finding) -> None:
    """Move a finding's exact point to elsewhere in its 1 km square, which keeps its public position."""
    lon, lat = lon_lat(finding.location)
    square = gridref.gridref_at(lon, lat, 4)
    _, easting, northing = gridref.to_grid(lon, lat)
    inside = (
        square.easting + 1000 - (easting - square.easting),
        square.northing + 1000 - (northing - square.northing),
    )
    moved = gridref.to_lonlat(square.system, *inside)
    assert gridref.gridref_at(*moved, 4) == square
    finding.location = db_point(*moved)
    db.commit()


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_suggested_records(world: World, db: Session, viewer: str, level: Sensitivity, kind: str) -> None:
    """Distances, order and the set returned all start from the position the viewer may see.

    For a viewer who sees only the square, moving the finding within its square
    changes nothing in the answer, so nothing in it can depend on the exact point.
    """
    _records_around(db)
    finding = world.of(kind, level)
    path = f"{API}/findings/{finding.public_id}/suggested-records"
    client = world.client(viewer)
    before = client.get(path, params={"limit": 50})
    assert before.status_code == 200
    allowed = {level} & SEES[viewer]
    check(before.text, allowed, where=f"suggested records ({level})")
    assert before.json()["origin"]["obscured"] is (level not in SEES[viewer])
    assert before.headers["cache-control"] == "private, no-cache"
    _move_within_square(db, finding)
    after = client.get(path, params={"limit": 50})
    if level in SEES[viewer]:
        assert after.json() != before.json()
    else:
        assert after.json() == before.json()


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", KINDS)
def test_the_search_box_flies_to_what_the_viewer_may_see(
    world: World, viewer: str, level: Sensitivity, kind: str
) -> None:
    finding = world.of(kind, level)
    response = world.client(viewer).get(f"{API}/geo/search", params={"q": finding.public_id.lower()})
    assert response.status_code == 200
    allowed = {level} & SEES[viewer]
    check(response.text, allowed, allowed, where=f"GET /geo/search ({level})")
    [hit] = [item for item in response.json()["items"] if item["type"] == "finding"]
    assert hit["obscured"] is (level not in SEES[viewer])
    if level not in SEES[viewer]:
        assert hit["bbox"] is not None
    elif kind == "line":
        # An exact viewer flies to the whole line.
        lons, lats = zip(*LINES[level], strict=True)
        assert hit["bbox"] == pytest.approx([min(lons), min(lats), max(lons), max(lats)])
    else:
        assert hit["bbox"] == pytest.approx(list(outline_of(finding).bounds))
    assert response.headers["cache-control"] == "private, no-cache"


@pytest.mark.parametrize("viewer", VIEWERS)
def test_a_records_linked_findings(world: World, db: Session, viewer: str) -> None:
    """A record lists only the findings linked to it that the viewer sees exactly.

    The record is near each finding's exact point, so naming a generalised
    finding here would place it as closely as the record, which is why its
    own page leaves the link out (`redacted`).
    """
    source = add_source(db)
    record = add_record(db, source, "Enclosure on the down", *POINTS[Sensitivity.PROTECTED])
    db.commit()
    for _, finding in world.every():
        findings.add_evidence(
            db,
            findings.lock(db, finding),
            world.people["trusted"],
            EvidenceFields(kind=EvidenceKind.RECORD_LINK, record_id=record.id, relation=Relation.RELATED),
        )
    db.commit()
    response = world.client(viewer).get(f"{API}/records/{record.id}/findings")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-cache"
    check(response.text, SEES[viewer], where="GET /records/{id}/findings")
    listed = {item["public_id"] for item in response.json()["items"]}
    assert listed == {f.public_id for level, f in world.every() if level in SEES[viewer]}
    # Every line is linked to the record, and one the viewer sees only as its square is left out.
    checked_unlisted(response, world, SEES[viewer])


def test_a_saved_zoom_goes_only_to_those_who_see_the_finding_exactly(
    db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
) -> None:
    """A low zoom would hint that a hidden finding is large, so no hidden finding has one, point or line."""
    finder = make_user()
    saved = {"zoom": 9.5, "layer": "slope", "bearing": 30}
    made = {}
    for kind, (lon, lat) in (
        ("point", POINTS[Sensitivity.PROTECTED]),
        ("open point", POINTS[Sensitivity.OPEN]),
    ):
        level = Sensitivity.PROTECTED if kind == "point" else Sensitivity.OPEN
        made[kind] = create(db, finder, lon=lon, lat=lat, requested_sensitivity=level, view_state=saved)
    line = findings.create_finding(
        db,
        finder,
        path=line_path(Sensitivity.PROTECTED, extended=False),
        feature_class=FeatureClass.ROAD,
        requested_sensitivity=Sensitivity.PROTECTED,
        view_state=saved,
    )
    db.commit()
    made["line"] = line
    visitor, member = client_for(app), client_for(app, make_user())
    for kind, finding in made.items():
        hidden = finding.sensitivity != Sensitivity.OPEN.value
        page = visitor.get(f"{API}/findings/{finding.public_id}").json()
        assert page["location"]["obscured"] is hidden
        assert page["view_state"]["zoom"] == (None if hidden else 9.5), kind
        assert page["view_state"]["layer"] == "slope"
        assert member.get(f"{API}/findings/{finding.public_id}").json()["view_state"]["zoom"] == 9.5
    # Help wanted shows a hidden finding at its square, with no zoom either.
    groups = visitor.get(f"{API}/review/tasks").json()["groups"]
    for item in (item for group in groups for item in group["items"]):
        if item["place"]["obscured"]:
            assert item["view_state"]["zoom"] is None, item["public_id"]
