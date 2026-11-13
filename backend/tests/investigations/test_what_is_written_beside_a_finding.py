"""What people write and draw beside a finding in an investigation gives no more away than the finding.

A public investigation holding a protected barrow, with a saved view centred
on it, a height profile across it, an area drawn round it and its grid
reference in the notes, must show a signed-out visitor no more than the
barrow's 1 km square, on the page and in every download, and a member no more
in a download (Decision 0005). The rules apply when the page is read, so items saved before them, or
while the finding was open, are covered too.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box, shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Finding, Investigation, InvestigationItem
from fieldclub.services import findings, investigations, sensitivity, shapes
from fieldclub.services.text_positions import PLACEHOLDER
from fieldclub.vocab import FeatureClass, InvestigationItemKind, InvestigationRole, Sensitivity, Visibility
from tests.findings.support import create
from tests.helpers import MakeUser, lon_lat
from tests.investigations.support import API, add, make, url

# The barrow, at a point nothing else in the test uses.
LON, LAT = -1.812947, 51.402583
# Every way its position is written or drawn below, so a leak names itself.
POSITIONS = (
    "1.812947", "51.402583", "1.81295", "51.40258", "SU 1310 6707", "SU13106707", "SU 13108 67078",
    "1.8133", "51.4028",
)  # fmt: skip


class World:
    def __init__(
        self, db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
    ) -> None:
        self.finder = make_user(handle="Finder")
        self.member = make_user(handle="Member")
        self.trusted = make_user("trusted", handle="Trusted")
        self.barrow: Finding = create(
            db, self.finder, lon=LON, lat=LAT, feature_class=FeatureClass.ENCLOSURE, title="Low mound"
        )
        # Written while the finding was open, then the finding was raised: nothing is refused at save time.
        self.notebook: Investigation = make(
            db,
            self.finder,
            Visibility.PUBLIC,
            title="The mound at SU 1310 6707",
            summary="Centred on 51.402583, -1.812947.",
            notes="## Where\n\nThe mound is at **SU 1310 6707**, by the hedge.",
            area=box(LON - 0.0002, LAT - 0.0002, LON + 0.0002, LAT + 0.0002),
        )
        add(db, self.notebook, self.finder, kind=InvestigationItemKind.FINDING, finding=self.barrow.public_id)
        add(
            db, self.notebook, self.finder, kind=InvestigationItemKind.VIEW,
            data={"centre": [LON, LAT], "zoom": 18, "layer": "slope"}, title="Slope view",
        )  # fmt: skip
        add(
            db, self.notebook, self.finder, kind=InvestigationItemKind.PROFILE,
            data={"line": {"type": "LineString", "coordinates": [[LON - 0.003, LAT], [LON + 0.003, LAT]]}},
        )  # fmt: skip
        add(db, self.notebook, self.finder, note="Exact spot: SU 1310 6707")
        add(
            db, self.notebook, self.finder, kind=InvestigationItemKind.REFERENCE, title="On the map",
            data={
                "url": "https://www.google.com/maps/@51.40258,-1.81295,18z",
                "citation": "Seen at 51.4028 -1.8133",
            },
        )  # fmt: skip
        # A view and a profile far from it, which everyone may see.
        add(
            db, self.notebook, self.finder, kind=InvestigationItemKind.VIEW,
            data={"centre": [-1.7, 51.5], "zoom": 14, "layer": "slope"}, title="Far away",
        )  # fmt: skip
        sensitivity.change_sensitivity(db, findings.lock(db, self.barrow), self.finder, Sensitivity.PROTECTED)
        db.commit()
        self.clients: dict[str, TestClient] = {
            "signed_out": client_for(app),
            "member": client_for(app, self.member),
            "finder": client_for(app, self.finder),
            "trusted": client_for(app, self.trusted),
        }

    def notebook_items(self, db: Session) -> list[InvestigationItem]:
        return list(
            db.scalars(
                select(InvestigationItem).where(InvestigationItem.investigation_id == self.notebook.id)
            )
        )

    def paths(self) -> list[str]:
        return [
            url(self.notebook),
            url(self.notebook, "/items"),
            url(self.notebook, "/export?format=geojson"),
            url(self.notebook, "/export?format=csv"),
            url(self.notebook, "/export?format=html"),
            f"{API}/investigations",
            f"{API}/investigations?bbox={LON - 0.05},{LAT - 0.05},{LON + 0.05},{LAT + 0.05}",
            f"{API}/activity",
        ]


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]) -> World:
    return World(db, make_user, app, client_for)


def _leaks(text: str) -> list[str]:
    return [position for position in POSITIONS if position in text]


def test_nothing_beside_the_finding_gives_its_place_away(world: World) -> None:
    client = world.clients["signed_out"]
    for path in world.paths():
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert _leaks(response.text) == [], path


@pytest.mark.parametrize("viewer", ["member", "finder", "trusted"])
def test_those_who_see_the_finding_exactly_get_everything_as_it_was_saved(world: World, viewer: str) -> None:
    client = world.clients[viewer]
    page = client.get(url(world.notebook)).json()
    assert page["title"] == "The mound at SU 1310 6707"
    assert "SU 1310 6707" in page["notes"]
    items = client.get(url(world.notebook, "/items")).json()["items"]
    assert [item["unavailable"] for item in items] == [None] * len(items)
    assert items[1]["view"]["centre"] == [LON, LAT]
    # A member downloads it at its square (Decision 0005, rule 8).
    downloaded = "51.402583" in client.get(url(world.notebook, "/export?format=geojson")).text
    assert downloaded is (viewer != "member")


@pytest.mark.parametrize("fmt", ["geojson", "csv", "html"])
def test_a_member_s_download_gives_no_more_than_the_square(world: World, fmt: str) -> None:
    """A member sees the barrow exactly on the page, and still downloads it at its square.

    The title, the summary, the notes, the view, the profile, the area and the
    reference all go through the download's stricter rule (Decision 0005, rule 8).
    """
    path = url(world.notebook, f"/export?format={fmt}")
    member = world.clients["member"].get(path)
    assert member.status_code == 200, member.text
    assert _leaks(member.text) == []
    # The finder's download holds what was saved, so the check above can fail.
    finder = world.clients["finder"].get(path)
    assert _leaks(finder.text) != []


def test_the_page_says_what_it_held_back(world: World) -> None:
    client = world.clients["signed_out"]
    page = client.get(url(world.notebook)).json()
    assert page["title"] == f"The mound at {PLACEHOLDER}"
    assert page["summary"] == f"Centred on {PLACEHOLDER}."
    assert PLACEHOLDER in page["notes"]
    items = {item["position"]: item for item in client.get(url(world.notebook, "/items")).json()["items"]}
    finding, view, profile, note, reference, far = (items[key] for key in sorted(items))
    assert finding["finding"]["location"]["obscured"] is True
    assert (view["unavailable"], view["view"]) == ("near_protected", None)
    assert view["title"] == "Slope view"
    assert (profile["unavailable"], profile["profile"]) == ("near_protected", None)
    assert note["note"] == f"Exact spot: {PLACEHOLDER}"
    assert reference["reference"] == {"url": None, "citation": f"Seen at {PLACEHOLDER}"}
    # Far from the barrow, a view says nothing about it.
    assert (far["unavailable"], far["view"]["centre"]) == (None, [-1.7, 51.5])


def _public_square(finding: Finding) -> Polygon:
    square = sensitivity.visible_location(finding, None).square_polygon()
    assert square is not None
    return square


def test_an_area_near_the_finding_is_shown_as_whole_squares_and_found_only_as_shown(world: World) -> None:
    """The shown area set beside the finding's public square must not narrow the square."""
    client = world.clients["signed_out"]
    (listed,) = client.get(f"{API}/investigations").json()["items"]
    shown = shape(listed["area"])
    square = _public_square(world.barrow)
    # Responses round positions to about a decimetre.
    assert shown.buffer(2e-6).contains(square)
    assert shown.intersection(square).area == pytest.approx(square.area, rel=1e-3)

    def found(bbox: tuple[float, float, float, float], viewer: str = "signed_out") -> bool:
        params = {"bbox": ",".join(str(value) for value in bbox)}
        items = world.clients[viewer].get(f"{API}/investigations", params=params).json()["items"]
        return world.notebook.public_id in [item["public_id"] for item in items]

    # A tiny box in a corner of the square, well away from the drawn area, still finds it ...
    west, south, _, _ = square.bounds
    corner = (west + 0.0012, south + 0.0012, west + 0.0013, south + 0.0013)
    assert square.contains(box(*corner))
    assert not box(*corner).intersects(box(LON - 0.0002, LAT - 0.0002, LON + 0.0002, LAT + 0.0002))
    assert found(corner)
    # ... so the search can't tell where in the square the drawing is. The finder's search finds the drawing.
    assert not found(corner, "finder")
    assert found((LON - 0.0001, LAT - 0.0001, LON + 0.0001, LAT + 0.0001), "finder")


