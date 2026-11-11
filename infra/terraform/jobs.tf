# Cloud Run jobs. Every one runs the service's image with another command, as
# its own service account, and is billed only while it runs.
#
#   gcloud run jobs execute fieldclub-schema --region europe-west2 --wait
#   gcloud run jobs execute fieldclub-ingest --region europe-west2 --wait \
#       --args=run,he-nhle-scheduled-monuments
#
# fieldclub-jobs (scan-channels, refresh-sources) is the backend's console
# script for the scheduled jobs; see infra/README.md.

locals {
  # Each job says only what differs from the defaults below.
  job_specs = {
    # Builds the extensions, tables and extras. Safe to run again. The module
    # is an argument, so an execution can run another one that needs the
    # database: `--args=-m,fieldclub.terrain.cli,sources` writes the LIDAR
    # sources rows, which the elevation jobs leave out (infra/README.md).
    "schema" = {
      command = ["python"]
      args    = ["-m", "fieldclub.db"]
      timeout = "900s"
    }
    # One source per execution; the key is passed with --args. `list` is a
    # harmless default for an execution started without arguments.
    "ingest" = {
      command = ["fieldclub-ingest"]
      args    = ["list"]
      memory  = "2Gi"
      timeout = "21600s"
      # Downloads live in the cache bucket between runs, so a run can ask the
      # publisher whether a file changed instead of fetching it again.
      env   = { FIELDCLUB_VAR_DIR = "/mnt/var" }
      mount = { bucket = "cache", path = "/mnt/var/ingest", only_dir = "ingest" }
    }
    "scan-channels" = {
      command = ["fieldclub-jobs"]
      args    = ["scan-channels"]
      timeout = "1800s"
      retries = 1
    }
    # Runs every bulk source and reference loader that is due, one after
    # another, so it gets what a single ingest gets: the memory, the time and
    # the downloads kept in the cache bucket.
    "refresh-sources" = {
      command = ["fieldclub-jobs"]
      args    = ["refresh-sources"]
      memory  = "2Gi"
      timeout = "21600s"
      retries = 1
      env     = { FIELDCLUB_VAR_DIR = "/mnt/var" }
      mount   = { bucket = "cache", path = "/mnt/var/ingest", only_dir = "ingest" }
    }
    # The one-off copy of England's 5,877 tiles. Each task takes an equal share
    # by size and holds one SFTP connection; see infra/README.md.
    "elevation-copy" = {
      command     = ["python", "/app/jobs/mirror_shard.py"]
      args        = ["--concurrency", "1"]
      memory      = "2Gi"
      timeout     = var.elevation_copy.timeout
      retries     = 2
      tasks       = var.elevation_copy.tasks
      parallelism = var.elevation_copy.parallelism
      env         = local.sftp_env
    }
    # Builds the national overview in its work folder and uploads it to the
    # elevation bucket, then points national.json at it. The work folder is in
    # /tmp, which on Cloud Run is memory, and holds about 8 GB for all of
    # England (fieldclub-terrain's own help), hence 16 GiB, which needs 4 vCPU.
    "national-build" = {
      command = ["fieldclub-terrain"]
      args    = var.national_build_args
      cpu     = "4"
      memory  = "16Gi"
      timeout = "21600s"
    }
  }

  no_mount = { bucket = "", path = "", only_dir = "" }

  jobs = {
    for key, spec in local.job_specs : key => {
      command     = spec.command
      args        = try(spec.args, [])
      cpu         = try(spec.cpu, "1")
      memory      = try(spec.memory, "512Mi")
      timeout     = try(spec.timeout, "3600s")
      retries     = try(spec.retries, 0)
      tasks       = try(spec.tasks, 1)
      parallelism = try(spec.parallelism, 1)
      env         = tomap(try(spec.env, {}))
      mount       = try(spec.mount, local.no_mount)
    }
  }

  job_names = { for key, _ in local.jobs : key => "${var.name}-${key}" }
}

