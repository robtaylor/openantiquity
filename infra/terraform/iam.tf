# One service account per workload, each with only what that workload uses.
# None has a key: Cloud Run lends each its identity, and GitHub reaches the
# deployer through workload identity federation (delivery.tf).

locals {
  workload_titles = {
    "service"         = "Open Antiquity web service"
    "schema"          = "Open Antiquity schema creation"
    "ingest"          = "Open Antiquity record ingest"
    "scan-channels"   = "Open Antiquity channel scan"
    "refresh-sources" = "Open Antiquity source refresh"
    "elevation-copy"  = "Open Antiquity elevation copy"
    "national-build"  = "Open Antiquity national overview"
  }

  # Bucket roles by workload. objectUser reads, writes, replaces, deletes and
  # lists objects; objectViewer only reads and lists; objectCreator only adds
  # objects that don't exist yet. Nothing may delete or replace a mirror file:
  # the mirror's writers get objectViewer plus objectCreator, and objectUser
  # only on the mirror's `locks/` and `failed/` folders, where a tile's lock is
  # rewritten while held and removed after, and a failure record is cleared
  # once the tile is in. The national build may change only the national
  # overview's folder, where it keeps its builds, national.json and its lock.
  bucket_access = merge(
    {
      "service/cache"                = { workload = "service", bucket = "cache", role = "roles/storage.objectUser" }
      "service/photos"               = { workload = "service", bucket = "photos", role = "roles/storage.objectUser" }
      "ingest/cache"                 = { workload = "ingest", bucket = "cache", role = "roles/storage.objectUser" }
      "refresh-sources/cache"        = { workload = "refresh-sources", bucket = "cache", role = "roles/storage.objectUser" }
      "service/elev-read"            = { workload = "service", bucket = "elevation", role = "roles/storage.objectViewer" }
      "elevation-copy/elev-read"     = { workload = "elevation-copy", bucket = "elevation", role = "roles/storage.objectViewer" }
      "elevation-copy/elev-add"      = { workload = "elevation-copy", bucket = "elevation", role = "roles/storage.objectCreator" }
      "elevation-copy/elev-locks"    = { workload = "elevation-copy", bucket = "elevation", role = "roles/storage.objectUser", only = "${local.mirror_prefix}/locks/" }
      "elevation-copy/elev-failed"   = { workload = "elevation-copy", bucket = "elevation", role = "roles/storage.objectUser", only = "${local.mirror_prefix}/failed/" }
      "national-build/elev-read"     = { workload = "national-build", bucket = "elevation", role = "roles/storage.objectViewer" }
      "national-build/elev-national" = { workload = "national-build", bucket = "elevation", role = "roles/storage.objectUser", only = "${local.national_prefix}/" }
    },
    # The service adds to the mirror only while it may fetch a missing tile.
    var.service_fetches_elevation ? {
      "service/elev-add"    = { workload = "service", bucket = "elevation", role = "roles/storage.objectCreator" }
      "service/elev-locks"  = { workload = "service", bucket = "elevation", role = "roles/storage.objectUser", only = "${local.mirror_prefix}/locks/" }
      "service/elev-failed" = { workload = "service", bucket = "elevation", role = "roles/storage.objectUser", only = "${local.mirror_prefix}/failed/" }
    } : {},
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

  # A grant limited to the objects whose names start with `only`.
  dynamic "condition" {
    for_each = try(each.value.only, "") == "" ? [] : [each.value.only]
    content {
      title      = "only ${condition.value}"
      expression = "resource.name.startsWith(\"projects/_/buckets/${local.buckets[each.value.bucket]}/objects/${condition.value}\")"
    }
  }
}

# Cloud Scheduler starts the recurring jobs as this account, which may only
# run those jobs (jobs.tf grants roles/run.invoker on each).
resource "google_service_account" "scheduler" {
  account_id   = "${var.name}-scheduler"
  display_name = "Open Antiquity scheduler"

  depends_on = [google_project_service.enabled]
}
