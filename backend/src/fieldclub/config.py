"""Settings, read from `FIELDCLUB_*` environment variables.

`backend/.env.example` documents every setting. A `.env` file in the working
directory is read when present. Set `FIELDCLUB_ENV_FILE` to another path, or to an
empty string to read no file at all (the tests do this).
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fieldclub import __version__
from fieldclub.errors import ConfigError

# A placeholder for local development. Settings refuse to load it in production.
DEV_SECRET_KEY = "dev-only-secret-change-me"
SESSION_COOKIE = "fieldclub_session"
CLIENT_HEADER = "X-FieldClub-Client"
CLIENT_HEADER_VALUE = "web"

# backend/src/fieldclub/config.py -> the repository root, when run from a checkout.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Cloud Run sets one of these in every container: the first for a service, the
# second for a job. Neither is ever set by hand.
_CLOUD_RUN_SERVICE = "K_SERVICE"
_CLOUD_RUN_JOB = "CLOUD_RUN_JOB"


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIELDCLUB_", extra="ignore")

    env: Environment = Environment.DEV
    log_level: str = "INFO"

    # Serving
    host: str = "127.0.0.1"
    # Cloud Run tells the container which port to listen on through PORT.
    port: int = Field(default=8000, validation_alias=AliasChoices("FIELDCLUB_PORT", "PORT"))
    public_url: str = "http://localhost:5173"
    frontend_dist: Path = _REPO_ROOT / "frontend" / "dist"
    trusted_proxy_hops: int = Field(default=0, ge=0)

    # Database
    database_url: str = "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    auto_create_schema: bool | None = None

    # Sessions and abuse limits
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    session_days: int = Field(default=365, ge=1)
    cookie_secure: bool | None = None
    ratelimit_enabled: bool = True
    # POST /auth/dev-login signs in as anyone by name. It has to be asked for,
    # and is refused outright in production.
    dev_login: bool = False

    # Contributors must be at least this old (Decision 0009). 16 admits both
    # age bands. 17 or 18 admits only 18 and over, because the 16 to 17 band
    # can't tell a 16 year old from a 17 year old.
    min_age: int = Field(default=16, ge=16, le=18)

    # Runtime data
    var_dir: Path = Path("var")
    storage_backend: Literal["local", "gcs"] = "local"
    gcs_bucket: str | None = None
    gcs_prefix: str = ""

    # Outbound HTTP
    contact: str = ""
    user_agent: str | None = None
    http_timeout_s: float = Field(default=20.0, gt=0)

    # Ingest
    ingest_batch_size: int = Field(default=500, ge=1, le=4000)
    # The share of a source's stored records a full run may find missing
    # before it refuses to delete them. See fieldclub.ingest.runner.
    ingest_max_shrink: float = Field(default=0.25, ge=0, le=1)

    # --- Terrain (Decision 0006) -----------------------------------------
    # Elevation is read only from the mirror of cloud-optimised GeoTIFFs: a
    # local folder, or `gs://bucket/prefix` in production. Relative paths are
    # resolved against the repository root, where `var/lidar` lives.
    terrain_mirror: str = "var/lidar/england/mirror"
    # Defra's source tiles already on disk, converted instead of fetched. Empty to fetch everything.
    terrain_source_dir: str = "var/lidar/england/dtm-2022"
    # The national 10 m composite as a cloud-optimised GeoTIFF, for zoom 12 and below.
    terrain_national: str = "var/lidar/england/dtm-2022-10m/england-dtm-2022-10m-cog.tif"
    # Downloads from the bulk supply that may run at once in one process.
    terrain_fetch_concurrency: int = Field(default=2, ge=1, le=8)
    # Where downloads and conversions are staged before they enter the mirror.
    terrain_work_dir: str = "var/lidar/england/work"

    def terrain_path(self, value: str) -> str:
        """A terrain location as given, or a relative local path resolved against the repository root."""
        if not value or "://" in value or Path(value).is_absolute():
            return value
        return str(_REPO_ROOT / value)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        is_prod = self.env is Environment.PROD
        if is_prod and self.secret_key.get_secret_value() == DEV_SECRET_KEY:
            raise ConfigError("FIELDCLUB_SECRET_KEY must be set to a long random value in production.")
        if is_prod and self.dev_login:
            raise ConfigError(
                "FIELDCLUB_DEV_LOGIN lets anyone sign in as anyone. It can't be on in production."
            )
        if is_prod and "trusted_proxy_hops" not in self.model_fields_set:
            # Unset means 0, and behind a proxy that puts every signed-out
            # caller in one rate-limit bucket. Make whoever deploys say.
            raise ConfigError(
                "FIELDCLUB_TRUSTED_PROXY_HOPS must be set in production: the number of reverse proxies "
                "in front of the API (1 on Cloud Run, 0 only when it is reached directly)."
            )
        on_cloud_run_service = bool(os.environ.get(_CLOUD_RUN_SERVICE))
        if (on_cloud_run_service or os.environ.get(_CLOUD_RUN_JOB)) and not is_prod:
            # FIELDCLUB_ENV defaults to dev, which turns off the Secure cookie and
            # accepts the placeholder secret. A deployment that forgot the
            # variable must not start like that.
            raise ConfigError(f"FIELDCLUB_ENV is '{self.env.value}' on Cloud Run. Set FIELDCLUB_ENV=prod.")
        if on_cloud_run_service and self.trusted_proxy_hops < 1:
            raise ConfigError(
                "FIELDCLUB_TRUSTED_PROXY_HOPS is 0 on Cloud Run, where every request arrives through "
                "Google's proxy. Set it to 1, or 2 behind a load balancer as well."
            )
        if self.storage_backend == "gcs" and not self.gcs_bucket:
            raise ConfigError("FIELDCLUB_GCS_BUCKET is required when FIELDCLUB_STORAGE_BACKEND is 'gcs'.")
        return self

    @property
    def is_dev(self) -> bool:
        return self.env is Environment.DEV

    @property
    def dev_login_enabled(self) -> bool:
        """Whether POST /auth/dev-login exists: only in dev or test, and only when asked for."""
        return self.dev_login and self.env in (Environment.DEV, Environment.TEST)

    @property
    def session_cookie_secure(self) -> bool:
        """Session cookies are Secure everywhere except local development."""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return not self.is_dev

    @property
    def should_create_schema(self) -> bool:
        """Whether the API builds the schema at start-up. On by default in development only."""
        if self.auto_create_schema is not None:
            return self.auto_create_schema
        return self.is_dev

    @property
    def outbound_user_agent(self) -> str:
        """The `User-Agent` sent to every upstream service."""
        if self.user_agent:
            return self.user_agent
        contact = f" (+{self.contact})" if self.contact else ""
        return f"FieldClub/{__version__}{contact}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_file = os.environ.get("FIELDCLUB_ENV_FILE", ".env")
    return Settings(_env_file=env_file or None)  # pyright: ignore[reportCallIssue]


def reset_settings() -> None:
    """Forget the cached settings so the next `get_settings()` re-reads the environment."""
    get_settings.cache_clear()


# --- Defra bulk supply credentials (Decision 0006) ---------------------------
# Named as Defra's ticket gave them, without the FIELDCLUB_ prefix. They are
# read from the environment, then from `.env` in the working directory, then
# from `.env` at the repository root, and nothing else is read from those files.


class DefraSftpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    defra_sftp_host: str | None = None
    defra_sftp_user: str | None = None
    defra_sftp_password: SecretStr | None = None
    defra_sftp_port: int = 22
    # The pinned host key. A connection to a host whose key isn't in it is refused.
    defra_sftp_known_hosts: Path = _REPO_ROOT / "var" / "defra_known_hosts"

    @property
    def missing(self) -> list[str]:
        """The names of the credentials that aren't set."""
        values = {
            "DEFRA_SFTP_HOST": self.defra_sftp_host,
            "DEFRA_SFTP_USER": self.defra_sftp_user,
            "DEFRA_SFTP_PASSWORD": self.defra_sftp_password.get_secret_value()
            if self.defra_sftp_password
            else None,
        }
        return [name for name, value in values.items() if not value]


def get_defra_sftp_settings() -> DefraSftpSettings:
    """The Defra SFTP credentials. `FIELDCLUB_ENV_FILE=""` reads no file, as for `get_settings()`."""
    env_file = os.environ.get("FIELDCLUB_ENV_FILE")
    files: tuple[Path | str, ...] = (_REPO_ROOT / ".env", ".env") if env_file is None else (env_file,)
    return DefraSftpSettings(_env_file=tuple(f for f in files if f) or None)  # pyright: ignore[reportCallIssue]
