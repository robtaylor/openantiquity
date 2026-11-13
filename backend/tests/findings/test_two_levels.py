"""A finding is open or protected, and every signed-in member sees both exactly (Decision 0032).

Investigations hold back what is drawn near a finding the reader doesn't see
exactly, measured to its exact place (Decision 0023). That is safe only while
nobody who can draw is kept from a place, so these tests pin it, and the
levels `/meta` and the finding's page offer.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.services import sensitivity
from fieldclub.vocab import Role, Sensitivity
from tests.findings.support import API, create
from tests.helpers import ClientAs, MakeFinding, MakeUser


def test_every_level_shows_its_exact_place_to_every_signed_in_member(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    """The property that makes Decision 0023's distance rule safe.

    Investigations hold back what is drawn near a finding the reader doesn't
    see exactly. Anyone who can draw is signed in, and with these levels every
    signed-in member sees every finding exactly, so the guard's answer tells
    them nothing they can't already see. If a level is ever added that keeps a
    place from someone who can draw, the guard's answer becomes a way to find
    the place, and this test is where that is caught.

    A finding a moderator has hidden is the one a member can't see at all. It
    takes no part in the guard for what is drawn near it, which
    `tests/investigations/test_a_hidden_finding_holds_nothing_back.py` checks.
    """
    assert tuple(Sensitivity) == (Sensitivity.OPEN, Sensitivity.PROTECTED)
    finder = make_user(Role.MEMBER, handle="Finder")
    readers: list[User] = [make_user(role) for role in Role]
    assert {Role(reader.role) for reader in readers} == set(Role)
    for level in Sensitivity:
        finding = make_finding(finder, sensitivity=level.value)
        for reader in readers:
            assert sensitivity.sees_exact(finding, reader), (level, reader.role)
            clause = sensitivity.as_sql(sensitivity.sees_exact_clause(reader))
            matched = db.scalars(select(Finding.id).where(Finding.id == finding.id, clause)).all()
            assert matched == [finding.id], (level, reader.role)


def test_meta_lists_both_levels(app: FastAPI, client_as: ClientAs, make_user: MakeUser) -> None:
    served = client_as(make_user()).get(f"{API}/meta").json()["vocab"]["sensitivity_levels"]
    assert [item["id"] for item in served] == ["open", "protected"]


def test_a_protected_finding_offers_no_higher_level(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """The page doesn't offer a raise the route would refuse."""
    finding = create(db, make_user(), feature_class="round_barrow")
    assert finding.sensitivity == Sensitivity.PROTECTED.value
    for who in (Role.TRUSTED, Role.MODERATOR):
        page = client_as(make_user(who)).get(f"{API}/findings/{finding.public_id}").json()
        assert page["actions"]["raise_level"] == {"allowed": False, "reason": "highest_level"}, who
