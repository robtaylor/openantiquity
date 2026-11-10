"""Every investigation route, as every kind of viewer, at every visibility.

The viewers are someone signed out, a signed-in stranger, a moderator who
isn't a member, a viewer, an editor and the owner. A private investigation
can't have viewers or editors, so there those two are strangers too.

| Need  | Who passes      | Everyone else who can read it | Can't read it |
|-------|-----------------|-------------------------------|---------------|
| read  | anyone who can  |                               | 404           |
| edit  | owner, editor   | 403 investigation_forbidden   | 404           |
| own   | owner           | 403 investigation_owner_only  | 404           |

Signed out, every write is a 401 before anything else is looked at.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from shapely.geometry import box
from sqlalchemy.orm import Session

from fieldclub.models import Investigation, User
from fieldclub.vocab import InvestigationRole, Visibility
from tests.helpers import MakeUser, error_code
from tests.investigations.support import API, add, make, url

VIEWERS = ("signed_out", "stranger", "moderator", "viewer", "editor", "owner")
VISIBILITIES = (Visibility.PUBLIC, Visibility.UNLISTED, Visibility.PRIVATE)


@dataclass
class World:
    investigation: Investigation
    people: dict[str, User]
    item_ids: list[int]
    client: Callable[[str], TestClient]


@pytest.fixture
def world_for(
    db: Session, make_user: MakeUser, app: FastAPI, client_for: Callable[..., TestClient]
) -> Callable[[Visibility], World]:
    def build(visibility: Visibility) -> World:
        people = {
            "owner": make_user(handle="Owner"),
            "editor": make_user(handle="Editor"),
            "viewer": make_user(handle="Viewer"),
            "stranger": make_user(handle="Stranger"),
            "moderator": make_user("moderator", handle="Moderator"),
            "newcomer": make_user(handle="Newcomer"),
        }
        members = (
            {}
            if visibility is Visibility.PRIVATE
            else {InvestigationRole.EDITOR: [people["editor"]], InvestigationRole.VIEWER: [people["viewer"]]}
        )
        investigation = make(db, people["owner"], visibility, members=members, notes="Working notes")
        item_ids = [add(db, investigation, people["owner"], note=f"note {n}").id for n in range(3)]

        def client(viewer: str) -> TestClient:
            return client_for(app, None if viewer == "signed_out" else people[viewer])

        return World(investigation, people, item_ids, client)

    return build


def role(viewer: str, visibility: Visibility) -> str:
    """The viewer's part in the investigation: owner, editor, viewer or none."""
    if viewer in ("viewer", "editor") and visibility is Visibility.PRIVATE:
        return "none"
    return viewer if viewer in ("owner", "editor", "viewer") else "none"


def expect(
    response: Response, viewer: str, visibility: Visibility, need: str, ok: int, *, write: bool
) -> None:
    """Check a response against the table in the module docstring."""
    part = role(viewer, visibility)
    where = f"{response.request.method} {response.request.url.path} as {viewer} on {visibility}"
    if write and viewer == "signed_out":
        assert response.status_code == 401, where
        return
    if visibility is Visibility.PRIVATE and part != "owner":
        assert response.status_code == 404, where
        assert error_code(response) == "investigation_not_found", where
        return
    passes = {"read": True, "edit": part in ("owner", "editor"), "own": part == "owner"}[need]
    if passes:
        assert response.status_code == ok, f"{where}: {response.text}"
    else:
        assert response.status_code == 403, where
        expected = "investigation_forbidden" if need == "edit" else "investigation_owner_only"
        assert error_code(response) == expected, where


@pytest.mark.parametrize("visibility", VISIBILITIES)
@pytest.mark.parametrize("viewer", VIEWERS)
def test_every_route(world_for: Callable[[Visibility], World], viewer: str, visibility: Visibility) -> None:
    world = world_for(visibility)
    client = world.client(viewer)
    inv = world.investigation
    first, second, third = world.item_ids

    # Reading.
    for path in (
        "",
        "/items",
        "/members",
        "/export?format=geojson",
        "/export?format=csv",
        "/export?format=html",
    ):
        response = client.get(url(inv, path))
        expect(response, viewer, visibility, "read", 200, write=False)
    detail = client.get(url(inv))
    if detail.status_code == 200:
        mine = role(viewer, visibility)
        assert detail.json()["my_role"] == (None if mine == "none" else mine)
        assert detail.json()["notes"] == "Working notes"
        assert detail.headers["Cache-Control"] == "private, no-cache"

    # Editing.
    expect(client.patch(url(inv), json={"title": "Renamed"}), viewer, visibility, "edit", 200, write=True)
    note = {"kind": "note", "note": "Added by a test"}
    expect(client.post(url(inv, "/items"), json=note), viewer, visibility, "edit", 201, write=True)
    patched = client.patch(url(inv, f"/items/{first}"), json={"note": "edited"})
    expect(patched, viewer, visibility, "edit", 200, write=True)
    moved = client.post(url(inv, f"/items/{third}/move"), json={"after": None})
    expect(moved, viewer, visibility, "edit", 200, write=True)
    expect(client.delete(url(inv, f"/items/{second}")), viewer, visibility, "edit", 204, write=True)

    # Members and visibility: the owner's.
    added = client.put(url(inv, "/members/Newcomer"), json={"role": "viewer"})
    if viewer == "owner" and visibility is Visibility.PRIVATE:
        assert added.status_code == 409
        assert error_code(added) == "private_investigation_has_one_member"
    else:
        expect(added, viewer, visibility, "own", 201, write=True)
    removed = client.delete(url(inv, "/members/Newcomer"))
    if viewer == "owner" and visibility is Visibility.PRIVATE:
        assert removed.status_code == 404
        assert error_code(removed) == "member_not_found"
    else:
        expect(removed, viewer, visibility, "own", 204, write=True)
    other = {Visibility.PUBLIC: "unlisted", Visibility.UNLISTED: "public", Visibility.PRIVATE: "unlisted"}[
        visibility
    ]
    changed = client.patch(url(inv), json={"visibility": other})
    if role(viewer, visibility) == "editor":
        assert changed.status_code == 403
        assert error_code(changed) == "investigation_owner_only"
    else:
        expect(changed, viewer, visibility, "edit", 200, write=True)
    expect(client.delete(url(inv)), viewer, visibility, "own", 204, write=True)


