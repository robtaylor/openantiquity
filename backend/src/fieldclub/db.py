"""Engine, sessions, the declarative base and schema creation.

Sessions come from `SessionLocal`, or from the `get_db` dependency inside a
request. Services flush and never commit. The caller that owns the unit of
work (a router, a CLI command, a job) commits.

Until the first release there's no migration history. `create_schema()` builds
everything from the models plus `models/extras.sql`, and is safe to run again.
"""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from importlib import resources

from sqlalchemy import (
    URL,
    CheckConstraint,
    Connection,
    Engine,
    MetaData,
    create_engine,
    event,
    make_url,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fieldclub.config import get_settings
from fieldclub.vocab import Sensitivity

logger = logging.getLogger(__name__)

EXTENSIONS = ("postgis", "pg_trgm", "citext")

# Any fixed number works. It only has to be the same in every process that
# might build the schema at the same moment.
_SCHEMA_LOCK_ID = 5_867_001

# How long a schema step waits for a lock on a table before the whole run
# fails. A deploy builds the schema while the old version is serving, and a
# step that waits behind a long query makes every later query on that table
# queue behind it. Failing the deploy leaves the old version serving.
SCHEMA_LOCK_TIMEOUT_MS = 5_000

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def constraint_name(exc: IntegrityError) -> str | None:
    """The constraint an `IntegrityError` broke. Safe to log, unlike the message, which holds the values."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def is_unique_violation(exc: IntegrityError, constraint: str) -> bool:
    """Whether an `IntegrityError` is the named unique constraint being broken."""
    return constraint_name(exc) == constraint


# libpq's TCP settings for every connection. A machine that Fly suspended and
# resumed may hold connections the database has long dropped. Keepalives find
# a silent one within about a minute however idle it is, and the user timeout
# ends one whose sent data goes unanswered for 30 s, instead of the quarter of
# an hour the kernel would otherwise wait. Linux honours all of them.
KEEPALIVES: dict[str, int] = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 30_000,
}


def describe(url: str | URL) -> str:
    """The address with its password masked, safe to log."""
    return make_url(url).render_as_string(hide_password=True)


def _make_engine(url: str) -> Engine:
    settings = get_settings()
    engine = create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=KEEPALIVES,
    )

    def first_connect(*_: object) -> None:
        # Once per engine, when logging is set up, in the API and every command alike.
        logger.info("Connected to the database at %s", describe(url))

    event.listen(engine, "first_connect", first_connect)
    return engine


# create_engine() opens no connection, so building it at import time is cheap
# and works without a database (fieldclub-openapi relies on that).
_engine: Engine = _make_engine(get_settings().database_url)

SessionLocal: sessionmaker[Session] = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine() -> Engine:
    """The current engine. Call this each time; don't keep the result in a module global."""
    return _engine


def configure_engine(url: str) -> Engine:
    """Point `SessionLocal` and `get_engine()` at another database.

    The tests use this to switch to their own freshly created database.
    """
    global _engine
    _engine.dispose()
    _engine = _make_engine(url)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_db() -> Generator[Session]:
    """FastAPI dependency: one session per request, rolled back if the request fails."""
    session = SessionLocal()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def _split_sql(script: str) -> list[str]:
    """Split a SQL script into statements.

    Statements end with a semicolon at the end of a line. Dollar-quoted bodies
    are kept whole, so functions can contain semicolons.
    """
    statements: list[str] = []
    current: list[str] = []
    in_dollar_quote = False
    for line in script.splitlines():
        stripped = line.strip()
        if not current and (not stripped or stripped.startswith("--")):
            continue
        current.append(line)
        if line.count("$$") % 2 == 1:
            in_dollar_quote = not in_dollar_quote
        if not in_dollar_quote and stripped.endswith(";"):
            statements.append("\n".join(current).strip().rstrip(";"))
            current = []
    assert not in_dollar_quote, "extras.sql has an unterminated $$ block"
    assert not current, f"extras.sql ends with an unterminated statement: {current[0]!r}"
    return statements


def extras_statements() -> list[str]:
    """The statements in `models/extras.sql`, in order."""
    script = resources.files("fieldclub.models").joinpath("extras.sql").read_text(encoding="utf-8")
    statements = _split_sql(script)
    assert statements, "models/extras.sql is empty"
    for statement in statements:
        # exec_driver_sql hands the text to psycopg, which reads % as a placeholder.
        assert "%" not in statement, f"extras.sql must not contain '%': {statement[:60]!r}"
    return statements


@dataclass(frozen=True)
class _EnumCheck:
    table: str
    name: str
    condition: str


def _enum_checks() -> list[_EnumCheck]:
    """Every `models.common.enum_check` on the tables, with its condition as the enumeration gives it now."""
    from fieldclub.models.common import enum_check_text

    found: list[_EnumCheck] = []
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint) and "enum" in constraint.info:
                assert isinstance(constraint.name, str), f"an unnamed check on {table.name}"
                condition = enum_check_text(constraint.info["column"], constraint.info["enum"])
                found.append(_EnumCheck(table.name, constraint.name, condition))
    return found


