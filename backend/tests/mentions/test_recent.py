"""`GET /mentions/recent`: the feed across the map leaks no position and nothing hidden.

The leak check is the one the findings tests use: each level's finding sits
at its own point, and the whole response is searched for that point in every
form it could take.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy.orm import Session

from fieldclub.models import Finding, Mention, User
from fieldclub.services import mentions
from fieldclub.vocab import FeatureClass, MentionKind, Sensitivity
from tests.findings.support import create
from tests.findings.test_leaks import LEVELS, POINTS, SEES, VIEWERS, check
from tests.helpers import MakeUser
from tests.mentions.support import API

# Not fetched: a port we don't fetch from, so no answer needs recording.
STORY = "https://www.wiltshire-gazette.example:8443/story-{}"


@dataclass
class World:
    people: dict[str, User]
    findings: dict[Sensitivity, Finding]
    client: Callable[[str], TestClient]


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]) -> World:
    people = {
        "finder": make_user(handle="Finder"),
        "member": make_user(handle="Member"),
        "trusted": make_user("trusted", handle="Trusted"),
        "moderator": make_user("moderator", handle="Moderator"),
    }
    adder = make_user(handle="Presenter")
    made = {}
    for level, (lon, lat) in POINTS.items():
        finding = create(
            db,
            people["finder"],
            lon=lon,
            lat=lat,
            feature_class=FeatureClass.ENCLOSURE,
            requested_sensitivity=level,
            outline=box(lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005),
            title=f"A {level} enclosure",
        )
        assert finding.sensitivity == level.value
        mentions.add(db, finding, adder, STORY.format(level.value))
        # A map link to the exact spot, as stored had it been added while the finding was open:
        # adding one to a finding that isn't open is refused.
        link = f"https://www.google.com/maps/@{lat:.6f},{lon:.6f},18z"
        db.add(
            Mention(
                finding_id=finding.id, user_id=adder.id, kind=MentionKind.ARTICLE.value, url=link,
                canonical_url=link, match_key=link, provider="google.com", title="On the map",
            )
        )  # fmt: skip
        db.commit()
        made[level] = finding

    def client(viewer: str) -> TestClient:
        return client_for(app, None if viewer == "signed_out" else people[viewer])

    return World(people, made, client)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_the_feed_shows_each_position_as_the_viewer_may_see_it(world: World, viewer: str) -> None:
    response = world.client(viewer).get(f"{API}/mentions/recent")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-cache"
    check(response.text, SEES[viewer], SEES[viewer], where="GET /mentions/recent")
    by_finding = {item["finding"]["public_id"]: item for item in response.json()["items"]}
    for item in response.json()["items"]:
        level = next(
            level
            for level, finding in world.findings.items()
            if finding.public_id == item["finding"]["public_id"]
        )
        if item["title"] == "On the map":
            assert (item["url"] is None) is (level not in SEES[viewer])
    assert set(by_finding) == {f.public_id for f in world.findings.values()}
    for level, finding in world.findings.items():
        location = by_finding[finding.public_id]["finding"]["location"]
        assert location["obscured"] is (level not in SEES[viewer])
        assert (location["outline"] is None) is (level not in SEES[viewer])
        assert (location["square"] is None) is (level in SEES[viewer])


@pytest.mark.parametrize("viewer", VIEWERS)
def test_every_page_of_the_feed_is_checked(world: World, viewer: str) -> None:
    client = world.client(viewer)
    cursor, seen = None, 0
    while True:
        params: dict[str, str | int] = {"limit": 1} | ({"cursor": cursor} if cursor else {})
        page = client.get(f"{API}/mentions/recent", params=params)
        check(page.text, SEES[viewer], where="a page of GET /mentions/recent")
        seen += len(page.json()["items"])
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
    assert seen == 2 * len(LEVELS)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_a_findings_own_list_carries_no_position(world: World, viewer: str) -> None:
    """No position of its own, and a mention's address only to those who see the finding exactly."""
    for level, finding in world.findings.items():
        listed = world.client(viewer).get(f"{API}/findings/{finding.public_id}/mentions")
        assert listed.status_code == 200
        check(listed.text, SEES[viewer] & {level}, where="GET /findings/{id}/mentions")
        (link,) = [item for item in listed.json()["items"] if item["title"] == "On the map"]
        assert (link["url"] is None) is (level not in SEES[viewer])


def test_the_feed_is_newest_first(world: World) -> None:
    items = world.client("member").get(f"{API}/mentions/recent").json()["items"]
    assert [item["id"] for item in items] == sorted((item["id"] for item in items), reverse=True)
    assert items[0]["added_by"]["handle"] == "Presenter"


@pytest.mark.parametrize("viewer", VIEWERS)
def test_hidden_and_withdrawn_findings_leave_the_feed(world: World, db: Session, viewer: str) -> None:
    hidden = world.findings[Sensitivity.OPEN]
    withdrawn = world.findings[Sensitivity.PROTECTED]
    hidden.hidden_at = datetime(2026, 11, 5, tzinfo=UTC)
    withdrawn.state = "withdrawn"
    db.commit()
    listed = {
        item["finding"]["public_id"]
        for item in world.client(viewer).get(f"{API}/mentions/recent").json()["items"]
    }
    assert withdrawn.public_id not in listed
    # Only the people who may see a hidden finding see it here.
    assert (hidden.public_id in listed) is (viewer in ("finder", "moderator"))


def test_a_removed_mention_leaves_the_feed(world: World, db: Session) -> None:
    finding = world.findings[Sensitivity.OPEN]
    mention = next(
        m for m in mentions.for_finding(db, finding, None, limit=5).mentions if m.title != "On the map"
    )
    mention.deleted_at = datetime(2026, 11, 5, tzinfo=UTC)
    db.commit()
    for viewer in VIEWERS:
        listed = world.client(viewer).get(f"{API}/mentions/recent").json()["items"]
        assert mention.id not in {item["id"] for item in listed}
