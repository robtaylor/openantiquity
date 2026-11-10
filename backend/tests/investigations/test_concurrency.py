"""Two changes to one investigation at the same moment.

Every change takes the investigation's row lock before it reads anything.
Each test holds the first change open after it has taken the lock, starts
the second, checks that it waits, then lets the first commit. Without the
lock, two reorders would each renumber from the order they read and one
move would be lost, and a member could be added while the investigation
was being made private.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.models import Investigation, User
from fieldclub.services import investigations
from fieldclub.services.investigations import Need, NewItem, PrivateInvestigationError
from fieldclub.vocab import InvestigationItemKind, InvestigationRole, Visibility
from tests.helpers import MakeUser
from tests.investigations.support import add, make, order, positions

Change = Callable[[Session, investigations.Access, User], object]


def _in_own_session(
    public_id: str, user_id: int, change: Change, *, before_commit: Callable[[], None] = lambda: None
) -> None:
    with fieldclub_db.SessionLocal() as session:
        user = session.get(User, user_id)
        assert user is not None
        access = investigations.load(session, public_id, user, Need.READ, lock=True)
        change(session, access, user)
        before_commit()
        session.commit()


def _race(public_id: str, user_id: int, first: Change, second: Change) -> dict[str, BaseException]:
    """Run `first`, hold it after the lock, start `second`, check it waits, then release both."""
    holding, release, second_done = threading.Event(), threading.Event(), threading.Event()
    errors: dict[str, BaseException] = {}

    def hold() -> None:
        holding.set()
        assert release.wait(10), "the test never released the first change"

    def run(name: str, change: Change, **kwargs: Callable[[], None]) -> Callable[[], None]:
        def target() -> None:
            try:
                _in_own_session(public_id, user_id, change, **kwargs)
            except BaseException as exc:
                errors[name] = exc
            finally:
                if name == "second":
                    second_done.set()

        return target

    one = threading.Thread(target=run("first", first, before_commit=hold))
    one.start()
    assert holding.wait(10), "the first change never took the lock"
    two = threading.Thread(target=run("second", second))
    two.start()
    assert not second_done.wait(0.5), "the second change didn't wait for the first"
    release.set()
    for thread in (one, two):
        thread.join(timeout=30)
        assert not thread.is_alive(), "a change never finished"
    return errors


def _move(item_id: int, after: int | None) -> Change:
    return lambda db, access, _: investigations.move_item(db, access, item_id, after)


def test_two_moves_at_once_both_apply_and_lose_nothing(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)
    a, b, c, d, e = (add(db, investigation, owner, note=name).id for name in "abcde")
    errors = _race(investigation.public_id, owner.id, _move(e, None), _move(d, a))
    assert errors == {}
    # The second move ran on the order the first left: e first, then d after a.
    assert order(db, investigation) == [e, a, d, b, c]
    assert positions(db, investigation) == [0, 1, 2, 3, 4]


def test_a_move_and_an_add_at_once_keep_every_item(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)
    a, b, c = (add(db, investigation, owner, note=name).id for name in "abc")

    def add_note(session: Session, access: investigations.Access, user: User) -> object:
        return investigations.add_item(session, access, user, NewItem(InvestigationItemKind.NOTE, note="new"))

    errors = _race(investigation.public_id, owner.id, _move(c, None), add_note)
    assert errors == {}
    ids = order(db, investigation)
    assert ids[:3] == [c, a, b]
    assert len(ids) == 4
    assert positions(db, investigation) == [0, 1, 2, 3]


def test_two_adds_at_once_take_different_places(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)

    def add_note(session: Session, access: investigations.Access, user: User) -> object:
        return investigations.add_item(session, access, user, NewItem(InvestigationItemKind.NOTE, note="x"))

    assert _race(investigation.public_id, owner.id, add_note, add_note) == {}
    assert positions(db, investigation) == [0, 1]


# --------------------------------------------------------------------------
# A private investigation never gains a second member
# --------------------------------------------------------------------------


def _add_helper(helper: User) -> Change:
    def change(session: Session, access: investigations.Access, _: User) -> object:
        person = session.get(User, helper.id)
        assert person is not None
        return investigations.put_member(session, access, person, InvestigationRole.EDITOR)

    return change


def _make_private(session: Session, access: investigations.Access, user: User) -> object:
    return investigations.change_visibility(session, access.investigation, user, Visibility.PRIVATE)


@pytest.mark.parametrize("adding_first", [True, False], ids=["add_then_private", "private_then_add"])
def test_adding_a_member_while_making_it_private_lets_only_the_first_through(
    db: Session, make_user: MakeUser, adding_first: bool
) -> None:
    owner, helper = make_user(), make_user()
    investigation = make(db, owner, Visibility.UNLISTED)
    first, second = (
        (_add_helper(helper), _make_private) if adding_first else (_make_private, _add_helper(helper))
    )
    errors = _race(investigation.public_id, owner.id, first, second)
    assert set(errors) == {"second"}
    assert isinstance(errors["second"], PrivateInvestigationError)
    db.expire_all()
    stored = db.get(Investigation, investigation.id)
    assert stored is not None
    assert stored.visibility == ("unlisted" if adding_first else "private")
    investigations.check_members(db, stored)
    assert investigations.counts(db, stored).members == (2 if adding_first else 1)
