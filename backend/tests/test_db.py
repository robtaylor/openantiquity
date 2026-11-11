"""The schema: extensions, tables, extras, and that building it twice is harmless."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.db import Base, _split_sql, create_schema, extras_statements, get_db
from fieldclub.models import User

EXPECTED_TABLES = {
    "users",
    "auth_identities",
    "sessions",
    "magic_links",
    "reputation_events",
    "findings",
    "observations",
    "evidence",
    "evidence_votes",
    "comments",
    "mentions",
    "follows",
    "media",
    "moderation_actions",
    "sources",
    "records",
    "record_cell_counts",
    "ingest_runs",
    "places",
    "admin_areas",
    "investigations",
    "investigation_members",
    "investigation_items",
    "square_surveys",
    "activity",
    "notifications",
    "reports",
    "watch_channels",
}


def _snapshot(engine: Engine) -> dict[str, list[tuple]]:
    """Everything create_schema makes, in a form that can be compared."""
    with engine.connect() as conn:
        columns = conn.execute(
            text(
                "SELECT table_name, column_name, data_type, is_nullable, is_generated "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position"
            )
        ).all()
        indexes = conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY indexname")
        ).all()
        constraints = conn.execute(
            text(
                "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2"
            )
        ).all()
        functions = conn.execute(
            text("SELECT proname, prosrc FROM pg_proc WHERE proname LIKE 'fieldclub\\_%' ORDER BY proname")
        ).all()
    return {
        "columns": [tuple(row) for row in columns],
        "indexes": [tuple(row) for row in indexes],
        "constraints": [tuple(row) for row in constraints],
        "functions": [tuple(row) for row in functions],
    }


def test_the_contract_tables_are_all_mapped() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_extensions_are_installed(database: Engine) -> None:
    with database.connect() as conn:
        installed = set(conn.scalars(text("SELECT extname FROM pg_extension")))
        version = conn.scalar(text("SELECT postgis_version()"))
    assert {"postgis", "pg_trgm", "citext"} <= installed
    assert version is not None
    assert version.startswith("3.")


def test_every_table_exists(database: Engine) -> None:
    assert set(inspect(database).get_table_names()) >= EXPECTED_TABLES


def test_create_schema_is_idempotent(database: Engine) -> None:
    before = _snapshot(database)
    assert before["columns"], "the schema should already exist"
    create_schema(database)
    create_schema(database)
    assert _snapshot(database) == before


def test_create_schema_keeps_existing_rows(db: Session, database: Engine) -> None:
    db.add(User(handle="Keeper", display_name="Keeper"))
    db.commit()
    create_schema(database)
    assert db.scalar(select(User.handle)) == "Keeper"


def test_records_search_is_a_generated_tsvector(database: Engine) -> None:
    with database.connect() as conn:
        row = conn.execute(
            text(
                "SELECT data_type, is_generated FROM information_schema.columns "
                "WHERE table_name = 'records' AND column_name = 'search'"
            )
        ).one()
    assert tuple(row) == ("tsvector", "ALWAYS")


@pytest.mark.parametrize(
    ("index", "fragments"),
    [
        ("idx_findings_location", ("USING gist", "(location)")),
        ("ix_findings_location_geography", ("USING gist", "geography")),
        ("idx_findings_location_public", ("USING gist", "(location_public)")),
        ("ix_findings_location_public_geography", ("USING gist", "location_public", "geography")),
        ("idx_records_geom", ("USING gist", "(geom)")),
        ("ix_records_centroid_geography", ("USING gist", "geography")),
        ("ix_records_search", ("USING gin", "(search)")),
        ("ix_records_name_trgm", ("USING gin", "gin_trgm_ops")),
        ("ix_places_name_trgm", ("USING gin", "gin_trgm_ops")),
        ("idx_places_geom", ("USING gist", "(geom)")),
        ("ix_notifications_user_id_read_at", ("(user_id, read_at)",)),
        ("ix_activity_created_at", ("created_at DESC",)),
    ],
)
def test_indexes_that_matter(database: Engine, index: str, fragments: tuple[str, ...]) -> None:
    with database.connect() as conn:
        definition = conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"), {"name": index}
        )
    assert definition is not None, f"index {index} is missing"
    for fragment in fragments:
        assert fragment in definition, f"{index} is defined as: {definition}"


def test_every_table_pointing_at_findings_indexes_the_link(database: Engine) -> None:
    inspector = inspect(database)
    missing = []
    for table in sorted(EXPECTED_TABLES):
        if "finding_id" not in {column["name"] for column in inspector.get_columns(table)}:
            continue
        # A partial index serves only queries whose WHERE implies its own, so it doesn't count.
        leading = {
            index["column_names"][0]
            for index in inspector.get_indexes(table)
            if index["column_names"] and "postgresql_where" not in index.get("dialect_options", {})
        }
        leading |= {constraint["column_names"][0] for constraint in inspector.get_unique_constraints(table)}
        primary = inspector.get_pk_constraint(table)["constrained_columns"]
        if primary:
            leading.add(primary[0])
        if "finding_id" not in leading:
            missing.append(table)
    assert not missing, f"no index led by finding_id on: {missing}"


def test_geometry_columns_are_wgs84(database: Engine) -> None:
    with database.connect() as conn:
        rows = conn.execute(
            text("SELECT f_table_name, f_geometry_column, srid, type FROM geometry_columns ORDER BY 1, 2")
        ).all()
    found = {(row[0], row[1]): (row[2], row[3]) for row in rows}
    assert found == {
        ("activity", "location"): (4326, "POINT"),
        ("admin_areas", "geom"): (4326, "MULTIPOLYGON"),
        ("findings", "location"): (4326, "POINT"),
        ("findings", "location_public"): (4326, "POINT"),
        ("findings", "outline"): (4326, "GEOMETRY"),
        ("investigations", "area"): (4326, "GEOMETRY"),
        ("places", "geom"): (4326, "POINT"),
        ("records", "centroid"): (4326, "POINT"),
        ("records", "geom"): (4326, "GEOMETRY"),
        ("square_surveys", "geom"): (4326, "POLYGON"),
    }


def test_no_native_enum_types(database: Engine) -> None:
    with database.connect() as conn:
        enums = conn.scalars(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()
    assert enums == []


def test_ids_are_bigint_identity_and_timestamps_have_zones(database: Engine) -> None:
    with database.connect() as conn:
        ids = conn.execute(
            text(
                "SELECT table_name, data_type, is_identity FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'id' AND table_name <> 'spatial_ref_sys'"
            )
        ).all()
        naive = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
            )
        ).all()
    assert ids
    assert all(tuple(row)[1:] == ("bigint", "YES") for row in ids), ids
    assert naive == []


def test_every_table_has_created_at(database: Engine) -> None:
    inspector = inspect(database)
    for table in EXPECTED_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert "created_at" in columns, f"{table} has no created_at"


def test_extras_file_is_packaged_and_parses() -> None:
    statements = extras_statements()
    assert any("fieldclub_join_text" in statement for statement in statements)
    assert all(not statement.rstrip().endswith(";") for statement in statements)


def test_split_sql_keeps_dollar_quoted_bodies_whole() -> None:
    script = """
    -- a comment
    CREATE FUNCTION f() RETURNS int LANGUAGE sql
        AS $$ SELECT 1; $$;

    CREATE FUNCTION g() RETURNS int LANGUAGE plpgsql AS $$
    BEGIN
        RETURN 1;
    END;
    $$;
    CREATE INDEX IF NOT EXISTS i ON t (c);
    """
    statements = _split_sql(script)
    assert len(statements) == 3
    assert statements[0].startswith("CREATE FUNCTION f()")
    assert "RETURN 1;" in statements[1]
    assert statements[2] == "CREATE INDEX IF NOT EXISTS i ON t (c)"


def test_split_sql_rejects_an_unfinished_statement() -> None:
    with pytest.raises(AssertionError, match="unterminated"):
        _split_sql("CREATE INDEX i ON t (c)")
    with pytest.raises(AssertionError, match="unterminated"):
        _split_sql("CREATE FUNCTION f() AS $$ SELECT 1;")


def test_get_db_rolls_back_when_the_request_fails(db: Session) -> None:
    generator = get_db()
    session = next(generator)
    session.add(User(handle="Doomed", display_name="Doomed"))
    session.flush()
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("the request blew up"))
    assert db.scalar(select(User.handle).where(User.handle == "Doomed")) is None


def test_get_db_does_not_commit_on_its_own(db: Session) -> None:
    generator = get_db()
    session = next(generator)
    session.add(User(handle="Unsaved", display_name="Unsaved"))
    session.flush()
    with pytest.raises(StopIteration):
        next(generator)
    assert db.scalar(select(User.handle).where(User.handle == "Unsaved")) is None


def test_sessions_use_this_test_database(database: Engine) -> None:
    assert fieldclub_db.get_engine() is database
    assert database.url.database is not None
    assert database.url.database.startswith("fieldclub_test_")
    with fieldclub_db.SessionLocal() as session:
        assert session.scalar(text("SELECT current_database()")) == database.url.database


@pytest.mark.parametrize("args", [["--help"], ["--frobnicate"], ["extra"]])
def test_the_schema_command_builds_nothing_when_asked_anything_else(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    def refuse() -> None:
        raise AssertionError("the schema was built")

    monkeypatch.setattr(fieldclub_db, "create_schema", refuse)
    with pytest.raises(SystemExit) as stopped:
        fieldclub_db.main(args)
    assert stopped.value.code == (0 if args == ["--help"] else 2)


def test_the_schema_command_builds_the_schema_with_no_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[bool] = []
    monkeypatch.setattr(fieldclub_db, "create_schema", lambda: built.append(True))
    fieldclub_db.main([])
    assert built == [True]


def test_the_address_used_is_logged_once_with_the_password_masked(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    password = database.url.password
    assert password
    engine = fieldclub_db._make_engine(database.url.render_as_string(hide_password=False))
    try:
        with caplog.at_level("INFO", logger="fieldclub.db"):
            for _ in range(2):
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()
    logged = [record.getMessage() for record in caplog.records if record.name == "fieldclub.db"]
    assert logged == [f"Connected to the database at {fieldclub_db.describe(database.url)}"]
    assert f":{password}@" not in logged[0]
    assert "***" in logged[0]
    assert f"@{database.url.host}:" in logged[0]


def test_every_connection_asks_for_tcp_keepalives(database: Engine) -> None:
    engine = fieldclub_db._make_engine(database.url.render_as_string(hide_password=False))
    try:
        with engine.connect() as conn:
            raw = conn.connection.dbapi_connection
            assert raw is not None
            params = raw.info.get_parameters()
    finally:
        engine.dispose()
    assert {name: params.get(name) for name in fieldclub_db.KEEPALIVES} == {
        name: str(value) for name, value in fieldclub_db.KEEPALIVES.items()
    }
