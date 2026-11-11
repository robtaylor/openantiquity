#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ruff: noqa: T201 - a command-line tool: what it prints is its output
"""Start Open Antiquity's jobs as Fly machines in the jobs app, from the web app's image.

    uv run infra/fly_jobs.py [--commit SHA | --image REF] [--dry-run] <job> ...

    sources                 write the LIDAR sources rows (fieldclub-terrain sources)
    ingest <source-key>     one ingest run (fieldclub-ingest run <source-key>)
    mirror <share> ...      shares of the elevation copy, one after another
    national                build the national overview
    run <command> ...       any other command, such as `fieldclub-jobs add-channel UC...`
    schedule                make, or bring up to date, the hourly machine that
                            runs `fieldclub-jobs due`

Each job but `schedule` is a new machine that runs one command, exits, and is
removed (`--rm`), and is never restarted (`--restart no`), so a failure is seen
in its logs and is run again by hand. `schedule` keeps one machine named `due`
that Fly starts every hour (`--schedule hourly`). Run it again after every
deploy: it moves that machine to the image of the commit deployed.

The image is `<image_repository>:<commit>`, which the web app's deploy pushes
(`fly deploy --image-label <commit>`). The commit is HEAD unless `--commit`
names another, and `--image` gives a whole reference instead. Settings come from
infra/fly/jobs.toml; the app's secrets reach every machine without being named.
`--dry-run` prints the fly command instead of running it. It asks Fly nothing,
so for `schedule` it prints the command that makes the hourly machine.

Nothing here reads a secret. The pinned host key reaches a mirror machine as a
file Fly writes from the app's secret `DEFRA_KNOWN_HOSTS_B64`
(infra/fly-secrets.sh).
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS = Path(__file__).resolve().parent / "fly" / "jobs.toml"

# The elevation copy is split into four shares (infra/README.md, "The elevation copy").
SHARES = 4
SCHEDULED_NAME = "due"
KNOWN_HOSTS_SECRET = "DEFRA_KNOWN_HOSTS_B64"
# Where the image tells the SFTP client to look (DEFRA_SFTP_KNOWN_HOSTS in infra/Dockerfile).
KNOWN_HOSTS_PATH = "/tmp/fieldclub/var/defra_known_hosts"
SOURCE_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Machine:
    """What one job machine is: its command and its size."""

    command: list[str]
    size: str = "shared-cpu-1x"
    # Megabytes, or None for the size's own.
    memory_mb: int | None = 2048
    rootfs_gb: int | None = None
    name: str | None = None
    files: dict[str, str] = field(default_factory=dict)


def sources() -> Machine:
    return Machine(["fieldclub-terrain", "sources"], memory_mb=1024, name="sources")


def ingest(key: str) -> Machine:
    if not SOURCE_KEY.fullmatch(key):
        raise SystemExit(
            f"{key!r} isn't a source key. `uv run infra/fly_jobs.py run fieldclub-ingest list` lists them."
        )
    # Ingest runs took 2 GiB on Cloud Run.
    return Machine(["fieldclub-ingest", "run", key], name=f"ingest-{key}")


def mirror(shares: Sequence[int]) -> Machine:
    if not shares or any(not 1 <= share <= SHARES for share in shares):
        raise SystemExit(f"Name the shares to run, each from 1 to {SHARES}.")
    command = ["python", "/app/jobs/mirror_shard.py", "--shares", str(SHARES)]
    for share in shares:
        command += ["--share", str(share)]
    # A tile is staged and converted on the root file system; a conversion peaked at 236 MiB.
    return Machine(
        command,
        name="mirror-" + "-".join(map(str, shares)),
        files={KNOWN_HOSTS_PATH: KNOWN_HOSTS_SECRET},
    )


def national() -> Machine:
    # The build stages about 8 GB of chunks and the COG in its work folder, on
    # the root file system here, and had 16 GiB of memory on Cloud Run.
    # performance-8x is the size Fly lists with 16 GB.
    return Machine(
        ["fieldclub-terrain", "national", "build", "--skip-sources"],
        size="performance-8x",
        memory_mb=None,
        rootfs_gb=20,
        name="national-build",
    )


def anything(command: Sequence[str]) -> Machine:
    if not command:
        raise SystemExit("Give the command to run, such as `fieldclub-jobs add-channel UC...`.")
    return Machine(list(command))


def scheduled() -> Machine:
    # The source refresh runs every due bulk source in turn, as one ingest
    # would, so it gets what an ingest gets.
    return Machine(["fieldclub-jobs", "due"], name=SCHEDULED_NAME)


@dataclass(frozen=True)
class Settings:
    app: str
    region: str
    image_repository: str
    env: dict[str, str]
    volume: str
    mount: str

    @classmethod
    def read(cls, path: Path = SETTINGS) -> Settings:
        data = tomllib.loads(path.read_text())
        env = {str(name): str(value) for name, value in data["env"].items()}
        assert all(not name.startswith("FLY_") for name in env), "Fly reserves FLY_ names"
        return cls(
            app=data["app"],
            region=data["region"],
            image_repository=data["image_repository"],
            env=env,
            volume=data["schedule"]["volume"],
            mount=data["schedule"]["mount"],
        )


def head_commit() -> str:
    found = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return found.stdout.strip()


def env_flags(env: dict[str, str]) -> list[str]:
    return [flag for name, value in env.items() for flag in ("--env", f"{name}={value}")]


def run_command(settings: Settings, image: str, machine: Machine) -> list[str]:
    """The `fly machine run` for a one-off job: removed when it exits, never restarted."""
    flags = ["--app", settings.app, "--region", settings.region, "--vm-size", machine.size]
    if machine.memory_mb is not None:
        flags += ["--vm-memory", str(machine.memory_mb)]
    if machine.rootfs_gb is not None:
        flags += ["--rootfs-size", str(machine.rootfs_gb)]
    if machine.name:
        flags += ["--name", machine.name]
    flags += ["--rm", "--restart", "no", *env_flags(settings.env)]
    for path, secret in machine.files.items():
        flags += ["--file-secret", f"{path}={secret}"]
    # `--` ends flyctl's own flags, so the job's flags are passed to the job.
    return ["fly", "machine", "run", *flags, image, "--", *machine.command]


def scheduled_env(settings: Settings) -> dict[str, str]:
    # Ingest downloads go under FIELDCLUB_VAR_DIR, here on the volume.
    return settings.env | {"FIELDCLUB_VAR_DIR": f"{settings.mount}/var"}


def schedule_commands(settings: Settings, image: str, existing: str | None) -> list[str]:
    """Make the hourly machine, or move the one there is to `image` with today's settings."""
    machine = scheduled()
    env = env_flags(scheduled_env(settings))
    if existing is None:
        flags = ["--app", settings.app, "--region", settings.region, "--vm-size", machine.size]
        flags += ["--vm-memory", str(machine.memory_mb), "--name", SCHEDULED_NAME]
        flags += [
            "--schedule",
            "hourly",
            "--restart",
            "no",
            "--volume",
            f"{settings.volume}:{settings.mount}",
        ]
        return ["fly", "machine", "run", *flags, *env, image, "--", *machine.command]
    flags = ["--app", settings.app, "--image", image, "--schedule", "hourly", "--restart", "no"]
    # Not started now: the next hour starts it.
    flags += [*env, "--skip-start", "--yes"]
    return ["fly", "machine", "update", existing, *flags]


