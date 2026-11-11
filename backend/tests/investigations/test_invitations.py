"""Invitations, the moderators' list of unlisted investigations, and what account deletion does.

Decision 0009 allows collaborators only where moderators can read the
investigation, and nobody joins one without saying yes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth.accounts import delete_account
from fieldclub.models import Investigation, InvestigationMember, User
from fieldclub.schemas.common import encode_cursor
from fieldclub.services import investigations
from fieldclub.vocab import InvestigationRole, Visibility
from tests.helpers import ClientAs, MakeUser, error_code
from tests.investigations.support import API, add, make, url


def listed(client: TestClient, scope: str) -> list[str]:
    response = client.get(f"{API}/investigations", params={"scope": scope})
    assert response.status_code == 200, response.text
    return [item["public_id"] for item in response.json()["items"]]


# --------------------------------------------------------------------------
# Invitations
# --------------------------------------------------------------------------


def test_an_invitation_gives_no_role_until_it_is_accepted(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner, teen = make_user(handle="Owner"), make_user(handle="Teen", age_band="16_17")
    inv = make(db, owner, Visibility.UNLISTED, title="Hi Teen, reply in the notes")
    me, them = client_as(owner), client_as(teen)

    invited = me.put(url(inv, "/members/Teen"), json={"role": "editor"})
    assert invited.status_code == 201
    assert invited.json()["pending"] is True

    assert listed(them, "mine") == []
    assert listed(them, "invited") == [inv.public_id]
    detail = them.get(url(inv)).json()
    assert (detail["my_role"], detail["invited_as"]) == (None, "editor")
    assert detail["member_count"] == 1
    note = {"kind": "note", "note": "Hello"}
    refused = them.post(url(inv, "/items"), json=note)
    assert refused.status_code == 403
    assert error_code(refused) == "investigation_forbidden"
    members = me.get(url(inv, "/members")).json()["items"]
    assert [(m["user"]["handle"], m["pending"]) for m in members] == [("Owner", False), ("Teen", True)]

    accepted = them.post(url(inv, "/invitation"))
    assert accepted.status_code == 200
    assert (accepted.json()["my_role"], accepted.json()["invited_as"]) == ("editor", None)
    assert accepted.json()["member_count"] == 2
    assert listed(them, "mine") == [inv.public_id]
    assert listed(them, "invited") == []
    assert them.post(url(inv, "/items"), json=note).status_code == 201
    again = them.post(url(inv, "/invitation"))
    assert again.status_code == 404
    assert error_code(again) == "invitation_not_found"
    db.expire_all()
    investigations.check_members(db, inv)


def test_an_invitation_can_be_declined_or_withdrawn(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner, guest = make_user(handle="Owner"), make_user(handle="Guest")
    inv = make(db, owner, Visibility.PUBLIC)
    me, them = client_as(owner), client_as(guest)
    nothing = them.post(url(inv, "/invitation"))
    assert nothing.status_code == 404
    assert error_code(nothing) == "invitation_not_found"

    assert me.put(url(inv, "/members/Guest"), json={"role": "viewer"}).status_code == 201
    assert them.delete(url(inv, "/members/Guest")).status_code == 204
    assert listed(them, "invited") == []
    assert error_code(them.post(url(inv, "/invitation"))) == "invitation_not_found"

    assert me.put(url(inv, "/members/Guest"), json={"role": "viewer"}).status_code == 201
    assert me.delete(url(inv, "/members/Guest")).status_code == 204
    assert error_code(them.post(url(inv, "/invitation"))) == "invitation_not_found"


def test_an_invitation_keeps_the_role_changed_before_it_is_accepted(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner, guest = make_user(), make_user(handle="Guest")
    inv = make(db, owner, Visibility.PUBLIC)
    me = client_as(owner)
    assert me.put(url(inv, "/members/Guest"), json={"role": "viewer"}).status_code == 201
    changed = me.put(url(inv, "/members/Guest"), json={"role": "editor"})
    assert (changed.status_code, changed.json()["pending"]) == (200, True)
    assert client_as(guest).post(url(inv, "/invitation")).json()["my_role"] == "editor"


def test_someone_who_has_not_finished_the_welcome_step_cannot_be_invited(
    db: Session, make_user: MakeUser, client_as: ClientAs, newcomer: User, env: Callable[..., None]
) -> None:
    owner = make_user()
    make_user(handle="Teen", age_band="16_17")
    inv = make(db, owner, Visibility.UNLISTED)
    me = client_as(owner)
    refused = me.put(url(inv, f"/members/{newcomer.handle}"), json={"role": "editor"})
    assert refused.status_code == 404
    assert error_code(refused) == "user_not_found"
    env(MIN_AGE="18")
    below = me.put(url(inv, "/members/Teen"), json={"role": "editor"})
    assert error_code(below) == "user_not_found"
    assert listed(client_as(newcomer), "invited") == []


def test_a_member_who_cannot_contribute_can_still_leave(
    db: Session, make_user: MakeUser, client_as: ClientAs, newcomer: User
) -> None:
    owner = make_user()
    # Written straight through the service, as an older row might have been.
    inv = make(db, owner, Visibility.PUBLIC, members={InvestigationRole.VIEWER: [newcomer]})
    assert client_as(newcomer).delete(url(inv, f"/members/{newcomer.handle}")).status_code == 204
    assert db.scalar(select(InvestigationMember).where(InvestigationMember.user_id == newcomer.id)) is None


def test_the_owner_can_remove_a_banned_member(db: Session, make_user: MakeUser, client_as: ClientAs) -> None:
    owner, banned = make_user(), make_user(handle="Banned")
    inv = make(db, owner, Visibility.PUBLIC, members={InvestigationRole.EDITOR: [banned]})
    banned.banned_at = datetime.now(UTC)
    db.commit()
    assert client_as(owner).delete(url(inv, "/members/Banned")).status_code == 204


# --------------------------------------------------------------------------
# Moderators can find every unlisted investigation
# --------------------------------------------------------------------------


def test_moderators_list_every_unlisted_investigation(
    db: Session, make_user: MakeUser, client_as: ClientAs, client: TestClient
) -> None:
    owner, helper = make_user(), make_user(handle="Helper")
    shared = make(db, owner, Visibility.UNLISTED, members={InvestigationRole.EDITOR: [helper]})
    alone = make(db, make_user(), Visibility.UNLISTED)
    make(db, owner, Visibility.PUBLIC)
    make(db, owner, Visibility.PRIVATE)
    for role in ("moderator", "admin"):
        assert set(listed(client_as(make_user(role)), "unlisted")) == {shared.public_id, alone.public_id}
    for person in (owner, helper, make_user("trusted")):
        refused = client_as(person).get(f"{API}/investigations", params={"scope": "unlisted"})
        assert refused.status_code == 403
        assert error_code(refused) == "investigation_moderator_only"
    assert client.get(f"{API}/investigations", params={"scope": "unlisted"}).status_code == 401
    # And the moderator reads what is in it.
    add(db, shared, helper, note="Meet at the lay-by")
    items = client_as(make_user("moderator")).get(url(shared, "/items")).json()["items"]
    assert [item["note"] for item in items] == ["Meet at the lay-by"]


# --------------------------------------------------------------------------
# Ids beyond BIGINT
# --------------------------------------------------------------------------

HUGE = 10**30


def test_ids_too_large_for_the_database_are_refused_not_crashed_on(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner = make_user()
    inv = make(db, owner, Visibility.PUBLIC)
    item = add(db, inv, owner)
    me = client_as(owner)
    for response in (
        me.patch(url(inv, f"/items/{HUGE}"), json={"note": "x"}),
        me.delete(url(inv, f"/items/{HUGE}")),
        me.post(url(inv, f"/items/{HUGE}/move"), json={"after": None}),
        me.post(url(inv, f"/items/{item.id}/move"), json={"after": HUGE}),
        me.post(url(inv, "/items"), json={"kind": "record", "record_id": HUGE}),
    ):
        assert response.status_code == 422, response.text
    largest = 2**63 - 1
    assert error_code(me.delete(url(inv, f"/items/{largest}"))) == "item_not_found"
    for path, cursor in (
        ("/items", [0, HUGE]),
        ("/items", [HUGE, 1]),
        ("/members", [HUGE]),
    ):
        response = me.get(url(inv, path), params={"cursor": encode_cursor(cursor)})
        assert error_code(response) == "invalid_cursor", path
    listing = me.get(f"{API}/investigations", params={"cursor": encode_cursor(["2026-01-01T00:00:00", HUGE])})
    assert error_code(listing) == "invalid_cursor"


# --------------------------------------------------------------------------
# Account deletion
# --------------------------------------------------------------------------


def test_deleting_an_account_deals_with_its_investigations(db: Session, make_user: MakeUser) -> None:
    owner = make_user(handle="Leaving")
    early, late, viewer = make_user(), make_user(), make_user()
    private = make(db, owner, Visibility.PRIVATE, title="Only mine")
    add(db, private, owner, note="Private notes")
    handed_on = make(db, owner, Visibility.UNLISTED, members={InvestigationRole.EDITOR: [early, late]})
    unmanaged = make(db, owner, Visibility.PUBLIC, members={InvestigationRole.VIEWER: [viewer]})
    elsewhere = make(db, early, Visibility.PUBLIC, members={InvestigationRole.EDITOR: [owner]})
    invited = make(db, late, Visibility.PUBLIC)
    access = investigations.load(db, invited.public_id, late, investigations.Need.OWN, lock=True)
    investigations.put_member(db, access, owner, InvestigationRole.VIEWER)
    db.commit()
    private_id = private.id

    delete_account(db, owner)
    db.commit()
    db.expire_all()

    assert db.get(Investigation, private_id) is None
    assert handed_on.owner_id == early.id
    assert investigations.role_of(db, handed_on, early) is InvestigationRole.OWNER
    assert unmanaged.owner_id == owner.id
    assert investigations.load(db, unmanaged.public_id, None).investigation.id == unmanaged.id
    assert db.scalars(
        select(InvestigationMember.investigation_id).where(InvestigationMember.user_id == owner.id)
    ).all() == [unmanaged.id]
    for investigation in (handed_on, unmanaged, elsewhere, invited):
        investigations.check_members(db, investigation)


@pytest.mark.parametrize("fmt", ["csv", "html", "geojson"])
def test_exports_leave_out_invitations_nobody_accepted(
    db: Session, make_user: MakeUser, client_as: ClientAs, fmt: str
) -> None:
    owner = make_user()
    make_user(handle="Pending", display_name="Penny Pending")
    inv = make(db, owner, Visibility.PUBLIC)
    me = client_as(owner)
    assert me.put(url(inv, "/members/Pending"), json={"role": "editor"}).status_code == 201
    exported = me.get(url(inv, "/export"), params={"format": fmt})
    assert exported.status_code == 200
    assert "Penny" not in exported.text
    assert "Pending" not in exported.text


def test_an_invitation_tells_the_person_with_no_free_text(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner, guest = make_user(handle="Owner"), make_user(handle="Guest")
    inv = make(db, owner, Visibility.UNLISTED, title="Meet me at the barrow on Saturday")
    me, them = client_as(owner), client_as(guest)
    assert me.put(url(inv, "/members/Guest"), json={"role": "viewer"}).status_code == 201
    # Changing the role offered tells nobody again.
    assert me.put(url(inv, "/members/Guest"), json={"role": "editor"}).status_code == 200

    page = them.get(f"{API}/notifications").json()
    assert page["unread_count"] == 1
    (told,) = page["items"]
    assert told["kind"] == "investigation_invitation"
    assert told["investigation"] == inv.public_id
    assert told["actor"]["handle"] == "Owner"
    assert told["finding"] is None
    assert "barrow" not in them.get(f"{API}/notifications").text, "the title is free text: it isn't sent"
    # Nobody else hears of it, and it never reaches the feed or the event bus.
    assert me.get(f"{API}/notifications").json()["items"] == []
    assert "investigation_invitation" not in client_as(make_user()).get(f"{API}/activity").text

    # Once the owner takes the invitation back it leaves the list.
    assert me.delete(url(inv, "/members/Guest")).status_code == 204
    assert them.get(f"{API}/notifications").json() | {"next_cursor": None} == {
        "items": [],
        "next_cursor": None,
        "unread_count": 0,
    }
