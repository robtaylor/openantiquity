data "google_project" "this" {
  project_id = var.project_id
}

locals {
  # Compute Engine is only needed for the optional load balancer. Turning it on
  # also makes a default network and a default service account with Editor,
  # so it stays off otherwise.
  services = toset(concat(var.cdn.enabled ? ["compute.googleapis.com"] : [], [
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]))

  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/fieldclub:${var.image_tag}"

  # Cloud Run's address is fixed by the service name and project number, so
  # it is known before the service exists.
  run_app_url = "https://${var.name}-${data.google_project.this.number}.${var.region}.run.app"
  public_url  = var.public_url != "" ? var.public_url : (var.cdn.enabled ? "https://${var.cdn.domain}" : local.run_app_url)

  # Where the elevation lives inside its bucket. The national overview is a
  # folder: one file per build and `national.json` naming the current one.
  mirror_prefix   = "england/mirror"
  national_prefix = "england/national"
}

resource "google_project_service" "enabled" {
  for_each = local.services

  service            = each.value
  disable_on_destroy = false
}
