"""The moderators' level route gives a finding's position to moderators only (Decision 0005),
and the admins' routes for orphaned markings give theirs, and the shapes before each change, to admins only.

Each answers with a finding's place, so each is tried as every kind of
viewer against every level, with the world `tests/findings/test_leaks.py`
builds and its lines.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import User
from fieldclub.services import findings, keeping
from fieldclub.vocab import Sensitivity
from tests.findings import test_leaks as leaks
from tests.helpers import MakeUser, error_code
from tests.moderation.support import API, REASON

world = leaks.world

REFUSED = {
    "signed_out": (401, "unauthorised"),
    "member": (403, "moderators_only"),
    "finder": (403, "moderators_only"),
    "trusted": (403, "moderators_only"),
}


@pytest.mark.parametrize("viewer", leaks.VIEWERS)
@pytest.mark.parametrize("level", leaks.LEVELS)
@pytest.mark.parametrize("kind", leaks.KINDS)
def test_the_moderators_level_route_answers_only_moderators(
    world: leaks.World, viewer: str, level: Sensitivity, kind: str
) -> None:
    finding = world.of(kind, level)
    response = world.client(viewer).put(
        f"{API}/mod/findings/{finding.public_id}/sensitivity", json={"level": level.value, **REASON}
    )
    where = f"PUT /mod/findings/{{id}}/sensitivity as {viewer} ({level})"
    if viewer == "moderator":
        assert response.status_code == 200, response.text
        leaks.check(response.text, leaks.SEES[viewer], {level}, where=where)
        assert response.json()["location"]["obscured"] is False
    else:
        assert (response.status_code, error_code(response)) == REFUSED[viewer], where
        leaks.check(response.text, set(), where=where)
    assert response.headers["cache-control"] == "private, no-cache"


ADMIN_REFUSED = {
    "signed_out": (401, "unauthorised"),
    "member": (403, "admins_only"),
    "finder": (403, "admins_only"),
    "trusted": (403, "admins_only"),
    "moderator": (403, "admins_only"),
}


def _orphaned(world: leaks.World, db: Session, make_user: MakeUser) -> User:
    """Hand each line to a new keeper, then ban them, so every line is orphaned. Returns an admin."""
    keeper = make_user(handle="Gone")
    for line in world.lines.values():
        keeping.offer(db, findings.lock(db, line), world.people["finder"], keeper.handle)
        keeping.take(db, line, keeper)
    keeper.banned_at = datetime.now(UTC)
    db.commit()
    return make_user("admin", handle="Admin")


@pytest.mark.parametrize("viewer", [*leaks.VIEWERS, "admin"])
@pytest.mark.parametrize("level", leaks.LEVELS)
def test_the_admins_marking_routes_answer_only_admins(
    world: leaks.World,
    db: Session,
    make_user: MakeUser,
    app: FastAPI,
    client_for: Callable[..., TestClient],
    viewer: str,
    level: Sensitivity,
) -> None:
    """The list of orphaned markings, their earlier shapes and their removal answer admins alone.

    Everyone else, moderators included, is refused with nothing of the
    finding in the refusal. An admin sees every finding exactly, and the
    earlier shapes are the one place the shape before a change is sent.
    """
    admin = _orphaned(world, db, make_user)
    client = client_for(app, admin) if viewer == "admin" else world.client(viewer)
    line = world.lines[level]
    reads = {
        "orphaned": client.get(f"{API}/mod/markings/orphaned"),
        "shapes": client.get(f"{API}/mod/findings/{line.public_id}/shapes"),
    }
    removed = client.put(
        f"{API}/mod/findings/{line.public_id}/marking",
        json={"to_revision": 0, "shape_revision": 1, **REASON},
    )
    for name, response in [*reads.items(), ("marking", removed)]:
        where = f"{name} as {viewer} ({level} line)"
        if viewer == "admin":
            assert response.status_code == 200, f"{where}: {response.text}"
            # The earlier shape is the line as first drawn, three of its points; the rest is the page.
            present = None if name == "orphaned" and level is not Sensitivity.OPEN else {level}
            leaks.check(response.text, set(leaks.LEVELS), present, where=where)
        else:
            assert (response.status_code, error_code(response)) == ADMIN_REFUSED[viewer], where
            leaks.check(response.text, set(), where=where)
            assert "path_before" not in response.text
        assert response.headers["cache-control"] == "private, no-cache", where
    if viewer == "admin":
        listed = {item["finding"]["public_id"] for item in reads["orphaned"].json()["items"]}
        assert listed == {f.public_id for f in world.lines.values()}
        (change,) = reads["shapes"].json()["items"]
        assert change["path_before"]["points"] == [
            {"lon": lon, "lat": lat, "kind": "corner"} for lon, lat in leaks.LINES[level][:3]
        ]
        assert removed.json()["location"]["shape"]["revision"] == 2


@pytest.mark.parametrize("viewer", [*leaks.VIEWERS, "admin"])
def test_the_admins_marking_reads_leave_out_what_is_hidden(
    world: leaks.World,
    db: Session,
    make_user: MakeUser,
    app: FastAPI,
    client_for: Callable[..., TestClient],
    viewer: str,
) -> None:
    """A hidden orphaned marking reaches admins, who see what moderators hide, and nobody else.

    Only admins may call these reads at all, and an admin is a moderator, so
    the hidden line is listed for them and refused, with nothing of it, to
    everyone else.
    """
    admin = _orphaned(world, db, make_user)
    hidden = world.lines[Sensitivity.PROTECTED]
    hidden.hidden_at = datetime.now(UTC)
    db.commit()
    client = client_for(app, admin) if viewer == "admin" else world.client(viewer)
    listed = client.get(f"{API}/mod/markings/orphaned")
    shapes_of = client.get(f"{API}/mod/findings/{hidden.public_id}/shapes")
    if viewer == "admin":
        assert hidden.public_id in {item["finding"]["public_id"] for item in listed.json()["items"]}
        assert shapes_of.status_code == 200
        return
    for response in (listed, shapes_of):
        assert (response.status_code, error_code(response)) == ADMIN_REFUSED[viewer]
        assert hidden.public_id not in response.text
        leaks.check(response.text, set(), where=f"hidden line as {viewer}")
