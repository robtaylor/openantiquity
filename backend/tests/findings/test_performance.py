"""The map's query over 50,000 findings answers a map-sized box quickly, through the spatial indexes.

The findings are inserted with one SQL statement, as open findings whose
public position is their location (which the trigger requires): 40,000
spread over southern England and 10,000 crowded round Avebury, so the box
holds more than a page. The test runs the service's own statement for a signed-out
visitor, a member and a trusted member, reads the query plan, and times it.
"""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from fieldclub.models import User
from fieldclub.services import findings
from fieldclub.services.findings import FindingFilters
from tests.helpers import MakeUser

COUNT = 50_000
# This many sit in a 10 km by 9 km patch round Avebury, so the box below holds about 830.
CLUSTERED = 10_000
# About 3.5 km by 2.2 km: a phone screen at zoom 14, plus the frontend's 500 m padding.
BOX = (-1.88, 51.41, -1.83, 51.43)
LIMIT = 500
# Generous, so a busy machine doesn't fail it. A sequential scan of 50,000 rows with
# ST_Intersects takes several times longer.
BUDGET_S = 0.25


def _seed(db: Session, author: User) -> None:
    db.execute(
        text(
            """
            INSERT INTO findings (public_id, author_id, title, feature_class, location, location_public,
                                  sensitivity, view_state, grid_ref)
            SELECT 'P' || lpad(i::text, 5, '0'), :author, 'Generated ' || i, 'enclosure',
                   pt, pt, 'open', '{}', NULL
            FROM (
                SELECT i, CASE WHEN i <= :clustered
                    THEN ST_SetSRID(ST_MakePoint(-1.93 + random() * 0.15, 51.38 + random() * 0.08), 4326)
                    ELSE ST_SetSRID(ST_MakePoint(-5.0 + random() * 6.5, 50.5 + random() * 2.5), 4326)
                END AS pt
                FROM generate_series(1, :count) AS i
            ) AS generated
            """
        ),
        {"author": author.id, "count": COUNT, "clustered": CLUSTERED},
    )
    db.commit()
    db.execute(text("ANALYZE findings"))
    db.commit()


def _sql(viewer: User | None) -> str:
    query = findings.findings_query(viewer, FindingFilters(bbox=BOX)).limit(LIMIT + 1)
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _plan(db: Session, sql: str) -> dict:
    (row,) = db.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}")).one()
    return row[0]


def _nodes(node: dict) -> list[dict]:
    found = [node]
    for child in node.get("Plans", []):
        found += _nodes(child)
    return found


@pytest.fixture
def seeded(db: Session, make_user: MakeUser) -> dict[str, User | None]:
    author = make_user()
    _seed(db, author)
    return {"signed_out": None, "member": make_user(), "trusted": make_user("trusted")}


@pytest.mark.parametrize("viewer", ["signed_out", "member", "trusted"])
def test_a_map_box_uses_the_spatial_index_and_is_quick(
    db: Session, seeded: dict[str, User | None], viewer: str
) -> None:
    sql = _sql(seeded[viewer])
    plan = _plan(db, sql)
    nodes = _nodes(plan["Plan"])
    indexes = {node["Index Name"] for node in nodes if "Index Name" in node}
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "findings" for n in nodes), (
        json.dumps(plan, indent=1)
    )
    expected = {"signed_out": {"idx_findings_location_public"}, "trusted": {"idx_findings_location"}}.get(
        viewer, {"idx_findings_location", "idx_findings_location_public"}
    )
    assert expected <= indexes, f"{viewer} used {indexes}"
    # The shapes crossing the box are found through the index of shaped findings alone. With the
    # whole-table index the planner sometimes read every finding for them.
    assert "idx_findings_outline_shaped" in indexes, f"{viewer} used {indexes}"

    returned = len(db.execute(text(sql)).all())
    # The box is crowded enough to fill the page.
    assert returned == LIMIT + 1
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        db.execute(text(sql)).all()
        timings.append(time.perf_counter() - started)
    assert min(timings) < BUDGET_S, f"{viewer}: fastest of five runs took {min(timings):.3f} s"


def test_the_map_endpoint_over_50000_findings(seeded: dict[str, User | None], client) -> None:
    started = time.perf_counter()
    response = client.get("/api/v1/findings", params={"bbox": ",".join(map(str, BOX)), "format": "geojson"})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert len(response.json()["features"]) > 0
    assert elapsed < 2.0, f"the endpoint took {elapsed:.2f} s"
