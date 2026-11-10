"""Create or drop the database `pnpm e2e:full` runs the backend against.

    uv run --project ../backend python e2e-full/support/database.py create fieldclub_e2e_123
    uv run --project ../backend python e2e-full/support/database.py drop fieldclub_e2e_123

`create` makes the database and builds the schema in it. `drop` removes it,
ending any connection the backend left open. Only names that start with
`fieldclub_e2e_` are accepted, so this can never touch the development
database. The server is `FIELDCLUB_TEST_SERVER_URL`, as for the backend's own
tests.
"""

from __future__ import annotations

import logging
import os
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

logger = logging.getLogger("e2e-full")

SERVER_URL = make_url(
    os.environ.get(
        "FIELDCLUB_TEST_SERVER_URL", "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    )
)
NAME = re.compile(r"fieldclub_e2e_[a-z0-9_]{1,40}")


def _server():
    return create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")


def create(name: str) -> None:
    with _server().connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ["FIELDCLUB_ENV_FILE"] = ""
    os.environ["FIELDCLUB_DATABASE_URL"] = SERVER_URL.set(database=name).render_as_string(hide_password=False)
    from fieldclub.db import create_schema

    create_schema()
    logger.info("Created %s", name)


def drop(name: str) -> None:
    with _server().connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    logger.info("Dropped %s", name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    if len(sys.argv) != 3 or sys.argv[1] not in {"create", "drop"}:
        sys.exit("usage: database.py create|drop fieldclub_e2e_<name>")
    action, name = sys.argv[1], sys.argv[2]
    if NAME.fullmatch(name) is None:
        sys.exit(f"{name!r} is not an end-to-end database name (fieldclub_e2e_...)")
    create(name) if action == "create" else drop(name)


if __name__ == "__main__":
    main()
