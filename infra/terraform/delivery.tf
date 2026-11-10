# GitHub Actions reaches the project through workload identity federation:
# the deploy workflow trades its short-lived GitHub token for a short-lived
# Google one, so no key exists anywhere. Only workflows in the named
# repository, running on main, may use it.
#
# The deployer pushes images and runs `terraform plan`. It can't apply: a
# deploy is the owner's `terraform apply` after reading that plan.

locals {
  federate = var.github_repository != ""
  deployer_project_roles = [
    # terraform plan reads every resource here, their IAM policies included.
    "roles/viewer",
    "roles/iam.securityReviewer",
    "roles/secretmanager.viewer",
    "roles/run.viewer",
  ]
}

resource "google_service_account" "deployer" {
  count = local.federate ? 1 : 0

  account_id   = "${var.name}-deployer"
  display_name = "Field Club deploy workflow"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool" "github" {
  count = local.federate ? 1 : 0

  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count = local.federate ? 1 : 0

  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions"
  display_name                       = "GitHub Actions OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer_federation" {
  count = local.federate ? 1 : 0

  service_account_id = google_service_account.deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  count = local.federate ? 1 : 0

  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer[0].member
}

resource "google_project_iam_member" "deployer" {
  for_each = local.federate ? toset(local.deployer_project_roles) : toset([])

  project = var.project_id
  role    = each.value
  member  = google_service_account.deployer[0].member
}

# The plan has to take the state lock, which is an object in the state bucket.
resource "google_storage_bucket_iam_member" "deployer_state" {
  count = local.federate ? 1 : 0

  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectUser"
  member = google_service_account.deployer[0].member
}
