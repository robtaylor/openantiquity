terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.10"
    }
  }

  # State lives in a bucket made by infra/bootstrap.sh. The bucket is given at
  # init time, because it is named after the project:
  #   terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "fieldclub"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # The budget API is called on behalf of this project, not the caller's
  # default one, so the owner's own gcloud configuration never matters.
  user_project_override = true
  billing_project       = var.project_id

  default_labels = {
    app        = "fieldclub"
    managed-by = "terraform"
  }
}