def test_the_squares_shown_for_an_area_hold_each_square_whole_or_not_at_all() -> None:
    """Over many places and shapes, the cover never cuts a 1 km square in two."""
    import random

    chance = random.Random(11)
    for _ in range(600):
        lon, lat = chance.uniform(-4.5, 1.5), chance.uniform(50.2, 55.5)
        size = chance.choice([0.0002, 0.003, 0.02])
        drawn = box(lon, lat, lon + size, lat + size * 0.6)
        cover = sensitivity.square_cover(drawn)
        assert cover is not None
        assert cover.is_valid
        assert cover.buffer(1e-7).contains(drawn)
        for corner_lon, corner_lat in [(lon, lat), (lon + size, lat + size * 0.6)]:
            square = gridref.gridref_at(corner_lon, corner_lat, sensitivity.SQUARE_DIGITS).polygon()
            assert cover.buffer(1e-7).contains(square), (corner_lon, corner_lat)
        # A square just outside the cover isn't cut either.
        far = sensitivity.square_cover(box(lon + 0.2, lat, lon + 0.2001, lat + 0.0001))
        assert far is not None
        assert cover.intersection(far).area < 1e-12


def test_a_finding_taken_off_the_page_is_still_guarded(
    db: Session, world: World, app: FastAPI, client_for: Callable[..., TestClient]
) -> None:
    """Taking the finding item off is ordinary curation, and must not publish what was drawn beside it."""
    item = db.scalar(
        select(InvestigationItem).where(
            InvestigationItem.investigation_id == world.notebook.id,
            InvestigationItem.kind == InvestigationItemKind.FINDING.value,
        )
    )
    assert item is not None
    removed = world.clients["finder"].delete(url(world.notebook, f"/items/{item.id}"))
    assert removed.status_code == 204, removed.text
    for path in world.paths():
        response = world.clients["signed_out"].get(path)
        assert response.status_code == 200, (path, response.text)
        assert _leaks(response.text) == [], path


