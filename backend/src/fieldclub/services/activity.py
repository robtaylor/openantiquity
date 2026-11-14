"""Events: the activity log, notifications to followers, and the live event bus.

`record()` does three things in the caller's transaction:

1. inserts an `activity` row,
2. creates a notification for everyone following the finding, except the actor
   and anyone named in `quiet_for`,
3. queues a small JSON payload on the PostgreSQL channel `fieldclub_events`.

PostgreSQL holds a notification until the transaction commits and discards it
on rollback, so listeners hear about an event exactly when it becomes true.
One listener per process fans payloads out to event-stream clients, and
because the bus is PostgreSQL it works across instances.

The payload carries ids only. Clients fetch details through the API, which
applies location sensitivity. Callers must not record events for things the
public can't see, such as a private investigation.

`activity.location` is the centre of the finding's 1 km grid square, for every
finding. It is there so a feed can be filtered by area. It is never an exact
position, because a finding that is open today may be protected tomorrow and
the row would not follow. A reader that shows where something happened gets
the position from `sensitivity.visible_location` at the time it is read.

`relocate` moves those squares when a finding moves, so the feed's area
filter follows the finding.

Nobody is notified of their own action. A second look is recorded with no
actor (Decision 0008), so the person who answered is passed as `quiet_for`
instead: they are left out of the notifications, and nothing that anyone else
receives changes.

This module only sends on the bus. `services.events` holds the listener that
fans payloads out to `GET /events/stream` clients.
"""

from __future__ import annotations

import json
from typing import Any

from geoalchemy2 import WKBElement
from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, Follow, Investigation, Notification, User
from fieldclub.models.common import JsonB, db_point
from fieldclub.services.sensitivity import square_centre
from fieldclub.vocab import ActivityKind

EVENT_CHANNEL = "fieldclub_events"

# PostgreSQL refuses NOTIFY payloads of 8000 bytes or more.
MAX_PAYLOAD_BYTES = 7900


def event_payload(
    activity: Activity, actor: User | None, finding: Finding | None, investigation: Investigation | None
) -> str:
    """The JSON sent on the event bus for an activity."""
    payload = json.dumps(
        {
            "id": activity.id,
            "kind": activity.kind,
            "finding": finding.public_id if finding is not None else None,
            "investigation": investigation.public_id if investigation is not None else None,
            "actor": actor.handle if actor is not None else None,
        },
        separators=(",", ":"),
    )
    assert len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES, "event payload is too large for NOTIFY"
    return payload


def record(
    db: Session,
    kind: ActivityKind | str,
    actor: User | None,
    finding: Finding | None = None,
    investigation: Investigation | None = None,
    data: dict[str, Any] | None = None,
    *,
    quiet_for: User | None = None,
) -> Activity:
    """Record that something happened. The caller commits.

    `actor` is None for things the system did, such as a mention found by the
    channel scan, and for anything a second look caused. Followers are then
    all notified, except `quiet_for`: the person whose second look it was,
    who must not be told of their own action but can't be named as its actor.
    """
    kind = ActivityKind(kind)
    assert quiet_for is None or actor is None, "quiet_for is for events with no actor"
    location = _square_point(finding) if finding is not None else None

    activity = Activity(
        kind=kind.value,
        actor_id=actor.id if actor is not None else None,
        finding_id=finding.id if finding is not None else None,
        investigation_id=investigation.id if investigation is not None else None,
        data=data,
        location=location,
    )
    db.add(activity)
    db.flush()

    if finding is not None:
        followers = select(
            Follow.user_id,
            literal(kind.value),
            literal(actor.id if actor is not None else None),
            literal(finding.id),
            literal(data, type_=JsonB),
        ).where(Follow.finding_id == finding.id)
        for left_out in (actor, quiet_for):
            if left_out is not None:
                assert left_out.id is not None, "a user left out of notifications must be saved"
                followers = followers.where(Follow.user_id != left_out.id)
        db.execute(
            insert(Notification).from_select(["user_id", "kind", "actor_id", "finding_id", "data"], followers)
        )

    db.execute(select(func.pg_notify(EVENT_CHANNEL, event_payload(activity, actor, finding, investigation))))
    return activity


def notify_invitation(db: Session, invited: User, owner: User, investigation: Investigation) -> Notification:
    """Tell someone they've been invited to an investigation. The caller commits.

    The notification goes to that one person, so it carries no free text at
    all, neither a message nor the investigation's title (Decision 0009: no
    private channel). It names the investigation by its id and the owner who
    invited them, and they open the investigation to read it. Nothing is
    written to `activity` or sent on the bus, because an invitation is
    nobody else's business.
    """
    assert invited.id is not None, "the invited person must be saved"
    assert owner.id is not None, "the owner must be saved"
    assert not invited.has_id(owner.id), "nobody invites themselves"
    notification = Notification(
        user_id=invited.id,
        kind=ActivityKind.INVESTIGATION_INVITATION.value,
        actor_id=owner.id,
        investigation_id=investigation.id,
    )
    db.add(notification)
    db.flush()
    return notification


def has_unread(
    db: Session, to: User, kind: ActivityKind, finding: Finding, actor: User | None = None
) -> bool:
    """Whether `to` has an unread notification of `kind` about `finding`, from `actor` when given.

    So a notification that could be asked for again and again, an offer or
    a replaced suggestion, isn't sent again while the last one waits.
    """
    query = select(Notification.id).where(
        Notification.user_id == to.id,
        Notification.kind == kind.value,
        Notification.finding_id == finding.id,
        Notification.read_at.is_(None),
    )
    if actor is not None:
        query = query.where(Notification.actor_id == actor.id)
    return db.scalar(query.limit(1)) is not None


def mark_read_about(
    db: Session, to: User, kind: ActivityKind, finding: Finding, actor: User | None = None
) -> None:
    """Mark read `to`'s notifications of `kind` about `finding`, from `actor` when given.

    For when the person has acted on what they were told, so `has_unread`
    doesn't hold back the next one.
    """
    statement = update(Notification).where(
        Notification.user_id == to.id,
        Notification.kind == kind.value,
        Notification.finding_id == finding.id,
        Notification.read_at.is_(None),
    )
    if actor is not None:
        statement = statement.where(Notification.actor_id == actor.id)
    db.execute(statement.values(read_at=func.now()).execution_options(synchronize_session=False))


def _square_point(finding: Finding) -> WKBElement | None:
    """The centre of the finding's 1 km square as a geometry value, or None off both grids.

    Never the exact position, even for an open finding. See the module docstring.
    """
    centre = square_centre(finding)
    return db_point(*centre) if centre is not None else None


def relocate(db: Session, finding: Finding) -> None:
    """Move the finding's activity to the square it is in now. Call it after a move. The caller commits."""
    db.execute(
        update(Activity).where(Activity.finding_id == finding.id).values(location=_square_point(finding))
    )
