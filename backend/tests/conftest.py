"""Shared fixtures. `tests/README.md` explains how to use them.

Every pytest session creates its own database on the development PostGIS
server and drops it at the end, so several sessions can run at once. A session
that is killed outright can't tidy up, so each session also removes what dead
sessions left behind.
"""

from __future__ import annotations

import itertools
import logging
import os
import re
import secrets
import shutil
import signal
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Settings. These must be in the environment before anything imports fieldclub,
# because fieldclub.db builds its engine from them at import time.
# --------------------------------------------------------------------------

# Any database on the server will do. It is only used to issue CREATE DATABASE
# and DROP DATABASE.
SERVER_URL = make_url(
    os.environ.get(
        "FIELDCLUB_TEST_SERVER_URL", "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    )
)
TEST_DATABASE = f"fieldclub_test_{os.getpid()}_{secrets.token_hex(4)}"
TEST_URL = SERVER_URL.set(database=TEST_DATABASE)
# Named, not created. Whatever writes there first makes it, so a session that
# never stores a file leaves nothing behind. `pytest_sessionfinish` removes it.
VAR_PREFIX = "fieldclub-test-var-"
VAR_DIR = Path(tempfile.gettempdir()) / f"{VAR_PREFIX}{os.getpid()}-{secrets.token_hex(4)}"

# The process id in each name is how a later session tells a leftover from a
# database or directory that is in use.
_DATABASE_NAME = re.compile(r"fieldclub_test_(\d+)_[0-9a-f]{8}")
_VAR_DIR_NAME = re.compile(re.escape(VAR_PREFIX) + r"(\d+)-[0-9a-f]{8}")
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})

os.environ.update(
    {
        "FIELDCLUB_ENV_FILE": "",  # ignore any developer .env
        "FIELDCLUB_ENV": "test",
        "FIELDCLUB_DATABASE_URL": TEST_URL.render_as_string(hide_password=False),
        "FIELDCLUB_VAR_DIR": str(VAR_DIR),
        "FIELDCLUB_STORAGE_BACKEND": "local",
        "FIELDCLUB_FRONTEND_DIST": str(VAR_DIR / "no-frontend"),
        "FIELDCLUB_RATELIMIT_ENABLED": "false",
        "FIELDCLUB_SECRET_KEY": "test-secret-key",
        "FIELDCLUB_TRUSTED_PROXY_HOPS": "0",
        "FIELDCLUB_AUTO_CREATE_SCHEMA": "false",
        "FIELDCLUB_DEV_LOGIN": "true",  # how a test gets a session over HTTP
    }
)
for _name in (
    "FIELDCLUB_COOKIE_SECURE",
    "FIELDCLUB_USER_AGENT",
    "FIELDCLUB_CONTACT",
    "FIELDCLUB_S3_BUCKET",
    "FIELDCLUB_CLIENT_IP_HEADER",
    "FIELDCLUB_INGEST_MAX_SHRINK",
    "PORT",
    # Read when FIELDCLUB_DATABASE_URL is unset, as Fly attaches it.
    "DATABASE_URL",
    # Would point every S3 client and GDAL at a real store.
    "AWS_ENDPOINT_URL_S3",
    "AWS_S3_ENDPOINT",
    "AWS_HTTPS",
    "AWS_VIRTUAL_HOSTING",
    # Set by Cloud Run and by Fly. Settings refuse a test environment there.
    "K_SERVICE",
    "CLOUD_RUN_JOB",
    "FLY_APP_NAME",
    "FLY_MACHINE_ID",
):
    os.environ.pop(_name, None)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from fieldclub import db as fieldclub_db  # noqa: E402
from fieldclub import gridref, ratelimit  # noqa: E402
from fieldclub.auth import sessions  # noqa: E402
from fieldclub.config import (  # noqa: E402
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    SESSION_COOKIE,
    get_settings,
    reset_settings,
)
from fieldclub.main import create_app  # noqa: E402
from fieldclub.models import Finding, User  # noqa: E402
from fieldclub.models.common import db_point  # noqa: E402
from fieldclub.services import findings, ids  # noqa: E402
from fieldclub.vocab import AgeBand, FeatureClass, Role, Sensitivity  # noqa: E402
from tests.helpers import AVEBURY, BASE_URL  # noqa: E402

