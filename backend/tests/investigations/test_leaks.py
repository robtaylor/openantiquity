"""No investigation route gives a viewer a finding's exact position they shouldn't have.

One public investigation holds an open, a protected and a restricted
finding, each with an outline and at a point of its own, and a line at each
level, extended after it was drawn. Its items and its
three exports are fetched as someone signed out, a member, the finder, a
trusted member and a moderator. Items follow what the finding's page shows,
and so does the item a write hands back to its writer; downloads follow the
stricter rule for downloads (Decision 0005, rule 8).
The check is the findings leak test's: it searches the whole body for the
exact position as degrees, as grid references and as easting and northing.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Finding, Investigation, User
from fieldclub.vocab import FeatureClass, InvestigationItemKind, Sensitivity, Visibility
from tests.findings.support import create
from tests.findings.test_leaks import DOWNLOADS, LEVELS, POINTS, SEES, VIEWERS, check, draw_line, extend_line
from tests.helpers import MakeUser
from tests.investigations.support import API, add, make, url

# What the investigation holds, in order: each level's area, then each level's line.
HELD = [*((level, "area") for level in LEVELS), *((level, "line") for level in LEVELS)]


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
    for level in LEVELS:
        line = draw_line(db, finder, level)
        extend_line(db, finder, line, level)
        add(db, investigation, owner, kind=InvestigationItemKind.FINDING, finding=line.public_id)

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
    for item, (level, kind) in zip(response.json()["items"], HELD, strict=True):
        location = item["finding"]["location"]
        assert location["obscured"] is (level not in SEES[viewer])
        # A finding in a list carries no shape, and its kind only for exact viewers.
        assert location["outline"] is None
        assert location["shape_kind"] == (kind if level in SEES[viewer] else None)


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
        for feature, (level, kind) in zip(features, HELD, strict=True):
            exact = level in DOWNLOADS[viewer]
            assert feature["properties"]["obscured"] is not exact
            assert (feature["properties"]["outline"] is None) is not exact
            assert feature["properties"]["shape_kind"] == (kind if exact else None)


@pytest.mark.parametrize("viewer", ["member", "finder", "trusted", "moderator"])
def test_item_writes_answer_with_what_the_writer_may_see(
    world: tuple[Investigation, Callable[[str], TestClient]], db: Session, viewer: str
) -> None:
    _, client = world
    writer = client(viewer)
    created = writer.post(f"{API}/investigations", json={"title": f"{viewer}'s notebook"})
    assert created.status_code == 201, created.text
    base = f"{API}/investigations/{created.json()['public_id']}/items"
    for finding in db.scalars(select(Finding).order_by(Finding.id)):
        level = Sensitivity(finding.sensitivity)
        allowed = {level} & SEES[viewer]
        added = writer.post(base, json={"kind": "finding", "finding": finding.public_id})
        assert added.status_code == 201, added.text
        check(added.text, allowed, allowed, where=f"POST item ({level})")
        item = f"{base}/{added.json()['id']}"
        changed = writer.patch(item, json={"note": "Worth a visit."})
        assert changed.status_code == 200, changed.text
        check(changed.text, allowed, allowed, where=f"PATCH item ({level})")
        moved = writer.post(f"{item}/move", json={"after": None})
        assert moved.status_code == 200, moved.text
        check(moved.text, allowed, allowed, where=f"move item ({level})")
