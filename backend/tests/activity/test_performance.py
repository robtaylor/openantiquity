"""The feed over 100,000 activity rows answers a map-sized box through an index, quickly.

5,000 open findings are inserted with one statement, 1,000 of them crowded
round Avebury, and 100,000 events spread over them, each at its finding's
point (the trigger needs open findings to be exact, and an event's position
only has to be near its finding for the plan to be realistic). The test runs
the feed's own statement for three viewers, reads the plan and times it.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from fieldclub.models import User
from fieldclub.services import feed
from fieldclub.services.feed import FeedFilters
from tests.helpers import MakeUser

FINDINGS = 5_000
CLUSTERED = 1_000
EVENTS = 100_000
# About 3.5 km by 2.2 km round Avebury: a phone screen at zoom 14, plus the frontend's padding.
BOX = (-1.88, 51.41, -1.83, 51.43)
LIMIT = 50
BUDGET_S = 0.25


def _seed(db: Session, author: User) -> None:
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


def _sql(viewer: User | None) -> str:
    query = feed.feed_query(viewer, FeedFilters(bbox=BOX)).limit(LIMIT + 1)
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node]
    for child in node.get("Plans", []):
        found += _nodes(child)
    return found


@pytest.fixture
def seeded(db: Session, make_user: MakeUser) -> dict[str, User | None]:
    author = make_user()
    _seed(db, author)
    assert db.scalar(text("SELECT count(*) FROM activity")) == EVENTS
    return {"signed_out": None, "member": make_user(), "moderator": make_user("moderator")}


@pytest.mark.parametrize("viewer", ["signed_out", "member", "moderator"])
def test_a_map_box_over_100000_events_uses_an_index(
    db: Session, seeded: dict[str, User | None], viewer: str
) -> None:
    sql = _sql(seeded[viewer])
    (row,) = db.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}")).one()
    plan = row[0]
    nodes = _nodes(plan["Plan"])
    shown = json.dumps(plan, indent=1)
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "activity" for n in nodes), (
        shown
    )
    on_activity = {
        n["Index Name"] for n in nodes if n.get("Relation Name") == "activity" and "Index Name" in n
    }
    on_activity |= {
        n["Index Name"]
        for n in nodes
        if n["Node Type"] == "Bitmap Index Scan" and "activity" in n["Index Name"]
    }
    assert on_activity, shown

    assert len(db.execute(text(sql)).all()) == LIMIT + 1, "the box is crowded enough to fill a page"
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        db.execute(text(sql)).all()
        timings.append(time.perf_counter() - started)
    assert min(timings) < BUDGET_S, f"{viewer}: fastest of five runs took {min(timings):.3f} s"


def test_the_feed_endpoint_over_100000_events(seeded: dict[str, User | None], client: Any) -> None:
    started = time.perf_counter()
    response = client.get("/api/v1/activity", params={"bbox": ",".join(map(str, BOX)), "limit": LIMIT})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert len(response.json()["items"]) == LIMIT
    assert elapsed < 2.0, f"the endpoint took {elapsed:.2f} s"
