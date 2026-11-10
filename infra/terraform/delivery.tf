# GitHub Actions reaches the project through workload identity federation:
# the deploy workflow trades its short-lived GitHub token for a short-lived
# Google one, so no key exists anywhere. Only deploy.yml, started by
# hand on main in the repository with the given id, may use it.
#
# The deployer pushes images and runs `terraform plan`. It can't apply: a
# deploy is the owner's `terraform apply` after reading that plan.

locals {
  federate = var.github_repository != ""
  # The one workflow allowed to deploy, as GitHub names it in its token.
  deploy_workflow = "${var.github_repository}/.github/workflows/deploy.yml@refs/heads/main"
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
  # The id as well as the name, because a name can be registered again by
  # someone else. The workflow and the event as well as the branch, because
  # other workflows on main, such as one started by pull_request_target, run
  # with the same ref.
  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository == '${var.github_repository}'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.job_workflow_ref == '${local.deploy_workflow}'",
    "assertion.event_name == 'workflow_dispatch'",
  ])

  lifecycle {
    precondition {
      condition     = var.github_repository_id != ""
      error_message = "Set github_repository_id with github_repository."
    }
  }

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

# The plan only reads the state: the workflow runs it with -lock=false, so the
# deployer needs no write access to the state bucket.
resource "google_storage_bucket_iam_member" "deployer_state" {
  count = local.federate ? 1 : 0

  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectViewer"
  member = google_service_account.deployer[0].member
}
