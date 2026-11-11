"""`infra/add-defra-secrets.sh` moves the supply login into Secret Manager without showing it.

The script is run for real, against a stand-in `gcloud` that records what it
was called with and what it was sent on standard input.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "infra" / "add-defra-secrets.sh"

HOST = "sftp.supply.invalid"
USER = "supply-user-7"
# Characters a hand-written parser gets wrong: a hash, a dollar, quotes and spaces.
PASSWORD = "p#ss $HOME 'w' \"d\""
KNOWN_HOSTS = (
    "sftp.supply.invalid ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPinnedPinnedPinnedPinnedPinnedPinnedPinnedPin\n"
)
VALUES = (HOST, USER, PASSWORD, "PinnedPinned")

FAKE_GCLOUD = """#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_GCLOUD_LOG"]
args = sys.argv[1:]
entry = {"args": args}
if args[:3] == ["secrets", "versions", "list"]:
    if args[3] in os.environ.get("FAKE_GCLOUD_FILLED", "").split():
        print("1")
elif args[:3] == ["secrets", "versions", "add"]:
    source = next(a.split("=", 1)[1] for a in args if a.startswith("--data-file="))
    entry["sent"] = sys.stdin.read() if source == "-" else open(source).read()
    print(f"Created version [1] of the secret [{args[3]}].")
else:
    sys.exit(f"unexpected gcloud call: {args}")
with open(log, "a") as out:
    out.write(json.dumps(entry) + "\\n")
"""


@pytest.fixture
def stage(tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(FAKE_GCLOUD)
    gcloud.chmod(gcloud.stat().st_mode | stat.S_IXUSR)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DEFRA_SFTP_HOST={HOST}\nDEFRA_SFTP_USER={USER}\nDEFRA_SFTP_PASSWORD='{_quoted(PASSWORD)}'\n"
    )
    known_hosts = tmp_path / "defra_known_hosts"
    known_hosts.write_text(KNOWN_HOSTS)
    return {"bin": bin_dir, "env": env_file, "known_hosts": known_hosts, "log": tmp_path / "gcloud.jsonl"}


def _quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def run(stage: dict[str, Path], *extra: str, filled: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{stage['bin']}{os.pathsep}{os.environ['PATH']}",
        "FAKE_GCLOUD_LOG": str(stage["log"]),
        "FAKE_GCLOUD_FILLED": filled,
    }
    command = ["bash", str(SCRIPT), "fieldclub-test", "--env-file", str(stage["env"])]
    command += ["--known-hosts", str(stage["known_hosts"]), *extra]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=120, check=False)


def calls(stage: dict[str, Path]) -> list[dict[str, Any]]:
    if not stage["log"].exists():
        return []
    return [json.loads(line) for line in stage["log"].read_text().splitlines()]


def added(stage: dict[str, Path]) -> dict[str, str]:
    adds = (call for call in calls(stage) if call["args"][:3] == ["secrets", "versions", "add"])
    return {call["args"][3]: call["sent"] for call in adds}


def test_each_value_reaches_its_secret_exactly_as_the_env_file_holds_it(stage: dict[str, Path]) -> None:
    result = run(stage)

    assert result.returncode == 0, result.stderr
    assert added(stage) == {
        "fieldclub-defra-sftp-host": HOST,
        "fieldclub-defra-sftp-user": USER,
        "fieldclub-defra-sftp-password": PASSWORD,
        "fieldclub-defra-sftp-known-hosts": KNOWN_HOSTS,
    }


def test_no_value_is_printed_or_passed_as_an_argument(stage: dict[str, Path]) -> None:
    result = run(stage)

    assert result.returncode == 0, result.stderr
    shown = result.stdout + result.stderr
    arguments = " ".join(arg for call in calls(stage) for arg in call["args"])
    for value in VALUES:
        assert value not in shown
        assert value not in arguments
    # The names of the secrets are what it reports.
    assert "fieldclub-defra-sftp-password" in result.stdout


def test_every_command_names_the_project(stage: dict[str, Path]) -> None:
    run(stage)

    assert calls(stage)
    for call in calls(stage):
        assert "--project=fieldclub-test" in call["args"]


def test_a_secret_that_has_a_value_is_left_alone(stage: dict[str, Path]) -> None:
    result = run(stage, filled="fieldclub-defra-sftp-host fieldclub-defra-sftp-password")

    assert result.returncode == 0, result.stderr
    assert set(added(stage)) == {"fieldclub-defra-sftp-user", "fieldclub-defra-sftp-known-hosts"}
    assert "already has a value" in result.stdout


def test_replace_adds_a_new_version_over_an_existing_one(stage: dict[str, Path]) -> None:
    result = run(stage, "--replace", filled="fieldclub-defra-sftp-host")

    assert result.returncode == 0, result.stderr
    assert added(stage)["fieldclub-defra-sftp-host"] == HOST


def test_a_missing_value_stops_it_before_anything_is_added(stage: dict[str, Path]) -> None:
    stage["env"].write_text(f"DEFRA_SFTP_HOST={HOST}\nDEFRA_SFTP_USER={USER}\n")

    result = run(stage)

    assert result.returncode != 0
    assert "DEFRA_SFTP_PASSWORD" in result.stderr
    assert added(stage) == {}
    assert HOST not in result.stdout + result.stderr


def test_a_missing_host_key_file_stops_it_before_anything_is_added(stage: dict[str, Path]) -> None:
    stage["known_hosts"].unlink()

    result = run(stage)

    assert result.returncode != 0
    assert "known" in result.stderr.lower()
    assert added(stage) == {}
