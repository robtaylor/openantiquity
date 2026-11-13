"""What a newer version stored and this one has no name for is passed over, not a 500.

A deploy changes the schema first and swaps the machines after, so for some
minutes this version serves beside a newer one, and going back to this
version leaves the newer one's rows in the database. An activity kind or a
next step it added mustn't break the feed, the notifications, the event
stream, a finding's page or the help-wanted list here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, Notification
from fieldclub.services import feed
from fieldclub.services.confidence import load_assessment, load_next_steps
from fieldclub.vocab import ActivityKind, NextStepCode
from tests.activity.support import API, comment, follow, items
from tests.findings.support import create
from tests.helpers import ClientAs, MakeUser, assert_checks_are_made_with_their_tables, checks_lifted

LATER_KIND = "made_by_a_later_version"
LATER_STEP: dict[str, Any] = {
    "code": "asked_by_a_later_version",
    "prompt": "Something this version can't ask for.",
    "people": 1,
    # A later step can carry a field this version doesn't have. The step is
    # left out before its fields are read, so the field does no harm. A field
    # added to a step this version does know is not covered: that needs a new
    # `ASSESSMENT_VERSION`.
    "added_later": True,
}
assert LATER_KIND not in set(ActivityKind), "the kind has to be one this version has no name for"
assert LATER_STEP["code"] not in set(NextStepCode), "the step has to be one this version has no name for"


_KIND_CHECK = {Activity.__tablename__: ("ck_activity_kind_valid",)}


def kind_check_lifted(db: Session, database: Engine) -> AbstractContextManager[None]:
    """The check on `activity.kind` lifted in this database, and put back on the way out."""
    return checks_lifted(db, database, _KIND_CHECK, [delete(Activity).where(Activity.kind == LATER_KIND)])


@pytest.fixture
def later_schema(db: Session, database: Engine) -> Iterator[None]:
    """The check on `activity.kind` lifted, as a later version's schema would have widened it."""
    with kind_check_lifted(db, database):
        yield


def test_lifting_the_check_leaves_it_in_every_schema_built_afterwards(db: Session, database: Engine) -> None:
    with kind_check_lifted(db, database):
        pass

    assert_checks_are_made_with_their_tables(_KIND_CHECK)


def later_activity(db: Session, finding: Finding) -> int:
    """A row of the later kind about `finding`, placed as its other rows are."""
    known = db.scalars(select(Activity).where(Activity.finding_id == finding.id)).first()
    assert known is not None, "the finding has a row to copy the place from"
    row = Activity(kind=LATER_KIND, finding_id=finding.id, actor_id=known.actor_id, location=known.location)
    db.add(row)
    db.commit()
    return row.id


def store_later_step(db: Session, finding: Finding) -> None:
    stored = dict(finding.assessment)
    stored["next_steps"] = [*stored["next_steps"], LATER_STEP]
    finding.assessment = stored
    db.commit()


def test_the_feed_passes_over_a_later_kind(
    db: Session, make_user: MakeUser, client: TestClient, later_schema: None
) -> None:
    finder = make_user()
    finding = create(db, finder)
    later_activity(db, finding)
    comment(db, finding, finder)

    response = client.get(f"{API}/activity")

    assert [item["kind"] for item in items(response)] == ["comment_added", "finding_created"]
    # A page is filled with rows this version can show, not cut short by one it can't.
    first = client.get(f"{API}/activity", params={"limit": 1}).json()
    rest = client.get(f"{API}/activity", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert [item["kind"] for item in first["items"] + rest["items"]] == ["comment_added", "finding_created"]
    assert rest["next_cursor"] is None


def test_the_event_stream_does_not_announce_a_later_kind(
    db: Session, make_user: MakeUser, later_schema: None
) -> None:
    finding = create(db, make_user())
    later = later_activity(db, finding)

    assert feed.public_event(db, later) is None


def test_notifications_pass_over_a_later_kind_and_do_not_count_it(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, watcher = make_user(), make_user()
    finding = create(db, finder)
    follow(db, finding, watcher)
    comment(db, finding, finder)
    db.add(Notification(user_id=watcher.id, kind=LATER_KIND, finding_id=finding.id, actor_id=finder.id))
    db.commit()

    response = client_as(watcher).get(f"{API}/notifications")

    assert [item["kind"] for item in items(response)] == ["comment_added"]
    assert response.json()["unread_count"] == 1


def test_a_stored_assessment_reads_without_a_later_step(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    before = load_assessment(finding.assessment)
    assert before is not None
    assert before.next_steps, "a new finding has something left to do"
    store_later_step(db, finding)

    after = load_assessment(finding.assessment)

    assert after == before
    assert load_next_steps(finding.assessment) == before.next_steps


def test_a_finding_s_page_and_help_wanted_serve_a_finding_with_a_later_step(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, helper = make_user(), make_user()
    finding = create(db, finder)
    store_later_step(db, finding)

    page = client_as(helper).get(f"{API}/findings/{finding.public_id}")
    tasks = client_as(helper).get(f"{API}/review/tasks")

    assert page.status_code == 200, page.text
    assert LATER_STEP["code"] not in page.text
    assert tasks.status_code == 200, tasks.text
    assert LATER_STEP["code"] not in tasks.text
    assert finding.public_id in tasks.text, "the steps this version knows are still asked for"
