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
from collections.abc import Generator, Sequence
from importlib import resources

from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fieldclub.config import get_settings

logger = logging.getLogger(__name__)

EXTENSIONS = ("postgis", "pg_trgm", "citext")

# Any fixed number works. It only has to be the same in every process that
# might build the schema at the same moment.
_SCHEMA_LOCK_ID = 5_867_001

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


def _make_engine(url: str) -> Engine:
    settings = get_settings()
    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


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


def create_schema(engine: Engine | None = None) -> None:
    """Create extensions, tables and the extras. Idempotent.

    The steps run in one transaction under an advisory lock, so two processes
    starting at the same moment can't trip over each other.
    """
    import fieldclub.models  # noqa: F401 - registers every table on Base.metadata

    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        for extension in EXTENSIONS:
            conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
        Base.metadata.create_all(conn)
        for statement in extras_statements():
            conn.exec_driver_sql(statement)
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
    print(f"Schema created in {get_engine().url.render_as_string(hide_password=True)}")


if __name__ == "__main__":
    # Run the canonical module, not this `__main__` copy. The models register
    # their tables on `fieldclub.db.Base`, which a second copy would not share.
    from fieldclub.db import main as _canonical_main

    _canonical_main()
