"""Settings, read from `FIELDCLUB_*` environment variables.

`backend/.env.example` documents every setting. A `.env` file in the working
directory is read when present. Set `FIELDCLUB_ENV_FILE` to another path, or to an
empty string to read no file at all (the tests do this).
"""

from __future__ import annotations

import os
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fieldclub import __version__
from fieldclub.errors import ConfigError

# A placeholder for local development. Settings refuse to load it in production.
DEV_SECRET_KEY = "dev-only-secret-change-me"
# The shortest key production accepts. It signs the sign-in flow and keys the
# hashes of addresses kept with sessions, so it must not be guessable.
SECRET_KEY_MIN_LENGTH = 32
# The fewest different characters it may have: a repeated or patterned value
# is no key, while any random one, even in hexadecimal, has more.
SECRET_KEY_MIN_DISTINCT = 10
_SECRET_KEY_NEEDED = (
    f"FIELDCLUB_SECRET_KEY must be a random value of at least {SECRET_KEY_MIN_LENGTH} characters "
    "in production, such as one from `openssl rand -base64 48`."
)


def is_weak_key(key: str) -> bool:
    """Whether a secret key is too short, the placeholder, or too plain to be random."""
    plain = key.strip()
    return (
        key == DEV_SECRET_KEY
        or len(plain) < SECRET_KEY_MIN_LENGTH
        or len(set(plain)) < SECRET_KEY_MIN_DISTINCT
    )


# The session cookie. Its `__Host-` prefix makes the browser refuse it unless it
# is Secure, for the whole site and for this host alone, so a page on another
# subdomain can't plant a session of its own. Local development over plain
# http can't set a Secure cookie, so there it goes by the bare name.
SESSION_COOKIE = "__Host-openantiquity_session"
INSECURE_SESSION_COOKIE = "openantiquity_session"
CLIENT_HEADER = "X-OpenAntiquity-Client"
CLIENT_HEADER_VALUE = "web"

# backend/src/fieldclub/config.py -> the repository root, when run from a checkout.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Cloud Run sets one of these in every container: the first for a service, the
# second for a job. Neither is ever set by hand.
_CLOUD_RUN_SERVICE = "K_SERVICE"
_CLOUD_RUN_JOB = "CLOUD_RUN_JOB"
# Fly sets both on every machine, a service's or a job's.
_FLY_MARKERS = ("FLY_APP_NAME", "FLY_MACHINE_ID")

# What an S3-compatible store needs, read by boto3 and GDAL from the
# environment. Fly sets them on an app when a Tigris bucket is attached.
S3_ENVIRONMENT = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3")
S3_SCHEME = "s3://"

# The database address Fly attaches is its connection pooler, on which LISTEN
# receives nothing and a session lock may be lost. The same cluster answers
# directly on `direct.<cluster>.flympg.net`.
_FLY_POOLED_HOST = re.compile(r"pgbouncer\.(?P<cluster>[a-z0-9-]+\.flympg\.net)", re.IGNORECASE)


def on_fly() -> bool:
    """Whether this process runs on a Fly machine."""
    return all(os.environ.get(name) for name in _FLY_MARKERS)


# Fly sets `FLY_IMAGE_REF` on a machine to the image it started from:
# `registry.fly.io/<app>:<tag>`, with `@sha256:<digest>` after it on a machine
# made from a pinned image, as the hourly one is. A web machine started by a
# deploy carries the tag alone. The deploy tags the image with the
# 40-character commit it was built from (`--image-label`, in
# `.github/workflows/deploy.yml` and `infra/fly_jobs.py`), so the commit is
# read from there and no build step has to pass it in.
_FLY_IMAGE = re.compile(r"registry\.fly\.io/[a-z0-9-]+:(?P<commit>[0-9a-f]{40})(?:@sha256:[0-9a-f]{64})?")


def commit_from_image(reference: str) -> str | None:
    """The commit in an image reference Fly gives, or None for any other form, such as a deploy's own tag."""
    found = _FLY_IMAGE.fullmatch(reference.strip())
    return found.group("commit") if found else None