_QUOTED = re.compile(r"'((?:[^']|'')*)'")


@dataclass(frozen=True)
class _DroppedValue:
    table: str
    column: str
    dropped: str
    becomes: str


# Values an earlier version stored that this one has no name for, each with
# the value it becomes. A finding's public position is its square's centre at
# both of these levels, so `location_public` stays right (Decision 0032).
_DROPPED_VALUES: tuple[_DroppedValue, ...] = (
    _DroppedValue("findings", "sensitivity", "restricted", Sensitivity.PROTECTED.value),
)


def _move_dropped_values(conn: Connection) -> None:
    """Give every row that holds a dropped value the value that replaced it.

    This runs before `_sync_enum_checks`, in the same transaction, so a check
    made again without the dropped value is never validated against a row
    that holds it. The version before may still be serving: no request it
    takes can store the dropped value, and it reads the new one as it always
    did. Once no row holds it, the update finds nothing and locks no row.
    """
    checked = {(check.table, check.name) for check in _enum_checks()}
    for value in _DROPPED_VALUES:
        assert (value.table, f"ck_{value.table}_{value.column}_valid") in checked, value
        moved = conn.execute(
            text(f'UPDATE "{value.table}" SET "{value.column}" = :becomes WHERE "{value.column}" = :dropped'),
            {"becomes": value.becomes, "dropped": value.dropped},
        ).rowcount
        if moved:
            logger.info("Moved %d rows of %s from %s to %s", moved, value.table, value.dropped, value.becomes)


def _sync_enum_checks(conn: Connection) -> None:
    """Make again each vocabulary check whose stored values differ from its enumeration's now.

    `create_all` makes a check only with its table, so a database built before
    a value was added keeps the old check. The new one is added `NOT VALID`,
    which needs no scan of the table, and `_validate_checks` checks the rows
    after this transaction has let go of its locks.
    """
    stored = {
        (table, name): definition
        for table, name, definition in conn.execute(
            text(
                "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE contype = 'c' AND connamespace = current_schema()::regnamespace"
            )
        )
    }
    for check in _enum_checks():
        definition = stored.get((check.table, check.name))
        assert definition is not None, f"{check.table} has no check {check.name}"
        if set(_QUOTED.findall(definition)) == set(_QUOTED.findall(check.condition)):
            continue
        logger.info("Making %s on %s again with the values it has now", check.name, check.table)
        conn.exec_driver_sql(
            f'ALTER TABLE "{check.table}" DROP CONSTRAINT "{check.name}", '
            f'ADD CONSTRAINT "{check.name}" CHECK ({check.condition}) NOT VALID'
        )


def _validate_checks(conn: Connection) -> None:
    """Check the rows against every vocabulary check added `NOT VALID`.

    `VALIDATE` lets reads and writes go on while it scans the table.
    """
    names = {check.name for check in _enum_checks()}
    for table, name in conn.execute(
        text(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint "
            "WHERE contype = 'c' AND NOT convalidated AND connamespace = current_schema()::regnamespace"
        )
    ):
        if name in names:
            conn.exec_driver_sql(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"')


def _limit_lock_waits(conn: Connection) -> None:
    conn.execute(
        text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": f"{SCHEMA_LOCK_TIMEOUT_MS}ms"}
    )


def create_schema(engine: Engine | None = None) -> None:
    """Create extensions, tables and the extras. Idempotent.

    The steps run in one transaction under an advisory lock, so two processes
    starting at the same moment can't trip over each other. Each waits at
    most `SCHEMA_LOCK_TIMEOUT_MS` for a lock on a table, and then the whole
    run fails and changes nothing. A row holding a value this version dropped
    is given its new value first. A vocabulary check made again is validated
    afterwards in a second transaction.
    """
    import fieldclub.models  # noqa: F401 - registers every table on Base.metadata

    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        _limit_lock_waits(conn)
        for extension in EXTENSIONS:
            conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
        Base.metadata.create_all(conn)
        for statement in extras_statements():
            conn.exec_driver_sql(statement)
        _move_dropped_values(conn)
        _sync_enum_checks(conn)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        _limit_lock_waits(conn)
        _validate_checks(conn)
    logger.info("Schema is up to date (%d tables)", len(Base.metadata.tables))


def main(argv: Sequence[str] | None = None) -> None:
    """`python -m fieldclub.db` builds the schema in the configured database."""
    parser = argparse.ArgumentParser(
        prog="python -m fieldclub.db",
        description="Create the extensions, tables and extras in FIELDCLUB_DATABASE_URL. Safe to run again.",
    )
    parser.parse_args(argv)
    logging.basicConfig(level=get_settings().log_level)
    create_schema()
    print(f"Schema created in {describe(get_engine().url)}")


if __name__ == "__main__":
    # Run the canonical module, not this `__main__` copy. The models register
    # their tables on `fieldclub.db.Base`, which a second copy would not share.
    from fieldclub.db import main as _canonical_main

    _canonical_main()
