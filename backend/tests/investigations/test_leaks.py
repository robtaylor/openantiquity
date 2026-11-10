"""No investigation route gives a viewer a finding's exact position they shouldn't have.

One public investigation holds an open, a protected and a restricted
finding, each with an outline and at a point of its own. Its items and its
three exports are fetched as someone signed out, a member, the finder, a
trusted member and a moderator. Items follow what the finding's page shows;
downloads follow the stricter rule for downloads (Decision 0005, rule 8).
The check is the findings leak test's: it searches the whole body for the
exact position as degrees, as grid references and as easting and northing.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy.orm import Session

from fieldclub.models import Investigation, User
from fieldclub.vocab import FeatureClass, InvestigationItemKind, Visibility
from tests.findings.support import create
from tests.findings.test_leaks import DOWNLOADS, LEVELS, POINTS, SEES, VIEWERS, check
from tests.helpers import MakeUser
from tests.investigations.support import add, make, url


@pytest.fixture
def world(
    db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
) -> tuple[Investigation, Callable[[str], TestClient]]:
    finder = make_user(handle="Finder")
    people: dict[str, User] = {
        "finder": finder,
        "member": make_user(handle="Member"),
        "trusted": make_user("trusted", handle="Trusted"),
        "moderator": make_user("moderator", handle="Moderator"),
    }
    owner = make_user(handle="Owner")
    investigation = make(db, owner, Visibility.PUBLIC)
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
        assert finding.sensitivity == level.value
        add(db, investigation, owner, kind=InvestigationItemKind.FINDING, finding=finding.public_id)

    def client(viewer: str) -> TestClient:
        return client_for(app, None if viewer == "signed_out" else people[viewer])

    return investigation, client


@pytest.mark.parametrize("viewer", VIEWERS)
def test_items_show_what_the_page_shows(
    world: tuple[Investigation, Callable[[str], TestClient]], viewer: str
) -> None:
    investigation, client = world
    response = client(viewer).get(url(investigation, "/items"))
    assert response.status_code == 200
    check(response.text, SEES[viewer], SEES[viewer], where="GET /investigations/{id}/items")
    for item, level in zip(response.json()["items"], LEVELS, strict=True):
        location = item["finding"]["location"]
        assert location["obscured"] is (level not in SEES[viewer])
        assert (location["outline"] is None) is (level not in SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("format", ["geojson", "csv", "html"])
def test_downloads_follow_the_download_rule(
    world: tuple[Investigation, Callable[[str], TestClient]], viewer: str, format: str
) -> None:
    investigation, client = world
    response = client(viewer).get(url(investigation, "/export"), params={"format": format})
    assert response.status_code == 200
    check(response.text, DOWNLOADS[viewer], DOWNLOADS[viewer], where=f"export {format}")
    if format == "geojson":
        features = response.json()["features"]
        for feature, level in zip(features, LEVELS, strict=True):
            assert feature["properties"]["obscured"] is (level not in DOWNLOADS[viewer])
            assert (feature["properties"]["outline"] is None) is (level not in DOWNLOADS[viewer])