def _field(entry: dict[str, Any], name: str) -> Any:
    return next((value for key, value in entry.items() if key.lower() == name), None)


def find_scheduled(settings: Settings) -> str | None:
    """The id of the machine named `due`, or None when there is none."""
    listed = subprocess.run(
        ["fly", "machine", "list", "--app", settings.app, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        raise SystemExit(f"fly could not list the machines of {settings.app}: {listed.stderr.strip()}")
    ids = [
        str(_field(entry, "id"))
        for entry in json.loads(listed.stdout or "[]")
        if _field(entry, "name") == SCHEDULED_NAME
    ]
    if len(ids) > 1:
        raise SystemExit(
            f"{settings.app} has {len(ids)} machines named {SCHEDULED_NAME}. Destroy all but one."
        )
    return ids[0] if ids else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fly_jobs.py", description="Start Open Antiquity's jobs on Fly.io.")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--commit", help="the commit whose image to run (default: HEAD)")
    which.add_argument("--image", help="a whole image reference instead")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the fly commands instead of running them"
    )
    jobs = parser.add_subparsers(dest="job", required=True)
    jobs.add_parser("sources", help="write the LIDAR sources rows")
    jobs.add_parser("ingest", help="one ingest run").add_argument("source_key")
    jobs.add_parser("mirror", help="shares of the elevation copy").add_argument("shares", type=int, nargs="+")
    jobs.add_parser("national", help="build the national overview")
    jobs.add_parser("run", help="any other command").add_argument("command", nargs=argparse.REMAINDER)
    jobs.add_parser("schedule", help="make or update the hourly machine")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.read()
    if args.image:
        image = args.image
    else:
        commit = args.commit or head_commit()
        if not COMMIT.fullmatch(commit):
            raise SystemExit(f"{commit!r} isn't a whole commit id. Give all 40 characters.")
        image = f"{settings.image_repository}:{commit}"
    print(f"App: {settings.app}. Image: {image}")
    if args.job == "schedule":
        existing = None if args.dry_run else find_scheduled(settings)
        command = schedule_commands(settings, image, existing)
    else:
        machine = {
            "sources": sources,
            "ingest": lambda: ingest(args.source_key),
            "mirror": lambda: mirror(args.shares),
            "national": national,
            "run": lambda: anything(args.command),
        }[args.job]()
        command = run_command(settings, image, machine)
    if args.dry_run:
        print(shlex.join(command))
        return 0
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
