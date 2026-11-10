# Every secret the settings need, created empty. Terraform never sees a value:
# the owner adds each one with `gcloud secrets versions add` (infra/README.md
# says where each comes from), so no secret enters the plan or the state.
#
# A secret is passed to a workload only when it is in use, because Cloud Run
# refuses to deploy a revision that names a secret with no version. So a
# sign-in provider's secret is wired once its client id is set, and so on.
# The database URL, the session key, the four defra-sftp-* secrets and every
# extra_secrets entry are always wired, so each needs a version before the
# apply with run_workloads = true (infra/README.md, step 4).

locals {
  all_workloads = ["service", "schema", "ingest", "scan-channels", "refresh-sources", "elevation-copy", "national-build"]
  db_workloads  = ["service", "schema", "ingest", "scan-channels", "refresh-sources"]
  sftp_users    = concat(["elevation-copy"], var.service_fetches_elevation ? ["service"] : [])

  apple_enabled = var.apple_client_id != "" && var.apple_team_id != "" && var.apple_key_id != ""

  # id => the variable it becomes, who gets it, and whether it is wired now.
  secrets = merge(
    {
      "database-url" = { env = "FIELDCLUB_DATABASE_URL", workloads = local.db_workloads, wired = true }
      # Every process in production refuses the development key, so every
      # workload needs one, even those that never sign anyone in.
      "secret-key"              = { env = "FIELDCLUB_SECRET_KEY", workloads = local.all_workloads, wired = true }
      "google-client-secret"    = { env = "FIELDCLUB_GOOGLE_CLIENT_SECRET", workloads = ["service"], wired = var.google_client_id != "" }
      "microsoft-client-secret" = { env = "FIELDCLUB_MICROSOFT_CLIENT_SECRET", workloads = ["service"], wired = var.microsoft_client_id != "" }
      "apple-private-key"       = { env = "FIELDCLUB_APPLE_PRIVATE_KEY", workloads = ["service"], wired = local.apple_enabled }
      "facebook-app-secret"     = { env = "FIELDCLUB_FACEBOOK_APP_SECRET", workloads = ["service"], wired = var.facebook_app_id != "" }
      "osm-client-secret"       = { env = "FIELDCLUB_OSM_CLIENT_SECRET", workloads = ["service"], wired = var.osm_client_id != "" }
      "smtp-password"           = { env = "FIELDCLUB_SMTP_PASSWORD", workloads = ["service"], wired = var.mail.host != "" && var.mail.username != "" }
      "defra-sftp-host"         = { env = "DEFRA_SFTP_HOST", workloads = local.sftp_users, wired = true }
      "defra-sftp-user"         = { env = "DEFRA_SFTP_USER", workloads = local.sftp_users, wired = true }
      "defra-sftp-password"     = { env = "DEFRA_SFTP_PASSWORD", workloads = local.sftp_users, wired = true }
    },
    { for id, extra in var.extra_secrets : id => { env = extra.env, workloads = extra.workloads, wired = true } },
  )

  # The pinned host key is a file, not a variable: it is mounted read-only.
  known_hosts_secret = "defra-sftp-known-hosts"
  known_hosts_dir    = "/secrets/defra"
  known_hosts_file   = "known_hosts"

  # workload => [{ id, env }] of the secrets it is given.
  secret_env = {
    for workload in local.all_workloads : workload => [
      for id, spec in local.secrets : { id = id, env = spec.env }
      if spec.wired && contains(spec.workloads, workload)
    ]
  }

  # (workload, secret) pairs that need an accessor binding, the host key file included.
  secret_access = merge(
    { for pair in flatten([
      for workload, items in local.secret_env : [for item in items : { workload = workload, id = item.id }]
    ]) : "${pair.workload}/${pair.id}" => pair },
    { for workload in local.sftp_users : "${workload}/${local.known_hosts_secret}" => { workload = workload, id = local.known_hosts_secret } },
  )
}

resource "google_secret_manager_secret" "managed" {
  for_each = toset(concat(keys(local.secrets), [local.known_hosts_secret]))

  secret_id = "${var.name}-${each.key}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "access" {
  for_each = local.secret_access

  secret_id = google_secret_manager_secret.managed[each.value.id].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.workload[each.value.workload].member
}
