"""What people write and draw beside a finding in an investigation gives no more away than the finding.

A public investigation holding a restricted barrow, with a saved view centred
on it, a height profile across it, an area drawn round it and its grid
reference in the notes, must show a signed-out visitor or a member no more
than the barrow's 1 km square, on the page and in every download (Decision
0005). The rules apply when the page is read, so items saved before them, or
while the finding was open, are covered too.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import Point, box, shape
from sqlalchemy.orm import Session

from fieldclub.models import Finding, Investigation
from fieldclub.services import findings, sensitivity
from fieldclub.services.text_positions import PLACEHOLDER
from fieldclub.vocab import FeatureClass, InvestigationItemKind, Sensitivity, Visibility
from tests.findings.support import create
from tests.helpers import MakeUser
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
        sensitivity.change_sensitivity(
            db, findings.lock(db, self.barrow), self.finder, Sensitivity.RESTRICTED
        )
        db.commit()
        self.clients: dict[str, TestClient] = {
            "signed_out": client_for(app),
            "member": client_for(app, self.member),
            "finder": client_for(app, self.finder),
            "trusted": client_for(app, self.trusted),
        }

    def paths(self) -> list[str]:
        return [
            url(self.notebook),
            url(self.notebook, "/items"),
            url(self.notebook, "/export?format=geojson"),
            url(self.notebook, "/export?format=csv"),
            url(self.notebook, "/export?format=html"),
            f"{API}/investigations",
            f"{API}/investigations?bbox={LON - 0.05},{LAT - 0.05},{LON + 0.05},{LAT + 0.05}",
        ]


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]) -> World:
    return World(db, make_user, app, client_for)


def _leaks(text: str) -> list[str]:
    return [position for position in POSITIONS if position in text]


@pytest.mark.parametrize("viewer", ["signed_out", "member"])
def test_nothing_beside_the_finding_gives_its_place_away(world: World, viewer: str) -> None:
    client = world.clients[viewer]
    for path in world.paths():
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert _leaks(response.text) == [], (viewer, path)


@pytest.mark.parametrize("viewer", ["finder", "trusted"])
def test_those_who_see_the_finding_exactly_get_everything_as_it_was_saved(world: World, viewer: str) -> None:
    client = world.clients[viewer]
    page = client.get(url(world.notebook)).json()
    assert page["title"] == "The mound at SU 1310 6707"
    assert "SU 1310 6707" in page["notes"]
    items = client.get(url(world.notebook, "/items")).json()["items"]
    assert [item["unavailable"] for item in items] == [None] * len(items)
    assert items[1]["view"]["centre"] == [LON, LAT]
    assert "51.402583" in client.get(url(world.notebook, "/export?format=geojson")).text


def test_the_page_says_what_it_held_back(world: World) -> None:
    client = world.clients["member"]
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


def test_an_area_near_the_finding_is_widened_to_the_grid_and_found_only_as_shown(world: World) -> None:
    """Narrowing a box search on the drawn area must find no more than its grid cells."""
    client = world.clients["signed_out"]
    (listed,) = client.get(f"{API}/investigations").json()["items"]
    shown = shape(listed["area"])
    drawn = box(LON - 0.0002, LAT - 0.0002, LON + 0.0002, LAT + 0.0002)
    assert shown.normalize().equals_exact(sensitivity.snapped_box(drawn).normalize(), tolerance=1e-6)
    assert shown.contains(box(LON - 0.0002, LAT - 0.0002, LON + 0.0002, LAT + 0.0002))
    west, south, east, north = shown.bounds
    assert east - west >= sensitivity.AREA_GRID_LON - 1e-9
    assert north - south >= sensitivity.AREA_GRID_LAT - 1e-9

    def found(bbox: tuple[float, float, float, float], viewer: str = "signed_out") -> bool:
        params = {"bbox": ",".join(str(value) for value in bbox)}
        items = world.clients[viewer].get(f"{API}/investigations", params=params).json()["items"]
        return world.notebook.public_id in [item["public_id"] for item in items]

    # A tiny box inside the shown cells but well away from the drawn area still finds it ...
    inside_cell = (west + 0.0005, south + 0.0005, west + 0.0006, south + 0.0006)
    assert not box(*inside_cell).intersects(box(LON - 0.0002, LAT - 0.0002, LON + 0.0002, LAT + 0.0002))
    assert found(inside_cell)
    # ... so the search can't tell where in the cells the drawing is. The finder's search finds the drawing.
    assert not found(inside_cell, "finder")
    assert found((LON - 0.0001, LAT - 0.0001, LON + 0.0001, LAT + 0.0001), "finder")


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


def test_the_guard_s_box_search_in_sql_matches_what_it_shows(db: Session, make_user: MakeUser) -> None:
    """`snapped_box_sql` and `snapped_box` agree, so the search can never be narrower than the page."""
    from geoalchemy2.shape import to_shape
    from sqlalchemy import select

    from fieldclub.models.common import to_db_geometry

    shapes = (
        box(-1.8133, 51.4021, -1.8126, 51.4029),
        box(-3.0001, 53.0, -2.9, 53.05),
        box(0.01, 51.0, 0.02, 51.01),
        # On a grid line: still a whole cell, not a line.
        Point(0.016, 51.0),
    )
    for shape_ in shapes:
        found = db.scalar(select(sensitivity.snapped_box_sql(to_db_geometry(shape_))))
        assert found is not None
        stored = to_shape(found)
        expected = sensitivity.snapped_box(shape_)
        assert stored.normalize().equals_exact(expected.normalize(), tolerance=1e-9), shape_.bounds
        assert expected.area > 0
