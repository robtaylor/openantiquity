# The optional load balancer and CDN, off by default. infra/README.md,
# "Content delivery network", says when it is worth turning on.

module "cdn" {
  source = "./modules/cdn"
  count  = var.cdn.enabled && var.run_workloads ? 1 : 0

  name         = var.name
  region       = var.region
  service_name = google_cloud_run_v2_service.web[0].name
  domain       = var.cdn.domain

  depends_on = [google_project_service.enabled]
}
