"""The shared fixtures do what tests/README.md says they do."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.config import Environment, get_settings
from fieldclub.models import Finding, User, UserSession
from fieldclub.services import ids
from tests.helpers import MakeFinding, MakeUser, lon_lat


def test_the_database_is_this_sessions_own(database: Engine) -> None:
    name = database.url.database
    assert name is not None
    assert name.startswith("fieldclub_test_")
    with database.connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == name
    assert name != "fieldclub", "tests must never touch the development database"


def test_settings_are_test_settings() -> None:
    settings = get_settings()
    assert settings.env is Environment.TEST
    assert settings.ratelimit_enabled is False
    assert settings.session_cookie_secure is True
    assert settings.should_create_schema is False
    assert settings.dev_login_enabled is True
    assert not settings.frontend_dist.exists()
    assert "fieldclub-test-var-" in str(settings.var_dir)


@pytest.mark.parametrize("attempt", [1, 2])
def test_each_test_starts_with_empty_tables(db: Session, make_user: MakeUser, attempt: int) -> None:
    assert db.scalar(select(func.count()).select_from(User)) == 0
    first = make_user(handle="OnlyOne")
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert first.id == 1, "identity columns restart for every test"


def test_spatial_reference_data_survives_the_truncate(db: Session) -> None:
    assert db.scalar(text("SELECT count(*) FROM spatial_ref_sys WHERE srid IN (4326, 27700, 29903)")) == 3


def test_make_user_defaults_and_overrides(db: Session, make_user: MakeUser) -> None:
    member = make_user()
    assert member.role == "member"
    assert member.id is not None
    assert member.display_name == member.handle

    trusted = make_user("trusted")
    assert trusted.role == "trusted"
    expert = make_user(role="expert", handle="DrTrowel", email="dr@example.org", reputation=80.0)
    assert (expert.role, expert.handle, expert.email, expert.reputation) == (
        "expert",
        "DrTrowel",
        "dr@example.org",
        80.0,
    )
    assert len({member.handle, trusted.handle, expert.handle}) == 3
    with pytest.raises(ValueError, match="wizard"):
        make_user("wizard")
    with pytest.raises(ValueError, match="guest"):
        make_user("guest")

    # Committed, so another session can see them.
    with fieldclub_db.SessionLocal() as other:
        assert other.scalar(select(func.count()).select_from(User)) == 3


def test_client_sends_the_client_header_but_no_session(client: TestClient) -> None:
    assert client.headers["X-OpenAntiquity-Client"] == "web"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/dev-login", json={"handle": "TestRob"}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_client_as_is_signed_in_as_that_user(
    client_as: Callable[[User], TestClient], make_user: MakeUser, db: Session
) -> None:
    alice, bob = make_user(handle="Alice"), make_user("moderator", handle="Bob")
    as_alice, as_bob = client_as(alice), client_as(bob)
    assert as_alice.get("/api/v1/auth/me").json()["handle"] == "Alice"
    assert as_bob.get("/api/v1/auth/me").json()["role"] == "moderator"
    assert as_alice.headers["X-OpenAntiquity-Client"] == "web"
    assert as_alice.patch("/api/v1/auth/me", json={"bio": "Hi"}).status_code == 200
    assert db.scalar(select(func.count()).select_from(UserSession)) == 2


def test_app_is_a_fresh_fastapi_app_on_the_test_database(app: FastAPI, make_user: MakeUser) -> None:
    make_user(handle="SeenByTheApp")
    assert isinstance(app, FastAPI)
    assert TestClient(app, base_url="https://testserver").get("/healthz").status_code == 200


def test_make_finding_defaults(db: Session, make_finding: MakeFinding) -> None:
    finding = make_finding()
    assert ids.normalise(finding.public_id) == finding.public_id
    assert (finding.feature_class, finding.sensitivity, finding.tier, finding.state) == (
        "enclosure",
        "open",
        "spotted",
        "open",
    )
    assert finding.grid_ref == "SU 1023 6996"
    assert finding.view_state == {"layer": "composite", "zoom": 16}
    assert lon_lat(finding.location) == pytest.approx((-1.8542, 51.4286))
    author = db.get(User, finding.author_id)
    assert author is not None
    assert author.role == "member"


def test_make_finding_overrides(db: Session, make_finding: MakeFinding, make_user: MakeUser) -> None:
    finder = make_user("trusted")
    finding = make_finding(
        finder,
        lon=-5.0036,
        lat=56.7969,
        feature_class="hut_circle",
        sensitivity="restricted",
        title="Ring on the shoulder of the hill",
        tier="seen",
        confidence=30,
        nation="scotland",
        public_id="BEN001",
    )
    assert (finding.author_id, finding.public_id, finding.title) == (
        finder.id,
        "BEN001",
        "Ring on the shoulder of the hill",
    )
    assert (finding.feature_class, finding.sensitivity, finding.tier, finding.confidence, finding.nation) == (
        "hut_circle",
        "restricted",
        "seen",
        30,
        "scotland",
    )
    assert finding.grid_ref is not None
    assert finding.grid_ref.startswith("NN ")
    with fieldclub_db.SessionLocal() as other:
        assert other.scalar(select(Finding.public_id)) == "BEN001"

    second = make_finding()
    assert second.public_id != finding.public_id
    assert second.author_id != finder.id
