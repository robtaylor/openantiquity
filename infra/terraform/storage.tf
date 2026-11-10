# Three private buckets. Nothing in them is public: the service reads and
# writes them with its own identity and sends the bytes itself.

# The elevation mirror: one cloud-optimised GeoTIFF per 5 km tile, about half
# the 354 GB of Defra's source files, and later the national overview.
resource "google_storage_bucket" "elevation" {
  name                        = "${var.project_id}-elevation"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # About 177 GB and eight hours of copying from a supply Defra may not keep
  # offering, so the mirror is guarded three ways. Terraform refuses to
  # destroy the bucket. No workload may delete or replace a mirror file
  # (iam.tf). And the default soft delete keeps anything deleted by hand for
  # seven days. It costs nothing until something is deleted, and mirror files
  # never are.
  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.enabled]
}

# Rendered tiles, cached elevation windows and ingest downloads. All of it can
# be made again, so old objects are deleted rather than kept for ever.
resource "google_storage_bucket" "cache" {
  name                        = "${var.project_id}-cache"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  # A tile's key carries its style and data version, so after a style change
  # the old tiles are never asked for again. Half a year without being
  # rewritten is a fair sign of that, and a tile still wanted is rendered
  # again in about 0.2 s.
  lifecycle_rule {
    condition {
      age            = 180
      matches_prefix = ["tiles/"]
    }
    action {
      type = "Delete"
    }
  }

  # Ingest downloads are kept between runs so a monthly run can ask the
  # publisher whether anything changed, then dropped.
  lifecycle_rule {
    condition {
      age            = 90
      matches_prefix = ["ingest/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "AbortIncompleteMultipartUpload"
    }
  }

  depends_on = [google_project_service.enabled]
}

# Photos members upload. These are contributions, so they keep Cloud Storage's
# default soft delete (seven days) and have no lifecycle rule.
resource "google_storage_bucket" "photos" {
  name                        = "${var.project_id}-photos"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  depends_on = [google_project_service.enabled]
}
