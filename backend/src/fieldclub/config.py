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

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
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


# Where each terrain folder is when it isn't set, below `var_dir`.
_TERRAIN_UNDER_VAR = {
    "terrain_mirror": "lidar/england/mirror",
    "terrain_source_dir": "lidar/england/dtm-2022",
    "terrain_national": "lidar/england/national",
    "terrain_work_dir": "lidar/england/work",
}


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
    # How long `fieldclub-api` waits for open requests to finish when told to stop.
    # Whole seconds, because uvicorn takes an int.
    shutdown_grace_s: int = Field(default=5, ge=0)

    # The live event stream, GET /events/stream (see fieldclub.services.events).
    # Events a client may fall behind by before it is dropped.
    events_queue_size: int = Field(default=64, ge=1, le=10_000)
    # Streams open at once from one address, and in one process. Generous per
    # address, because many people can share one (mobile networks, schools):
    # the per-process cap and the rate limit on opening are what protect.
    events_max_per_address: int = Field(default=50, ge=1)
    events_max_streams: int = Field(default=1000, ge=1)
    # Seconds between keep-alive comments, and the longest one stream lasts.
    events_heartbeat_s: float = Field(default=15.0, gt=0)
    events_max_stream_s: float = Field(default=1800.0, gt=0)

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

    # Sign-in providers and the emailed link.
    # A provider is offered only when all of its settings are present. See
    # fieldclub.auth.oauth and backend/.env.example for where each comes from.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: SecretStr | None = None
    # common, organizations, consumers, or one directory's tenant id.
    microsoft_tenant: str = Field(
        default="common",
        pattern=r"^(common|organizations|consumers|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    )
    apple_client_id: str | None = None
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: SecretStr | None = None
    facebook_app_id: str | None = None
    facebook_app_secret: SecretStr | None = None
    facebook_graph_version: str = Field(default="v23.0", pattern=r"^v\d+\.\d+$")
    osm_client_id: str | None = None
    osm_client_secret: SecretStr | None = None
    osm_url: str = "https://www.openstreetmap.org"
    # Unset switches the emailed link off. `log` writes the link to the log and
    # is refused in production. `smtp` sends through the server below.
    mail_backend: Literal["log", "smtp"] | None = None
    mail_from: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"

    # Runtime data. A relative path is resolved against the repository root,
    # so storage, ingest caches and terrain agree whatever the working directory.
    var_dir: Path = Path("var")
    storage_backend: Literal["local", "gcs"] = "local"
    gcs_bucket: str | None = None
    gcs_prefix: str = ""
    # Namespaces kept in a bucket of their own, such as {"media": "<photos bucket>"},
    # so uploads and caches can have different lifecycles. Others use gcs_bucket.
    gcs_namespace_buckets: dict[str, str] = {}

    # Outbound HTTP
    contact: str = ""
    user_agent: str | None = None
    http_timeout_s: float = Field(default=20.0, gt=0)

    # Ingest
    ingest_batch_size: int = Field(default=500, ge=1, le=4000)
    # The share of a source's stored records a full run may find missing
    # before it refuses to delete them. See fieldclub.ingest.runner.
    ingest_max_shrink: float = Field(default=0.25, ge=0, le=1)

    # Terrain (Decision 0006).
    # Elevation is read only from the mirror of cloud-optimised GeoTIFFs: a
    # local folder, or `gs://bucket/prefix` in production. Relative paths are
    # resolved against the repository root, where `var/lidar` lives. Each
    # folder left unset is under `var_dir`, as in `_TERRAIN_UNDER_VAR`.
    terrain_mirror: str = ""
    # Defra's source tiles already on disk, converted instead of fetched. Empty to fetch everything.
    terrain_source_dir: str = ""
    # The national overview for zoom 12 and below, built from the mirror by
    # `fieldclub-terrain national build`: a local folder or `gs://bucket/prefix`.
    terrain_national: str = ""
    # Downloads from the bulk supply that may run at once in one process.
    terrain_fetch_concurrency: int = Field(default=2, ge=1, le=8)
    # A mirror in a bucket is filled under a lock object per tile, which its
    # holder rewrites every quarter of this. One not rewritten for this long is
    # taken to be left by a process that died. Kept below the wait.
    terrain_lock_stale_s: float = Field(default=90.0, gt=0)
    # How long a request waits for another server to finish fetching a tile.
    terrain_lock_wait_s: float = Field(default=120.0, ge=0)
    # Where downloads and conversions are staged before they enter the mirror.
    terrain_work_dir: str = ""

    def terrain_path(self, value: str) -> str:
        """A terrain location as given, or a relative local path resolved against the repository root."""
        if not value or "://" in value or Path(value).is_absolute():
            return value
        return str(_REPO_ROOT / value)

    @field_validator("var_dir")
    @classmethod
    def _var_dir_from_repo_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else _REPO_ROOT / value

    @model_validator(mode="after")
    def _terrain_under_var_dir(self) -> Self:
        """Put each terrain folder that wasn't set under `var_dir`, like every other runtime path."""
        for name, below in _TERRAIN_UNDER_VAR.items():
            if name not in self.model_fields_set:
                setattr(self, name, str(self.var_dir / below))
        return self

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
        if self.gcs_namespace_buckets and self.storage_backend != "gcs":
            raise ConfigError(
                "FIELDCLUB_GCS_NAMESPACE_BUCKETS only applies when FIELDCLUB_STORAGE_BACKEND is 'gcs'."
            )
        # The log mailer writes working sign-in links to the log, so it must
        # never run where other people sign in.
        if is_prod and self.mail_backend == "log":
            raise ConfigError("FIELDCLUB_MAIL_BACKEND=log writes sign-in links to the log. Use smtp in prod.")
        if self.mail_backend == "smtp" and not (self.smtp_host and self.mail_from):
            raise ConfigError("FIELDCLUB_MAIL_BACKEND=smtp needs FIELDCLUB_SMTP_HOST and FIELDCLUB_MAIL_FROM")
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