# An address with one "@", a dot after it, and none of the characters that
# could add a recipient or a header to the email link (`?`, `&`, `%`, `,`,
# `;`, `<`, `>`) or white space. Whether it takes mail is the owner's to check.
_EMAIL = re.compile(r"[^@\s?&%,;<>]+@[^@\s?&%,;<>]+\.[^@\s?&%,;<>]+")


# SQLAlchemy's own pattern for a URL (`sqlalchemy.engine.url._parse_url` in
# 2.1), so the host found here is the host it connects to, whatever the
# password holds. A test checks the two agree.
_SQLALCHEMY_URL = re.compile(
    r"""
    (?P<name>[\w+]+)://
    (?:(?P<username>[^:/]*)(?::(?P<password>[^@]*))?@)?
    (?:(?:\[(?P<ipv6host>[^/?]+)\]|(?P<ipv4host>[^/:?]+))?(?::(?P<port>[^/?]*))?)?
    (?:/(?P<database>[^?]*))?
    (?:\?(?P<query>.*))?
    """,
    re.VERBOSE,
)


def database_address(url: str) -> str:
    """The URL to connect with: SQLAlchemy's psycopg driver, and Fly's direct address for its pooled one.

    Accepts what Fly attaches (`postgres://` or `postgresql://`, the pooled
    host) as well as a full SQLAlchemy URL, and changes nothing else in it.
    Plain string work, because importing SQLAlchemy here would load it into
    every command that reads a setting.
    """
    scheme, separator, _ = url.partition("://")
    backend, _, driver = scheme.lower().partition("+")
    found = _SQLALCHEMY_URL.match(url)
    if (
        found is None
        or not separator
        or backend not in ("postgres", "postgresql")
        or driver not in ("", "psycopg")
    ):
        raise ConfigError("The database address must be a postgresql:// or postgresql+psycopg:// URL.")
    if (host := found.group("ipv4host")) and (pooled := _FLY_POOLED_HOST.fullmatch(host)):
        start, end = found.span("ipv4host")
        url = f"{url[:start]}direct.{pooled.group('cluster')}{url[end:]}"
    address = "postgresql+psycopg" + url[len(scheme) :]
    rewritten = _SQLALCHEMY_URL.match(address)
    assert rewritten is not None, "a rewritten address still parses"
    assert not _FLY_POOLED_HOST.fullmatch(rewritten.group("ipv4host") or ""), (
        "the pooled address must never be the one connected to"
    )
    return address


def same_or_nested(first: str, second: str) -> bool:
    """Whether two folders, `s3://bucket/prefix` or local paths, are one folder or one inside the other."""

    def parts(location: str) -> tuple[str, ...]:
        if location.startswith(S3_SCHEME):
            return ("s3", *(part for part in location[len(S3_SCHEME) :].split("/") if part))
        return ("local", *Path(location).resolve().parts)

    a, b = parts(first), parts(second)
    shorter = min(len(a), len(b))
    return a[:shorter] == b[:shorter]


