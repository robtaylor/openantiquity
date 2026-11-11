# Inputs. Only project_id and billing_account have no default. Copy
# example.tfvars to terraform.tfvars (ignored by git) and fill it in.

variable "project_id" {
  description = "The Google Cloud project to deploy into. Chosen by the owner; there is deliberately no default."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "A project id is 6 to 30 lower-case letters, digits and hyphens, starting with a letter."
  }
}

variable "billing_account" {
  description = "The billing account id (XXXXXX-XXXXXX-XXXXXX) the budget alert watches."
  type        = string
  # Kept out of plans, which the deploy workflow runs where others may read them.
  sensitive = true

  validation {
    condition     = can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account))
    error_message = "A billing account id looks like 012345-6789AB-CDEF01."
  }
}

variable "region" {
  description = "Where everything runs. London, close to the data and the people using it."
  type        = string
  default     = "europe-west2"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "fieldclub"
}

# --- Phases ------------------------------------------------------------------

variable "run_workloads" {
  description = <<-EOT
    Create the Cloud Run service, jobs and schedules. Leave false for the first
    apply, which makes the registry, buckets, database and empty secrets. Set it
    true once an image is in the registry and these secrets have values: the
    database URL, the session key, all four defra-sftp-* secrets (the elevation
    copy always uses them) and every extra_secrets entry. Cloud Run refuses to
    deploy a revision that names a secret with no version.
  EOT
  type        = bool
  default     = false
}

variable "image_tag" {
  description = "The tag of the fieldclub image in the registry to run, normally a git commit."
  type        = string
  default     = "latest"
}

# --- The service -------------------------------------------------------------

variable "public_url" {
  description = "Where people reach the site, with https and no trailing slash. Empty means the run.app address."
  type        = string
  default     = ""
}

variable "contact" {
  description = "A URL or address added to the User-Agent sent upstream, so operators can reach the owner."
  type        = string
  default     = ""
}

variable "service_cpu" {
  description = "vCPUs per service instance. See infra/README.md, Sizing."
  type        = string
  default     = "1"
}

variable "service_memory" {
  description = "Memory per service instance."
  type        = string
  default     = "1Gi"
}

variable "service_concurrency" {
  description = "Requests one instance takes at once."
  type        = number
  default     = 20
}

variable "service_max_instances" {
  description = <<-EOT
    The most instances the service may run. Caps cost and database connections:
    each instance holds up to 8, and during a deploy the old revision's
    instances still hold theirs. Each instance takes service_concurrency
    requests, and every open tab's event stream holds one. While
    service_fetches_elevation is true each instance may also open its own
    connection to Defra. See infra/README.md, Sizing.
  EOT
  type        = number
  default     = 3
}

variable "service_min_instances" {
  description = "Instances kept warm. 0 scales to zero; each warm instance is billed all month."
  type        = number
  default     = 0
}

variable "service_fetches_elevation" {
  description = <<-EOT
    Give the service Defra's SFTP credentials, so a map tile over an area the
    mirror lacks fetches its 5 km source tile (Decision 0006, point 5). Once the
    whole-country copy has finished nothing is missing and this can be false.
  EOT
  type        = bool
  default     = true
}

variable "min_age" {
  description = "The youngest contributor age, 16 to 18 (Decision 0009)."
  type        = number
  default     = 16
}

# --- Sign-in -----------------------------------------------------------------
# Client ids aren't secret, so they are plain variables. Each provider is
# offered only when its id is set here and its secret has a value.

variable "google_client_id" {
  type    = string
  default = ""
}

variable "microsoft_client_id" {
  type    = string
  default = ""
}

variable "microsoft_tenant" {
  type    = string
  default = "common"
}

variable "apple_client_id" {
  type    = string
  default = ""
}

variable "apple_team_id" {
  type    = string
  default = ""
}

variable "apple_key_id" {
  type    = string
  default = ""
}

variable "facebook_app_id" {
  type    = string
  default = ""
}

