resource "google_artifact_registry_repository" "images" {
  repository_id = var.name
  location      = var.region
  format        = "DOCKER"
  description   = "Field Club container images."

  # Storage is billed per GB beyond 0.5 GB, and each image is about 280 MB
  # compressed, so keep the recent ones for rollback and drop the rest.
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"

    condition {
      older_than = "2592000s"
    }
  }

  depends_on = [google_project_service.enabled]
}
