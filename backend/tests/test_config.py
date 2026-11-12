"""Settings come from FIELDCLUB_* variables and refuse unsafe combinations."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldclub import __version__
from fieldclub.config import (
    DEV_SECRET_KEY,
    Environment,
    Settings,
    database_address,
    get_settings,
    reset_settings,
)
from fieldclub.errors import ConfigError
from tests.helpers import settings

LONG_KEY = "a-long-random-value-of-forty-characters!"

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No FIELDCLUB_* variables at all, so defaults show through."""
    import os

    for name in list(os.environ):
        if name.startswith(("FIELDCLUB_", "AWS_", "FLY_")) or name in PLATFORM_VARIABLES:
            monkeypatch.delenv(name)
    return monkeypatch


# Variables a platform sets that the settings look at.
PLATFORM_VARIABLES = ("PORT", "K_SERVICE", "CLOUD_RUN_JOB", "DATABASE_URL")
# What Fly sets on an app with a Tigris bucket attached, with made-up credentials.
TIGRIS = {
    "AWS_ACCESS_KEY_ID": "tid_test",
    "AWS_SECRET_ACCESS_KEY": "tsec_test",
    "AWS_ENDPOINT_URL_S3": "https://fly.storage.tigris.dev",
    "AWS_REGION": "auto",
}


@pytest.fixture
def prod_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The least a production deployment has to set."""
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", LONG_KEY)
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_TERMS_URL", "https://example.org/terms")
    return clean_env


def test_defaults_suit_local_development(clean_env: pytest.MonkeyPatch) -> None:
    config = settings()
    assert config.env is Environment.DEV
    assert config.database_url == "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    assert (config.host, config.port) == ("127.0.0.1", 8000)
    assert config.storage_backend == "local"
    assert config.var_dir == REPO_ROOT / "var"
    assert config.session_cookie_secure is False
    assert config.should_create_schema is True
    assert config.ratelimit_enabled is True
    assert config.frontend_dist.parts[-2:] == ("frontend", "dist")
    assert config.trusted_proxy_hops == 0
    assert config.ingest_max_shrink == 0.25
    assert (config.dev_login, config.dev_login_enabled) == (False, False), "it has to be asked for"


def test_environment_variables_use_the_fieldclub_prefix(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", LONG_KEY)
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_TERMS_URL", "/terms")
    clean_env.setenv("FIELDCLUB_PORT", "9000")
    clean_env.setenv("FIELDCLUB_SESSION_DAYS", "30")
    config = settings()
    assert config.env is Environment.PROD
    assert config.port == 9000
    assert config.session_days == 30
    assert config.session_cookie_secure is True
    assert config.should_create_schema is False


def test_port_falls_back_to_the_platform_s_variable(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("PORT", "8080")
    assert settings().port == 8080
    clean_env.setenv("FIELDCLUB_PORT", "9001")
    assert settings().port == 9001


def test_production_refuses_the_development_secret(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", DEV_SECRET_KEY)
    with pytest.raises(ConfigError, match="FIELDCLUB_SECRET_KEY"):
        settings()


def test_production_serves_nothing_without_a_secret_but_a_job_may_run_without_one(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Only what signs needs the key, so a job that never signs anything needn't be given it."""
    from fieldclub.main import create_app

    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_TERMS_URL", "/about#terms")
    keyless = settings()
    with pytest.raises(ConfigError, match="FIELDCLUB_SECRET_KEY"):
        keyless.require_signing_key()
    with pytest.raises(ConfigError, match="FIELDCLUB_SECRET_KEY"):
        create_app(keyless)
    # Outside production the placeholder stands in.
    assert settings(env="dev").signing_key == DEV_SECRET_KEY.encode()