variable "osm_client_id" {
  type    = string
  default = ""
}

variable "mail" {
  description = "The SMTP relay for the emailed sign-in link. host empty switches the emailed link off."
  type = object({
    host     = string
    port     = optional(number, 587)
    username = optional(string, "")
    security = optional(string, "starttls")
    from     = optional(string, "")
  })
  default = { host = "" }
}

# --- Database ----------------------------------------------------------------

variable "db_tier" {
  description = "Cloud SQL machine type. See infra/README.md, Sizing."
  type        = string
  default     = "db-g1-small"
}

variable "db_disk_gb" {
  description = "Starting SSD size. It grows by itself and can never shrink."
  type        = number
  default     = 20
}

variable "db_disk_limit_gb" {
  description = "The most the disk may grow to by itself."
  type        = number
  default     = 100
}

variable "db_deletion_protection" {
  description = "Refuse to delete the database instance. Turn off only to tear the project down."
  type        = bool
  default     = true
}

# --- Jobs --------------------------------------------------------------------

variable "elevation_copy" {
  description = <<-EOT
    The one-off copy of England's elevation from Defra's SFTP supply into the
    bucket. tasks shares the 5,877 tiles; parallelism is how many run at once,
    which is how many connections Defra's server sees.
  EOT
  type = object({
    tasks       = optional(number, 4)
    parallelism = optional(number, 2)
    # A share should take about four hours. A stalled task gives up here.
    timeout = optional(string, "18000s")
  })
  default = {}
}

variable "national_build_args" {
  description = <<-EOT
    Arguments to fieldclub-terrain that build the national overview into the
    elevation bucket. The job is only ever started by hand. It has no database,
    so the sources rows are left to `fieldclub-terrain sources`.
  EOT
  type        = list(string)
  default     = ["national", "build", "--skip-sources"]
}

variable "schedules" {
  description = <<-EOT
    Cron schedules (Europe/London) for the recurring jobs. An empty string
    leaves a job unscheduled, which is the default: both run `fieldclub-jobs`,
    which the image doesn't have yet. Once it does, "15 */6 * * *" for the
    channel scan and "30 4 * * *" for the source refresh.
  EOT
  type = object({
    scan_channels   = optional(string, "")
    refresh_sources = optional(string, "")
  })
  default = {}
}

variable "ingest_schedules" {
  description = "Source keys to ingest on a schedule, each with a cron expression (Europe/London)."
  type        = map(string)
  default     = {}
}

variable "extra_secrets" {
  description = <<-EOT
    Further secrets created empty and passed to some workloads as environment
    variables, for connector or job keys added later. Keyed by secret id; each
    names the variable and the workloads (service, schema, ingest,
    scan-channels, refresh-sources, elevation-copy, national-build) that get it.
  EOT
  type = map(object({
    env       = string
    workloads = list(string)
  }))
  default = {}
}

# --- Delivery ----------------------------------------------------------------

variable "github_repository" {
  description = "owner/name of the GitHub repository whose deploy workflow may push images and plan. Empty makes no federation."
  type        = string
  default     = ""
}

variable "github_repository_id" {
  description = <<-EOT
    The repository's numeric id, from `gh api repos/<owner>/<name> --jq .id`.
    A name can be given up and registered again by someone else; the id can't.
    Required with github_repository.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.github_repository_id == "" || can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "A repository id is a number."
  }
}

variable "cdn" {
  description = <<-EOT
    The optional load balancer with Cloud CDN in front of the service, which
    also carries a custom domain. Off by default: it costs about $18 a month
    before any traffic. See infra/README.md, Content delivery network.
  EOT
  type = object({
    enabled = optional(bool, false)
    domain  = optional(string, "")
  })
  default = {}
}

# --- Budget ------------------------------------------------------------------

variable "budget" {
  description = "Monthly budget alert. currency must match the billing account's."
  type = object({
    amount   = optional(number, 40)
    currency = optional(string, "GBP")
    emails   = optional(list(string), [])
  })
  default = {}
}
