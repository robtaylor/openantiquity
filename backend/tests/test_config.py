"""Settings come from FIELDCLUB_* variables and refuse unsafe combinations."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldclub import __version__
from fieldclub.config import DEV_SECRET_KEY, Environment, Settings, get_settings, reset_settings
from fieldclub.errors import ConfigError
from tests.helpers import settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No FIELDCLUB_* variables at all, so defaults show through."""
    import os

    for name in list(os.environ):
        if name.startswith("FIELDCLUB_") or name in ("PORT", "K_SERVICE", "CLOUD_RUN_JOB"):
            monkeypatch.delenv(name)
    return monkeypatch


@pytest.fixture
def prod_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The least a production deployment has to set."""
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "a-long-random-value")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
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
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "a-long-random-value")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    clean_env.setenv("FIELDCLUB_PORT", "9000")
    clean_env.setenv("FIELDCLUB_SESSION_DAYS", "30")
    config = settings()
    assert config.env is Environment.PROD
    assert config.port == 9000
    assert config.session_days == 30
    assert config.session_cookie_secure is True
    assert config.should_create_schema is False


def test_port_falls_back_to_the_cloud_run_variable(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("PORT", "8080")
    assert settings().port == 8080
    clean_env.setenv("FIELDCLUB_PORT", "9001")
    assert settings().port == 9001


def test_production_refuses_the_development_secret(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_ENV", "prod")
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "1")
    with pytest.raises(ConfigError, match="FIELDCLUB_SECRET_KEY"):
        settings()
    clean_env.setenv("FIELDCLUB_SECRET_KEY", DEV_SECRET_KEY)
    with pytest.raises(ConfigError, match="FIELDCLUB_SECRET_KEY"):
        settings()


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
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "a-long-random-value")
    with pytest.raises(ConfigError, match="FIELDCLUB_TRUSTED_PROXY_HOPS"):
        settings()
    # Zero is a fine answer for a server reached directly. It has to be given.
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "0")
    assert settings().trusted_proxy_hops == 0
    clean_env.setenv("FIELDCLUB_TRUSTED_PROXY_HOPS", "2")
    assert settings().trusted_proxy_hops == 2


@pytest.mark.parametrize("marker", ["K_SERVICE", "CLOUD_RUN_JOB"])
@pytest.mark.parametrize("env", [None, "dev", "test"])
def test_cloud_run_refuses_anything_but_production(
    clean_env: pytest.MonkeyPatch, marker: str, env: str | None
) -> None:
    clean_env.setenv(marker, "fieldclub-api")
    clean_env.setenv("FIELDCLUB_SECRET_KEY", "a-long-random-value")
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


def test_gcs_storage_needs_a_bucket(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_STORAGE_BACKEND", "gcs")
    with pytest.raises(ConfigError, match="FIELDCLUB_GCS_BUCKET"):
        settings()
    clean_env.setenv("FIELDCLUB_GCS_BUCKET", "fieldclub-data")
    assert settings().gcs_bucket == "fieldclub-data"


def test_namespace_buckets_need_the_gcs_backend(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("FIELDCLUB_GCS_NAMESPACE_BUCKETS", '{"media": "fieldclub-photos"}')
    with pytest.raises(ConfigError, match="FIELDCLUB_GCS_NAMESPACE_BUCKETS"):
        settings()
    clean_env.setenv("FIELDCLUB_STORAGE_BACKEND", "gcs")
    clean_env.setenv("FIELDCLUB_GCS_BUCKET", "fieldclub-data")
    assert settings().gcs_namespace_buckets == {"media": "fieldclub-photos"}


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
    assert settings().outbound_user_agent == f"FieldClub/{__version__}"
    clean_env.setenv("FIELDCLUB_CONTACT", "https://example.org/about")
    assert settings().outbound_user_agent == f"FieldClub/{__version__} (+https://example.org/about)"
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
        assert get_settings().session_days == 365
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
    assert default.terrain_national == str(var / "lidar/england/dtm-2022-10m/england-dtm-2022-10m-cog.tif")
    assert default.terrain_work_dir == str(var / "lidar/england/work")
    moved = settings(var_dir=tmp_path)
    assert moved.terrain_mirror == str(tmp_path / "lidar" / "england" / "mirror")
    assert moved.terrain_work_dir == str(tmp_path / "lidar" / "england" / "work")
    assert moved.terrain_path(moved.terrain_mirror) == str(tmp_path / "lidar" / "england" / "mirror")
    chosen = settings(var_dir=tmp_path, terrain_mirror="gs://bucket/mirror", terrain_source_dir="")
    assert (chosen.terrain_mirror, chosen.terrain_source_dir) == ("gs://bucket/mirror", "")
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


def test_many_people_behind_one_address_can_all_have_live_events(clean_env: pytest.MonkeyPatch) -> None:
    # A mobile network or a school puts many people behind one address, and a
    # browser that is refused a stream doesn't try again.
    assert settings().events_max_per_address >= 50
