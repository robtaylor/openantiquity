# Copy to terraform.tfvars (ignored by git) and fill in. Every value here is a
# placeholder. Secrets never go in this file: they are added to Secret Manager
# with gcloud, as infra/README.md describes.

project_id      = "your-project-id"
billing_account = "000000-000000-000000"

# false for the first apply; true once an image is pushed and the database URL,
# session key and four defra-sftp-* secrets have values (infra/README.md, step 6).
run_workloads = false
image_tag     = "latest"

# false holds the service back: only the owner reaches it, through
# `gcloud run services proxy`. Leave it out, or true, for the open site.
# service_public = false

# Where the site is reached. Leave empty for the run.app address.
public_url = ""
contact    = "https://example.org/contact"

# The contributor terms the welcome step asks people to accept. Required
# before the workloads run (step 5).
terms_url = "https://example.org/terms"

# Sign-in providers: set an id once its secret has a value.
google_client_id = ""
osm_client_id    = ""

# The SMTP relay for the emailed link. host = "" switches it off.
mail = {
  host     = ""
  username = ""
  from     = "OpenAntiquity <signin@example.org>"
}

# currency must be the billing account's own.
budget = {
  amount   = 40
  currency = "GBP"
  emails   = []
}

# owner/name of the GitHub repository that may push images and run plans, and
# its numeric id (gh api repos/<owner>/<name> --jq .id). Set both in step 12.
github_repository    = ""
github_repository_id = ""

# service_fetches_elevation = false once the whole-country copy has finished.
