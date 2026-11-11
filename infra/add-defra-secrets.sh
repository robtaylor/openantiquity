#!/usr/bin/env bash
# Put Defra's bulk supply login into Secret Manager, from the untracked .env.
#
#   bash infra/add-defra-secrets.sh <project-id> [--replace]
#                                   [--env-file <path>] [--known-hosts <path>]
#
# Run from the main checkout, after the first apply has made the empty secrets
# (infra/README.md, step 4). It reads DEFRA_SFTP_HOST, DEFRA_SFTP_USER and
# DEFRA_SFTP_PASSWORD from .env at the repository root, the way the backend
# reads them, and the pinned host key from var/defra_known_hosts.
#
# Each value goes from its file straight to gcloud's standard input. None is
# printed, passed as an argument or held in a shell variable, so none reaches
# the terminal, the process list or the shell history.
#
# Safe to run again: a secret that already has a value is left alone unless
# --replace is given. It names the project on every command, so the gcloud
# configuration's own default project is never used.
set -euo pipefail

usage() {
  echo "usage: $0 <project-id> [--replace] [--env-file <path>] [--known-hosts <path>]" >&2
  exit 2
}

root=$(cd "$(dirname "$0")/.." && pwd)
env_file="$root/.env"
known_hosts="$root/var/defra_known_hosts"
replace=false
project=""

while [ $# -gt 0 ]; do
  case "$1" in
    --replace) replace=true ;;
    --env-file) [ $# -ge 2 ] || usage; env_file=$2; shift ;;
    --known-hosts) [ $# -ge 2 ] || usage; known_hosts=$2; shift ;;
    -*) usage ;;
    *) [ -z "$project" ] || usage; project=$1 ;;
  esac
  shift
done

[ -n "$project" ] || usage
if ! [[ $project =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "'$project' isn't a valid project id" >&2
  exit 2
fi

# The same prefix as var.name in infra/terraform/variables.tf.
prefix=fieldclub

# Check that a variable is set in the .env, or send its value to a secret. The
# value is read in full before gcloud is started and is handed to it on
# standard input, so a failure to read it can never leave an empty version
# behind, and the value is never an argument or a shell variable.
#   env_value <key> --check
#   env_value <key> --send <secret>
env_value() {
  uv run --quiet --project "$root/backend" python - "$env_file" "$project" "$@" <<'PYTHON'
import subprocess
import sys

from dotenv import dotenv_values

path, project, key, mode, *rest = sys.argv[1:]
value = dotenv_values(path).get(key)
if not value:
    sys.exit(f"{key} is not set in {path}")
if mode == "--send":
    command = ["gcloud", "secrets", "versions", "add", rest[0], f"--project={project}", "--data-file=-"]
    done = subprocess.run(command, input=value.encode(), stdout=subprocess.DEVNULL, check=False)
    if done.returncode != 0:
        sys.exit(f"gcloud could not add a version to {rest[0]}")
PYTHON
}

has_value() {
  # Quiet, because gcloud warns about the filter when a secret has no versions at all.
  gcloud secrets versions list "$1" --project="$project" --filter=state:ENABLED --limit=1 \
    --format="value(name)" --verbosity=error | grep -q .
}

wanted() {
  if [ "$replace" = false ] && has_value "$1"; then
    echo "$1 already has a value: left alone"
    return 1
  fi
}

# Check everything first, so a missing value stops the run before any secret changes.
if [ ! -f "$env_file" ]; then
  echo "No .env at $env_file" >&2
  exit 1
fi
if [ ! -s "$known_hosts" ]; then
  echo "No pinned host key at $known_hosts (the known-hosts file)" >&2
  exit 1
fi
for key in DEFRA_SFTP_HOST DEFRA_SFTP_USER DEFRA_SFTP_PASSWORD; do
  env_value "$key" --check
done

echo "Project: $project"

for pair in host:DEFRA_SFTP_HOST user:DEFRA_SFTP_USER password:DEFRA_SFTP_PASSWORD; do
  secret="$prefix-defra-sftp-${pair%%:*}"
  key=${pair#*:}
  if wanted "$secret"; then
    env_value "$key" --send "$secret"
    echo "$secret set from $key"
  fi
done

secret="$prefix-defra-sftp-known-hosts"
if wanted "$secret"; then
  gcloud secrets versions add "$secret" --project="$project" --data-file="$known_hosts" >/dev/null
  echo "$secret set from the pinned host key file"
fi
