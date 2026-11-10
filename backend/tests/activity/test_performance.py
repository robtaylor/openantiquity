"""The feed and notifications over 100,000 rows answer through an index, quickly.

5,000 open findings are inserted with one statement, 1,000 of them crowded
round Avebury, and 100,000 events spread over them, each at its finding's
point (the trigger needs open findings to be exact, and an event's position
only has to be near its finding for the plan to be realistic). Before them
come a few events of a rare kind, the oldest rows, so a filter by that kind
has to find them past every other row. The tests run the feed's own
statement for three viewers, read the plan and time it.

Notifications get 100,000 rows of their own, half of them one person's.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from sqlalchemy import Select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from fieldclub.models import User
from fieldclub.services import feed
from fieldclub.services.feed import FeedFilters
from fieldclub.vocab import ActivityKind
from tests.helpers import MakeUser

FINDINGS = 5_000
CLUSTERED = 1_000
EVENTS = 100_000
RARE = 30
NOTIFICATIONS = 100_000
# About 3.5 km by 2.2 km round Avebury: a phone screen at zoom 14, plus the frontend's padding.
BOX = (-1.88, 51.41, -1.83, 51.43)
LIMIT = 50
BUDGET_S = 0.25


def _seed_findings(db: Session, author: User) -> None:
    db.execute(
        text(
            """
            INSERT INTO findings (public_id, author_id, title, feature_class, location, location_public,
                                  sensitivity, view_state)
            SELECT 'P' || lpad(i::text, 5, '0'), :author, 'Generated ' || i, 'enclosure', pt, pt, 'open', '{}'
            FROM (
                SELECT i, CASE WHEN i <= :clustered
                    THEN ST_SetSRID(ST_MakePoint(-1.93 + random() * 0.15, 51.38 + random() * 0.08), 4326)
                    ELSE ST_SetSRID(ST_MakePoint(-5.0 + random() * 6.5, 50.5 + random() * 2.5), 4326)
                END AS pt
                FROM generate_series(1, :findings) AS i
            ) AS generated
            """
        ),
        {"author": author.id, "findings": FINDINGS, "clustered": CLUSTERED},
    )


def _seed(db: Session, author: User) -> None:
    _seed_findings(db, author)
    db.execute(
        text(
            """
            INSERT INTO activity (kind, actor_id, finding_id, data, location, created_at)
            SELECT 'tier_changed', NULL, f.id, NULL, f.location, now() - interval '1 year'
            FROM generate_series(1, :rare) AS e(i)
            JOIN findings AS f ON f.id = 1 + (e.i * 7919) % :findings
            """
        ),
        {"rare": RARE, "findings": FINDINGS},
    )
    db.execute(
        text(
            """
            INSERT INTO activity (kind, actor_id, finding_id, data, location, created_at)
            SELECT 'finding_created', :author, f.id, NULL, f.location, now() - (e.i || ' seconds')::interval
            FROM generate_series(1, :events) AS e(i)
            JOIN findings AS f ON f.id = 1 + (e.i * 7919) % :findings
            """
        ),
        {"author": author.id, "events": EVENTS, "findings": FINDINGS},
    )
    db.commit()
    db.execute(text("ANALYZE findings"))
    db.execute(text("ANALYZE activity"))
    db.commit()


def _compiled(query: Select[*tuple[Any, ...]]) -> str:
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


IN_BOX = FeedFilters(bbox=BOX)


def _sql(viewer: User | None, filters: FeedFilters = IN_BOX) -> str:
    return _compiled(feed.feed_query(viewer, filters).limit(LIMIT + 1))


def _nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node]
    for child in node.get("Plans", []):
        found += _nodes(child)
    return found


def _indexes_on(db: Session, sql: str, table: str) -> tuple[set[str], str]:
    """The indexes the plan reads `table` through, and the plan to show, after checking it never scans it."""
    (row,) = db.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}")).one()
    plan = row[0]
    nodes = _nodes(plan["Plan"])
    shown = json.dumps(plan, indent=1)
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == table for n in nodes), shown
    used = {n["Index Name"] for n in nodes if n.get("Relation Name") == table and "Index Name" in n}
    bitmaps = (n for n in nodes if n["Node Type"] == "Bitmap Index Scan")
    used |= {n["Index Name"] for n in bitmaps if table in n["Index Name"]}
    return used, shown


def _fastest(db: Session, sql: str) -> float:
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        db.execute(text(sql)).all()
        timings.append(time.perf_counter() - started)
    return min(timings)


@pytest.fixture
def seeded(db: Session, make_user: MakeUser) -> dict[str, User | None]:
    author = make_user()
    _seed(db, author)
    assert db.scalar(text("SELECT count(*) FROM activity")) == RARE + EVENTS
    return {"signed_out": None, "member": make_user(), "moderator": make_user("moderator")}


@pytest.mark.parametrize("viewer", ["signed_out", "member", "moderator"])
def test_a_map_box_over_100000_events_uses_an_index(
    db: Session, seeded: dict[str, User | None], viewer: str
) -> None:
    sql = _sql(seeded[viewer])
    on_activity, shown = _indexes_on(db, sql, "activity")
    assert on_activity, shown

    assert len(db.execute(text(sql)).all()) == LIMIT + 1, "the box is crowded enough to fill a page"
    fastest = _fastest(db, sql)
    assert fastest < BUDGET_S, f"{viewer}: fastest of five runs took {fastest:.3f} s"


@pytest.mark.parametrize("viewer", ["signed_out", "member", "moderator"])
def test_a_rare_kind_over_100000_events_uses_its_index(
    db: Session, seeded: dict[str, User | None], viewer: str
) -> None:
    sql = _sql(seeded[viewer], FeedFilters(kinds=(ActivityKind.TIER_CHANGED,)))
    on_activity, shown = _indexes_on(db, sql, "activity")
    assert "ix_activity_kind_id" in on_activity, shown

    assert len(db.execute(text(sql)).all()) == RARE
    fastest = _fastest(db, sql)
    assert fastest < BUDGET_S, f"{viewer}: fastest of five runs took {fastest:.3f} s"


@pytest.fixture
def notified(db: Session, make_user: MakeUser) -> User:
    """A person with half of 100,000 notifications, all but 50 read. Three others share the rest."""
    author, reader = make_user(), make_user()
    others = [make_user() for _ in range(3)]
    _seed_findings(db, author)
    db.execute(
        text(
            """
            INSERT INTO notifications (user_id, kind, finding_id, read_at)
            SELECT CASE WHEN n.i % 2 = 0 THEN :reader ELSE (ARRAY[:a, :b, :c])[1 + n.i % 3] END,
                   'tier_changed', 1 + (n.i * 7919) % :findings,
                   CASE WHEN n.i > :notifications - 100 THEN NULL ELSE now() END
            FROM generate_series(1, :notifications) AS n(i)
            """
        ),
        {
            "reader": reader.id,
            "a": others[0].id,
            "b": others[1].id,
            "c": others[2].id,
            "findings": FINDINGS,
            "notifications": NOTIFICATIONS,
        },
    )
    db.commit()
    db.execute(text("ANALYZE findings"))
    db.execute(text("ANALYZE notifications"))
    db.commit()
    return reader


def test_a_page_of_50000_notifications_uses_an_index(db: Session, notified: User) -> None:
    sql = _compiled(feed.notifications_query(notified).limit(LIMIT + 1))
    on_notifications, shown = _indexes_on(db, sql, "notifications")
    assert "ix_notifications_user_id_id" in on_notifications, shown
    fastest = _fastest(db, sql)
    assert fastest < BUDGET_S, f"fastest of five runs took {fastest:.3f} s"

    started = time.perf_counter()
    page = feed.list_notifications(db, notified, limit=LIMIT)
    elapsed = time.perf_counter() - started
    assert len(page.items) == LIMIT
    assert page.unread_count == 50
    assert elapsed < BUDGET_S, f"list_notifications took {elapsed:.3f} s"


def test_the_feed_endpoint_over_100000_events(seeded: dict[str, User | None], client: Any) -> None:
    started = time.perf_counter()
    response = client.get("/api/v1/activity", params={"bbox": ",".join(map(str, BOX)), "limit": LIMIT})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert len(response.json()["items"]) == LIMIT
    assert elapsed < 2.0, f"the endpoint took {elapsed:.2f} s"
