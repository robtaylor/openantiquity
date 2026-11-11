"""Notifications: nobody is told of their own action, and each account sees only its own."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Notification, User
from fieldclub.services import activity, feed, findings, review
from fieldclub.vocab import ActivityKind, Visible
from tests.activity.support import API, add_map, comment, follow, items, kinds_of, notifications_of
from tests.findings.support import answer, create
from tests.helpers import ClientAs, ClientFor, MakeUser, error_code

# --------------------------------------------------------------------------
# Nobody is notified of their own action
# --------------------------------------------------------------------------


def test_a_follower_is_not_told_of_their_own_second_look(db: Session, make_user: MakeUser) -> None:
    finder, first, second, watcher = make_user(), make_user(), make_user(), make_user()
    finding = create(db, finder)
    # Following before answering is the case the findings track left open:
    # the answerer was told, without a name, about their own answer.
    follow(db, finding, first, second, watcher)

    answer(db, finding, first, Visible.YES)
    answer(db, finding, second, Visible.YES)  # two yeses: the finding reaches Seen

    db.refresh(finding)
    assert finding.tier == "seen"
    assert kinds_of(notifications_of(db, second)) == ["observation_added"]  # the first one's, not their own
    assert kinds_of(notifications_of(db, first)) == ["observation_added", "tier_changed"]  # the second's
    assert kinds_of(notifications_of(db, watcher)) == [
        "observation_added",
        "observation_added",
        "tier_changed",
    ]
    assert kinds_of(notifications_of(db, finder)) == kinds_of(notifications_of(db, watcher))
    # Nobody is named, and nothing says how anyone answered (Decision 0008).
    for row in db.scalars(select(Notification)):
        assert row.actor_id is None
        assert row.data is None or set(row.data) <= {"from", "to", "reason"}


def test_taking_a_second_look_back_tells_others_but_not_the_person(db: Session, make_user: MakeUser) -> None:
    finder, first, second = make_user(), make_user(), make_user()
    finding = create(db, finder)
    answer(db, finding, first, Visible.YES)
    answer(db, finding, second, Visible.YES)
    before = {user.id: len(notifications_of(db, user)) for user in (finder, first, second)}

    review.delete_observation(db, finding, second)
    db.commit()

    db.refresh(finding)
    assert finding.tier == "spotted"
    assert len(notifications_of(db, second)) == before[second.id]
    assert kinds_of(notifications_of(db, first))[before[first.id] :] == ["tier_changed"]
    assert kinds_of(notifications_of(db, finder))[before[finder.id] :] == ["tier_changed"]


def test_the_finder_and_a_contributor_are_not_told_of_their_own_work(
    db: Session, make_user: MakeUser
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    assert notifications_of(db, finder) == []
    add_map(db, finding, helper)
    comment(db, finding, helper)
    assert notifications_of(db, helper) == []
    assert kinds_of(notifications_of(db, finder)) == ["evidence_added", "comment_added"]


def test_quiet_for_is_only_for_events_with_no_actor(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    with pytest.raises(AssertionError, match="no actor"):
        activity.record(db, ActivityKind.COMMENT_ADDED, finder, finding, quiet_for=make_user())


# --------------------------------------------------------------------------
# Listing and reading
# --------------------------------------------------------------------------


@pytest.fixture
def busy(db: Session, make_user: MakeUser) -> dict[str, User]:
    """A finder and a watcher with three notifications each about other people's comments."""
    finder, watcher, talker = (
        make_user(handle="Finder"),
        make_user(handle="Watcher"),
        make_user(handle="Talker"),
    )
    finding = create(db, finder, title="A busy enclosure")
    follow(db, finding, watcher)
    for _ in range(3):
        comment(db, finding, talker)
    return {"finder": finder, "watcher": watcher, "talker": talker}


def test_notifications_list_newest_first_with_the_unread_count(
    busy: dict[str, User], client_as: ClientAs
) -> None:
    response = client_as(busy["watcher"]).get(f"{API}/notifications", params={"limit": 2})
    body = response.json()
    assert response.headers["cache-control"] == "private, no-cache"
    assert body["unread_count"] == 3
    assert [item["kind"] for item in body["items"]] == ["comment_added", "comment_added"]
    assert body["items"][0]["id"] > body["items"][1]["id"]
    first = body["items"][0]
    assert first["read"] is False
    assert first["actor"]["handle"] == "Talker"
    assert first["finding"]["title"] == "A busy enclosure"
    assert first["details"]["comment_id"] is not None
    rest = (
        client_as(busy["watcher"]).get(f"{API}/notifications", params={"cursor": body["next_cursor"]}).json()
    )
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


