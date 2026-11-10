"""Events: the activity log, notifications to followers, and the live event bus.

`record()` does three things in the caller's transaction:

1. inserts an `activity` row,
2. creates a notification for everyone following the finding, except the actor,
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
position, because a finding that is open today may be restricted tomorrow and
the row would not follow. A reader that shows where something happened gets
the position from `sensitivity.visible_location` at the time it is read.

This module only sends on the bus. The listener that fans payloads out to
`GET /events/stream` clients is not built yet.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, insert, literal, select
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
) -> Activity:
    """Record that something happened. The caller commits.

    `actor` is None for things the system did, such as a mention found by the
    channel scan. Followers are then all notified.
    """
    kind = ActivityKind(kind)
    location = None
    if finding is not None:
        # Never the exact position, even for an open finding. See the module docstring.
        centre = square_centre(finding)
        if centre is not None:
            location = db_point(*centre)

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
        if actor is not None:
            followers = followers.where(Follow.user_id != actor.id)
        db.execute(
            insert(Notification).from_select(["user_id", "kind", "actor_id", "finding_id", "data"], followers)
        )

    db.execute(select(func.pg_notify(EVENT_CHANNEL, event_payload(activity, actor, finding, investigation))))
    return activity
