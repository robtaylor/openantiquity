# The web service: the API, the tiles and the built frontend from one image.
# Sizing is argued in infra/README.md, Sizing. In short: one vCPU, scale to
# zero, CPU billed only while a request is in flight.

resource "google_cloud_run_v2_service" "web" {
  count = var.run_workloads ? 1 : 0

  name                 = var.name
  location             = var.region
  deletion_protection  = false
  invoker_iam_disabled = true
  # Behind the optional load balancer, the run.app address is closed so that
  # every request comes through the proxy count the settings expect.
  ingress = var.cdn.enabled ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.workload["service"].email
    max_instance_request_concurrency = var.service_concurrency
    # Long enough for a slow tile that has to fetch its source first; the
    # event stream reconnects by itself when a connection reaches it.
    timeout = "600s"

    scaling {
      min_instance_count = var.service_min_instances
      max_instance_count = var.service_max_instances
    }

    containers {
      image = local.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.service_cpu
          memory = var.service_memory
        }
        # Request-based billing: CPU is charged only while a request is being
        # served, and an idle instance costs nothing until it is shut down.
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.service_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env["service"]
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

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      dynamic "volume_mounts" {
        for_each = var.service_fetches_elevation ? [1] : []
        content {
          name       = "defra-known-hosts"
          mount_path = local.known_hosts_dir
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 0
        period_seconds        = 2
        timeout_seconds       = 2
        failure_threshold     = 30
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    dynamic "volumes" {
      for_each = var.service_fetches_elevation ? [1] : []
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
  }

  depends_on = [
    google_secret_manager_secret_iam_member.access,
    google_project_iam_member.sql_client,
    google_storage_bucket_iam_member.workload,
  ]
}
