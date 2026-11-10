"""The investigation service without HTTP: publishing, editing, items and what each viewer sees of them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, InvestigationItem
from fieldclub.services import investigations
from fieldclub.services.findings import FindingClosedError, FindingNotFoundError
from fieldclub.services.investigations import (
    InvalidItemError,
    InvestigationForbiddenError,
    InvestigationNotFoundError,
    ItemNotFoundError,
    Need,
    NewItem,
    OwnerOnlyError,
    TooManyItemsError,
    Unavailable,
)
from fieldclub.services.records import RecordNotFoundError
from fieldclub.vocab import FindingState, InvestigationItemKind, InvestigationRole, Visibility
from tests.helpers import MakeFinding, MakeUser, add_record, add_source
from tests.investigations.support import PROFILE, REFERENCE, VIEW, add, make, order, positions

KIND = InvestigationItemKind


def published(db: Session) -> list[tuple[int | None, int | None]]:
    """(investigation id, actor id) of every investigation_published row."""
    db.expire_all()
    rows = db.execute(
        select(Activity.investigation_id, Activity.actor_id).where(Activity.kind == "investigation_published")
    )
    return [(investigation_id, actor_id) for investigation_id, actor_id in rows]


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------


def test_creating_a_public_investigation_publishes_it(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner, Visibility.PUBLIC)
    assert published(db) == [(investigation.id, owner.id)]


@pytest.mark.parametrize("visibility", [Visibility.PRIVATE, Visibility.UNLISTED])
def test_private_and_unlisted_ones_record_no_event(
    db: Session, make_user: MakeUser, visibility: Visibility
) -> None:
    make(db, make_user(), visibility)
    assert published(db) == []
    assert db.scalars(select(Activity)).all() == []


def test_unpublishing_removes_the_event_and_publishing_again_records_one(
    db: Session, make_user: MakeUser
) -> None:
    owner = make_user()
    investigation = make(db, owner, Visibility.UNLISTED)
    investigations.change_visibility(db, investigation, owner, Visibility.PUBLIC)
    db.commit()
    assert published(db) == [(investigation.id, owner.id)]
    investigations.change_visibility(db, investigation, owner, Visibility.UNLISTED)
    db.commit()
    assert published(db) == []
    investigations.change_visibility(db, investigation, owner, Visibility.PRIVATE)
    investigations.change_visibility(db, investigation, owner, Visibility.PUBLIC)
    investigations.change_visibility(db, investigation, owner, Visibility.PUBLIC)
    db.commit()
    assert published(db) == [(investigation.id, owner.id)]


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


def test_a_private_investigation_is_not_found_by_anyone_but_its_owner(
    db: Session, make_user: MakeUser
) -> None:
    owner, moderator = make_user(), make_user("moderator")
    investigation = make(db, owner, Visibility.PRIVATE)
    assert investigations.load(db, investigation.public_id, owner).role is InvestigationRole.OWNER
    for viewer in (None, moderator, make_user("admin")):
        with pytest.raises(InvestigationNotFoundError):
            investigations.load(db, investigation.public_id, viewer)


def test_a_banned_owner_counts_as_signed_out(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner, Visibility.PRIVATE)
    owner.banned_at = datetime(2026, 11, 10, tzinfo=UTC)
    db.commit()
    with pytest.raises(InvestigationNotFoundError):
        investigations.load(db, investigation.public_id, owner)


def test_a_malformed_id_is_not_found(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(InvestigationNotFoundError):
        investigations.load(db, "not an id at all", make_user())


def test_an_editor_edits_but_does_not_change_visibility(db: Session, make_user: MakeUser) -> None:
    owner, editor = make_user(), make_user()
    investigation = make(db, owner, members={InvestigationRole.EDITOR: [editor]})
    access = investigations.load(db, investigation.public_id, editor, Need.EDIT, lock=True)
    investigations.update_investigation(db, access, editor, {"title": "Renamed", "visibility": "public"})
    db.commit()
    assert investigation.title == "Renamed"
    with pytest.raises(OwnerOnlyError):
        investigations.update_investigation(db, access, editor, {"visibility": "unlisted"})
    with pytest.raises(OwnerOnlyError):
        investigations.delete_investigation(db, access)


def test_a_viewer_cannot_edit(db: Session, make_user: MakeUser) -> None:
    owner, viewer = make_user(), make_user()
    investigation = make(db, owner, members={InvestigationRole.VIEWER: [viewer]})
    with pytest.raises(InvestigationForbiddenError):
        investigations.load(db, investigation.public_id, viewer, Need.EDIT)
    access = investigations.load(db, investigation.public_id, viewer)
    with pytest.raises(InvestigationForbiddenError):
        investigations.add_item(db, access, viewer, NewItem(KIND.NOTE, note="Sneaky"))


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def test_every_kind_of_item_can_be_added_in_order(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user()
    investigation = make(db, owner)
    finding = make_finding()
    record = add_record(db, add_source(db), "Avebury henge", -1.8542, 51.4286)
    db.commit()
    added = [
        add(db, investigation, owner, kind=KIND.FINDING, finding=finding.public_id),
        add(db, investigation, owner, kind=KIND.RECORD, record_id=record.id, note="Scheduled"),
        add(db, investigation, owner, kind=KIND.VIEW, title="From the south", data=VIEW),
        add(db, investigation, owner, kind=KIND.NOTE, note="The bank is clearest here."),
        add(db, investigation, owner, kind=KIND.REFERENCE, title="Avebury", data=REFERENCE),
        add(db, investigation, owner, kind=KIND.PROFILE, data=PROFILE),
    ]
    assert order(db, investigation) == [item.id for item in added]
    assert positions(db, investigation) == list(range(6))
    assert investigations.counts(db, investigation).items == 6


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"kind": KIND.NOTE, "note": None}, "note needs"),
        ({"kind": KIND.REFERENCE, "data": REFERENCE}, "needs a title"),
        ({"kind": KIND.VIEW}, "needs view data"),
        ({"kind": KIND.NOTE, "note": "x", "data": VIEW}, "takes no note data"),
        ({"kind": KIND.FINDING}, "names its finding"),
        ({"kind": KIND.RECORD}, "names its record"),
        ({"kind": KIND.NOTE, "note": "x", "record_id": 1}, "Only a record item"),
        ({"kind": KIND.NOTE, "note": "x", "finding": "ABC123"}, "Only a finding item"),
    ],
)
def test_an_item_missing_what_its_kind_needs_is_refused(
    db: Session, make_user: MakeUser, fields: dict[str, object], message: str
) -> None:
    owner = make_user()
    investigation = make(db, owner)
    access = investigations.load(db, investigation.public_id, owner, Need.EDIT, lock=True)
    with pytest.raises(InvalidItemError, match=message):
        investigations.add_item(db, access, owner, NewItem(**fields))  # pyright: ignore[reportArgumentType]


def test_a_finding_or_record_must_exist_and_be_visible(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user()
    investigation = make(db, owner)
    hidden = make_finding(hidden_at=datetime(2026, 11, 1, tzinfo=UTC))
    withdrawn = make_finding(state=FindingState.WITHDRAWN.value)
    access = investigations.load(db, investigation.public_id, owner, Need.EDIT, lock=True)
    with pytest.raises(FindingNotFoundError):
        investigations.add_item(db, access, owner, NewItem(KIND.FINDING, finding=hidden.public_id))
    with pytest.raises(FindingClosedError):
        investigations.add_item(db, access, owner, NewItem(KIND.FINDING, finding=withdrawn.public_id))
    with pytest.raises(RecordNotFoundError):
        investigations.add_item(db, access, owner, NewItem(KIND.RECORD, record_id=999))


def test_an_investigation_holds_at_most_max_items(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(investigations, "MAX_ITEMS", 3)
    owner = make_user()
    investigation = make(db, owner)
    for _ in range(3):
        add(db, investigation, owner)
    with pytest.raises(TooManyItemsError):
        add(db, investigation, owner)


def test_moving_items(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)
    a, b, c, d = (add(db, investigation, owner, note=name).id for name in "abcd")

    def move(item: int, after: int | None) -> list[int]:
        access = investigations.load(db, investigation.public_id, owner, Need.EDIT, lock=True)
        investigations.move_item(db, access, item, after)
        db.commit()
        assert positions(db, investigation) == [0, 1, 2, 3]
        return order(db, investigation)

    assert move(d, None) == [d, a, b, c]
    assert move(d, c) == [a, b, c, d]
    assert move(a, b) == [b, a, c, d]
    assert move(c, c) == [b, a, c, d]
    with pytest.raises(ItemNotFoundError):
        move(a, 99999)


def test_removing_an_item_keeps_the_order_of_the_rest(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)
    a, b, c = (add(db, investigation, owner).id for _ in range(3))
    access = investigations.load(db, investigation.public_id, owner, Need.EDIT, lock=True)
    investigations.remove_item(db, access, b)
    db.commit()
    assert order(db, investigation) == [a, c]
    d = add(db, investigation, owner).id
    assert order(db, investigation) == [a, c, d]


def test_an_item_from_another_investigation_is_not_found(db: Session, make_user: MakeUser) -> None:
    owner, other = make_user(), make_user()
    mine, theirs = make(db, owner), make(db, other)
    item = add(db, theirs, other)
    access = investigations.load(db, mine.public_id, owner, Need.EDIT, lock=True)
    with pytest.raises(ItemNotFoundError):
        investigations.update_item(db, access, item.id, {"note": "mine now"})
    with pytest.raises(ItemNotFoundError):
        investigations.remove_item(db, access, item.id)


def test_an_edit_keeps_the_kind_and_its_needs(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = make(db, owner)
    note = add(db, investigation, owner, note="first")
    view = add(db, investigation, owner, kind=KIND.VIEW, data=VIEW)
    access = investigations.load(db, investigation.public_id, owner, Need.EDIT, lock=True)
    investigations.update_item(db, access, note.id, {"note": "second", "title": "Heading"})
    assert (note.note, note.title) == ("second", "Heading")
    with pytest.raises(InvalidItemError):
        investigations.update_item(db, access, note.id, {"note": None})
    with pytest.raises(InvalidItemError):
        investigations.update_item(db, access, view.id, {"data": None}, [KIND.VIEW])
    with pytest.raises(InvalidItemError, match="its own content"):
        investigations.update_item(db, access, view.id, {"data": REFERENCE}, [KIND.REFERENCE])
    investigations.update_item(db, access, view.id, {"data": VIEW | {"zoom": 17}}, [KIND.VIEW])
    assert view.data == VIEW | {"zoom": 17}


# --------------------------------------------------------------------------
# What each viewer sees of an item
# --------------------------------------------------------------------------


def _views(db: Session, investigation_id: int, viewer: object) -> dict[int, investigations.ItemView]:
    items = db.scalars(
        select(InvestigationItem).where(InvestigationItem.investigation_id == investigation_id)
    ).all()
    return {view.item.id: view for view in investigations.item_views(db, items, viewer)}  # pyright: ignore[reportArgumentType]


def test_a_hidden_finding_is_a_line_for_everyone_who_may_not_see_it(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner, finder, moderator = make_user(), make_user(), make_user("moderator")
    investigation = make(db, owner)
    finding = make_finding(finder)
    item = add(db, investigation, owner, kind=KIND.FINDING, finding=finding.public_id)
    finding.hidden_at = datetime(2026, 11, 10, tzinfo=UTC)
    db.commit()
    for viewer in (None, owner, make_user("trusted")):
        view = _views(db, investigation.id, viewer)[item.id]
        assert view.unavailable is Unavailable.HIDDEN
        assert view.finding is None
        assert view.finding_author is None
    for viewer in (finder, moderator):
        view = _views(db, investigation.id, viewer)[item.id]
        assert view.unavailable is None
        assert view.finding is finding


def test_a_withdrawn_finding_and_a_vanished_record_are_lines(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user()
    investigation = make(db, owner)
    finding = make_finding()
    source = add_source(db)
    kept, removed = (
        add_record(db, source, "Kept", -1.85, 51.42),
        add_record(db, source, "Removed", -1.86, 51.43),
    )
    other = add_source(db, "other-source")
    switched_off = add_record(db, other, "Switched off", -1.87, 51.44)
    db.commit()
    items = {
        "finding": add(db, investigation, owner, kind=KIND.FINDING, finding=finding.public_id),
        "kept": add(db, investigation, owner, kind=KIND.RECORD, record_id=kept.id),
        "removed": add(db, investigation, owner, kind=KIND.RECORD, record_id=removed.id),
        "switched_off": add(db, investigation, owner, kind=KIND.RECORD, record_id=switched_off.id),
    }
    finding.state = FindingState.WITHDRAWN.value
    other.enabled = False
    db.execute(delete(type(removed)).where(type(removed).id == removed.id))
    db.commit()
    views = _views(db, investigation.id, owner)
    assert views[items["finding"].id].unavailable is Unavailable.WITHDRAWN
    assert views[items["finding"].id].finding is None
    assert views[items["kept"].id].record is not None
    assert views[items["kept"].id].unavailable is None
    for name in ("removed", "switched_off"):
        assert views[items[name].id].unavailable is Unavailable.GONE
        assert views[items[name].id].record is None
