"""The coverage query reads through the spatial index, not the whole table.

200,000 surveys are written straight into the table, 20 people by 10,000
squares in a block 100 km on each side. A coverage box of a few kilometres
must then be answered from the GIST index on `square_surveys.geom`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from fieldclub.services import squares
from tests.helpers import MakeUser

PEOPLE = 20
SIDE = 100


def test_coverage_over_200000_surveys_uses_the_index(db: Session, make_user: MakeUser) -> None:
    users = [make_user().id for _ in range(PEOPLE)]
    # Squares of about 1 km, in degrees, south-west corner at (-3, 51).
    db.execute(
        text(
            """
            INSERT INTO square_surveys (user_id, square, geom, result, findings_count)
            SELECT u, 'T' || lpad(i::text, 3, '0') || lpad(j::text, 3, '0'),
                   ST_MakeEnvelope(
                       -3 + i * 0.0144, 51 + j * 0.009, -3 + (i + 1) * 0.0144, 51 + (j + 1) * 0.009, 4326
                   ),
                   CASE WHEN (i + j + u) % 5 = 0 THEN 'skipped' ELSE 'nothing' END, 0
            FROM unnest(CAST(:users AS bigint[])) AS u,
                 generate_series(0, :side - 1) AS i,
                 generate_series(0, :side - 1) AS j
            """
        ),
        {"users": users, "side": SIDE},
    )
    db.commit()
    db.execute(text("ANALYZE square_surveys"))
    assert db.scalar(text("SELECT count(*) FROM square_surveys")) == PEOPLE * SIDE * SIDE

    bbox = (-2.5, 51.3, -2.45, 51.33)
    statement = squares.coverage_query(bbox).compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    plan = "\n".join(row[0] for row in db.execute(text(f"EXPLAIN {statement}")))
    assert "Seq Scan on square_surveys" not in plan, plan
    assert "idx_square_surveys_geom" in plan, plan

    # These squares aren't grid squares, so run the query itself rather than `squares.coverage`.
    rows = db.execute(squares.coverage_query(bbox)).all()
    assert rows
    assert all(scans <= PEOPLE for _, scans, _ in rows)
