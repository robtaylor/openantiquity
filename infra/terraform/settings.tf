# The settings every workload runs with, as FIELDCLUB_* variables. The image
# already sets the paths (see infra/Dockerfile); these are the deployment's.
# backend/.env.example documents each one. FIELDCLUB_TERRAIN_NATIONAL is the
# national overview's folder: until the first build has written national.json
# there, zooms below 13 are drawn from the mirrored tiles' own overviews.

locals {
  common_env = {
    FIELDCLUB_ENV                       = "prod"
    FIELDCLUB_LOG_LEVEL                 = "INFO"
    FIELDCLUB_PUBLIC_URL                = local.public_url
    FIELDCLUB_CONTACT                   = var.contact
    FIELDCLUB_MIN_AGE                   = tostring(var.min_age)
    FIELDCLUB_STORAGE_BACKEND           = "gcs"
    FIELDCLUB_GCS_BUCKET                = google_storage_bucket.cache.name
    FIELDCLUB_GCS_NAMESPACE_BUCKETS     = jsonencode({ media = google_storage_bucket.photos.name })
    FIELDCLUB_TERRAIN_MIRROR            = "gs://${google_storage_bucket.elevation.name}/${local.mirror_prefix}"
    FIELDCLUB_TERRAIN_NATIONAL          = "gs://${google_storage_bucket.elevation.name}/${local.national_prefix}"
    FIELDCLUB_TERRAIN_FETCH_CONCURRENCY = "1"
    # Production refuses to start unless this is said out loud. A job serves
    # no requests, so 0 is right for it; the service overrides it.
    FIELDCLUB_TRUSTED_PROXY_HOPS = "0"
    FIELDCLUB_DB_POOL_SIZE       = "2"
    FIELDCLUB_DB_MAX_OVERFLOW    = "2"
    # Production refuses to start without it (see var.terms_url).
    FIELDCLUB_TERMS_URL = var.terms_url
  }

  terms_env = var.terms_summary == "" ? {} : { FIELDCLUB_TERMS_SUMMARY = var.terms_summary }

  sftp_env = { DEFRA_SFTP_KNOWN_HOSTS = "${local.known_hosts_dir}/${local.known_hosts_file}" }

  mail_env = var.mail.host == "" ? {} : merge(
    {
      FIELDCLUB_MAIL_BACKEND  = "smtp"
      FIELDCLUB_MAIL_FROM     = var.mail.from
      FIELDCLUB_SMTP_HOST     = var.mail.host
      FIELDCLUB_SMTP_PORT     = tostring(var.mail.port)
      FIELDCLUB_SMTP_SECURITY = var.mail.security
    },
    var.mail.username == "" ? {} : { FIELDCLUB_SMTP_USERNAME = var.mail.username },
  )

  # Client ids, only for the providers in use. A provider whose id is set
  # needs its secret too (secrets.tf wires it at the same moment).
  provider_env = merge(
    var.google_client_id == "" ? {} : { FIELDCLUB_GOOGLE_CLIENT_ID = var.google_client_id },
    var.microsoft_client_id == "" ? {} : {
      FIELDCLUB_MICROSOFT_CLIENT_ID = var.microsoft_client_id
      FIELDCLUB_MICROSOFT_TENANT    = var.microsoft_tenant
    },
    local.apple_enabled ? {
      FIELDCLUB_APPLE_CLIENT_ID = var.apple_client_id
      FIELDCLUB_APPLE_TEAM_ID   = var.apple_team_id
      FIELDCLUB_APPLE_KEY_ID    = var.apple_key_id
    } : {},
    var.facebook_app_id == "" ? {} : { FIELDCLUB_FACEBOOK_APP_ID = var.facebook_app_id },
    var.osm_client_id == "" ? {} : { FIELDCLUB_OSM_CLIENT_ID = var.osm_client_id },
  )

  service_env = merge(
    local.common_env,
    local.terms_env,
    local.provider_env,
    local.mail_env,
    var.service_fetches_elevation ? local.sftp_env : {},
    {
      # Google's front end is one proxy; the optional load balancer is a second.
      FIELDCLUB_TRUSTED_PROXY_HOPS = var.cdn.enabled ? "2" : "1"
      # Up to service_max_instances x 8 connections, well inside the tier's limit.
      FIELDCLUB_DB_POOL_SIZE    = "4"
      FIELDCLUB_DB_MAX_OVERFLOW = "4"
      # A stream ends itself, with `closed`, before Cloud Run's 600 s request
      # timeout (service.tf) cuts it off, and the browser opens the next one.
      FIELDCLUB_EVENTS_MAX_STREAM_S = "540"
      # Streams hold a request slot each, so leave an instance four slots for
      # everything else. A stream refused with too_many_streams is polled instead.
      FIELDCLUB_EVENTS_MAX_STREAMS = tostring(max(1, var.service_concurrency - 4))
      # Cloud Run kills an instance ten seconds after SIGTERM. The server ends
      # its streams at once and closes the rest after this many seconds.
      FIELDCLUB_SHUTDOWN_GRACE_S = "5"
    },
  )
}
