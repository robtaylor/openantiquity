"""Events: the activity row, notifications to followers, and NOTIFY after commit."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Activity, Finding, Follow, Investigation, Notification, User
from fieldclub.services import activity
from fieldclub.services.sensitivity import visible_location
from fieldclub.vocab import ActivityKind
from tests.helpers import MakeFinding, MakeUser, lon_lat


class Listener:
    """A second connection that LISTENs on the event channel."""

    def __init__(self, engine: Engine) -> None:
        url = engine.url
        self.conn = psycopg.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=url.password,
            dbname=url.database,
            autocommit=True,
        )
        self.conn.execute(f"LISTEN {activity.EVENT_CHANNEL}")

    def received(self, timeout: float = 1.0) -> list[dict[str, Any]]:
        return [json.loads(notice.payload) for notice in self.conn.notifies(timeout=timeout, stop_after=1)]

    def nothing_received(self) -> bool:
        return self.received(timeout=0.2) == []

    def close(self) -> None:
        self.conn.close()


@pytest.fixture
def listener(database: Engine, db: Session) -> Iterator[Listener]:
    listening = Listener(database)
    yield listening
    listening.close()


def follow(db: Session, finding: Finding, *users: User) -> None:
    db.add_all(Follow(user_id=user.id, finding_id=finding.id) for user in users)
    db.commit()


def test_record_inserts_an_activity_row(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> None:
    actor = make_user()
    finding = make_finding(actor, lon=-1.8542, lat=51.4286)
    row = activity.record(
        db, ActivityKind.FINDING_CREATED, actor, finding, data={"feature_class": "enclosure"}
    )
    db.commit()

    stored = db.scalars(select(Activity)).one()
    assert stored.id == row.id
    assert (stored.kind, stored.actor_id, stored.finding_id) == ("finding_created", actor.id, finding.id)
    assert stored.investigation_id is None
    assert stored.data == {"feature_class": "enclosure"}
    assert stored.created_at is not None
    assert stored.location is not None
    # The centre of the finding's 1 km square, never the spot itself.
    assert lon_lat(stored.location) == pytest.approx(gridref.centre_of_square("SU1069"))


def test_kind_may_be_given_as_a_string_but_must_be_known(db: Session, make_user: MakeUser) -> None:
    assert activity.record(db, "tier_changed", make_user()).kind == "tier_changed"
    with pytest.raises(ValueError, match="made_up"):
        activity.record(db, "made_up", None)


def test_activity_for_a_restricted_finding_stores_only_the_coarse_position(
    db: Session, make_finding: MakeFinding
) -> None:
    finding = make_finding(lon=-1.8542, lat=51.4286, sensitivity="restricted")
    row = activity.record(db, ActivityKind.FINDING_CREATED, None, finding)
    db.commit()
    assert row.location is not None
    assert lon_lat(row.location) == pytest.approx(gridref.centre_of_square("SU1069"))


def test_restricting_a_finding_later_leaves_no_exact_position_in_the_feed(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    # The usual order: a finding is created open, things happen to it, and
    # then its finder or a moderator restricts it.
    exact = (-1.85421, 51.42861)
    finding = make_finding(lon=exact[0], lat=exact[1])
    activity.record(db, ActivityKind.FINDING_CREATED, None, finding)
    activity.record(db, ActivityKind.OBSERVATION_ADDED, make_user(), finding)
    db.commit()

    finding.sensitivity = "restricted"
    db.commit()

    public = visible_location(finding, None)
    assert public.obscured is True
    stored = [lon_lat(row.location) for row in db.scalars(select(Activity)) if row.location is not None]
    assert len(stored) == 2
    for position in stored:
        assert position == pytest.approx((public.lon, public.lat), abs=1e-9)
        assert position != pytest.approx(exact, abs=1e-4)
    # Nothing within 100 m of the real spot, asked of the database itself.
    here = func.ST_SetSRID(func.ST_MakePoint(*exact), 4326)
    near = select(func.count()).select_from(Activity).where(func.ST_DWithin(Activity.location, here, 0.001))
    assert db.scalar(near) == 0


def test_an_open_and_a_restricted_finding_in_one_square_are_stored_alike(
    db: Session, make_finding: MakeFinding
) -> None:
    open_row = activity.record(db, ActivityKind.FINDING_CREATED, None, make_finding(lon=-1.851, lat=51.4281))
    hidden_row = activity.record(
        db,
        ActivityKind.FINDING_CREATED,
        None,
        make_finding(lon=-1.857, lat=51.4263, sensitivity="restricted"),
    )
    db.commit()
    assert open_row.location is not None
    assert hidden_row.location is not None
    assert lon_lat(open_row.location) == pytest.approx(lon_lat(hidden_row.location))


def test_a_finding_off_the_grids_stores_no_position(db: Session, make_finding: MakeFinding) -> None:
    row = activity.record(
        db, ActivityKind.FINDING_CREATED, None, make_finding(lon=2.3522, lat=48.8566, grid_ref="none")
    )
    db.commit()
    assert row.location is None


def test_followers_are_notified_but_not_the_actor(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder, helper, watcher, stranger = make_user(), make_user(), make_user(), make_user()
    finding = make_finding(finder)
    other_finding = make_finding(finder)
    follow(db, finding, finder, helper, watcher)
    follow(db, other_finding, stranger)

    activity.record(db, ActivityKind.EVIDENCE_ADDED, helper, finding, data={"kind": "historic_map"})
    db.commit()

    rows = db.scalars(select(Notification).order_by(Notification.user_id)).all()
    assert [row.user_id for row in rows] == sorted([finder.id, watcher.id])
    for row in rows:
        assert (row.kind, row.actor_id, row.finding_id) == ("evidence_added", helper.id, finding.id)
        assert row.data == {"kind": "historic_map"}
        assert row.read_at is None


def test_system_events_notify_every_follower(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder, watcher = make_user(), make_user()
    finding = make_finding(finder)
    follow(db, finding, finder, watcher)
    activity.record(db, ActivityKind.MENTION_ADDED, None, finding)
    db.commit()
    rows = db.scalars(select(Notification)).all()
    assert sorted(row.user_id for row in rows) == sorted([finder.id, watcher.id])
    assert all(row.actor_id is None and row.data is None for row in rows)
    # Stored as SQL NULL, not as the JSON value null.
    assert db.scalars(select(Notification.data.is_(None))).all() == [True, True]
    assert db.scalars(select(Activity.data.is_(None))).all() == [True]


def test_no_followers_no_notifications(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> None:
    activity.record(db, ActivityKind.COMMENT_ADDED, make_user(), make_finding())
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_events_without_a_finding_notify_nobody(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    investigation = Investigation(
        public_id="INV001", owner_id=owner.id, title="Parish survey", visibility="public"
    )
    db.add(investigation)
    db.flush()
    row = activity.record(db, ActivityKind.INVESTIGATION_PUBLISHED, owner, investigation=investigation)
    db.commit()
    assert (row.finding_id, row.investigation_id, row.location) == (None, investigation.id, None)
    assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_notify_is_sent_only_after_commit(
    db: Session, listener: Listener, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    actor = make_user(handle="QuietBarrow42")
    finding = make_finding(actor, public_id="7K3QXM")
    row = activity.record(
        db, ActivityKind.TIER_CHANGED, actor, finding, data={"from": "spotted", "to": "seen"}
    )
    assert listener.nothing_received(), "nothing may be announced before the transaction commits"

    db.commit()
    assert listener.received() == [
        {
            "id": row.id,
            "kind": "tier_changed",
            "finding": "7K3QXM",
            "investigation": None,
            "actor": "QuietBarrow42",
        }
    ]


def test_rolled_back_events_are_never_announced(
    db: Session, listener: Listener, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    actor, finding = make_user(), make_finding()
    activity.record(db, ActivityKind.COMMENT_ADDED, actor, finding)
    db.rollback()
    assert listener.nothing_received()
    assert db.scalar(select(func.count()).select_from(Activity)) == 0


def test_each_event_in_a_transaction_is_announced(
    db: Session, listener: Listener, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    actor, finding = make_user(), make_finding()
    first = activity.record(db, ActivityKind.OBSERVATION_ADDED, actor, finding)
    second = activity.record(db, ActivityKind.TIER_CHANGED, None, finding)
    db.commit()
    payloads = listener.received() + listener.received()
    assert [(payload["id"], payload["kind"], payload["actor"]) for payload in payloads] == [
        (first.id, "observation_added", actor.handle),
        (second.id, "tier_changed", None),
    ]


def test_the_payload_is_small_and_carries_no_position(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    actor = make_user()
    finding = make_finding(actor, sensitivity="restricted")
    row = activity.record(db, ActivityKind.FINDING_CREATED, actor, finding, data={"note": "x" * 50_000})
    payload = activity.event_payload(row, actor, finding, None)
    assert len(payload) < 200
    assert set(json.loads(payload)) == {"id", "kind", "finding", "investigation", "actor"}
