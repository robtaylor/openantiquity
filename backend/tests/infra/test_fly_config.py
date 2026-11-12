"""The Fly configuration files agree with the application and with each other.

They can't be checked against Fly here, so these check what can be: that the
settings in each file start the application as a Fly machine would, and that
the numbers argued in infra/README.md hold together.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from fieldclub.config import Environment
from tests.helpers import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB = tomllib.loads((REPO_ROOT / "fly.toml").read_text())
JOBS = tomllib.loads((REPO_ROOT / "infra" / "fly" / "jobs.toml").read_text())

# What a machine has besides the file's settings: Fly's own variables and the
# app's secrets, with made-up values.
ON_A_MACHINE = {
    "FLY_APP_NAME": "openantiquity",
    "FLY_MACHINE_ID": "e784079b449483",
    "FIELDCLUB_SECRET_KEY": "a-long-random-value-for-the-test-only",
    "DATABASE_URL": "postgres://fly-user:pw@pgbouncer.k8x2rq1yjv5lpwzd.flympg.net/fly-db",
    "AWS_ACCESS_KEY_ID": "tid_test",
    "AWS_SECRET_ACCESS_KEY": "tsec_test",
}


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in list(os.environ):
        if name.startswith(("FIELDCLUB_", "AWS_", "FLY_", "DEFRA_")) or name in ("DATABASE_URL", "PORT"):
            monkeypatch.delenv(name)
    for name, value in ON_A_MACHINE.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def start(machine: pytest.MonkeyPatch, env: dict[str, Any]) -> Any:
    for name, value in env.items():
        machine.setenv(name, str(value))
    return settings()


def test_the_web_app_s_settings_start_the_service(machine: pytest.MonkeyPatch) -> None:
    config = start(machine, WEB["env"])

    assert config.env is Environment.PROD
    assert config.client_ip_header == "Fly-Client-IP"
    assert config.database_url.startswith("postgresql+psycopg://fly-user:pw@direct.")
    assert config.storage_backend == "s3"
    assert config.s3_namespace_buckets == {"media": "openantiquity-photos"}
    assert "openantiquity.org" not in config.redirect_hosts


def test_every_job_s_settings_start(machine: pytest.MonkeyPatch) -> None:
    config = start(machine, JOBS["env"])

    assert config.env is Environment.PROD
    assert config.terrain_mirror == WEB["env"]["FIELDCLUB_TERRAIN_MIRROR"]
    assert config.terrain_national == WEB["env"]["FIELDCLUB_TERRAIN_NATIONAL"]


def test_no_secret_is_written_in_either_file() -> None:
    secrets = set(ON_A_MACHINE) | {
        "FIELDCLUB_SMTP_PASSWORD",
        "FIELDCLUB_GOOGLE_CLIENT_SECRET",
        "FIELDCLUB_MICROSOFT_CLIENT_SECRET",
        "FIELDCLUB_FACEBOOK_APP_SECRET",
        "FIELDCLUB_OSM_CLIENT_SECRET",
        "FIELDCLUB_APPLE_PRIVATE_KEY",
        "FIELDCLUB_DATABASE_URL",
    }
    for env in (WEB["env"], JOBS["env"]):
        assert not secrets & env.keys()
        assert not [name for name in env if name.startswith(("DEFRA_", "FLY_"))]


def test_the_service_listens_where_fly_sends_requests() -> None:
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile").read_text()

    assert WEB["http_service"]["internal_port"] == 8080
    assert "PORT=8080" in dockerfile
    assert (REPO_ROOT / WEB["build"]["dockerfile"]).is_file()


def test_machines_are_suspended_and_small_enough_to_be() -> None:
    service = WEB["http_service"]
    (vm,) = WEB["vm"]

    assert service["auto_stop_machines"] == "suspend"
    assert service["force_https"] is True
    # Fly suspends a machine of 2 GB or less with no swap.
    assert vm["memory"] == "2gb"
    assert "swap_size_mb" not in WEB


def test_streams_leave_room_for_everything_else() -> None:
    limits = WEB["http_service"]["concurrency"]

    assert limits["type"] == "requests"
    assert limits["soft_limit"] < limits["hard_limit"]
    assert int(WEB["env"]["FIELDCLUB_EVENTS_MAX_STREAMS"]) == limits["hard_limit"] - 4


def test_health_checks_ask_the_route_the_application_has() -> None:
    (check,) = WEB["http_service"]["checks"]

    assert check["path"] == "/healthz"


def test_the_schema_is_made_once_per_release() -> None:
    assert WEB["deploy"]["release_command"] == "python -m fieldclub.db"


def test_the_shutdown_fits_inside_fly_s_wait() -> None:
    assert WEB["kill_signal"] == "SIGTERM"
    assert int(WEB["env"]["FIELDCLUB_SHUTDOWN_GRACE_S"]) < WEB["kill_timeout"] <= 300


def test_every_other_name_has_a_redirect_and_the_site_is_not_one() -> None:
    names = json.loads(WEB["env"]["FIELDCLUB_REDIRECT_HOSTS"])

    assert sorted(names) == sorted(
        [
            "www.openantiquity.org",
            "openantiquity.com",
            "www.openantiquity.com",
            "openantiquity.co.uk",
            "www.openantiquity.co.uk",
        ]
    )


def test_the_jobs_run_an_image_of_their_own_app_s_repository() -> None:
    # Not the web app's, which the deploy token in GitHub can push to.
    assert JOBS["image_repository"] == f"registry.fly.io/{JOBS['app']}"
    assert JOBS["region"] == WEB["primary_region"] == "lhr"
    assert JOBS["app"] != WEB["app"]


def test_the_service_listens_only_where_fly_s_proxy_reaches_it() -> None:
    """The image binds IPv4 only, and nothing on Fly overrides it.

    Fly's private network (6PN) is IPv6 and bypasses the proxy, and a service
    is reachable on it only when it binds the machine's 6PN address. Bound to
    0.0.0.0, every request comes through the proxy, which overwrites
    `Fly-Client-IP`, so another machine in the organisation can't choose the
    address that rate limits and bans rest on. Binding `::` or
    `fly-local-6pn` would undo that.
    """
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile").read_text()
    assert "FIELDCLUB_HOST=0.0.0.0" in dockerfile
    for config in (WEB, JOBS):
        assert "FIELDCLUB_HOST" not in config.get("env", {})


def test_the_web_app_adds_nothing_to_the_mirror(machine: pytest.MonkeyPatch) -> None:
    # It has no supply login, and its key only reads the elevation bucket.
    assert start(machine, WEB["env"]).terrain_api_fetch is False
    assert "FIELDCLUB_TERRAIN_API_FETCH" not in JOBS["env"]
