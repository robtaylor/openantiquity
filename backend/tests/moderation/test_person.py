"""`GET /mod/users/{handle}`: one person as a moderator sees them, and what that moderator may do.

The page is for an account the public profile may not show: a banned one,
or one its owner deleted. Its `actions` say, for ban, unban and each role,
whether the moderator may do it, with the code the route would refuse with
when not, so the interface needs no copy of the rules. Each answer is held
to what the route actually does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.auth import accounts
from fieldclub.models import AuthIdentity
from fieldclub.vocab import Role
from tests.activity.support import walk
from tests.helpers import ClientAs, MakeUser, error_code
from tests.moderation.support import API, REASON

BANNED_AT = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)


def person(client: TestClient, handle: str) -> dict[str, Any]:
    response = client.get(f"{API}/mod/users/{handle}")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_moderator_sees_a_banned_account_the_public_profile_hides(
    make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    make_user(handle="Banned", display_name="Pat Banned", banned_at=BANNED_AT, email="pat@example.org")
    assert error_code(client.get(f"{API}/users/Banned")) == "user_not_found"
    seen = person(client_as(make_user(Role.MODERATOR)), "banned")
    assert (seen["handle"], seen["display_name"], seen["role"]) == ("Banned", "Pat Banned", "member")
    assert seen["banned"] is True
    assert seen["banned_at"] == "2026-11-01T09:30:00Z"
    assert seen["deleted"] is False
    assert seen["actions"]["ban"] == {"allowed": False, "reason": "already_banned"}
    assert seen["actions"]["unban"] == {"allowed": True, "reason": None}
    # A banned account's role can't change until the ban is lifted.
    assert {role: action["reason"] for role, action in seen["actions"]["roles"].items()} == {
        "member": "user_banned",
        "trusted": "user_banned",
        "expert": "user_banned",
        "moderator": "role_change_forbidden",
        "admin": "role_change_forbidden",
    }


def test_a_moderator_sees_a_deleted_account_and_may_do_nothing_to_it(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    gone = make_user(handle="Leaving")
    accounts.delete_account(db, gone)
    db.commit()
    seen = person(client_as(make_user(Role.MODERATOR)), gone.handle)
    assert seen["deleted"] is True
    assert seen["handle"] == gone.handle != "Leaving"
    for action in (seen["actions"]["ban"], seen["actions"]["unban"], *seen["actions"]["roles"].values()):
        assert action == {"allowed": False, "reason": "user_not_found"}


def test_an_unknown_handle_is_not_found(make_user: MakeUser, client_as: ClientAs) -> None:
    response = client_as(make_user(Role.MODERATOR)).get(f"{API}/mod/users/Nobody")
    assert (response.status_code, error_code(response)) == (404, "user_not_found")


def test_no_email_address_or_sign_in_identity_is_shown(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    target = make_user(handle="Private", email="private.person@example.org")
    db.add(
        AuthIdentity(
            user_id=target.id,
            provider="google",
            subject="google-subject-123",
            email="private.person@example.org",
        )
    )
    db.commit()
    seen = person(client_as(make_user(Role.ADMIN)), "Private")
    for key, value in walk(seen):
        for word in ("email", "identit", "provider"):
            assert word not in key, key
        if isinstance(value, str):
            assert "example.org" not in value, key
            assert "google-subject" not in value, key


# Each moderator role, each target role, and what the moderator may then give.
EXPECTED_ROLES = {
    # A moderator manages members, trusted members and archaeologists, and no moderator or admin.
    ("moderator", "member"): {"trusted": "not_eligible", "expert": None},
    ("moderator", "trusted"): {"member": None, "expert": None},
    ("moderator", "expert"): {"member": None, "trusted": None},
    ("moderator", "moderator"): {},
    ("moderator", "admin"): {},
    # An admin makes and unmakes moderators too, and admins are made outside OpenAntiquity.
    ("admin", "member"): {"trusted": "not_eligible", "expert": None, "moderator": None},
    ("admin", "moderator"): {"member": None, "trusted": None, "expert": None},
    ("admin", "admin"): {},
}


@pytest.mark.parametrize(("actor_role", "target_role"), list(EXPECTED_ROLES))
def test_each_answer_is_what_the_route_does(
    actor_role: str, target_role: str, make_user: MakeUser, client_as: ClientAs, db: Session
) -> None:
    """Every action the page allows, the route accepts; every one it refuses, the route refuses alike."""
    actor = make_user(Role(actor_role), handle="Acting")
    target = make_user(Role(target_role), handle="Target", reputation=10)
    client = client_as(actor)
    actions = person(client, "Target")["actions"]
    allowed_roles = {role for role, action in actions["roles"].items() if action["allowed"]}
    expected = {role for role, reason in EXPECTED_ROLES[actor_role, target_role].items() if reason is None}
    assert allowed_roles == expected
    # The role they have now, unless the route would refuse to touch their role at all.
    untouchable = not EXPECTED_ROLES[actor_role, target_role]
    current = "role_change_forbidden" if untouchable else "current_role"
    assert actions["roles"][target_role] == {"allowed": False, "reason": current}
    for role, action in actions["roles"].items():
        if role == target_role:
            continue
        response = client.put(f"{API}/mod/users/Target/role", json={"role": role, **REASON})
        if action["allowed"]:
            assert response.status_code == 200, (role, response.text)
            # Put the role back by hand so the next one is tried from the same place.
            db.refresh(target)
            assert target.role == role
            target.role = target_role
            db.commit()
        else:
            assert error_code(response) == action["reason"], role
    for verb in ("ban", "unban"):
        action = person(client, "Target")["actions"][verb]
        response = client.post(f"{API}/mod/users/Target/{verb}", json=REASON)
        if action["allowed"]:
            assert response.status_code == 200, (verb, response.text)
        else:
            assert error_code(response) == action["reason"], verb
    db.refresh(target)
    assert target.role == target_role


def test_nobody_acts_on_themselves(make_user: MakeUser, client_as: ClientAs) -> None:
    admin = make_user(Role.ADMIN, handle="Self")
    actions = person(client_as(admin), "Self")["actions"]
    assert actions["ban"] == {"allowed": False, "reason": "ban_forbidden"}
    assert actions["unban"] == {"allowed": False, "reason": "ban_forbidden"}
    assert all(not action["allowed"] for action in actions["roles"].values())


def test_a_member_is_refused_as_for_any_mod_route(make_user: MakeUser, client_as: ClientAs) -> None:
    make_user(handle="Target")
    member = client_as(make_user(Role.MEMBER))
    for path in ("/mod/users/Target", "/mod/users/eligible", "/mod/actions"):
        response = member.get(API + path)
        assert (response.status_code, error_code(response)) == (403, "moderators_only"), path


def test_the_shape_names_every_role(make_user: MakeUser, client_as: ClientAs) -> None:
    make_user(handle="Target")
    actions = person(client_as(make_user(Role.MODERATOR)), "Target")["actions"]
    assert list(actions) == ["ban", "unban", "roles"]
    assert list(actions["roles"]) == [role.value for role in Role]