@pytest.mark.parametrize("visibility", [Visibility.PUBLIC, Visibility.UNLISTED])
@pytest.mark.parametrize("member", ["viewer", "editor"])
def test_a_member_can_leave(
    world_for: Callable[[Visibility], World], visibility: Visibility, member: str
) -> None:
    world = world_for(visibility)
    client = world.client(member)
    assert client.delete(url(world.investigation, f"/members/{member.capitalize()}")).status_code == 204
    assert client.get(url(world.investigation)).json()["my_role"] is None


def test_the_owner_cannot_leave_or_be_removed(world_for: Callable[[Visibility], World]) -> None:
    world = world_for(Visibility.PUBLIC)
    response = world.client("owner").delete(url(world.investigation, "/members/Owner"))
    assert response.status_code == 409
    assert error_code(response) == "owner_is_always_a_member"
    owner_role = world.client("owner").put(
        url(world.investigation, "/members/Owner"), json={"role": "viewer"}
    )
    assert owner_role.status_code == 409
    assert (
        world.client("owner")
        .put(url(world.investigation, "/members/Editor"), json={"role": "owner"})
        .status_code
        == 422
    )


def test_a_role_can_be_changed_and_an_unknown_handle_is_not_found(
    world_for: Callable[[Visibility], World],
) -> None:
    world = world_for(Visibility.PUBLIC)
    owner = world.client("owner")
    changed = owner.put(url(world.investigation, "/members/Viewer"), json={"role": "editor"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "editor"
    note = {"kind": "note", "note": "Now I can"}
    assert world.client("viewer").post(url(world.investigation, "/items"), json=note).status_code == 201
    for handle in ("NobodyAtAll", "Nul%00Handle"):
        missing = owner.put(url(world.investigation, f"/members/{handle}"), json={"role": "viewer"})
        assert missing.status_code == 404
        assert error_code(missing) == "user_not_found"
    too_long = owner.put(url(world.investigation, "/members/" + "x" * 65), json={"role": "viewer"})
    assert too_long.status_code == 422
    members = owner.get(url(world.investigation, "/members")).json()["items"]
    assert [m["user"]["handle"] for m in members] == ["Owner", "Editor", "Viewer"]
    assert [m["role"] for m in members] == ["owner", "editor", "editor"]


def test_lists_show_only_public_ones_and_mine_shows_all_of_mine(
    db: Session, make_user: MakeUser, client_as: Callable[[User], TestClient], client: TestClient
) -> None:
    owner, helper = make_user(), make_user()
    made = {v: make(db, owner, v, title=f"A {v} one") for v in VISIBILITIES}
    shared = make(db, make_user(), Visibility.UNLISTED, members={InvestigationRole.VIEWER: [helper]})
    for viewer in (client, client_as(helper), client_as(owner), client_as(make_user("moderator"))):
        listed = viewer.get(f"{API}/investigations").json()["items"]
        assert [item["public_id"] for item in listed] == [made[Visibility.PUBLIC].public_id]
    mine = client_as(owner).get(f"{API}/investigations", params={"scope": "mine"}).json()["items"]
    assert {item["public_id"] for item in mine} == {inv.public_id for inv in made.values()}
    theirs = client_as(helper).get(f"{API}/investigations", params={"scope": "mine"}).json()["items"]
    assert [item["public_id"] for item in theirs] == [shared.public_id]
    signed_out = client.get(f"{API}/investigations", params={"scope": "mine"})
    assert signed_out.status_code == 401


def test_the_public_list_pages_and_filters_by_area(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    owner = make_user()
    avebury = make(db, owner, area=box(-1.87, 51.42, -1.84, 51.44), title="Avebury")
    make(db, owner, area=box(-1.83, 51.17, -1.81, 51.19), title="Stonehenge")
    nowhere = make(db, owner, title="No area")
    found = client.get(f"{API}/investigations", params={"bbox": "-1.9,51.4,-1.8,51.45"}).json()
    assert [item["public_id"] for item in found["items"]] == [avebury.public_id]
    assert found["items"][0]["area"]["type"] == "Polygon"
    pages, cursor = [], None
    while True:
        params = {"limit": 1} | ({"cursor": cursor} if cursor else {})
        page = client.get(f"{API}/investigations", params=params).json()
        pages.extend(item["public_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(pages) == 3
    assert pages[0] == nowhere.public_id
    bad = client.get(f"{API}/investigations", params={"bbox": "1,2,3"})
    assert error_code(bad) == "invalid_bbox"
    assert error_code(client.get(f"{API}/investigations", params={"cursor": "nonsense"})) == "invalid_cursor"
