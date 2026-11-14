"""An action a newer version logged, which this one has no name for, is left out of the log, not a 500.

A deploy changes the schema first and swaps the machines after, and going
back to this version leaves the newer one's rows in the database
(Decision 0033). The moderation log is read in one place, `GET /mod/actions`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from fieldclub.models import ModerationAction
from fieldclub.vocab import ModerationActionKind, ReportTarget, Role
from tests.findings.support import create
from tests.helpers import ClientAs, MakeUser, assert_checks_are_made_with_their_tables, checks_lifted
from tests.moderation.support import API, comment, log_entries

LATER_ACTION = "done_by_a_later_version"
LATER_TARGET = "kind_of_thing_added_later"
assert LATER_ACTION not in set(ModerationActionKind), "the action has to be one this version has no name for"
assert LATER_TARGET not in set(ReportTarget), "the target has to be one this version has no name for"

_CHECKS = {
    ModerationAction.__tablename__: (
        "ck_moderation_actions_action_valid",
        "ck_moderation_actions_target_kind_valid",
    )
}


def checks_on_the_log_lifted(db: Session, database: Engine) -> AbstractContextManager[None]:
    """The checks on the log's two vocabularies lifted in this database, and put back on the way out."""
    return checks_lifted(
        db,
        database,
        _CHECKS,
        [
            delete(ModerationAction).where(ModerationAction.action == LATER_ACTION),
            delete(ModerationAction).where(ModerationAction.target_kind == LATER_TARGET),
        ],
    )


@pytest.fixture
def later_schema(db: Session, database: Engine) -> Iterator[None]:
    """The log's checks lifted, as a later version's schema would have widened them."""
    with checks_on_the_log_lifted(db, database):
        yield


def test_lifting_the_checks_leaves_them_in_every_schema_built_afterwards(
    db: Session, database: Engine
) -> None:
    with checks_on_the_log_lifted(db, database):
        pass

    assert_checks_are_made_with_their_tables(_CHECKS)


def later_row(
    db: Session, like: ModerationAction, *, action: str | None = None, target_kind: str | None = None
) -> int:
    """A row a later version wrote, about the same target and by the same person as `like`."""
    row = ModerationAction(
        actor_id=like.actor_id,
        action=action or like.action,
        target_kind=target_kind or like.target_kind,
        target_id=like.target_id,
        reason="Something a later version did.",
    )
    db.add(row)
    db.commit()
    return row.id


@pytest.mark.usefixtures("later_schema")
def test_the_log_leaves_out_an_action_it_has_no_name_for(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    owner = make_user(handle="Owner")
    finding = create(db, owner)
    moderator = client_as(make_user(Role.MODERATOR, handle="Mod"))
    said = [comment(db, finding, owner, f"Rude words {n}") for n in range(3)]

    # Three actions this version knows, with a later version's rows among them.
    moderator.post(f"{API}/mod/comments/{said[0].id}/hide", json={"reason": "Abusive."})
    first = log_entries(db)[-1]
    later_action = later_row(db, first, action=LATER_ACTION)
    moderator.post(f"{API}/mod/comments/{said[1].id}/hide", json={"reason": "Abusive."})
    later_target = later_row(db, first, target_kind=LATER_TARGET)
    moderator.post(f"{API}/mod/comments/{said[2].id}/hide", json={"reason": "Abusive."})
    known = [entry.id for entry in log_entries(db) if entry.id not in {later_action, later_target}]
    assert len(known) == 3

    whole = moderator.get(f"{API}/mod/actions")
    assert whole.status_code == 200, whole.text
    assert [item["id"] for item in whole.json()["items"]] == sorted(known, reverse=True)

    # Pages are still full: the later rows are passed over in the query, not after it.
    first_page = moderator.get(f"{API}/mod/actions", params={"limit": 2})
    assert first_page.status_code == 200, first_page.text
    assert [item["id"] for item in first_page.json()["items"]] == sorted(known, reverse=True)[:2]
    rest = moderator.get(
        f"{API}/mod/actions", params={"limit": 2, "cursor": first_page.json()["next_cursor"]}
    )
    assert rest.status_code == 200, rest.text
    assert [item["id"] for item in rest.json()["items"]] == sorted(known, reverse=True)[2:]
    assert rest.json()["next_cursor"] is None

    # One target's log, which the later action was written about.
    one = moderator.get(f"{API}/mod/actions", params={"target_kind": "comment", "target_id": str(said[0].id)})
    assert one.status_code == 200, one.text
    assert [item["id"] for item in one.json()["items"]] == [first.id]