def test_a_view_near_a_protected_finding_is_held_back_in_any_investigation(
    db: Session, world: World, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
) -> None:
    """Holding the finding isn't what matters: being near it is."""
    other = make_user(handle="Other")
    unrelated = make(db, other, Visibility.PUBLIC, title="A walk", notes="Stopped at SU 1310 6707.")
    add(
        db, unrelated, other, kind=InvestigationItemKind.VIEW,
        data={"centre": [LON + 0.001, LAT], "zoom": 18, "layer": "slope"}, title="Here",
    )  # fmt: skip
    client = world.clients["signed_out"]
    (view,) = client.get(url(unrelated, "/items")).json()["items"]
    assert (view["unavailable"], view["view"]) == ("near_protected", None)
    assert _leaks(client.get(url(unrelated)).text) == []
    assert _leaks(client.get(url(unrelated, "/export?format=html")).text) == []
    for viewer in ("member", "finder"):
        (view,) = world.clients[viewer].get(url(unrelated, "/items")).json()["items"]
        assert view["view"]["centre"] == [LON + 0.001, LAT], viewer


@pytest.mark.parametrize(
    "link",
    [
        "https://maps.app.goo.gl/AbCdEf123",
        "https://goo.gl/maps/AbCdEf123",
        "https://plus.codes/9C3WC4HW+F8",
        "https://geohash.org/gcnstf3c",
        "https://example.org/where?q=Avebury",
        "https://bit.ly/3xYzAbc",
    ],
)
def test_a_reference_link_goes_only_to_those_who_see_the_finding_exactly(
    db: Session, world: World, link: str
) -> None:
    """A link is the member's own text and can say where the finding is in any form (as `visible_url`)."""
    add(
        db,
        world.notebook,
        world.finder,
        kind=InvestigationItemKind.REFERENCE,
        title="Link",
        data={"url": link},
    )
    items = world.clients["signed_out"].get(url(world.notebook, "/items")).json()["items"]
    assert items[-1]["reference"].get("url") is None
    for viewer in ("signed_out", "member"):
        for form in ("geojson", "html"):
            download = world.clients[viewer].get(url(world.notebook, f"/export?format={form}")).text
            assert link not in download, (viewer, form)
    for viewer in ("member", "finder"):
        items = world.clients[viewer].get(url(world.notebook, "/items")).json()["items"]
        assert items[-1]["reference"]["url"] == link, viewer


