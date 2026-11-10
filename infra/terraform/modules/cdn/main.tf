# A global external Application Load Balancer with Cloud CDN in front of the
# Cloud Run service, answering on a custom domain with a Google-managed
# certificate. Plain http is redirected to https.
#
# What is cached is decided by the service's own Cache-Control headers
# (USE_ORIGIN_HEADERS). Only responses marked public are stored: terrain and
# record tiles, the hashed frontend assets, and a few public catalogues.
# Anything that depends on the viewer, such as a finding's position (Decision
# 0005), carries no public header and always reaches the service.

terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "service_name" {
  description = "The Cloud Run service to send traffic to."
  type        = string
}

variable "domain" {
  description = "The site's domain, whose A record the owner points at the address this module outputs."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.[a-z]{2,}$", var.domain))
    error_message = "Give the domain alone, such as fieldclub.example.org."
  }
}

resource "google_compute_global_address" "site" {
  name = "${var.name}-site"
}

resource "google_compute_region_network_endpoint_group" "service" {
  name                  = "${var.name}-service"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = var.service_name
  }
}

resource "google_compute_backend_service" "service" {
  name                  = "${var.name}-service"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  enable_cdn            = true

  backend {
    group = google_compute_region_network_endpoint_group.service.id
  }

  cdn_policy {
    cache_mode                   = "USE_ORIGIN_HEADERS"
    serve_while_stale            = 86400
    signed_url_cache_max_age_sec = 0

    cache_key_policy {
      include_host         = true
      include_protocol     = true
      include_query_string = true
    }
  }

  log_config {
    enable      = true
    sample_rate = 0.1
  }
}

resource "google_compute_url_map" "https" {
  name            = "${var.name}-https"
  default_service = google_compute_backend_service.service.id
}

resource "google_compute_managed_ssl_certificate" "site" {
  name = "${var.name}-site"

  managed {
    domains = [var.domain]
  }
}

resource "google_compute_target_https_proxy" "site" {
  name             = "${var.name}-https"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.site.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${var.name}-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.site.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.site.id
}

resource "google_compute_url_map" "redirect" {
  name = "${var.name}-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${var.name}-redirect"
  url_map = google_compute_url_map.redirect.id
}

# The second forwarding rule costs nothing more: the first five are one price.
resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${var.name}-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.site.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
}

output "address" {
  description = "Point the domain's A record here."
  value       = google_compute_global_address.site.address
}
