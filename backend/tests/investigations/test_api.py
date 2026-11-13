"""Investigations over HTTP: creating, editing, items of every kind, and the private rule in any order."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Investigation, InvestigationItem
from fieldclub.services import investigations
from fieldclub.vocab import FindingState
from tests.helpers import ClientAs, MakeFinding, MakeUser, add_record, add_source, error_code
from tests.investigations.support import API, PROFILE, REFERENCE, VIEW, make, url

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[-1.87, 51.42], [-1.84, 51.42], [-1.84, 51.44], [-1.87, 51.44], [-1.87, 51.42]]],
}


def create(client: TestClient, **body: object) -> dict[str, Any]:
    response = client.post(f"{API}/investigations", json={"title": "Parish survey", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_read_edit_delete(
    db: Session, make_user: MakeUser, client_as: ClientAs, client: TestClient
) -> None:
    owner = make_user(display_name="Ann Owner")
    me = client_as(owner)
    made = create(
        me, summary="Earthworks round the henge", notes="# Notes\n\nStart at the bank.", area=SQUARE
    )
    assert made["visibility"] == "private"
    assert made["my_role"] == "owner"
    assert made["member_count"] == 1
    assert made["item_count"] == 0
    assert made["owner"]["display_name"] == "Ann Owner"
    assert made["area"]["type"] == "Polygon"
    path = f"{API}/investigations/{made['public_id']}"
    assert client.get(path).status_code == 404
    edited = me.patch(path, json={"title": "Avebury parish", "area": None, "summary": None})
    assert edited.status_code == 200
    assert (edited.json()["title"], edited.json()["area"], edited.json()["summary"]) == (
        "Avebury parish",
        None,
        None,
    )
    assert edited.json()["notes"] == "# Notes\n\nStart at the bank."
    assert me.delete(path).status_code == 204
    assert me.get(path).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "x" * 121},
        {"title": "ok", "notes": "x" * 50_001},
        {"title": "ok", "visibility": "secret"},
        {"title": "ok", "area": {"type": "Point", "coordinates": [-1.85, 51.43]}},
        {
            "title": "ok",
            "area": {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 10]]]},
        },
        {"title": "ok", "owner_id": 1},
        {"title": "bad\u0000title"},
    ],
)
def test_bad_investigations_are_refused(
    make_user: MakeUser, client_as: ClientAs, body: dict[str, object]
) -> None:
    response = client_as(make_user()).post(f"{API}/investigations", json=body)
    assert response.status_code == 422, response.text


def test_an_area_with_too_many_points_is_refused(make_user: MakeUser, client_as: ClientAs) -> None:
    ring = [[-1.85 + 0.00001 * i, 51.43] for i in range(1200)] + [[-1.85 + 0.012, 51.44], [-1.85, 51.44]]
    ring.append(ring[0])
    area = {"type": "MultiPolygon", "coordinates": [[ring], [[[c[0], c[1] - 0.05] for c in ring]]]}
    response = client_as(make_user()).post(f"{API}/investigations", json={"title": "Big", "area": area})
    assert response.status_code == 422
    assert "2000 points" in response.text


def test_title_and_visibility_cannot_be_cleared(make_user: MakeUser, client_as: ClientAs) -> None:
    me = client_as(make_user())
    path = f"{API}/investigations/{create(me)['public_id']}"
    for field in ("title", "visibility"):
        response = me.patch(path, json={field: None})
        assert response.status_code == 422
        assert error_code(response) == "invalid_investigation"


def test_a_contributor_must_have_finished_the_welcome_step(newcomer: object, client_as: ClientAs) -> None:
    response = client_as(newcomer).post(f"{API}/investigations", json={"title": "Too soon"})  # pyright: ignore[reportArgumentType]
    assert response.status_code == 403
    assert error_code(response) == "onboarding_required"


def test_publishing_through_the_api_records_the_event_once(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner = make_user()
    me = client_as(owner)
    path = f"{API}/investigations/{create(me)['public_id']}"
    me.patch(path, json={"visibility": "public"})
    me.patch(path, json={"visibility": "public", "title": "Still public"})
    events = db.scalars(select(Activity)).all()
    assert [(event.kind, event.actor_id) for event in events] == [("investigation_published", owner.id)]
    me.patch(path, json={"visibility": "unlisted"})
    db.expire_all()
    assert db.scalars(select(Activity)).all() == []


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def test_items_of_every_kind_round_trip(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs
) -> None:
    owner = make_user()
    me = client_as(owner)
    inv = make(db, owner)
    finding = make_finding(title="Ring ditch")
    record = add_record(db, add_source(db), "Avebury henge", -1.8542, 51.4286, record_type="Henge")
    db.commit()
    bodies = [
        {"kind": "finding", "finding": finding.public_id.lower(), "note": "Clear on the slope view"},
        {"kind": "record", "record_id": record.id},
        {"kind": "view", "view": VIEW | {"compare_layer": "slope"}, "title": "Looking south"},
        {"kind": "note", "note": "The bank is clearest here."},
        {"kind": "reference", "title": "Avebury", "reference": REFERENCE},
        {"kind": "profile", "profile": PROFILE},
    ]
    for body in bodies:
        response = me.post(url(inv, "/items"), json=body)
        assert response.status_code == 201, response.text
    items = me.get(url(inv, "/items")).json()["items"]
    assert [item["kind"] for item in items] == ["finding", "record", "view", "note", "reference", "profile"]
    assert [item["position"] for item in items] == list(range(6))
    by_kind = {item["kind"]: item for item in items}
    assert by_kind["finding"]["finding"]["title"] == "Ring ditch"
    assert by_kind["finding"]["finding"]["location"]["obscured"] is False
    assert by_kind["record"]["record"]["name"] == "Avebury henge"
    assert by_kind["record"]["record"]["source"]["licence"] == "Open Government Licence v3.0"
    assert by_kind["record"]["record"]["source"]["attribution"]
    assert by_kind["view"]["view"]["centre"] == VIEW["centre"]
    assert by_kind["view"]["view"]["compare_layer"] == "slope"
    assert by_kind["reference"]["reference"] == {"url": REFERENCE["url"], "citation": REFERENCE["citation"]}
    assert by_kind["profile"]["profile"] == PROFILE
    assert all(item["unavailable"] is None for item in items)
    assert all(item["added_by"]["handle"] == owner.handle for item in items)
    assert me.get(url(inv)).json()["item_count"] == 6


def test_items_page_in_order(db: Session, make_user: MakeUser, client_as: ClientAs) -> None:
    owner = make_user()
    me = client_as(owner)
    inv = make(db, owner)
    for n in range(5):
        me.post(url(inv, "/items"), json={"kind": "note", "note": f"note {n}"})
    seen, cursor = [], None
    while True:
        page = me.get(url(inv, "/items"), params={"limit": 2} | ({"cursor": cursor} if cursor else {})).json()
        seen.extend(item["note"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"note {n}" for n in range(5)]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "note"},
        {"kind": "note", "note": ""},
        {"kind": "note", "note": "x" * 10_001},
        {"kind": "note", "note": "ok", "title": "x" * 201},
        {"kind": "finding"},
        {"kind": "record", "record_id": 0},
        {"kind": "view", "view": {"zoom": 12}},
        {"kind": "view", "view": VIEW | {"centre": [200, 51]}},
        {"kind": "view", "view": VIEW | {"note": "smuggled"}},
        {"kind": "reference", "reference": REFERENCE},
        {"kind": "reference", "title": "x", "reference": {"url": "javascript:alert(1)"}},
        {"kind": "profile", "profile": {"line": {"type": "LineString", "coordinates": [[-1.85, 51.42]]}}},
        {
            "kind": "profile",
            "profile": {"line": {"type": "LineString", "coordinates": [[-1.85, 51.42]] * 201}},
        },
        {"kind": "note", "note": "ok", "view": VIEW},
        {"kind": "scribble", "note": "ok"},
    ],
)
def test_bad_items_are_refused(db: Session, make_user: MakeUser, client_as: ClientAs, body: dict) -> None:
    owner = make_user()
    inv = make(db, owner)
    response = client_as(owner).post(url(inv, "/items"), json=body)
    assert response.status_code == 422, response.text


def test_an_unknown_finding_or_record_is_not_found(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner = make_user()
    inv = make(db, owner)
    me = client_as(owner)
    assert error_code(me.post(url(inv, "/items"), json={"kind": "finding", "finding": "ZZZZZZ"})) == (
        "finding_not_found"
    )
    assert (
        error_code(me.post(url(inv, "/items"), json={"kind": "record", "record_id": 4})) == "record_not_found"
    )
    assert error_code(me.patch(url(inv, "/items/77"), json={"note": "x"})) == "item_not_found"
    assert error_code(me.post(url(inv, "/items/77/move"), json={"after": None})) == "item_not_found"
    assert error_code(me.delete(url(inv, "/items/77"))) == "item_not_found"


def test_an_item_edit_takes_only_its_own_content(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner = make_user()
    me = client_as(owner)
    inv = make(db, owner)
    view = me.post(url(inv, "/items"), json={"kind": "view", "view": VIEW}).json()
    path = url(inv, f"/items/{view['id']}")
    wrong = me.patch(path, json={"reference": REFERENCE})
    assert wrong.status_code == 422
    assert error_code(wrong) == "invalid_item"
    assert error_code(me.patch(path, json={"view": VIEW, "profile": PROFILE})) == "invalid_item"
    assert error_code(me.patch(path, json={"view": None})) == "invalid_item"
    changed = me.patch(path, json={"view": VIEW | {"zoom": 18}, "title": "Closer", "note": "Bank and ditch"})
    assert changed.status_code == 200
    assert (changed.json()["view"]["zoom"], changed.json()["title"]) == (18, "Closer")
    cleared = me.patch(path, json={"title": None})
    assert cleared.json()["title"] is None
    assert cleared.json()["note"] == "Bank and ditch"


def test_moving_through_the_api(db: Session, make_user: MakeUser, client_as: ClientAs) -> None:
    owner = make_user()
    me = client_as(owner)
    inv = make(db, owner)
    ids = [me.post(url(inv, "/items"), json={"kind": "note", "note": n}).json()["id"] for n in "abc"]
    moved = me.post(url(inv, f"/items/{ids[0]}/move"), json={"after": ids[2]})
    assert moved.json()["position"] == 2
    assert [item["id"] for item in me.get(url(inv, "/items")).json()["items"]] == [ids[1], ids[2], ids[0]]
    assert me.post(url(inv, f"/items/{ids[0]}/move"), json={}).status_code == 422


def test_unavailable_items_render_as_lines(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs, client: TestClient
) -> None:
    owner, finder = make_user(), make_user()
    inv = make(db, owner)
    hidden = make_finding(finder, title="Secret barrow")
    withdrawn = make_finding(finder, title="Taken back enclosure")
    record = add_record(db, add_source(db), "Vanishing monument", -1.85, 51.43)
    db.commit()
    me = client_as(owner)
    for body in (
        {"kind": "finding", "finding": hidden.public_id},
        {"kind": "finding", "finding": withdrawn.public_id},
        {"kind": "record", "record_id": record.id},
    ):
        assert me.post(url(inv, "/items"), json=body).status_code == 201
    hidden.hidden_at = datetime(2026, 11, 10, tzinfo=UTC)
    withdrawn.state = FindingState.WITHDRAWN.value
    db.delete(record)
    db.commit()
    for viewer in (client, me):
        response = viewer.get(url(inv, "/items"))
        assert response.status_code == 200
        assert [item["unavailable"] for item in response.json()["items"]] == ["hidden", "withdrawn", "gone"]
        assert all(item["finding"] is None and item["record"] is None for item in response.json()["items"])
        for secret in ("Secret barrow", "Taken back enclosure", "Vanishing monument", hidden.public_id):
            assert secret not in response.text
    as_finder = client_as(finder).get(url(inv, "/items")).json()["items"]
    assert as_finder[0]["finding"]["title"] == "Secret barrow"
    assert as_finder[1]["unavailable"] == "withdrawn"


@pytest.mark.parametrize("gone_how", ["hidden", "withdrawn"])
def test_what_an_editor_isn_t_shown_of_an_item_they_can_t_write_over(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, client_as: ClientAs, gone_how: str
) -> None:
    """A finding item whose finding isn't shown has the places in its text hidden, from its editors too.

    Saving back what they were shown would put the placeholder where the
    place was written. The interface offers no edit for such an item, and the
    API refuses one.
    """
    owner, finder = make_user(), make_user()
    inv = make(db, owner)
    finding = make_finding(finder, title="A barrow")
    db.commit()
    me = client_as(owner)
    written = "Bank on the east side, at SU 1310 6707."
    added = me.post(
        url(inv, "/items"), json={"kind": "finding", "finding": finding.public_id, "note": written}
    )
    assert added.status_code == 201, added.text
    if gone_how == "hidden":
        finding.hidden_at = datetime(2026, 11, 10, tzinfo=UTC)
    else:
        finding.state = FindingState.WITHDRAWN.value
    db.commit()

    (shown,) = me.get(url(inv, "/items")).json()["items"]
    assert shown["unavailable"] == gone_how
    assert "SU 1310 6707" not in shown["note"], "the editor is shown the note with the place hidden"

    path = url(inv, f"/items/{added.json()['id']}")
    refused = me.patch(path, json={"note": shown["note"]})
    assert error_code(refused) == "item_unavailable", refused.text
    assert refused.status_code == 409
    assert error_code(me.patch(path, json={"title": "Renamed"})) == "item_unavailable"
    stored = db.scalars(select(InvestigationItem).where(InvestigationItem.investigation_id == inv.id)).one()
    db.refresh(stored)
    assert (stored.title, stored.note) == (None, written)

    # It can still be moved and removed.
    assert me.delete(path).status_code == 204


# --------------------------------------------------------------------------
# A private investigation never has a second member, whatever the order of calls
# --------------------------------------------------------------------------


def test_the_private_rule_holds_through_every_order_of_calls(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    owner = make_user()
    helpers = [make_user(handle=f"Helper{n}") for n in range(2)]
    me = client_as(owner)
    path = f"{API}/investigations/{create(me)['public_id']}"

    def check() -> None:
        db.expire_all()
        stored = db.scalars(select(Investigation)).one()
        investigations.check_members(db, stored)

    def put(handle: str) -> int:
        response = me.put(f"{path}/members/{handle}", json={"role": "editor"})
        check()
        return response.status_code

    def visibility(value: str) -> int:
        response = me.patch(path, json={"visibility": value})
        check()
        return response.status_code

    assert put("Helper0") == 409
    assert visibility("unlisted") == 200
    assert put("Helper0") == 201
    assert put("Helper0") == 200
    assert visibility("private") == 409
    assert visibility("public") == 200
    assert put("Helper1") == 201
    assert visibility("private") == 409
    assert me.delete(f"{path}/members/Helper0").status_code == 204
    assert visibility("private") == 409
    assert client_as(helpers[1]).delete(f"{path}/members/Helper1").status_code == 204
    assert visibility("private") == 200
    assert put("Helper1") == 409
    assert me.patch(path, json={"visibility": "public", "title": "Back"}).status_code == 200
    assert put("Helper1") == 201
    check()