@pytest.mark.parametrize(
    "key", ["x", "a" * 31, " " * 32, "a" * 32, "ab" * 32, "abcdabcd" * 8, "  x" + " " * 40]
)
def test_production_refuses_a_short_or_plain_secret(clean_env: pytest.MonkeyPatch, key: str) -> None:
    """The key signs the sign-in flow and keys the address hashes, so it must not be guessable."""
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_TERMS_URL", "/about#terms")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", key)
    with pytest.raises(ConfigError, match="at least 32"):
        settings()
    # What `openssl rand -base64 48` and `openssl rand -hex 32` give.
    for good in (
        "q7Vt0J2mXbN8yKp4Lr6sWd1Zc9Hf3Ga5Ue/Ti+Ro0Pn2Ml4Kj6Ih8Gf0Ed2Cb4Az6Yx8Wv",
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    ):
        clean_env.setenv("FIELDCLUB_SECRET_KEY", good)
        assert settings().env is Environment.PROD


def test_production_refuses_cookies_that_are_not_secure(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_TERMS_URL", "/about#terms")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", LONG_KEY)
    clean_env.setenv("FIELDCLUB_COOKIE_SECURE", "false")
    with pytest.raises(ConfigError, match="FIELDCLUB_COOKIE_SECURE"):
        settings()
    clean_env.setenv("FIELDCLUB_COOKIE_SECURE", "true")
    assert settings().session_cookie_secure is True


# --------------------------------------------------------------------------
# The development login
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "dev_login", "enabled"),
    [
        ("dev", None, False),
        ("dev", "false", False),
        ("dev", "true", True),
        ("test", None, False),
        ("test", "true", True),
    ],
)
def test_dev_login_needs_both_the_setting_and_a_non_production_environment(
    clean_env: pytest.MonkeyPatch, env: str, dev_login: str | None, enabled: bool
) -> None:
    clean_env.setenv("FIELDCLUB_ENV", env)
    if dev_login is not None:
        clean_env.setenv("FIELDCLUB_DEV_LOGIN", dev_login)
    assert settings().dev_login_enabled is enabled


def test_a_deployment_that_forgets_fieldclub_env_still_has_no_dev_login(
    clean_env: pytest.MonkeyPatch,
) -> None:
    # FIELDCLUB_ENV defaults to dev. That alone must not let anyone sign in as anyone.
    assert settings().env is Environment.DEV
    assert settings().dev_login_enabled is False


def test_production_refuses_to_start_with_dev_login_on(prod_env: pytest.MonkeyPatch) -> None:
    assert settings().dev_login_enabled is False
    prod_env.setenv("FIELDCLUB_DEV_LOGIN", "true")
    with pytest.raises(ConfigError, match="FIELDCLUB_DEV_LOGIN"):
        settings()


# --------------------------------------------------------------------------
# Deployments
# --------------------------------------------------------------------------


def test_production_must_say_how_many_proxies_it_is_behind(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", LONG_KEY)
    clean_env.setenv("FIELDCLUB_TERMS_URL", "/terms")
    with pytest.raises(ConfigError, match="FIELDCLUB_TRUSTED_PROXY_HOPS"):
        settings()
    # Zero is a fine answer for a server reached directly. It has to be given.
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "0")
    assert settings().trusted_proxy_hops == 0
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "2")
    assert settings().trusted_proxy_hops == 2


def test_production_must_say_where_the_contributor_terms_are(prod_env: pytest.MonkeyPatch) -> None:
    # The default points at a page the site doesn't have yet, and the welcome step asks
    # everyone to accept what it links to.
    prod_env.delenv("FIELDCLUB_TERMS_URL")
    with pytest.raises(ConfigError, match="FIELDCLUB_TERMS_URL"):
        settings()
    prod_env.setenv("FIELDCLUB_TERMS_URL", "/about#terms")
    assert settings().terms_url == "/about#terms", "said out loud, any address will do"


@pytest.mark.parametrize("marker", ["K_SERVICE", "CLOUD_RUN_JOB"])
@pytest.mark.parametrize("env", [None, "dev", "test"])
def test_cloud_run_refuses_anything_but_production(
    clean_env: pytest.MonkeyPatch, marker: str, env: str | None
) -> None:
    clean_env.setenv(marker, "fieldclub-api")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", LONG_KEY)
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    if env is not None:
        clean_env.setenv("FIELDCLUB_ENV", env)
    with pytest.raises(ConfigError, match="FIELDCLUB_ENV=prod"):
        settings()


