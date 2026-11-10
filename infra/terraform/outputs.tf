output "image_repository" {
  description = "Push images here, tagged with the git commit."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/fieldclub"
}

output "service_url" {
  description = "The run.app address of the service."
  value       = var.run_workloads ? google_cloud_run_v2_service.web[0].uri : null
}

output "public_url" {
  description = "The address the app builds its links and sign-in redirects from."
  value       = local.public_url
}

output "site_address" {
  description = "With the CDN on, point the domain's A record at this address."
  value       = length(module.cdn) > 0 ? module.cdn[0].address : null
}

output "sql_connection_name" {
  description = "For the database URL: postgresql+psycopg://fieldclub:PASSWORD@/fieldclub?host=/cloudsql/<this>"
  value       = google_sql_database_instance.main.connection_name
}

output "buckets" {
  value = local.buckets
}

output "secrets" {
  description = "The secrets to fill, by id."
  value       = sort([for secret in google_secret_manager_secret.managed : secret.secret_id])
}

output "workload_identity_provider" {
  description = "For the deploy workflow's GCP_WORKLOAD_IDENTITY_PROVIDER variable."
  value       = local.federate ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "deployer_service_account" {
  description = "For the deploy workflow's GCP_DEPLOYER_SERVICE_ACCOUNT variable."
  value       = local.federate ? google_service_account.deployer[0].email : null
}
