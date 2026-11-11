#!/usr/bin/env bash
# Make the bucket that holds Terraform's state for an Open Antiquity project.
#
#   bash infra/bootstrap.sh <project-id> [region]
#
# Run once by the owner, after the project exists and has billing. Safe to run
# again: each step checks first and changes nothing that is already right.
# It names the project on every command, so the gcloud configuration's own
# default project is never used.
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "usage: $0 <project-id> [region]" >&2
  exit 2
fi

project=$1
# The same default as var.region in infra/terraform/variables.tf.
region=${2:-europe-west2}
bucket="${project}-tfstate"

if ! [[ $project =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "'$project' isn't a valid project id" >&2
  exit 2
fi

echo "Project: $project"
gcloud projects describe "$project" --format="value(projectId)" >/dev/null

billing=$(gcloud billing projects describe "$project" --format="value(billingEnabled)")
if [ "$billing" != "True" ]; then
  echo "Billing isn't enabled on $project. Link a billing account first." >&2
  exit 1
fi

# The APIs Terraform needs before it can enable the rest itself.
gcloud services enable --project="$project" \
  cloudresourcemanager.googleapis.com serviceusage.googleapis.com storage.googleapis.com

if gcloud storage buckets describe "gs://$bucket" --project="$project" >/dev/null 2>&1; then
  echo "State bucket gs://$bucket already exists"
else
  gcloud storage buckets create "gs://$bucket" --project="$project" --location="$region" \
    --uniform-bucket-level-access --public-access-prevention
  echo "Created gs://$bucket"
fi

# Versioning keeps every earlier state, so a bad apply can be undone by hand.
gcloud storage buckets update "gs://$bucket" --project="$project" --versioning >/dev/null
echo "Versioning is on for gs://$bucket"

cat <<EOF

Next, from infra/terraform:
  terraform init -backend-config="bucket=$bucket"
  terraform apply -var-file=terraform.tfvars
EOF