def test_a_cloud_run_service_needs_at_least_one_trusted_proxy(prod_env: pytest.MonkeyPatch) -> None:
    prod_env.setenv("K_SERVICE", "fieldclub-api")
    assert settings().trusted_proxy_hops == 1
    prod_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "0")
    with pytest.raises(ConfigError, match="FIELDCLUB_TRUSTED_PROXY_HOPS is 0 on Cloud Run"):
        settings()


def test_a_cloud_run_job_serves_no_requests_so_any_proxy_count_will_do(prod_env: pytest.MonkeyPatch) -> None:
    prod_env.setenv("CLOUD_RUN_JOB", "fieldclub-ingest")
    prod_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "0")
    assert settings().env is Environment.PROD


def test_ingest_max_shrink_is_a_share(clean_env: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    clean_env.setenv("FIELDCLUB_INGEST_MAX_SHRINK", "0.5")
    assert settings().ingest_max_shrink == 0.5
    for bad in ("-0.1", "1.5"):
        clean_env.setenv("FIELDCLUB_INGEST_MAX_SHRINK", bad)
        with pytest.raises(ValidationError):
            settings()


def test_s3_storage_needs_a_bucket_and_the_store_s_variables(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_STORAGE_BACKEND", "s3")
    with pytest.raises(ConfigError, match="FIELDCLUB_S3_BUCKET"):
        settings()
    clean_env.setenv("FIELDCLUB_S3_BUCKET", "openantiquity-data")
    with pytest.raises(ConfigError, match="AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL_S3"):
        settings()
    for name, value in TIGRIS.items():
        clean_env.setenv(name, value)
    assert settings().s3_bucket == "openantiquity-data"
    clean_env.delenv("AWS_ENDPOINT_URL_S3")
    with pytest.raises(ConfigError, match="AWS_ENDPOINT_URL_S3 must be set"):
        settings()


def test_namespace_buckets_need_the_s3_backend(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_S3_NAMESPACE_BUCKETS", '{"media": "openantiquity-photos"}')
    with pytest.raises(ConfigError, match="FIELDCLUB_S3_NAMESPACE_BUCKETS"):
        settings()
    for name, value in TIGRIS.items():
        clean_env.setenv(name, value)
    clean_env.setenv("FIELDCLUB_STORAGE_BACKEND", "s3")
    clean_env.setenv("FIELDCLUB_S3_BUCKET", "openantiquity-data")
    assert settings().s3_namespace_buckets == {"media": "openantiquity-photos"}


@pytest.mark.parametrize("name", ["FIELDCLUB_TERRAIN_MIRROR", "FIELDCLUB_TERRAIN_NATIONAL"])
def test_a_terrain_folder_in_a_bucket_needs_the_store_s_variables(
    clean_env: pytest.MonkeyPatch, name: str
) -> None:
    clean_env.setenv(name, "s3://openantiquity-lidar/england")
    with pytest.raises(ConfigError, match="AWS_ACCESS_KEY_ID"):
        settings()
    for variable, value in TIGRIS.items():
        clean_env.setenv(variable, value)
    assert settings().uses_s3


@pytest.mark.parametrize("location", ["gs://fieldclub-lidar/england/mirror", "https://example.org/mirror"])
def test_a_terrain_folder_is_local_or_s3(clean_env: pytest.MonkeyPatch, location: str) -> None:
    clean_env.setenv("FIELDCLUB_TERRAIN_MIRROR", location)
    with pytest.raises(ConfigError, match="a local path or s3://"):
        settings()


def test_the_gcs_backend_is_gone(clean_env: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    clean_env.setenv("FIELDCLUB_STORAGE_BACKEND", "gcs")
    with pytest.raises(ValidationError, match="storage_backend"):
        settings()


# --------------------------------------------------------------------------
# The database address
# --------------------------------------------------------------------------

FLY_POOLED = "postgres://fly-user:s3cr%2Fet@pgbouncer.k8x2rq1yjv5lpwzd.flympg.net/fly-db"
FLY_DIRECT = "postgresql+psycopg://fly-user:s3cr%2Fet@direct.k8x2rq1yjv5lpwzd.flympg.net/fly-db"


@pytest.mark.parametrize(
    ("given", "used"),
    [
        # What Fly attaches: the pooled host, under either scheme.
        (FLY_POOLED, FLY_DIRECT),
        (FLY_POOLED.replace("postgres://", "postgresql://"), FLY_DIRECT),
        # Fly's direct address, given by hand.
        (FLY_DIRECT.replace("postgresql+psycopg://", "postgresql://"), FLY_DIRECT),
        (FLY_DIRECT, FLY_DIRECT),
        # A port and options are kept.
        (
            "postgresql://u:p@pgbouncer.abc.flympg.net:5432/db?sslmode=require",
            "postgresql+psycopg://u:p@direct.abc.flympg.net:5432/db?sslmode=require",
        ),
        # Anywhere else is left as it is.
        (
            "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub",
            "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub",
        ),
        ("postgresql://u@pgbouncer.example.org/db", "postgresql+psycopg://u@pgbouncer.example.org/db"),
        ("postgresql://u@[::1]:5432/db", "postgresql+psycopg://u@[::1]:5432/db"),
    ],
)
def test_the_database_address_is_the_direct_one_with_psycopg(given: str, used: str) -> None:
    assert database_address(given) == used


@pytest.mark.parametrize(
    "given", ["mysql://u:p@host/db", "postgresql+psycopg2://u:p@host/db", "localhost:5432/db", ""]
)
def test_a_database_address_that_isnt_postgresql_s_is_refused(given: str) -> None:
    with pytest.raises(ConfigError, match="postgresql"):
        database_address(given)


@pytest.mark.parametrize(
    "given",
    [
        FLY_POOLED,
        # A raw "/" in the password, which SQLAlchemy reads as part of the password.
        "postgresql://fly-user:pa/ss@pgbouncer.abc123.flympg.net/fly-db",
        # Options with no database name.
        "postgresql://u:pw@pgbouncer.abc123.flympg.net?sslmode=require",
        "postgresql://u:pw@pgbouncer.abc123.flympg.net:5432?sslmode=require",
        "postgresql://u:pw@pgbouncer.abc123.flympg.net",
        "postgresql://u:p%40ss@PGBOUNCER.abc123.flympg.net/fly-db",
        "postgresql://u:pw@pgbouncer.abc123.flympg.net/fly-db?options=a@b",
    ],
)
def test_sqlalchemy_never_connects_to_the_pooled_address(given: str) -> None:
    from sqlalchemy.engine import make_url

    original, used = make_url(given), make_url(database_address(given))
    assert original.host is not None
    assert original.host.lower().startswith("pgbouncer.")
    assert used.host is not None
    assert used.host.startswith("direct.")
    assert (used.username, used.password, used.port, used.database, dict(used.query)) == (
        original.username,
        original.password,
        original.port,
        original.database,
        dict(original.query),
    )


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://u:p@pgbouncer.x.flympg.net.evil.example/db",
        "postgresql://u:p@evilpgbouncer.x.flympg.net/db",
        "postgresql://u:p@pgbouncer.a.b.flympg.net/db",
        "postgresql://u:p@localhost/db?host=/tmp",
    ],
)
def test_hosts_that_only_look_like_fly_s_pooler_are_left_alone(given: str) -> None:
    from sqlalchemy.engine import make_url

    assert make_url(database_address(given)).host == make_url(given).host


def test_fly_s_database_url_is_read_on_fly_when_the_setting_is_unset(prod_env: pytest.MonkeyPatch) -> None:
    on_fly(prod_env)
    prod_env.setenv("FIELDCLUB_CLIENT_IP_HEADER", "Fly-Client-IP")
    prod_env.setenv("DATABASE_URL", FLY_POOLED)
    assert settings().database_url == FLY_DIRECT
    prod_env.setenv("FIELDCLUB_DATABASE_URL", "postgresql://fieldclub:fieldclub@db.internal/fieldclub")
    assert settings().database_url == "postgresql+psycopg://fieldclub:fieldclub@db.internal/fieldclub"


def test_a_database_url_exported_for_something_else_is_ignored_off_fly(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql://other:pw@shellhost/otherdb")
    assert settings().database_url == "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"


# --------------------------------------------------------------------------
# Platforms
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mirror", "national"),
    [
        ("s3://elevation/england/mirror", "s3://elevation/england/mirror"),
        ("s3://elevation/england/mirror", "s3://elevation/england/mirror/"),
        ("s3://elevation/england", "s3://elevation/england/national"),
        ("s3://elevation/england/mirror/national", "s3://elevation/england/mirror"),
        ("s3://elevation", "s3://elevation/national"),
        ("var/lidar/england", "var/lidar/england/national"),
        ("var/lidar/england/mirror", str(REPO_ROOT / "var/lidar/england/mirror")),
    ],
)
def test_the_mirror_and_the_overview_must_be_separate_folders(
    clean_env: pytest.MonkeyPatch, mirror: str, national: str
) -> None:
    for name, value in TIGRIS.items():
        clean_env.setenv(name, value)
    with pytest.raises(ConfigError, match="must be separate folders"):
        settings(terrain_mirror=mirror, terrain_national=national)


@pytest.mark.parametrize(
    ("mirror", "national"),
    [
        ("s3://elevation/england/mirror", "s3://elevation/england/national"),
        ("s3://elevation/england/mirror", "s3://elevation/england/mirror-national"),
        ("s3://elevation/england/mirror", "s3://overview/england/mirror"),
        ("s3://elevation/england/mirror", "var/lidar/england/mirror"),
    ],
)
def test_separate_terrain_folders_are_accepted(
    clean_env: pytest.MonkeyPatch, mirror: str, national: str
) -> None:
    for name, value in TIGRIS.items():
        clean_env.setenv(name, value)
    config = settings(terrain_mirror=mirror, terrain_national=national)
    assert (config.terrain_mirror, config.terrain_national) == (mirror, national)


def on_fly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLY_APP_NAME", "openantiquity")
    monkeypatch.setenv("FLY_MACHINE_ID", "d8901e3c6e4789")


@pytest.mark.parametrize("env", [None, "dev", "test"])
def test_fly_refuses_anything_but_production(clean_env: pytest.MonkeyPatch, env: str | None) -> None:
    on_fly(clean_env)
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "a-long-random-value")
    clean_env.setenv("FIELDCLUB_CLIENT_IP_HEADER", "Fly-Client-IP")
    if env is not None:
        clean_env.setenv("FIELDCLUB_ENV", env)
    with pytest.raises(ConfigError, match=r"on Fly\. Set FIELDCLUB_ENV=prod"):
        settings()


def test_one_of_fly_s_variables_alone_is_not_fly(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FLY_APP_NAME", "openantiquity")
    assert settings().env is Environment.DEV


def test_production_on_fly_needs_the_client_address_header(prod_env: pytest.MonkeyPatch) -> None:
    on_fly(prod_env)
    with pytest.raises(ConfigError, match="FIELDCLUB_CLIENT_IP_HEADER must be set on Fly"):
        settings()
    prod_env.setenv("FIELDCLUB_CLIENT_IP_HEADER", "Fly-Client-IP")
    assert settings().client_ip_header == "Fly-Client-IP"


def test_the_client_address_header_does_for_the_proxy_count_in_production(
    prod_env: pytest.MonkeyPatch,
) -> None:
    prod_env.delenv("FIELDCLUB_TRUSTED_PROXY_HOPS")
    with pytest.raises(ConfigError, match="FIELDCLUB_TRUSTED_PROXY_HOPS or FIELDCLUB_CLIENT_IP_HEADER"):
        settings()
    prod_env.setenv("FIELDCLUB_CLIENT_IP_HEADER", "Fly-Client-IP")
    assert settings().trusted_proxy_hops == 0


@pytest.mark.parametrize("value", ["Fly Client IP", "X-Real-IP:", ""])
def test_the_client_address_header_is_one_header_name(clean_env: pytest.MonkeyPatch, value: str) -> None:
    from pydantic import ValidationError

    clean_env.setenv("FIELDCLUB_CLIENT_IP_HEADER", value)
    with pytest.raises(ValidationError, match="client_ip_header"):
        settings()


def test_cookie_secure_and_schema_creation_can_be_forced(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_COOKIE_SECURE", "true")
    clean_env.setenv("FIELDCLUB_AUTO_CREATE_SCHEMA", "false")
    config = settings()
    assert config.session_cookie_secure is True
    assert config.should_create_schema is False


def test_the_secret_is_not_shown_when_settings_are_printed(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "do-not-print-me")
    assert "do-not-print-me" not in repr(settings())


def test_user_agent_names_the_project(clean_env: pytest.MonkeyPatch) -> None:
    assert settings().outbound_user_agent == f"OpenAntiquity/{__version__}"
    clean_env.setenv("FIELDCLUB_CONTACT", "https://example.org/about")
    assert settings().outbound_user_agent == f"OpenAntiquity/{__version__} (+https://example.org/about)"
    clean_env.setenv("FIELDCLUB_USER_AGENT", "Custom/1.0")
    assert settings().outbound_user_agent == "Custom/1.0"


def test_get_settings_is_cached_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    assert get_settings() is first
    assert first.env is Environment.TEST
    monkeypatch.setenv("FIELDCLUB_SESSION_DAYS", "7")
    assert get_settings().session_days != 7
    reset_settings()
    try:
        assert get_settings().session_days == 7
    finally:
        monkeypatch.undo()
        reset_settings()
    assert get_settings().session_days == first.session_days


def test_env_file_is_read_unless_switched_off(tmp_path: Path, clean_env: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIELDCLUB_SESSION_DAYS=12\n")
    clean_env.setenv("FIELDCLUB_ENV_FILE", str(env_file))
    reset_settings()
    try:
        assert get_settings().session_days == 12
        clean_env.setenv("FIELDCLUB_ENV_FILE", "")
        reset_settings()
        assert get_settings().session_days == 90
    finally:
        clean_env.undo()
        reset_settings()


def test_env_example_documents_every_setting() -> None:
    text = ENV_EXAMPLE.read_text()
    documented = {
        line.lstrip("# ").split("=", 1)[0]
        for line in text.splitlines()
        if line.lstrip("# ").startswith("FIELDCLUB_") and "=" in line
    }
    expected = {f"FIELDCLUB_{name.upper()}" for name in Settings.model_fields} | {"FIELDCLUB_ENV_FILE"}
    assert documented == expected


def test_env_example_documents_every_bulk_supply_setting() -> None:
    from fieldclub.config import DefraSftpSettings

    lines = [line.lstrip("# ") for line in ENV_EXAMPLE.read_text().splitlines()]
    documented = {line.split("=", 1)[0] for line in lines if line.startswith("DEFRA_") and "=" in line}
    assert documented == {name.upper() for name in DefraSftpSettings.model_fields}


def test_terrain_folders_follow_the_var_dir(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Like every other runtime path, unless one is set for itself."""
    default = settings()
    var = REPO_ROOT / "var"
    assert default.terrain_mirror == str(var / "lidar/england/mirror")
    assert default.terrain_source_dir == str(var / "lidar/england/dtm-2022")
    assert default.terrain_national == str(var / "lidar/england/national")
    assert default.terrain_work_dir == str(var / "lidar/england/work")
    moved = settings(var_dir=tmp_path)
    assert moved.terrain_mirror == str(tmp_path / "lidar" / "england" / "mirror")
    assert moved.terrain_work_dir == str(tmp_path / "lidar" / "england" / "work")
    assert moved.terrain_path(moved.terrain_mirror) == str(tmp_path / "lidar" / "england" / "mirror")
    for name, value in TIGRIS.items():
        clean_env.setenv(name, value)
    chosen = settings(var_dir=tmp_path, terrain_mirror="s3://bucket/mirror", terrain_source_dir="")
    assert (chosen.terrain_mirror, chosen.terrain_source_dir) == ("s3://bucket/mirror", "")
    assert chosen.terrain_national.startswith(str(tmp_path))


def test_env_example_holds_no_real_secret() -> None:
    values = dict(
        line.lstrip("# ").split("=", 1)
        for line in ENV_EXAMPLE.read_text().splitlines()
        if line.lstrip("# ").startswith("FIELDCLUB_") and "=" in line
    )
    assert values["FIELDCLUB_SECRET_KEY"] in ("", DEV_SECRET_KEY)


def test_env_example_loads_as_it_stands(tmp_path: Path, clean_env: pytest.MonkeyPatch) -> None:
    # Copying the example to .env has to give a working development setup.
    env_file = tmp_path / ".env"
    env_file.write_text(ENV_EXAMPLE.read_text())
    config = Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
    assert config.env is Environment.DEV
    assert config.dev_login_enabled is True


def test_min_age_defaults_to_16(clean_env: pytest.MonkeyPatch) -> None:
    assert settings().min_age == 16
    clean_env.setenv("FIELDCLUB_MIN_AGE", "18")
    assert settings().min_age == 18


@pytest.mark.parametrize("value", ["13", "15", "19", "sixteen"])
def test_min_age_must_be_between_16_and_18(clean_env: pytest.MonkeyPatch, value: str) -> None:
    clean_env.setenv("FIELDCLUB_MIN_AGE", value)
    with pytest.raises(ValueError, match="min_age"):
        settings()


def test_a_relative_var_dir_is_the_same_folder_from_any_working_directory(
    clean_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Storage, ingest caches and terrain all read `var_dir`, so they must agree on where it is."""
    from fieldclub.ingest.adapters.common import cache_dir
    from fieldclub.storage import LocalStorage

    clean_env.chdir(tmp_path)
    config = settings(var_dir="runtime")
    expected = REPO_ROOT / "runtime"
    assert config.var_dir == expected
    assert LocalStorage(config.var_dir / "tiles").root == expected / "tiles"
    assert config.terrain_path(config.terrain_mirror) == str(expected / "lidar" / "england" / "mirror")
    clean_env.setattr(Path, "mkdir", lambda *args, **kwargs: None)
    assert cache_dir(config, "nhle") == expected / "ingest" / "nhle"


def test_the_shutdown_grace_is_whole_seconds(clean_env: pytest.MonkeyPatch) -> None:
    # Uvicorn takes an int, and truncating 0.5 to 0 would cut every request off at once.
    clean_env.setenv("FIELDCLUB_SHUTDOWN_GRACE_S", "0.5")
    with pytest.raises(ValueError, match="shutdown_grace_s"):
        Settings()
    clean_env.setenv("FIELDCLUB_SHUTDOWN_GRACE_S", "3")
    assert Settings().shutdown_grace_s == 3


def test_one_address_can_hold_at_most_a_quarter_of_the_streams(clean_env: pytest.MonkeyPatch) -> None:
    """A few addresses mustn't be able to take every stream a process serves.

    A household or a school behind one address that opens more streams than
    this falls back to asking now and then, as the frontend does whenever the
    stream is refused.
    """
    defaults = settings()
    assert 4 <= defaults.events_max_per_address <= defaults.events_max_streams // 4
    clean_env.setenv("FIELDCLUB_EVENTS_MAX_STREAMS", "16")
    clean_env.setenv("FIELDCLUB_EVENTS_MAX_PER_ADDRESS", "5")
    with pytest.raises(ConfigError, match="FIELDCLUB_EVENTS_MAX_PER_ADDRESS"):
        settings()
    clean_env.setenv("FIELDCLUB_EVENTS_MAX_PER_ADDRESS", "4")
    assert settings().events_max_per_address == 4