TERMS_ACCEPTED_AT = datetime(2026, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------
# Tidying up, including after sessions that could not
# --------------------------------------------------------------------------


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists and belongs to someone else.
        return True
    return True


def _reap_stale_var_dirs() -> None:
    """Remove the runtime directories of sessions whose process has gone."""
    for path in Path(tempfile.gettempdir()).glob(f"{VAR_PREFIX}*"):
        match = _VAR_DIR_NAME.fullmatch(path.name)
        if match and not _pid_is_alive(int(match.group(1))):
            shutil.rmtree(path, ignore_errors=True)


def _reap_stale_databases(admin: Engine) -> None:
    """Drop the databases of sessions that were killed before they could.

    A database is a leftover only when the process named in it has gone and
    nothing is connected to it. Process ids mean nothing on another machine,
    so this only runs against a server on this one.
    """
    if SERVER_URL.host not in _LOOPBACK:
        return
    with admin.connect() as conn:
        names = conn.scalars(
            text(
                "SELECT datname FROM pg_database d WHERE datname LIKE 'fieldclub_test_%' "
                "AND NOT EXISTS (SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname)"
            )
        ).all()
        for name in names:
            match = _DATABASE_NAME.fullmatch(name)
            if match is None or name == TEST_DATABASE or _pid_is_alive(int(match.group(1))):
                continue
            try:
                # Without FORCE: if something connected after all, leave it be.
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            except DBAPIError as exc:
                logger.warning("Could not drop the leftover test database %s: %s", name, exc)


class _Terminated(KeyboardInterrupt):
    """SIGTERM arrived. pytest winds a session down in order for a KeyboardInterrupt."""


_SIGTERM_EXIT_STATUS = 128 + signal.SIGTERM
_previous_sigterm: Any = None
_terminated = False


def _on_sigterm(signum: int, frame: FrameType | None) -> None:
    global _terminated
    _terminated = True
    raise _Terminated("terminated by SIGTERM")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Make SIGTERM end the session the way Ctrl-C does, so fixtures are torn down.

    SIGTERM is what a CI timeout or a stopping container sends. Left alone it
    kills the process on the spot and the session's database stays behind.
    """
    global _previous_sigterm
    _reap_stale_var_dirs()
    if threading.current_thread() is threading.main_thread():
        _previous_sigterm = signal.signal(signal.SIGTERM, _on_sigterm)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _previous_sigterm is not None:
        signal.signal(signal.SIGTERM, _previous_sigterm)
    if _terminated:
        session.exitstatus = _SIGTERM_EXIT_STATUS
    shutil.rmtree(VAR_DIR, ignore_errors=True)


def _admin_engine() -> Engine:
    return create_engine(SERVER_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)


def _create_database(admin: Engine) -> None:
    # CREATE DATABASE copies template1 and fails if another session happens to
    # be copying it at the same instant, so try a few times.
    for attempt in range(10):
        try:
            with admin.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
            return
        except OperationalError:
            if attempt == 9:
                raise
            time.sleep(0.3 * (attempt + 1))


@pytest.fixture(scope="session")
def database() -> Iterator[Engine]:
    """This session's own database, with the full schema. Dropped at the end."""
    assert get_settings().database_url == TEST_URL.render_as_string(hide_password=False), (
        "fieldclub was imported before conftest set the test database URL"
    )
    admin = _admin_engine()
    try:
        _create_database(admin)
    except OperationalError as exc:
        pytest.exit(
            f"Can't reach PostGIS at {SERVER_URL.render_as_string(hide_password=True)}.\n"
            f"Start it with: docker compose -f infra/docker-compose.yml up -d db\n{exc}",
            returncode=3,
        )
    _reap_stale_databases(admin)
    engine = fieldclub_db.configure_engine(TEST_URL.render_as_string(hide_password=False))
    try:
        fieldclub_db.create_schema(engine)
        yield engine
    finally:
        fieldclub_db.get_engine().dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
        admin.dispose()


def _truncate_all(engine: Engine) -> None:
    tables = ", ".join(f'"{table.name}"' for table in fieldclub_db.Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(database: Engine) -> Iterator[Session]:
    """A session on a database with every table emptied first.

    The app under test uses its own sessions, so commit anything a request
    needs to see. `make_user` and `make_finding` commit for you.
    """
    _truncate_all(database)
    session = fieldclub_db.SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def app(db: Session) -> FastAPI:
    """The FastAPI app, wired to this session's database."""
    ratelimit.reset_all()
    return create_app()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """`env(MIN_AGE="18", ...)` sets `FIELDCLUB_*` variables and reloads the settings.

    Both are undone, and the settings reloaded again, when the test ends.
    """

    def set_env(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(f"FIELDCLUB_{name}", value)
        reset_settings()

    yield set_env
    monkeypatch.undo()
    reset_settings()


@pytest.fixture
def limits_on(env: Callable[..., None]) -> Iterator[None]:
    """Rate limits switched on, with one trusted proxy so each test can pick its address."""
    env(RATELIMIT_ENABLED="true", TRUSTED_PROXY_HOPS="1")
    ratelimit.reset_all()
    yield
    ratelimit.reset_all()


@pytest.fixture
def client_for(db: Session) -> Iterator[Callable[..., TestClient]]:
    """`client_for(app, user=None, *, with_header=True)` returns a TestClient for any app.

    Given a user, it is signed in with a real session cookie. Without
    `with_header` it leaves out the client header, as a non-browser caller
    would. Every client is closed when the test ends.
    """
    clients: list[TestClient] = []

    def make(app: FastAPI, user: User | None = None, *, with_header: bool = True) -> TestClient:
        headers = {CLIENT_HEADER: CLIENT_HEADER_VALUE} if with_header else None
        test_client = TestClient(app, base_url=BASE_URL, headers=headers)
        if user is not None:
            token = sessions.create_session(db, user, user_agent="pytest")
            db.commit()
            test_client.cookies.set(SESSION_COOKIE, token)
        clients.append(test_client)
        return test_client

    yield make
    for test_client in clients:
        test_client.close()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """An anonymous browser: no session, but it sends the client header like the web app does."""
    with TestClient(app, base_url=BASE_URL, headers={CLIENT_HEADER: CLIENT_HEADER_VALUE}) as test_client:
        yield test_client


_counter = itertools.count(1)


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    """`make_user(role=Role.MEMBER, handle=None, **columns)` returns a committed user.

    The user has finished the welcome step as an adult. Pass `age_band=None,
    terms_accepted_at=None` for an account that hasn't.
    """

    def make(role: Role | str = Role.MEMBER, *, handle: str | None = None, **columns: Any) -> User:
        role = Role(role)
        number = next(_counter)
        handle = handle or f"Tester{number}"
        # A contributor who has finished the welcome step, unless told otherwise.
        columns.setdefault("age_band", AgeBand.AGE_18_PLUS.value)
        columns.setdefault("terms_accepted_at", TERMS_ACCEPTED_AT)
        user = User(
            handle=handle,
            display_name=columns.pop("display_name", handle),
            role=role.value,
            **columns,
        )
        db.add(user)
        db.commit()
        return user

    return make


@pytest.fixture
def newcomer(make_user: Callable[..., User]) -> User:
    """An account straight from a provider sign-in, before the welcome step."""
    return make_user(
        handle="QuietBarrow42",
        display_name="Robert Provider",
        age_band=None,
        terms_accepted_at=None,
    )


@pytest.fixture
def client_as(app: FastAPI, client_for: Callable[..., TestClient]) -> Callable[[User], TestClient]:
    """`client_as(user)` returns a TestClient signed in as that user, with the client header."""
    return lambda user: client_for(app, user)


@pytest.fixture
def make_finding(db: Session, make_user: Callable[..., User]) -> Callable[..., Finding]:
    """`make_finding(author=None, lon=..., lat=..., **columns)` returns a committed finding.

    It defaults to an enclosure at Avebury by a fresh member. Left out,
    `sensitivity` is the feature class's default, so an enclosure is open and a
    round barrow protected. Pass any `Finding` column to override it.
    """

    def make(
        author: User | None = None,
        *,
        lon: float = AVEBURY[0],
        lat: float = AVEBURY[1],
        feature_class: FeatureClass | str = FeatureClass.ENCLOSURE,
        sensitivity: Sensitivity | str | None = None,
        **columns: Any,
    ) -> Finding:
        author = author or make_user()
        public_id = columns.pop("public_id", None)
        fields: dict[str, Any] = {
            "author_id": author.id,
            "title": columns.pop("title", f"Test finding {next(_counter)}"),
            "feature_class": FeatureClass(feature_class).value,
            "sensitivity": Sensitivity(sensitivity).value if sensitivity is not None else None,
            "location": db_point(lon, lat),
            "grid_ref": columns.pop("grid_ref", None) or gridref.to_gridref(lon, lat),
            "view_state": columns.pop("view_state", {"layer": "composite", "zoom": 16}),
            **columns,
        }
        if public_id is None:
            finding = ids.insert_with_public_id(
                db, lambda generated: Finding(public_id=generated, **fields), findings.PUBLIC_ID_CONSTRAINT
            )
        else:
            finding = Finding(public_id=public_id, **fields)
            db.add(finding)
        db.commit()
        return finding

    return make