def test_nobody_sees_another_accounts_notifications(
    busy: dict[str, User], client_as: ClientAs, db: Session
) -> None:
    mine = {item["id"] for item in items(client_as(busy["watcher"]).get(f"{API}/notifications"))}
    theirs = {item["id"] for item in items(client_as(busy["finder"]).get(f"{API}/notifications"))}
    assert len(mine) == len(theirs) == 3
    assert not mine & theirs
    assert client_as(busy["talker"]).get(f"{API}/notifications").json() == {
        "items": [],
        "next_cursor": None,
        "unread_count": 0,
    }

    # Marking someone else's as read does nothing, and says nothing about them.
    marked = client_as(busy["talker"]).post(f"{API}/notifications/read", json={"ids": sorted(mine)})
    assert marked.json() == {"marked": 0, "unread_count": 0}
    assert all(row.read_at is None for row in notifications_of(db, busy["watcher"]))


def test_marking_some_read(busy: dict[str, User], client_as: ClientAs) -> None:
    watcher = client_as(busy["watcher"])
    listed = items(watcher.get(f"{API}/notifications"))
    marked = watcher.post(f"{API}/notifications/read", json={"ids": [listed[0]["id"], listed[0]["id"]]})
    assert marked.json() == {"marked": 1, "unread_count": 2}
    again = watcher.post(f"{API}/notifications/read", json={"ids": [listed[0]["id"]]})
    assert again.json() == {"marked": 0, "unread_count": 2}
    assert [item["read"] for item in items(watcher.get(f"{API}/notifications"))] == [True, False, False]


def test_marking_all_read_up_to_the_newest_seen(
    busy: dict[str, User], client_as: ClientAs, db: Session
) -> None:
    watcher = client_as(busy["watcher"])
    listed = items(watcher.get(f"{API}/notifications"))
    # Seen up to the middle one; a newer one arrives meanwhile and stays unread.
    marked = watcher.post(f"{API}/notifications/read", json={"all": True, "up_to": listed[1]["id"]})
    assert marked.json() == {"marked": 2, "unread_count": 1}
    everything = watcher.post(f"{API}/notifications/read", json={"all": True})
    assert everything.json() == {"marked": 1, "unread_count": 0}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"ids": [1], "all": True},
        {"ids": []},
        {"ids": [0]},
        {"ids": [1], "up_to": 3},
        {"all": False},
        {"ids": list(range(1, 202))},
        {"all": True, "extra": 1},
    ],
)
def test_mark_read_refuses_what_it_cant_mean(busy: dict[str, User], client_as: ClientAs, body: dict) -> None:
    response = client_as(busy["watcher"]).post(f"{API}/notifications/read", json=body)
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_notifications_and_marking_them_read_need_only_a_session(
    app, client_for: ClientFor, newcomer: User
) -> None:
    signed_out = client_for(app)
    assert error_code(signed_out.get(f"{API}/notifications")) == "unauthorised"
    assert error_code(signed_out.post(f"{API}/notifications/read", json={"all": True})) == "unauthorised"
    # Marking your own notifications read stores nothing, so it needs no welcome step.
    fresh = client_for(app, newcomer)
    assert fresh.get(f"{API}/notifications").status_code == 200
    marked = fresh.post(f"{API}/notifications/read", json={"all": True})
    assert marked.status_code == 200, marked.text


def test_notifications_about_hidden_or_removed_things_disappear(
    busy: dict[str, User], client_as: ClientAs, db: Session, make_user: MakeUser
) -> None:
    watcher = busy["watcher"]
    assert feed.unread_count(db, watcher) == 3
    comment_ids = [row.data["comment_id"] for row in notifications_of(db, watcher) if row.data]
    findings.delete_comment(db, comment_ids[0], busy["talker"])
    db.commit()
    assert feed.unread_count(db, watcher) == 2
    assert len(items(client_as(watcher).get(f"{API}/notifications"))) == 2

    finding = findings.get_finding(
        db, items(client_as(watcher).get(f"{API}/notifications"))[0]["finding"]["public_id"], None
    )
    finding.hidden_at = datetime.now(UTC)
    db.commit()
    assert items(client_as(watcher).get(f"{API}/notifications")) == []
    assert client_as(watcher).get(f"{API}/notifications").json()["unread_count"] == 0
    # The finder may still see a hidden finding, so their notifications stay.
    assert len(items(client_as(busy["finder"]).get(f"{API}/notifications"))) == 2