def test_a_doi_reference_keeps_its_link_rebuilt_from_the_doi(db: Session, world: World) -> None:
    add(
        db, world.notebook, world.finder, kind=InvestigationItemKind.REFERENCE, title="Paper",
        data={"url": "https://dx.doi.org/10.5284/1040209?utm_source=x"},
    )  # fmt: skip
    items = world.clients["signed_out"].get(url(world.notebook, "/items")).json()["items"]
    assert items[-1]["reference"]["url"] == "https://doi.org/10.5284/1040209"


def test_the_feed_shows_an_investigation_s_title_as_its_page_does(world: World) -> None:
    events = world.clients["signed_out"].get(f"{API}/activity").json()["items"]
    titles = [event["investigation"]["title"] for event in events if event["investigation"] is not None]
    assert titles == [f"The mound at {PLACEHOLDER}"]
    for viewer in ("member", "finder"):
        events = world.clients[viewer].get(f"{API}/activity").json()["items"]
        assert [event["investigation"]["title"] for event in events if event["investigation"]] == [
            "The mound at SU 1310 6707"
        ], viewer


def test_a_member_s_own_view_near_the_finding_is_held_back_from_others_and_from_their_download(
    db: Session, world: World
) -> None:
    """A member sees it on the page, as they see the finding. A download keeps the download rule."""
    investigations.add_member(db, world.notebook, world.member, InvestigationRole.EDITOR)
    db.commit()
    add(
        db, world.notebook, world.member, kind=InvestigationItemKind.VIEW,
        data={"centre": [LON + 0.002, LAT], "zoom": 17, "layer": "slope"}, title="Mine",
        note="I stood at SU 1330 6707",
    )  # fmt: skip
    mine = world.clients["member"].get(url(world.notebook, "/items")).json()["items"][-1]
    assert (mine["unavailable"], mine["view"]["centre"]) == (None, [LON + 0.002, LAT])
    assert mine["note"] == "I stood at SU 1330 6707"
    theirs = world.clients["signed_out"].get(url(world.notebook, "/items")).json()["items"][-1]
    assert (theirs["unavailable"], theirs["view"]) == ("near_protected", None)
    assert theirs["note"] == f"I stood at {PLACEHOLDER}"
    # A download keeps the download rule, even for their own view (Decision 0005, rule 8).
    download = world.clients["member"].get(url(world.notebook, "/export?format=geojson")).text
    assert str(LON + 0.002)[:8] not in download
    assert "SU 1330 6707" not in download


def test_a_member_downloads_a_protected_finding_s_neighbours_at_its_square(
    db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
) -> None:
    """Members see a protected finding exactly on the page, but download it at its square (Decision 0005)."""
    finder, member = make_user(), make_user()
    protected = create(db, finder, lon=LON, lat=LAT, feature_class=FeatureClass.ROUND_BARROW)
    notebook = make(db, finder, Visibility.PUBLIC, notes="Bank at SU 1310 6707")
    add(db, notebook, finder, kind=InvestigationItemKind.FINDING, finding=protected.public_id)
    add(
        db, notebook, finder, kind=InvestigationItemKind.VIEW,
        data={"centre": [LON, LAT], "zoom": 18, "layer": "slope"},
    )  # fmt: skip
    client = client_for(app, member)
    page = client.get(url(notebook, "/items")).json()["items"]
    assert page[1]["view"]["centre"] == [LON, LAT]
    for form in ("geojson", "csv", "html"):
        download = client.get(url(notebook, f"/export?format={form}")).text
        assert _leaks(download) == [], form
    assert "51.402583" in client_for(app, finder).get(url(notebook, "/export?format=geojson")).text


