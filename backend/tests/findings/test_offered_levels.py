"""A finding is open or protected, and nothing sets it to restricted (Decision 0032).

The restricted level is dropped because it kept a finding's exact place from
people who could draw beside it. The enum and the services still know the
level until a later sweep removes it, so these tests hold the line at the
boundary: no request admits it, and every level that is offered shows its
exact place to every signed-in member.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.services import sensitivity
from fieldclub.vocab import OFFERED_SENSITIVITIES, Role, Sensitivity
from tests.findings.support import API, LAT, LON, create, point
from tests.helpers import ClientAs, MakeFinding, MakeUser

DROPPED = Sensitivity.RESTRICTED.value


def _resolve(spec: dict[str, Any], node: Any) -> Any:
    ref = node.get("$ref") if isinstance(node, dict) else None
    if ref is None:
        return node
    assert ref.startswith("#/"), ref
    target: Any = spec
    for part in ref.removeprefix("#/").split("/"):
        target = target[part]
    return target


def _admits_dropped(spec: dict[str, Any], node: Any, seen: set[str], where: str) -> list[str]:
    """Every place under `node` whose enum or const admits the dropped level."""
    if isinstance(node, dict) and "$ref" in node:
        if node["$ref"] in seen:
            return []
        seen = seen | {node["$ref"]}
        return _admits_dropped(spec, _resolve(spec, node), seen, f"{where} -> {node['$ref']}")
    found: list[str] = []
    if isinstance(node, dict):
        if DROPPED in node.get("enum", ()) or node.get("const") == DROPPED:
            found.append(where)
        for key, value in node.items():
            if key not in ("enum", "const", "examples", "example", "default", "description"):
                found.extend(_admits_dropped(spec, value, seen, f"{where}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_admits_dropped(spec, value, seen, f"{where}[{index}]"))
    return found


def test_no_request_admits_the_dropped_level(app: FastAPI) -> None:
    """Every request body and parameter of every route. A new route can't bring the level back."""
    spec = app.openapi()
    found: list[str] = []
    operations = 0
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            operations += 1
            where = f"{method.upper()} {path}"
            for parameter in operation.get("parameters", []):
                parameter = _resolve(spec, parameter)
                found.extend(
                    _admits_dropped(spec, parameter.get("schema"), set(), f"{where} ?{parameter['name']}")
                )
            body = _resolve(spec, operation.get("requestBody", {}))
            found.extend(_admits_dropped(spec, body.get("content", {}), set(), f"{where} body"))
    assert operations > 50, "the walk reached the app's routes"
    assert found == []


def test_the_walk_finds_the_level_where_it_is_still_served(app: FastAPI) -> None:
    """Responses still name it, since a stored finding can hold it, so the walk would see it in a request."""
    spec = app.openapi()
    summary = spec["components"]["schemas"]["FindingSummary"]
    assert _admits_dropped(spec, summary, set(), "FindingSummary") != []


def test_every_offered_level_shows_its_exact_place_to_every_signed_in_member(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    """The property that makes Decision 0023's distance rule safe.

    Investigations hold back what is drawn near a finding the reader doesn't
    see exactly. Anyone who can draw is signed in, and with these levels every
    signed-in member sees every finding exactly, so the guard's answer tells
    them nothing they can't already see. If a level is ever added that keeps a
    place from someone who can draw, the guard's answer becomes a way to find
    the place, and this test is where that is caught.
    """
    assert OFFERED_SENSITIVITIES == (Sensitivity.OPEN, Sensitivity.PROTECTED)
    finder = make_user(Role.MEMBER, handle="Finder")
    readers: list[User] = [make_user(role) for role in Role]
    assert {Role(reader.role) for reader in readers} == set(Role)
    for level in OFFERED_SENSITIVITIES:
        finding = make_finding(finder, sensitivity=level.value)
        for reader in readers:
            assert sensitivity.sees_exact(finding, reader), (level, reader.role)
            clause = sensitivity.as_sql(sensitivity.sees_exact_clause(reader))
            matched = db.scalars(select(Finding.id).where(Finding.id == finding.id, clause)).all()
            assert matched == [finding.id], (level, reader.role)


def test_meta_lists_only_the_offered_levels(app: FastAPI, client_as: ClientAs, make_user: MakeUser) -> None:
    served = client_as(make_user()).get(f"{API}/meta").json()["vocab"]["sensitivity_levels"]
    assert [item["id"] for item in served] == [level.value for level in OFFERED_SENSITIVITIES]


PEOPLE = ("member", "finder", "trusted", "moderator")


def _person(name: str, make_user: MakeUser, finder: User) -> User:
    return finder if name == "finder" else make_user(Role(name))


@pytest.mark.parametrize("who", PEOPLE)
def test_nobody_creates_a_restricted_finding(
    db: Session, client_as: ClientAs, make_user: MakeUser, who: str
) -> None:
    person = _person(who, make_user, make_user(Role.MEMBER))
    body = {"location": point(), "feature_class": "enclosure", "sensitivity": DROPPED}
    response = client_as(person).post(f"{API}/findings", json=body)
    assert response.status_code == 422, response.text
    assert db.scalars(select(Finding)).all() == []


@pytest.mark.parametrize("who", PEOPLE)
def test_nobody_raises_a_finding_to_restricted(
    db: Session, client_as: ClientAs, make_user: MakeUser, who: str
) -> None:
    finder = make_user(Role.MEMBER)
    finding = create(db, finder, lon=LON, lat=LAT)
    person = _person(who, make_user, finder)
    response = client_as(person).put(
        f"{API}/findings/{finding.public_id}/sensitivity", json={"level": DROPPED}
    )
    assert response.status_code == 422, response.text
    db.expire_all()
    assert finding.sensitivity == Sensitivity.OPEN.value


@pytest.mark.parametrize("who", PEOPLE)
def test_nobody_sets_restricted_through_moderation(
    db: Session, client_as: ClientAs, make_user: MakeUser, who: str
) -> None:
    finder = make_user(Role.MEMBER)
    finding = create(db, finder)
    person = _person(who, make_user, finder)
    response = client_as(person).put(
        f"{API}/mod/findings/{finding.public_id}/sensitivity",
        json={"level": DROPPED, "reason": "Asked to restrict it."},
    )
    # Only a moderator passes the role check. Everyone else may be stopped there first.
    allowed = {422} if who == "moderator" else {403, 422}
    assert response.status_code in allowed, response.text
    db.expire_all()
    assert finding.sensitivity == Sensitivity.OPEN.value


def test_a_protected_finding_offers_no_higher_level(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """The page doesn't offer a raise the route would refuse."""
    finding = create(db, make_user(), feature_class="round_barrow")
    assert finding.sensitivity == Sensitivity.PROTECTED.value
    for who in (Role.TRUSTED, Role.MODERATOR):
        page = client_as(make_user(who)).get(f"{API}/findings/{finding.public_id}").json()
        assert page["actions"]["raise_level"] == {"allowed": False, "reason": "highest_level"}, who
