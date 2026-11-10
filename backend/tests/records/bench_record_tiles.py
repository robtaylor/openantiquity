# ruff: noqa: T201 - a command-line report, so it prints
"""Record tile timings and query plans over 500,000 synthetic records.

    uv run python -m tests.records.bench_record_tiles [--records 500000]

Not a test: pytest doesn't collect it. It creates its own database on the
development server, named `fieldclub_bench_<pid>`, builds the schema, fills
it, prints `EXPLAIN ANALYZE` and timings for a tile at several zooms, and
drops the database again. It never touches the development database itself.

The records are spread over England the way heritage records are: most in
clusters around 300 centres, the rest scattered. One in five is a small
polygon, the rest points. Categories cycle through five values.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

SERVER = os.environ.get(
    "FIELDCLUB_TEST_SERVER_URL", "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
)
NAME = f"fieldclub_bench_{os.getpid()}"
# The densest cluster centre is placed here, so the high-zoom tiles are busy.
DENSE = (-1.8542, 51.4286)

FILL = """
SELECT setseed(0.42);
INSERT INTO sources (key, name, publisher, licence, attribution, reuse, category, access)
    VALUES ('bench', 'Benchmark', 'The benchmark', 'OGL v3.0', 'Synthetic', 'open', 'monument', 'bulk');
CREATE TEMP TABLE centres AS
    SELECT c, CASE WHEN c = 0 THEN :dense_lon ELSE -5.5 + random() * 7.0 END AS lon,
              CASE WHEN c = 0 THEN :dense_lat ELSE 50.2 + random() * 5.4 END AS lat
    FROM generate_series(0, 299) AS c;
INSERT INTO records (source_key, external_id, name, category, geom, centroid, ingested_at)
SELECT 'bench', 'r' || i, 'Synthetic record ' || i,
       (ARRAY['designation', 'monument', 'find', 'event', 'document'])[1 + i % 5],
       g, ST_PointOnSurface(g), now()
FROM (
    SELECT i, CASE WHEN i % 5 = 0 THEN ST_Buffer(p, 0.0004, 2) ELSE p END AS g
    FROM (
        SELECT i, ST_SetSRID(ST_MakePoint(
            CASE WHEN i % 10 < 7 THEN c.lon + (random() + random() + random() - 1.5) * 0.15
                 ELSE -5.5 + random() * 7.0 END,
            CASE WHEN i % 10 < 7 THEN c.lat + (random() + random() + random() - 1.5) * 0.10
                 ELSE 50.2 + random() * 5.4 END), 4326) AS p
        FROM generate_series(1, :count) AS i
        JOIN centres c ON c.c = CASE WHEN i % 4 = 0 THEN 0 ELSE i % 300 END
    ) AS points
) AS shapes;
ANALYZE records;
"""


def tile_of(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=500_000)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()

    admin = create_engine(SERVER, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{NAME}"'))
    url = make_url(SERVER).set(database=NAME)
    os.environ["FIELDCLUB_DATABASE_URL"] = url.render_as_string(hide_password=False)
    try:
        from fieldclub import db as fieldclub_db
        from fieldclub.services import record_tiles

        engine = fieldclub_db.configure_engine(url.render_as_string(hide_password=False))
        fieldclub_db.create_schema(engine)
        started = time.perf_counter()
        with engine.begin() as conn:
            for statement in FILL.strip().split(";\n"):
                if statement.strip():
                    conn.execute(
                        text(statement),
                        {"count": args.records, "dense_lon": DENSE[0], "dense_lat": DENSE[1]},
                    )
        print(f"Filled {args.records:,} records in {time.perf_counter() - started:.1f} s")

        cases = [(6, "most of England in one tile"), (10, "about 40 km across"), (14, "about 2.4 km across")]
        cases.insert(2, (record_tiles.FEATURES_FROM_ZOOM, "the first zoom that can carry individual records"))
        cases.insert(3, (13, "about 4.8 km across"))
        with Session(engine) as db:
            for z, what in cases:
                x, y = tile_of(*DENSE, z)
                timings, size = [], 0
                for _ in range(args.runs):
                    clock = time.perf_counter()
                    size = len(record_tiles.record_tile(db, z, x, y))
                    timings.append((time.perf_counter() - clock) * 1000)
                params = {"z": z, "x": x, "y": y, "extent": record_tiles.EXTENT, "categories": None}
                features = z >= record_tiles.FEATURES_FROM_ZOOM and not record_tiles.is_busy(db, params)
                statement = record_tiles._FEATURES if features else record_tiles._COUNTS
                params |= {"buffer": record_tiles.BUFFER, "margin": record_tiles.BUFFER / record_tiles.EXTENT}
                params |= {"grid": record_tiles.GRID}
                plan = (
                    db.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {statement.text}"), params).scalars().all()
                )
                inside = db.execute(
                    text(
                        "SELECT count(*) FROM records "
                        "WHERE centroid && ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326)"
                    ),
                    {"z": z, "x": x, "y": y},
                ).scalar()
                layer = "records" if features else "record_counts"
                print(f"\n=== z{z}/{x}/{y}: {what}. {inside:,} records, layer {layer}, tile {size:,} bytes")
                print(
                    f"    median {statistics.median(timings):.1f} ms, "
                    f"min {min(timings):.1f} ms, max {max(timings):.1f} ms over {args.runs} runs"
                )
                print("\n".join(f"    {line}" for line in plan))
    finally:
        from fieldclub import db as fieldclub_db

        fieldclub_db.get_engine().dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{NAME}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