def test_what_is_drawn_beside_a_protected_road_far_from_its_anchor_is_held_back(
    db: Session, world: World, make_user: MakeUser
) -> None:
    """The guard measures to the whole line, not only to its anchor (Decision 0030)."""
    surveyor = make_user(handle="Surveyor")
    # A road 40 km long drawn first, so its anchor is near its middle, 20 km from either end.
    road_lon = -2.5
    road = findings.create_finding(
        db,
        world.finder,
        path=shapes.read_path(
            {"points": [{"lon": road_lon, "lat": lat, "kind": "corner"} for lat in (51.0, 51.18, 51.36)]}
        ),
        feature_class=FeatureClass.ROAD,
        requested_sensitivity=Sensitivity.PROTECTED,
    )
    db.commit()
    assert abs(lon_lat(road.location)[1] - 51.18) < 1e-5
    # About 1.4 km east of the road's southern end, 20 km from its anchor.
    beside = road_lon + 0.02
    walk = make(
        db, surveyor, Visibility.PUBLIC, title="A walk south", area=box(beside, 51.0, beside + 0.001, 51.001)
    )
    add(
        db, walk, surveyor, kind=InvestigationItemKind.PROFILE,
        data={"line": {"type": "LineString", "coordinates": [[beside, 51.0], [beside, 51.01]]}},
    )  # fmt: skip
    add(
        db, walk, surveyor, kind=InvestigationItemKind.VIEW,
        data={"centre": [beside, 51.005], "zoom": 17, "layer": "slope"}, title="Bank",
    )  # fmt: skip
    client = world.clients["signed_out"]
    items = client.get(url(walk, "/items")).json()["items"]
    assert [item["unavailable"] for item in items] == ["near_protected", "near_protected"]
    assert all(item["view"] is None and item["profile"] is None for item in items)
    area = shape(client.get(url(walk)).json()["area"])
    # Shown as whole squares, not as drawn.
    assert area.area > box(beside, 51.0, beside + 0.001, 51.001).area * 50
    for viewer in ("member", "finder", "trusted"):
        items = world.clients[viewer].get(url(walk, "/items")).json()["items"]
        assert [item["unavailable"] for item in items] == [None, None], viewer


def test_a_height_profile_beside_a_protected_road_far_from_its_anchor_is_held_back_from_a_visitor(
    db: Session, world: World, make_user: MakeUser
) -> None:
    """The guard measures to the whole of a protected line too, for the signed-out visitor (Decision 0030)."""
    surveyor = make_user(handle="Surveyor")
    road_lon = -2.6
    road = findings.create_finding(
        db,
        world.finder,
        path=shapes.read_path(
            {"points": [{"lon": road_lon, "lat": lat, "kind": "corner"} for lat in (51.0, 51.18, 51.36)]}
        ),
        feature_class=FeatureClass.ROAD,
        requested_sensitivity=Sensitivity.PROTECTED,
    )
    db.commit()
    assert road.sensitivity == Sensitivity.PROTECTED.value
    assert abs(lon_lat(road.location)[1] - 51.18) < 1e-5
    # About 1.4 km east of the road's southern end, 20 km from its anchor.
    beside = road_lon + 0.02
    walk = make(db, surveyor, Visibility.PUBLIC, title="A walk by the road")
    add(
        db, walk, surveyor, kind=InvestigationItemKind.PROFILE,
        data={"line": {"type": "LineString", "coordinates": [[beside, 51.0], [beside, 51.01]]}},
    )  # fmt: skip
    visitor = world.clients["signed_out"].get(url(walk, "/items")).json()["items"]
    assert [(item["unavailable"], item["profile"]) for item in visitor] == [("near_protected", None)]
    for viewer in ("member", "finder", "trusted"):
        items = world.clients[viewer].get(url(walk, "/items")).json()["items"]
        assert [item["unavailable"] for item in items] == [None], viewer
        assert items[0]["profile"] is not None, viewer
