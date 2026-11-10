"""No route this track adds returns an exact position to a viewer who shouldn't have it.

The feed, notifications, profiles, a person's findings and contributions,
points, and the event stream's payloads, each as a signed-out visitor, a
member, the finder, a trusted member and a moderator, against an open, a
protected and a restricted finding. The check is the findings track's: it
searches the whole body for the exact position in every form it could take.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, User
from fieldclub.services import events, findings, sensitivity
from fieldclub.services.events import Announcement, EventHub, StreamFilter
from fieldclub.vocab import FeatureClass, Sensitivity, Visible
from tests.activity.support import API, add_map, comment, follow
from tests.findings.support import answer, create
from tests.findings.test_leaks import LEVELS, POINTS, SEES, check
from tests.helpers import ClientFor, MakeUser

VIEWERS = ("signed_out", "member", "finder", "trusted", "moderator")


@dataclass
class World:
    people: dict[str, User]
    findings: dict[Sensitivity, Finding]
    client: Callable[[str], TestClient]


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: ClientFor) -> World:
    finder = make_user(handle="Finder")
    people = {
        "finder": finder,
        "member": make_user(handle="Member"),
        "trusted": make_user("trusted", handle="Trusted"),
        "moderator": make_user("moderator", handle="Moderator"),
    }
    helpers = [make_user("trusted", handle=f"Helper{n}") for n in (1, 2)]
    made: dict[Sensitivity, Finding] = {}
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
        follow(db, finding, people["member"], people["trusted"], people["moderator"])
        for helper in helpers:
            answer(db, finding, helper, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
        add_map(db, finding, helpers[0], url=f"https://maps.example/view?lat={lat:.6f}&lon={lon:.6f}")
        comment(db, finding, helpers[1])
        assert finding.sensitivity == level.value
        made[level] = finding

    def client(viewer: str) -> TestClient:
        return client_for(app, None if viewer == "signed_out" else people[viewer])

    return World(people, made, client)


def get(world: World, viewer: str, path: str, **params: Any) -> str:
    response = world.client(viewer).get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.text


@pytest.mark.parametrize("viewer", VIEWERS)
def test_the_feed(world: World, viewer: str) -> None:
    allowed = SEES[viewer]
    check(get(world, viewer, "/activity", limit=200), allowed, allowed, where="feed")
    for level, finding in world.findings.items():
        shown = allowed & {level}
        text = get(world, viewer, "/activity", finding=finding.public_id)
        check(text, shown, shown, where=f"feed of the {level} finding")


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("level", LEVELS)
def test_a_box_round_the_exact_point_finds_only_the_square(
    world: World, viewer: str, level: Sensitivity
) -> None:
    lon, lat = POINTS[level]
    finding = world.findings[level]
    tiny = f"{lon - 0.0001},{lat - 0.0001},{lon + 0.0001},{lat + 0.0001}"
    # The box is matched against the square's centre for everyone, so a box
    # that holds only the spot finds nothing, however small it gets.
    assert json.loads(get(world, viewer, "/activity", bbox=tiny))["items"] == []
    centre = sensitivity.square_centre(finding)
    assert centre is not None
    around = f"{centre[0] - 0.0001},{centre[1] - 0.0001},{centre[0] + 0.0001},{centre[1] + 0.0001}"
    text = get(world, viewer, "/activity", bbox=around)
    assert finding.public_id in text
    check(text, SEES[viewer] & {level}, where=f"box round the {level} square")


@pytest.mark.parametrize("viewer", [v for v in VIEWERS if v != "signed_out"])
def test_notifications(world: World, viewer: str) -> None:
    text = get(world, viewer, "/notifications", limit=200)
    assert json.loads(text)["items"], "every viewer here follows every finding"
    check(text, SEES[viewer], SEES[viewer], where="notifications")


@pytest.mark.parametrize("viewer", VIEWERS)
def test_profiles_findings_and_contributions(world: World, viewer: str) -> None:
    allowed = SEES[viewer]
    check(get(world, viewer, "/users/Finder"), set(), where="profile")
    check(get(world, viewer, "/users/Finder/findings"), allowed, allowed, where="a person's findings")
    for kind in (None, "evidence", "comment", "second_look"):
        params = {"kind": kind} if kind else {}
        for helper in ("Helper1", "Helper2"):
            text = get(world, viewer, f"/users/{helper}/contributions", **params)
            check(text, allowed, where=f"{helper}'s contributions ({kind or 'all'})")


@pytest.mark.parametrize("viewer", [v for v in VIEWERS if v != "signed_out"])
def test_points(world: World, viewer: str) -> None:
    handle = world.people[viewer].handle
    check(get(world, viewer, f"/users/{handle}/points"), SEES[viewer], where="points")


def test_the_finders_points_are_for_findings_they_see_exactly(world: World) -> None:
    text = get(world, "finder", "/users/Finder/points")
    assert json.loads(text)["items"], "the finder earned points for Seen"
    check(text, set(LEVELS), set(LEVELS), where="finder's points")


def test_stream_payloads_carry_no_position(world: World, db: Session) -> None:
    """Every event the hub would announce, as a client gets it, holds ids and a kind alone."""

    async def announced() -> list[Announcement]:
        hub = EventHub(
            events.conninfo(), events.lookup_public, queue_size=200, max_per_address=1, max_streams=1
        )
        hub.start()
        await asyncio.wait_for(hub.connected.wait(), 10)
        everything = hub.subscribe(StreamFilter(), "a")
        for row in db.query(Activity).order_by(Activity.id):
            await hub.deliver(
                json.dumps(
                    {
                        "id": row.id,
                        "kind": row.kind,
                        "finding": next(
                            f.public_id for f in world.findings.values() if f.id == row.finding_id
                        ),
                        "investigation": None,
                        "actor": None,
                    }
                )
            )
        got = []
        while (item := await everything.next(0.1)) is not None:
            assert isinstance(item, Announcement)
            got.append(item)
        await hub.stop()
        return got

    got = asyncio.run(announced())
    assert len(got) == db.query(Activity).count()
    for item in got:
        assert set(asdict(item)) == {"id", "kind", "finding", "investigation", "actor"}
        check(json.dumps(asdict(item)), set(), where=f"stream event {item.kind}")


def test_a_withdrawn_finding_leaves_every_list(world: World, db: Session) -> None:
    finding = world.findings[Sensitivity.OPEN]
    findings.withdraw_finding(db, findings.lock(db, finding), world.people["finder"])
    db.commit()
    for viewer in VIEWERS:
        for path in ("/activity", "/users/Finder/findings", "/users/Helper1/contributions"):
            assert finding.public_id not in get(world, viewer, path), f"{viewer} still sees it in {path}"
