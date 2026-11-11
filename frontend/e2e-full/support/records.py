"""Put a few heritage records and a place in the database `pnpm e2e:full` runs against.

    uv run --project ../backend python e2e-full/support/records.py fieldclub_e2e_123

Two sources of different kinds, three records near Avebury that share the
word "barrow", and one place, so the record search, a record's page and the
search box can be tried against the real API. It is safe to run again: rows
that are there already are left as they are. Only databases whose names
start with `fieldclub_e2e_` are accepted, as in `database.py`.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import make_url

logger = logging.getLogger("e2e-full")

SERVER_URL = make_url(
    os.environ.get(
        "FIELDCLUB_TEST_SERVER_URL", "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    )
)
NAME = re.compile(r"fieldclub_e2e_[a-z0-9_]{1,40}")

OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

# key, name, publisher, category, attribution
SOURCES = (
    ("e2e-designations", "E2E designations", "E2E Heritage", "designation", "© E2E Heritage 2026"),
    ("e2e-monuments", "E2E monument records", "E2E Archive", "monument", "© E2E Archive 2026"),
    ("e2e-places", "E2E place names", "E2E Survey", "place", "Contains E2E Survey data © 2026"),
)

# source key, external id, name, category, lon, lat
RECORDS = (
    ("e2e-designations", "D1", "Barrow cemetery on Overton Hill", "designation", -1.8510, 51.4085),
    ("e2e-monuments", "M1", "Long barrow at East Kennett", "monument", -1.8300, 51.3990),
    ("e2e-monuments", "F1", "Barrow ditch finds", "find", -1.8420, 51.4150),
)

PLACE = ("Kennettbury", -1.8400, 51.4100)


def seed(name: str) -> None:
    os.environ["FIELDCLUB_ENV_FILE"] = ""
    os.environ["FIELDCLUB_DATABASE_URL"] = SERVER_URL.set(database=name).render_as_string(hide_password=False)
    from shapely.geometry import Point

    from fieldclub.db import SessionLocal
    from fieldclub.models import Place, Record, Source
    from fieldclub.models.common import to_db_geometry

    with SessionLocal() as db:
        for key, title, publisher, category, attribution in SOURCES:
            if db.get(Source, key) is None:
                db.add(
                    Source(
                        key=key,
                        name=title,
                        publisher=publisher,
                        licence="OGL v3.0",
                        licence_url=OGL,
                        attribution=attribution,
                        reuse="open",
                        category=category,
                        access="bulk",
                        enabled=True,
                    )
                )
        db.flush()
        for source_key, external_id, title, category, lon, lat in RECORDS:
            found = db.scalar(
                select(Record.id).where(Record.source_key == source_key, Record.external_id == external_id)
            )
            if found is not None:
                continue
            point = to_db_geometry(Point(lon, lat))
            db.add(
                Record(
                    source_key=source_key,
                    external_id=external_id,
                    name=title,
                    category=category,
                    record_type="Barrow",
                    geom=point,
                    centroid=point,
                    precision_m=5,
                    url=f"https://example.org/records/{external_id}",
                    ingested_at=datetime(2026, 11, 10, tzinfo=UTC),
                )
            )
        place, lon, lat = PLACE
        if db.scalar(select(Place.id).where(Place.name == place)) is None:
            db.add(
                Place(
                    name=place,
                    kind="village",
                    county="Wiltshire",
                    nation="england",
                    geom=to_db_geometry(Point(lon, lat)),
                    rank=10,
                    source="e2e-places",
                )
            )
        db.commit()
    logger.info("Seeded records in %s", name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    if len(sys.argv) != 2 or NAME.fullmatch(sys.argv[1]) is None:
        sys.exit("usage: records.py fieldclub_e2e_<name>")
    seed(sys.argv[1])


if __name__ == "__main__":
    main()
