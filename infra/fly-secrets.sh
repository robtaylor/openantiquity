#!/usr/bin/env bash
# Set an Open Antiquity app's secrets on Fly.io without showing them.
#
#   bash infra/fly-secrets.sh <web|jobs> [--session-key] [--defra] [--from <file>]
#                             [--replace] [--env-file <path>] [--known-hosts <path>]
#
#   web   the app openantiquity, the public service
#   jobs  the app openantiquity-jobs, the jobs (infra/README.md)
#
#   --session-key  FIELDCLUB_SECRET_KEY, generated here: a long random value
#   --defra        jobs only. DEFRA_SFTP_HOST, DEFRA_SFTP_USER and
#                  DEFRA_SFTP_PASSWORD from the untracked .env, and the pinned
#                  host key from var/defra_known_hosts as DEFRA_KNOWN_HOSTS_B64,
#                  which the jobs write to the path DEFRA_SFTP_KNOWN_HOSTS names
#   --from <file>  the other secrets, read from a NAME=VALUE file such as an
#                  untracked var/web-secrets.env. Only the names this script
#                  knows for the app are read; any other line is ignored
#
# Run from the main checkout, where .env and var/ are. Every value goes from its
# file, or from the generator, to `fly secrets import` on standard input. None
# is printed, passed as an argument or held in a shell variable, so none
# reaches the terminal, the process list or the shell history. The secrets are
# staged (`--stage`): the web app's take effect at its next deploy, and the jobs
# app's on each machine started afterwards.
#
# Safe to run again: a secret the app already has is left alone unless
# --replace is given. Everything is read and checked before anything is sent,
# so a missing value stops the run with nothing changed. Defra's login is
# refused for the web app, which must never hold it (Decision 0018).
set -euo pipefail

usage() {
  echo "usage: $0 <web|jobs> [--session-key] [--defra] [--from <file>] [--replace]" \
    "[--env-file <path>] [--known-hosts <path>]" >&2
  exit 2
}

root=$(cd "$(dirname "$0")/.." && pwd)
env_file="$root/.env"
known_hosts="$root/var/defra_known_hosts"
role=""
session_key=false
defra=false
from_file=""
replace=false

while [ $# -gt 0 ]; do
  case "$1" in
    --session-key) session_key=true ;;
    --defra) defra=true ;;
    --replace) replace=true ;;
    --from) [ $# -ge 2 ] || usage; from_file=$2; shift ;;
    --env-file) [ $# -ge 2 ] || usage; env_file=$2; shift ;;
    --known-hosts) [ $# -ge 2 ] || usage; known_hosts=$2; shift ;;
    -*) usage ;;
    *) [ -z "$role" ] || usage; role=$1 ;;
  esac
  shift
done

case "$role" in
  web) app=openantiquity ;;
  jobs) app=openantiquity-jobs ;;
  *) usage ;;
esac

if [ "$defra" = true ] && [ "$role" != jobs ]; then
  echo "Defra's login goes to the jobs app only: the public service must never hold it." >&2
  exit 2
fi
if [ "$session_key" = false ] && [ "$defra" = false ] && [ -z "$from_file" ]; then
  echo "Nothing to set: give --session-key, --defra or --from <file>." >&2
  exit 2
fi

echo "App: $app"

uv run --quiet --project "$root/backend" python - "$app" "$role" "$session_key" "$defra" \
  "$from_file" "$replace" "$env_file" "$known_hosts" <<'PYTHON'
import base64
import json
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

app, role, session_key, defra, from_file, replace, env_file, known_hosts = sys.argv[1:]

# What --from may set on each app. Defra's names are on neither list: they come
# only from --defra, which only the jobs app accepts.
FROM_FILE = {
    "web": (
        "FIELDCLUB_GOOGLE_CLIENT_SECRET",
        "FIELDCLUB_MICROSOFT_CLIENT_SECRET",
        "FIELDCLUB_APPLE_PRIVATE_KEY",
        "FIELDCLUB_FACEBOOK_APP_SECRET",
        "FIELDCLUB_OSM_CLIENT_SECRET",
        "FIELDCLUB_SMTP_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ),
    "jobs": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
}
DEFRA = ("DEFRA_SFTP_HOST", "DEFRA_SFTP_USER", "DEFRA_SFTP_PASSWORD")
assert role in FROM_FILE, f"unknown role {role!r}"
assert not (defra == "true" and role != "jobs"), "Defra's login is for the jobs app only"


def fail(message: str) -> None:
    sys.exit(message)


def read(path: str, names: tuple[str, ...], *, every: bool) -> dict[str, str]:
    if not Path(path).is_file():
        fail(f"No file at {path}")
    values = dotenv_values(path)
    found = {name: values[name] for name in names if values.get(name)}
    if every and (missing := [name for name in names if name not in found]):
        fail(f"{', '.join(missing)} not set in {path}")
    return found  # type: ignore[return-value]


wanted: dict[str, str] = {}
if session_key == "true":
    wanted["FIELDCLUB_SECRET_KEY"] = secrets.token_urlsafe(48)
if defra == "true":
    wanted |= read(env_file, DEFRA, every=True)
    pinned = Path(known_hosts)
    if not pinned.is_file() or not pinned.stat().st_size:
        fail(f"No pinned host key at {known_hosts} (the known-hosts file)")
    # Fly writes a file from a secret holding its contents in base64 (fly machine run --file-secret).
    wanted["DEFRA_KNOWN_HOSTS_B64"] = base64.b64encode(pinned.read_bytes()).decode("ascii")
if from_file:
    found = read(from_file, FROM_FILE[role], every=False)
    if not found:
        fail(f"{from_file} sets none of the secrets the {role} app takes: {', '.join(FROM_FILE[role])}")
    wanted |= found

# `fly secrets import` reads one NAME=VALUE a line. Its documentation says
# nothing of quoting, of values over several lines or of spaces at either end,
# so a value with any of those is refused rather than risk it arriving changed.
for name, value in wanted.items():
    if "\n" in value or "\r" in value:
        fail(f"{name} runs over several lines, which this script can't send. See infra/README.md.")
    if value != value.strip():
        fail(f"{name} starts or ends with a space, which this script can't send safely.")

if replace != "true":
    listed = subprocess.run(
        ["fly", "secrets", "list", "--app", app, "--json"], capture_output=True, text=True, check=False
    )
    if listed.returncode != 0:
        fail(f"fly could not list the secrets of {app}: {listed.stderr.strip()}")
    present = {
        str(next((v for k, v in entry.items() if k.lower() == "name"), "")) for entry in json.loads(listed.stdout or "[]")
    }
    for name in sorted(present & wanted.keys()):
        print(f"{name} is already set on {app}: left alone")
        del wanted[name]

if not wanted:
    print("Nothing to send.")
    sys.exit(0)

lines = "".join(f"{name}={value}\n" for name, value in wanted.items())
done = subprocess.run(
    ["fly", "secrets", "import", "--app", app, "--stage"],
    input=lines.encode(),
    stdout=subprocess.DEVNULL,
    check=False,
)
if done.returncode != 0:
    fail(f"fly could not set the secrets of {app}")
for name in wanted:
    print(f"{name} set on {app}")
PYTHON
