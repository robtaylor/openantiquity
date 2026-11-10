# One service account per workload, each with only what that workload uses.
# None has a key: Cloud Run lends each its identity, and GitHub reaches the
# deployer through workload identity federation (delivery.tf).

locals {
  workload_titles = {
    "service"         = "Field Club web service"
    "schema"          = "Field Club schema creation"
    "ingest"          = "Field Club record ingest"
    "scan-channels"   = "Field Club channel scan"
    "refresh-sources" = "Field Club source refresh"
    "elevation-copy"  = "Field Club elevation copy"
    "national-build"  = "Field Club national overview"
  }

  # Bucket roles by workload. objectUser reads, writes and lists objects;
  # objectViewer only reads and lists.
  bucket_access = merge(
    {
      "service/cache"       = { workload = "service", bucket = "cache", role = "roles/storage.objectUser" }
      "service/photos"      = { workload = "service", bucket = "photos", role = "roles/storage.objectUser" }
      "ingest/cache"        = { workload = "ingest", bucket = "cache", role = "roles/storage.objectUser" }
      "elevation-copy/elev" = { workload = "elevation-copy", bucket = "elevation", role = "roles/storage.objectUser" }
      "national-build/elev" = { workload = "national-build", bucket = "elevation", role = "roles/storage.objectUser" }
    },
    # The service writes to the mirror only when it may fetch a missing tile.
    { "service/elev" = {
      workload = "service", bucket = "elevation",
      role     = var.service_fetches_elevation ? "roles/storage.objectUser" : "roles/storage.objectViewer"
    } },
  )
  buckets = {
    elevation = google_storage_bucket.elevation.name
    cache     = google_storage_bucket.cache.name
    photos    = google_storage_bucket.photos.name
  }
}

resource "google_service_account" "workload" {
  for_each = local.workload_titles

  account_id   = "${var.name}-${each.key}"
  display_name = each.value

  depends_on = [google_project_service.enabled]
}

# The Cloud SQL connector checks this before it opens a connection.
resource "google_project_iam_member" "sql_client" {
  for_each = toset(local.db_workloads)

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.workload[each.value].member
}

resource "google_storage_bucket_iam_member" "workload" {
  for_each = local.bucket_access

  bucket = local.buckets[each.value.bucket]
  role   = each.value.role
  member = google_service_account.workload[each.value.workload].member
}

# Cloud Scheduler starts the recurring jobs as this account, which may only
# run those jobs (jobs.tf grants roles/run.invoker on each).
resource "google_service_account" "scheduler" {
  account_id   = "${var.name}-scheduler"
  display_name = "Field Club scheduler"

  depends_on = [google_project_service.enabled]
}
