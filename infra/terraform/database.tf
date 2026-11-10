# PostgreSQL 17 with PostGIS. The extensions themselves (postgis, pg_trgm,
# citext) are created by the schema job, which runs `python -m fieldclub.db`.
#
# Reachable only by the service and the jobs: the instance has a public
# address but no authorised networks, and connector_enforcement refuses any
# connection that doesn't come through the Cloud SQL connector, which checks
# the caller's IAM identity for roles/cloudsql.client. Only the workload
# service accounts in iam.tf hold that role. The database password is a second
# lock, kept in Secret Manager.
#
# A public address with no authorised networks, rather than a private one,
# avoids a VPC, Private Service Access and a VPC egress path for Cloud Run,
# none of which a single small instance needs.

resource "google_sql_database_instance" "main" {
  name                = var.name
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = var.db_deletion_protection

  settings {
    # Shared-core tiers only exist in Enterprise edition. PostgreSQL 16 and
    # later default to Enterprise Plus, which starts at about ten times the price.
    edition           = "ENTERPRISE"
    tier              = var.db_tier
    availability_type = "ZONAL"

    disk_type             = "PD_SSD"
    disk_size             = var.db_disk_gb
    disk_autoresize       = true
    disk_autoresize_limit = var.db_disk_limit_gb

    connector_enforcement = "REQUIRED"

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "02:00"
      point_in_time_recovery_enabled = false
      transaction_log_retention_days = 1

      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7
      hour         = 3
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = false
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "fieldclub" {
  name     = "fieldclub"
  instance = google_sql_database_instance.main.name
}

# The login the app uses is made by the owner with gcloud (see
# infra/README.md), so its password never passes through Terraform or its
# state. The owner writes the whole database URL into the secret below.
