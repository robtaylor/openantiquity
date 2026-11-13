"""The schema: extensions, tables, extras, and that building it twice is harmless."""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from fieldclub import db as fieldclub_db
from fieldclub.db import Base, _split_sql, create_schema, extras_statements, get_db
from fieldclub.models import User
from fieldclub.models.common import values_check_text
from fieldclub.vocab import ActivityKind, FeatureClass, ShapeKind

EXPECTED_TABLES = {
    "users",
    "auth_identities",
    "sessions",
    "magic_links",
    "released_handles",
    "reputation_events",
    "findings",
    "finding_shape_changes",
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
    "investigation_held_findings",
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


# What the shapes of lines and curves added to a database built before them.
_SHAPE_COLUMNS = (
    "path",
    "outline_mid",
    "outline_low",
    "shape_kind",
    "shape_length_m",
    "shape_revision",
    "location_derived",
    "looked_at",
    "added_since_looked_m",
    "added_view",
)


@pytest.fixture
def scratch_database(database: Engine) -> Iterator[Engine]:
    """Another empty database on the same server, named as a session's so a killed run's is reaped."""
    name = f"fieldclub_test_{os.getpid()}_{secrets.token_hex(4)}"
    admin = create_engine(database.url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(database.url.set(database=name), poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _unordered(snapshot: dict[str, list[tuple]]) -> dict[str, list[tuple]]:
    """A snapshot without column order, which a column added later can't keep."""
    return {key: sorted(rows, key=repr) for key, rows in snapshot.items()}


def _as_main_made_it(engine: Engine) -> None:
    """Take out of a freshly built schema what lines and curves added, as `main` built it, and add rows."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE finding_shape_changes"))
        conn.execute(text("DROP INDEX idx_findings_outline"))
        conn.execute(
            text("ALTER TABLE findings " + ", ".join(f"DROP COLUMN {name}" for name in _SHAPE_COLUMNS))
        )
        conn.execute(text("ALTER TABLE observations DROP COLUMN shape_revision"))
        # The activity kinds as they were, before `shape_extended`.
        kinds = ", ".join(
            f"'{kind.value}'" for kind in ActivityKind if kind is not ActivityKind.SHAPE_EXTENDED
        )
        conn.execute(text("ALTER TABLE activity DROP CONSTRAINT ck_activity_kind_valid"))
        conn.execute(
            text(f"ALTER TABLE activity ADD CONSTRAINT ck_activity_kind_valid CHECK (kind IN ({kinds}))")
        )
        finder, helper = (
            conn.scalar(
                text("INSERT INTO users (handle, display_name) VALUES (:name, :label) RETURNING id"),
                {"name": name, "label": name},
            )
            for name in ("Old", "Helper")
        )
        finding_id = conn.scalar(
            text(
                "INSERT INTO findings (public_id, author_id, title, feature_class, location, "
                "location_public, outline) VALUES ('OLD001', :user_id, 'An old outline', 'enclosure', "
                "ST_GeomFromText('POINT(-1.85 51.43)', 4326), ST_GeomFromText('POINT(-1.85 51.43)', 4326), "
                "ST_GeomFromText('LINESTRING(-1.85 51.43, -1.84 51.43)', 4326)) RETURNING id"
            ),
            {"user_id": finder},
        )
        conn.execute(
            text(
                "INSERT INTO observations (finding_id, user_id, visible, role_at_answer) "
                "VALUES (:finding_id, :user_id, 'yes', 'member')"
            ),
            {"finding_id": finding_id, "user_id": helper},
        )
        conn.execute(
            text(
                "INSERT INTO activity (kind, actor_id, finding_id) VALUES "
                "('finding_created', :user_id, :finding_id), ('observation_added', NULL, :finding_id)"
            ),
            {"user_id": finder, "finding_id": finding_id},
        )


def _rows(engine: Engine) -> dict[str, list[tuple]]:
    with engine.connect() as conn:
        return {
            "findings": [
                tuple(row)
                for row in conn.execute(
                    text("SELECT id, public_id, title, ST_AsText(outline) FROM findings ORDER BY id")
                )
            ],
            "observations": [
                tuple(row)
                for row in conn.execute(text("SELECT id, finding_id, user_id, visible FROM observations"))
            ],
            "activity": [
                tuple(row)
                for row in conn.execute(text("SELECT id, kind, finding_id FROM activity ORDER BY id"))
            ],
        }


def test_create_schema_brings_a_database_made_by_main_up_to_date_and_keeps_every_row(
    database: Engine, scratch_database: Engine
) -> None:
    create_schema(scratch_database)
    _as_main_made_it(scratch_database)
    columns = {column["name"] for column in inspect(scratch_database).get_columns("findings")}
    assert not columns & set(_SHAPE_COLUMNS), "the old database still has the shape columns"
    rows = _rows(scratch_database)
    assert [len(found) for found in rows.values()] == [1, 1, 2]

    create_schema(scratch_database)
    once = _snapshot(scratch_database)
    create_schema(scratch_database)

    assert _snapshot(scratch_database) == once, "a second run changed the schema"
    assert _unordered(once) == _unordered(_snapshot(database))
    assert _rows(scratch_database) == rows
    with scratch_database.connect() as conn:
        old = conn.execute(
            text(
                "SELECT path, outline_mid, shape_kind, shape_revision, location_derived, "
                "ST_AsText(outline) FROM findings WHERE public_id = 'OLD001'"
            )
        ).one()
        answered = conn.scalar(text("SELECT shape_revision FROM observations"))
        unchecked = conn.scalar(text("SELECT count(*) FROM pg_constraint WHERE NOT convalidated"))
    assert tuple(old) == (None, None, None, 0, False, "LINESTRING(-1.85 51.43,-1.84 51.43)")
    assert answered is None
    assert unchecked == 0, "a check was left NOT VALID"


# A reader holds a table for longer than this, so a schema step that needs to
# wait for it fails, or a test before `create_schema` set its own timeout would hang.
_READER_WAIT = "lock_timeout=2000"


@contextmanager
def _reading(engine: Engine, *tables: str) -> Iterator[None]:
    """A long query: a transaction holding ACCESS SHARE on each table until the block ends."""
    with engine.connect() as conn, conn.begin():
        for table in tables:
            conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        yield


def test_an_up_to_date_schema_waits_for_no_reader(scratch_database: Engine) -> None:
    create_schema(scratch_database)
    impatient = create_engine(
        scratch_database.url, poolclass=NullPool, connect_args={"options": f"-c {_READER_WAIT}"}
    )
    try:
        with _reading(scratch_database, *EXPECTED_TABLES):
            create_schema(impatient)
    finally:
        impatient.dispose()


def test_a_schema_change_that_cant_get_its_lock_fails_instead_of_queueing(
    scratch_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_schema(scratch_database)
    _as_main_made_it(scratch_database)
    monkeypatch.setattr(fieldclub_db, "SCHEMA_LOCK_TIMEOUT_MS", 200)
    # Without a timeout of its own, the schema would wait ten seconds for the reader.
    patient = create_engine(
        scratch_database.url, poolclass=NullPool, connect_args={"options": "-c lock_timeout=10000"}
    )
    try:
        with _reading(scratch_database, "findings"):
            started = time.monotonic()
            with pytest.raises(OperationalError, match="lock timeout"):
                create_schema(patient)
            assert time.monotonic() - started < 5
    finally:
        patient.dispose()
    columns = {column["name"] for column in inspect(scratch_database).get_columns("findings")}
    assert not columns & set(_SHAPE_COLUMNS), "a failed schema run left part of its change"
    create_schema(scratch_database)
    columns = {column["name"] for column in inspect(scratch_database).get_columns("findings")}
    assert set(_SHAPE_COLUMNS) <= columns


def _kind_check(engine: Engine) -> tuple[str, bool]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                "WHERE conname = 'ck_activity_kind_valid'"
            )
        ).one()
    return row[0], row[1]


def _kind_check_constraint() -> CheckConstraint:
    (check,) = [
        constraint
        for constraint in Base.metadata.tables["activity"].constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_activity_kind_valid"
    ]
    assert check.info["enum"] is ActivityKind
    return check


def _kinds_and(*later: str) -> type[StrEnum]:
    """The activity kinds with `later` added, as a version that added them would have them."""
    assert not set(later) & {kind.value for kind in ActivityKind}, (
        "a later kind has to be new to this version"
    )
    values = [*(kind.value for kind in ActivityKind), *later]
    # The functional form makes a class, which the type stubs call an instance.
    return cast("type[StrEnum]", StrEnum("LaterActivityKind", {value: value for value in values}))


def test_the_activity_kind_check_follows_the_vocabulary(
    scratch_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_schema(scratch_database)
    check = _kind_check_constraint()
    monkeypatch.setitem(check.info, "enum", _kinds_and("made_up"))

    create_schema(scratch_database)
    definition, validated = _kind_check(scratch_database)
    assert "'made_up'" in definition
    assert validated
    with scratch_database.begin() as conn:
        conn.execute(text("INSERT INTO activity (kind) VALUES ('made_up')"))
        conn.execute(text("DELETE FROM activity WHERE kind = 'made_up'"))


def test_a_version_gone_back_to_leaves_a_check_a_later_one_widened(
    scratch_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Going back to an earlier image runs its schema step against what the later one left.

    The later version added a value and stored rows with it. Made again
    without it, the check would refuse everything the later version saves,
    and validating it would fail on those rows after the narrowed check had
    been committed.
    """
    create_schema(scratch_database)
    check = _kind_check_constraint()
    monkeypatch.setitem(check.info, "enum", _kinds_and("made_up"))
    create_schema(scratch_database)
    with scratch_database.begin() as conn:
        conn.execute(text("INSERT INTO activity (kind) VALUES ('made_up')"))

    monkeypatch.setitem(check.info, "enum", ActivityKind)
    create_schema(scratch_database)

    definition, validated = _kind_check(scratch_database)
    assert "'made_up'" in definition
    assert "'shape_extended'" in definition
    assert validated
    with scratch_database.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM activity WHERE kind = 'made_up'")) == 1
        # The later version, still serving or put back, goes on saving its value.
        conn.execute(text("INSERT INTO activity (kind) VALUES ('made_up')"))
        conn.execute(text("DELETE FROM activity WHERE kind = 'made_up'"))


def test_a_check_made_again_for_a_new_value_keeps_what_a_later_version_added(
    scratch_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_schema(scratch_database)
    check = _kind_check_constraint()
    monkeypatch.setitem(check.info, "enum", _kinds_and("made_up"))
    create_schema(scratch_database)
    with scratch_database.begin() as conn:
        conn.execute(text("INSERT INTO activity (kind) VALUES ('made_up')"))

    # A version cut before that one, with a value of its own to add.
    monkeypatch.setitem(check.info, "enum", _kinds_and("its_own"))
    create_schema(scratch_database)

    definition, validated = _kind_check(scratch_database)
    assert "'made_up'" in definition
    assert "'its_own'" in definition
    assert validated
    with scratch_database.begin() as conn:
        conn.execute(text("INSERT INTO activity (kind) VALUES ('its_own')"))
        conn.execute(text("DELETE FROM activity WHERE kind IN ('made_up', 'its_own')"))


def _class_checks() -> list[CheckConstraint]:
    return [
        constraint
        for table in ("findings", "observations")
        for constraint in Base.metadata.tables[table].constraints
        if isinstance(constraint, CheckConstraint) and constraint.info.get("enum") is FeatureClass
    ]


def _class_check_definitions(engine: Engine, checks: list[CheckConstraint]) -> dict[str, tuple[str, bool]]:
    names = {str(check.name) for check in checks}
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint")
        ).all()
    return {row[0]: (row[1], row[2]) for row in rows if row[0] in names}


def test_the_schema_step_adds_building_to_the_class_checks_of_a_database_that_lacks_it(
    scratch_database: Engine,
) -> None:
    checks = _class_checks()
    assert len(checks) == 3, "the finder's class, the community's class and a second look's class"
    create_schema(scratch_database)
    # A database made before the class existed. The schema step never narrows a check
    # itself, so the older check is written here as that version made it.
    older = [c.value for c in FeatureClass if c is not FeatureClass.BUILDING]
    with scratch_database.begin() as conn:
        for check in checks:
            table, column = check.table.name, check.info["column"]
            conn.exec_driver_sql(
                f'ALTER TABLE "{table}" DROP CONSTRAINT "{check.name}", '
                f'ADD CONSTRAINT "{check.name}" CHECK ({values_check_text(column, older)})'
            )
    before = _class_check_definitions(scratch_database, checks)
    assert len(before) == 3
    assert all("'building'" not in definition for definition, _ in before.values())

    create_schema(scratch_database)

    after = _class_check_definitions(scratch_database, checks)
    assert all("'building'" in definition and validated for definition, validated in after.values()), after


def test_the_hand_written_shape_kind_check_holds_the_vocabulary() -> None:
    """`extras.sql` writes the check on `findings.shape_kind` by hand, for a database made before the column.

    The model makes the same check from `ShapeKind`, so the two must hold the same values.
    """
    name = "ck_findings_shape_kind_valid"
    (model_check,) = [
        constraint
        for constraint in Base.metadata.tables["findings"].constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == name
    ]
    assert model_check.info["enum"] is ShapeKind
    (statement,) = [statement for statement in extras_statements() if name in statement]
    found = re.search(rf"CONSTRAINT {name} CHECK \(shape_kind IN \(([^)]*)\)\)", statement)
    assert found is not None, "extras.sql checks shape_kind with IN (...)"
    written = re.findall(r"'([^']*)'", found.group(1))
    assert sorted(written) == sorted(kind.value for kind in ShapeKind)


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
        ("idx_findings_outline", ("USING gist", "(outline)")),
        ("idx_findings_outline_low", ("USING gist", "(outline_low)")),
        ("idx_findings_outline_shaped", ("USING gist", "(outline)", "shape_kind IS NOT NULL")),
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
        ("findings", "looked_at"): (4326, "GEOMETRY"),
        ("findings", "outline"): (4326, "GEOMETRY"),
        ("findings", "outline_low"): (4326, "GEOMETRY"),
        ("findings", "outline_mid"): (4326, "GEOMETRY"),
        ("investigations", "area"): (4326, "GEOMETRY"),
        ("investigations", "area_squares"): (4326, "POLYGON"),
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
