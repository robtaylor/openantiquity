"""A finding a moderator has hidden takes no part in what is held back (Decision 0032).

Only its finder and the moderators can see a hidden finding. What is drawn
near a protected finding is held back from signed-out readers, and if that
went on once the finding was hidden, the holding back would say that
something hidden is there, and how near. So a hidden finding is left out of
the guard for what is drawn near it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box, shape
from sqlalchemy.orm import Session

from fieldclub.services import sensitivity
from fieldclub.vocab import FeatureClass, InvestigationItemKind, Sensitivity, Visibility
from tests.helpers import MakeFinding, MakeUser
from tests.investigations.support import API, add, make, url

# A round barrow, protected by its class, at a point nothing else in the tests uses.
LON, LAT = -1.812947, 51.402583


def test_a_view_near_a_hidden_finding_is_shown_as_it_was_saved(
    db: Session,
    make_user: MakeUser,
    make_finding: MakeFinding,
    app: FastAPI,
    client_for: Callable[..., TestClient],
) -> None:
    barrow = make_finding(
        make_user(handle="Finder"), lon=LON, lat=LAT, feature_class=FeatureClass.ROUND_BARROW
    )
    assert barrow.sensitivity == Sensitivity.PROTECTED.value
    walker = make_user(handle="Walker")
    walk = make(db, walker, Visibility.PUBLIC, title="A walk")
    centre = [LON + 0.001, LAT]
    add(
        db, walk, walker, kind=InvestigationItemKind.VIEW,
        data={"centre": centre, "zoom": 18, "layer": "slope"}, title="Here",
    )  # fmt: skip
    signed_out = client_for(app)

    # While the barrow is shown as its square, a view beside it is held back.
    (view,) = signed_out.get(url(walk, "/items")).json()["items"]
    assert (view["unavailable"], view["view"]) == ("near_protected", None)

    barrow.hidden_at = datetime.now(UTC)
    db.commit()

    # Hidden, it is nowhere for this reader, and nothing drawn near it says otherwise.
    (view,) = signed_out.get(url(walk, "/items")).json()["items"]
    assert (view["unavailable"], view["view"]["centre"]) == (None, centre)


def test_an_area_near_a_hidden_finding_is_shown_and_matched_as_drawn(
    db: Session,
    make_user: MakeUser,
    make_finding: MakeFinding,
    app: FastAPI,
    client_for: Callable[..., TestClient],
) -> None:
    barrow = make_finding(
        make_user(handle="Finder"), lon=LON, lat=LAT, feature_class=FeatureClass.ROUND_BARROW
    )
    drawn = box(LON + 0.002, LAT, LON + 0.003, LAT + 0.0005)
    survey = make(db, make_user(handle="Walker"), Visibility.PUBLIC, title="A survey", area=drawn)
    squares = sensitivity.square_cover(drawn)
    assert squares is not None
    # A place inside the area's squares and well outside the area itself.
    aside = squares.difference(drawn.buffer(0.002)).representative_point()
    beside = f"{aside.x - 0.0001},{aside.y - 0.0001},{aside.x + 0.0001},{aside.y + 0.0001}"
    signed_out = client_for(app)

    def listed() -> list[str]:
        items = signed_out.get(f"{API}/investigations?bbox={beside}").json()["items"]
        return [item["public_id"] for item in items]

    # While the barrow is shown as its square, the area is whole squares, on the page and to a search.
    assert shape(signed_out.get(url(survey)).json()["area"]).area > drawn.area * 2
    assert listed() == [survey.public_id]

    barrow.hidden_at = datetime.now(UTC)
    db.commit()

    assert shape(signed_out.get(url(survey)).json()["area"]).equals_exact(drawn, 1e-7)
    assert listed() == []