# A host name and nothing else: no scheme, port or path.
_HOST_NAME = r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$"

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
    # The site's other names, such as its `www.` name and other domains. A
    # request for one is answered 308 with the same path on `public_url`
    # (fieldclub.redirects). Any name not listed is served as it is.
    redirect_hosts: list[Annotated[str, Field(pattern=_HOST_NAME)]] = []
    frontend_dist: Path = _REPO_ROOT / "frontend" / "dist"
    trusted_proxy_hops: int = Field(default=0, ge=0)
    # A header the proxy in front sets to the visitor's address, overwriting
    # whatever the visitor sent: `Fly-Client-IP` on Fly. When set it is read
    # in place of X-Forwarded-For and `trusted_proxy_hops`.
    client_ip_header: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]+$")
    # How long `fieldclub-api` waits for open requests to finish when told to stop.
    # Whole seconds, because uvicorn takes an int.
    shutdown_grace_s: int = Field(default=5, ge=0)

    # The live event stream, GET /events/stream (see fieldclub.services.events).
    # Events a client may fall behind by before it is dropped.
    events_queue_size: int = Field(default=64, ge=1, le=10_000)
    # Streams open at once from one address, and in one process. One address
    # may hold at most a quarter of a process's streams, so a few addresses
    # can't take them all. A household or a school sharing one address and
    # opening more falls back to asking now and then, as the frontend does
    # whenever the stream is refused.
    events_max_per_address: int = Field(default=8, ge=1)
    events_max_streams: int = Field(default=1000, ge=1)
    # Seconds between keep-alive comments, and the longest one stream lasts.
    events_heartbeat_s: float = Field(default=15.0, gt=0)
    events_max_stream_s: float = Field(default=1800.0, gt=0)

    # Database. On a Fly machine, DATABASE_URL, which Fly attaches, is read
    # when this is unset (`_fly_database_url`); anywhere else it is ignored,
    # so one exported for another project never replaces the default. Either
    # is turned into the address to connect with by `database_address`.
    database_url: str = "postgresql+psycopg://fieldclub:fieldclub@localhost:54329/fieldclub"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    auto_create_schema: bool | None = None

    # Sessions and abuse limits
    # Signs the sign-in flow and keys the hashes of addresses kept with sessions.
    # Only what serves people needs it: production refuses to serve without one
    # (`signing_key`), and a job that never signs anything starts without it.
    secret_key: SecretStr | None = None
    # A session ends after this many days without use, and after
    # `session_max_days` from sign-in however much it is used.
    session_days: int = Field(default=90, ge=1)
    session_max_days: int = Field(default=365, ge=1)
    cookie_secure: bool | None = None
    ratelimit_enabled: bool = True
    # POST /auth/dev-login signs in as anyone by name. It has to be asked for,
    # and is refused outright in production.
    dev_login: bool = False

    # Contributors must be at least this old (Decision 0009). 16 admits both
    # age bands. 17 or 18 admits only 18 and over, because the 16 to 17 band
    # can't tell a 16 year old from a 17 year old.
    min_age: int = Field(default=16, ge=16, le=18)
    # The contributor terms the welcome step asks people to accept, as `/meta`
    # gives them: a short summary for the sheet, and where the full terms are.
    # The address is a path on this site or a full https address. Production
    # must set it, because the default names a page the site may not have.
    terms_summary: str = Field(
        default=(
            "You're 16 or over. What you add is public and published under CC BY 4.0, so anyone may "
            "reuse it with credit. If you leave, it stays on the map, credited to “Former member”."
        ),
        min_length=1,
        max_length=1000,
    )
    terms_url: str = Field(default="/about#terms", pattern=r"^(/[^/\\]|https://)")

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
    # `s3` is any store with the S3 interface, such as Tigris, reached with the
    # credentials and endpoint in `S3_ENVIRONMENT`.
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_prefix: str = ""
    # Namespaces kept in a bucket of their own, such as {"media": "<photos bucket>"},
    # so uploads and caches can have different lifecycles. Others use s3_bucket.
    s3_namespace_buckets: dict[str, str] = {}

    # Fly's own variable, not a FIELDCLUB_ one: Fly sets it on every machine
    # to the image the machine started from, and the commit is read from it
    # (`commit`). Unset anywhere but on Fly.
    fly_image_ref: str = Field(default="", validation_alias="FLY_IMAGE_REF")
    # Where a problem report may be emailed. Unset, the report form offers
    # GitHub and copying the text, and no email link.
    report_email: str | None = None

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
    # local folder, or `s3://bucket/prefix` in production. Relative paths are
    # resolved against the repository root, where `var/lidar` lives. Each
    # folder left unset is under `var_dir`, as in `_TERRAIN_UNDER_VAR`.
    terrain_mirror: str = ""
    # Defra's source tiles already on disk, converted instead of fetched. Empty to fetch everything.
    terrain_source_dir: str = ""
    # The national overview for zoom 12 and below, built from the mirror by
    # `fieldclub-terrain national build`: a local folder or `s3://bucket/prefix`.
    terrain_national: str = ""
    # Downloads from the bulk supply that may run at once in one process. A map
    # tile or a profile never waits for one: missing tiles are added in the
    # background on a pool of this many threads (`terrain/prefetch.py`).
    terrain_fetch_concurrency: int = Field(default=2, ge=1, le=8)
    # Whether the API adds missing tiles to the mirror at all. Off where it
    # can't (no supply login and a key that only reads the mirror, as on Fly):
    # a map tile that needs one is then answered `elevation_unavailable` for a
    # minute at a time, with a warning and no writes to the mirror's folder.
    # The commands always fetch.
    terrain_api_fetch: bool = True
    # How many of the catalogue's tiles may be missing from the mirror before
    # `fieldclub-terrain check`, which a deploy runs first, stops the deploy.
    terrain_check_allow_missing: int = Field(default=0, ge=0)
    # Terrain map tiles drawn at once in one process, on threads of their own,
    # and how many more may wait for a turn before a tile is answered 503
    # `tiles_busy` (`terrain/workers.py`). Tiles never use the thread pool the
    # rest of the API runs on.
    terrain_render_workers: int = Field(default=4, ge=1, le=32)
    terrain_render_queue: int = Field(default=64, ge=0, le=1000)
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

    @model_validator(mode="before")
    @classmethod
    def _fly_database_url(cls, data: object) -> object:
        attached = os.environ.get("DATABASE_URL")
        if isinstance(data, dict) and "database_url" not in data and attached and on_fly():
            return {**data, "database_url": attached}
        return data

    @field_validator("report_email")
    @classmethod
    def _report_email(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if not _EMAIL.fullmatch(value):
            raise ValueError("FIELDCLUB_REPORT_EMAIL must be an email address, or unset.")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_address(cls, value: str) -> str:
        return database_address(value)

    @property
    def uses_s3(self) -> bool:
        """Whether anything is kept in an S3-compatible store: the storage backend or a terrain folder."""
        return self.storage_backend == "s3" or any(
            location.startswith(S3_SCHEME) for location in (self.terrain_mirror, self.terrain_national)
        )

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
        key = self.secret_key.get_secret_value() if self.secret_key is not None else None
        if is_prod and key is not None and is_weak_key(key):
            raise ConfigError(_SECRET_KEY_NEEDED)
        if is_prod and self.cookie_secure is False:
            raise ConfigError("FIELDCLUB_COOKIE_SECURE can't be false in production: cookies must be Secure.")
        if self.events_max_per_address > max(1, self.events_max_streams // 4):
            raise ConfigError(
                "FIELDCLUB_EVENTS_MAX_PER_ADDRESS must be at most a quarter of FIELDCLUB_EVENTS_MAX_STREAMS, "
                "so that a few addresses can't hold every stream."
            )
        if self.session_days > self.session_max_days:
            raise ConfigError("FIELDCLUB_SESSION_DAYS can't be longer than FIELDCLUB_SESSION_MAX_DAYS.")
        if is_prod and self.dev_login:
            raise ConfigError(
                "FIELDCLUB_DEV_LOGIN lets anyone sign in as anyone. It can't be on in production."
            )
        if is_prod and "trusted_proxy_hops" not in self.model_fields_set and not self.client_ip_header:
            # Unset means 0, and behind a proxy that puts every signed-out
            # caller in one rate-limit bucket. Make whoever deploys say.
            raise ConfigError(
                "FIELDCLUB_TRUSTED_PROXY_HOPS or FIELDCLUB_CLIENT_IP_HEADER must be set in production: "
                "the number of reverse proxies in front of the API (1 on Cloud Run, 0 only when it is "
                "reached directly), or the header its proxy sets to the visitor's address."
            )
        if on_fly():
            # The same protections as on Cloud Run, by Fly's own variables.
            if not is_prod:
                raise ConfigError(f"FIELDCLUB_ENV is '{self.env.value}' on Fly. Set FIELDCLUB_ENV=prod.")
            if not self.client_ip_header:
                # Fly's proxy appends two entries to X-Forwarded-For, so a hop
                # count is easy to get wrong. Its own header can't be forged.
                raise ConfigError(
                    "FIELDCLUB_CLIENT_IP_HEADER must be set on Fly. Set it to Fly-Client-IP, which "
                    "Fly's proxy sets to the visitor's address."
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
        site = urlsplit(self.public_url).hostname
        if site and site in {host.lower() for host in self.redirect_hosts}:
            raise ConfigError(
                f"FIELDCLUB_REDIRECT_HOSTS names {site}, the site's own address in FIELDCLUB_PUBLIC_URL, "
                "which would redirect to itself."
            )
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ConfigError("FIELDCLUB_S3_BUCKET is required when FIELDCLUB_STORAGE_BACKEND is 's3'.")
        if self.s3_namespace_buckets and self.storage_backend != "s3":
            raise ConfigError(
                "FIELDCLUB_S3_NAMESPACE_BUCKETS only applies when FIELDCLUB_STORAGE_BACKEND is 's3'."
            )
        for name in ("terrain_mirror", "terrain_national"):
            location: str = getattr(self, name)
            if "://" in location and not location.startswith(S3_SCHEME):
                raise ConfigError(
                    f"FIELDCLUB_{name.upper()} is {location!r}. A terrain folder is a local path or "
                    f"{S3_SCHEME}bucket/prefix."
                )
        mirror, national = self.terrain_path(self.terrain_mirror), self.terrain_path(self.terrain_national)
        if mirror and national and same_or_nested(mirror, national):
            # Building the overview removes every older build file in its
            # folder, and on Fly the key that does it may write to the
            # mirror too: nothing but this keeps the two apart.
            raise ConfigError(
                f"FIELDCLUB_TERRAIN_MIRROR ({self.terrain_mirror}) and FIELDCLUB_TERRAIN_NATIONAL "
                f"({self.terrain_national}) must be separate folders, neither inside the other."
            )
        missing = [name for name in S3_ENVIRONMENT if not os.environ.get(name)]
        if self.uses_s3 and missing:
            # boto3 and GDAL read these themselves. Without them a store would
            # fail at its first read, or reach AWS instead of the one meant.
            raise ConfigError(
                f"{', '.join(missing)} must be set to use an S3 store. Fly sets them when a Tigris "
                "bucket is attached to the app."
            )
        # The log mailer writes working sign-in links to the log, so it must
        # never run where other people sign in.
        if is_prod and self.mail_backend == "log":
            raise ConfigError("FIELDCLUB_MAIL_BACKEND=log writes sign-in links to the log. Use smtp in prod.")
        if self.mail_backend == "smtp" and not (self.smtp_host and self.mail_from):
            raise ConfigError("FIELDCLUB_MAIL_BACKEND=smtp needs FIELDCLUB_SMTP_HOST and FIELDCLUB_MAIL_FROM")
        if is_prod and "terms_url" not in self.model_fields_set:
            # The welcome step asks everyone to accept what this links to.
            raise ConfigError(
                "FIELDCLUB_TERMS_URL must be set in production: the address of the contributor terms "
                "the welcome step asks people to accept."
            )
        return self

    @property
    def signing_key(self) -> bytes:
        """The secret key, or the development placeholder outside production.

        Production has no placeholder: asking for the key there without one set
        raises, and `create_app` asks at start-up, so the API never serves without it.
        """
        if self.secret_key is not None:
            return self.secret_key.get_secret_value().encode("utf-8")
        if self.env is Environment.PROD:
            raise ConfigError(_SECRET_KEY_NEEDED)
        return DEV_SECRET_KEY.encode("utf-8")

    def require_signing_key(self) -> None:
        """Raise `ConfigError` unless there is a key to sign with: always outside production."""
        self.signing_key  # noqa: B018 - reading it raises when there is none

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
    def session_cookie_name(self) -> str:
        return SESSION_COOKIE if self.session_cookie_secure else INSECURE_SESSION_COOKIE

    @property
    def should_create_schema(self) -> bool:
        """Whether the API builds the schema at start-up. On by default in development only."""
        if self.auto_create_schema is not None:
            return self.auto_create_schema
        return self.is_dev

    @property
    def commit(self) -> str | None:
        """The commit the running image was built from, or None when it can't be told."""
        return commit_from_image(self.fly_image_ref)

    @property
    def outbound_user_agent(self) -> str:
        """The `User-Agent` sent to every upstream service."""
        if self.user_agent:
            return self.user_agent
        contact = f" (+{self.contact})" if self.contact else ""
        return f"OpenAntiquity/{__version__}{contact}"


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