resource "google_cloud_run_v2_job" "job" {
  for_each = var.run_workloads ? local.jobs : {}

  name                = local.job_names[each.key]
  location            = var.region
  deletion_protection = false

  template {
    task_count  = each.value.tasks
    parallelism = each.value.parallelism

    template {
      service_account       = google_service_account.workload[each.key].email
      timeout               = each.value.timeout
      max_retries           = each.value.retries
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

      containers {
        image   = local.image
        command = each.value.command
        args    = each.value.args

        resources {
          limits = {
            cpu    = each.value.cpu
            memory = each.value.memory
          }
        }

        dynamic "env" {
          for_each = merge(local.common_env, each.value.env)
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.secret_env[each.key]
          content {
            name = env.value.env
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.managed[env.value.id].secret_id
                version = "latest"
              }
            }
          }
        }

        dynamic "volume_mounts" {
          for_each = contains(local.db_workloads, each.key) ? [1] : []
          content {
            name       = "cloudsql"
            mount_path = "/cloudsql"
          }
        }

        dynamic "volume_mounts" {
          for_each = contains(local.sftp_users, each.key) ? [1] : []
          content {
            name       = "defra-known-hosts"
            mount_path = local.known_hosts_dir
          }
        }

        dynamic "volume_mounts" {
          for_each = each.value.mount.bucket == "" ? [] : [each.value.mount]
          content {
            name       = "bucket"
            mount_path = volume_mounts.value.path
          }
        }
      }

      dynamic "volumes" {
        for_each = contains(local.db_workloads, each.key) ? [1] : []
        content {
          name = "cloudsql"
          cloud_sql_instance {
            instances = [google_sql_database_instance.main.connection_name]
          }
        }
      }

      dynamic "volumes" {
        for_each = contains(local.sftp_users, each.key) ? [1] : []
        content {
          name = "defra-known-hosts"
          secret {
            secret = google_secret_manager_secret.managed[local.known_hosts_secret].secret_id
            items {
              version = "latest"
              path    = local.known_hosts_file
              mode    = 292 # 0444
            }
          }
        }
      }

      dynamic "volumes" {
        for_each = each.value.mount.bucket == "" ? [] : [each.value.mount]
        content {
          name = "bucket"
          gcs {
            bucket        = local.buckets[volumes.value.bucket]
            read_only     = false
            mount_options = volumes.value.only_dir == "" ? [] : ["only-dir=${volumes.value.only_dir}"]
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.access,
    google_project_iam_member.sql_client,
    google_storage_bucket_iam_member.workload,
  ]
}

# --- Schedules ---------------------------------------------------------------

locals {
  schedules = merge(
    var.schedules.scan_channels == "" ? {} : {
      "scan-channels" = { job = "scan-channels", cron = var.schedules.scan_channels, args = [] }
    },
    var.schedules.refresh_sources == "" ? {} : {
      "refresh-sources" = { job = "refresh-sources", cron = var.schedules.refresh_sources, args = [] }
    },
    { for key, cron in var.ingest_schedules : "ingest-${key}" => { job = "ingest", cron = cron, args = ["run", key] } },
  )
  # Starting a job with other arguments needs a role that allows overrides.
  scheduled_jobs = { for key, s in local.schedules : s.job => length(s.args) > 0... }
}

resource "google_cloud_run_v2_job_iam_member" "scheduler" {
  for_each = var.run_workloads ? local.scheduled_jobs : {}

  name     = google_cloud_run_v2_job.job[each.key].name
  location = var.region
  role     = anytrue(each.value) ? "roles/run.jobsExecutorWithOverrides" : "roles/run.invoker"
  member   = google_service_account.scheduler.member
}

resource "google_cloud_scheduler_job" "run" {
  for_each = var.run_workloads ? local.schedules : {}

  name      = "${var.name}-${each.key}"
  region    = var.region
  schedule  = each.value.cron
  time_zone = "Europe/London"
  # A missed run waits for the next one rather than piling up.
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.job[each.value.job].name}:run"
    headers     = { "Content-Type" = "application/json" }
    body = base64encode(length(each.value.args) == 0 ? jsonencode({}) : jsonencode({
      overrides = { containerOverrides = [{ args = each.value.args }] }
    }))

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler]
}
