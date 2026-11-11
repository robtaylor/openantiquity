"""`infra/fly_jobs.py` starts each job as a Fly machine in the jobs app, from the web app's image.

The script is run for real, with the repository's own infra/fly/jobs.toml,
against a stand-in `fly` that records what it was called with.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "infra" / "fly_jobs.py"
SETTINGS = tomllib.loads((REPO_ROOT / "infra" / "fly" / "jobs.toml").read_text())
IMAGE = "registry.fly.io/openantiquity:" + "a" * 40

FAKE_FLY = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_FLY_LOG"], "a") as out:
    out.write(json.dumps(args) + "\\n")
if args[:2] == ["machine", "list"]:
    print(os.environ.get("FAKE_FLY_MACHINES", "[]"))
sys.exit(int(os.environ.get("FAKE_FLY_STATUS", "0")))
"""


@pytest.fixture
def fly(tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "fly"
    stand_in.write_text(FAKE_FLY)
    stand_in.chmod(stand_in.stat().st_mode | stat.S_IXUSR)
    return {"bin": bin_dir, "log": tmp_path / "fly.jsonl"}


def run(fly: dict[str, Path], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    environ = {
        **os.environ,
        "PATH": f"{fly['bin']}{os.pathsep}{os.environ['PATH']}",
        "FAKE_FLY_LOG": str(fly["log"]),
        **env,
    }
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(command, env=environ, capture_output=True, text=True, timeout=60, check=False)


def calls(fly: dict[str, Path]) -> list[list[str]]:
    if not fly["log"].exists():
        return []
    return [json.loads(line) for line in fly["log"].read_text().splitlines()]


def started(fly: dict[str, Path]) -> list[str]:
    """The one `fly machine run` or `update` the script made."""
    made = [call for call in calls(fly) if call[:2] in (["machine", "run"], ["machine", "update"])]
    assert len(made) == 1, made
    return made[0]


def flag(call: list[str], name: str) -> list[str]:
    """Every value given to a flag, in order."""
    return [call[i + 1] for i, arg in enumerate(call) if arg == name]


def job_command(call: list[str]) -> list[str]:
    """What the machine runs: after the image and `--`."""
    separator = call.index("--")
    assert call[separator - 1] == IMAGE
    return call[separator + 1 :]


def test_an_ingest_is_a_machine_that_runs_once_and_is_removed(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "ingest", "he-nhle-scheduled-monuments")

    assert result.returncode == 0, result.stderr
    call = started(fly)
    assert call[:2] == ["machine", "run"]
    assert flag(call, "--app") == [SETTINGS["app"]]
    assert flag(call, "--region") == ["lhr"]
    assert "--rm" in call
    assert flag(call, "--restart") == ["no"]
    assert job_command(call) == ["fieldclub-ingest", "run", "he-nhle-scheduled-monuments"]


def test_every_setting_in_the_file_is_given_and_nothing_secret(fly: dict[str, Path]) -> None:
    run(fly, "--image", IMAGE, "sources")

    given = dict(pair.split("=", 1) for pair in flag(started(fly), "--env"))
    assert given == SETTINGS["env"]
    secret_names = {"FIELDCLUB_SECRET_KEY", "DATABASE_URL", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
    assert not secret_names & given.keys()
    assert not [name for name in given if name.startswith("DEFRA_SFTP_")]


def test_mirror_shares_run_on_one_machine_with_the_pinned_host_key(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "mirror", "1", "3")

    assert result.returncode == 0, result.stderr
    call = started(fly)
    assert job_command(call) == [
        "python",
        "/app/jobs/mirror_shard.py",
        "--shares",
        "4",
        "--share",
        "1",
        "--share",
        "3",
    ]
    assert flag(call, "--file-secret") == ["/tmp/fieldclub/var/defra_known_hosts=DEFRA_KNOWN_HOSTS_B64"]
    assert flag(call, "--name") == ["mirror-1-3"]


@pytest.mark.parametrize("shares", [["0"], ["5"]])
def test_a_share_out_of_range_is_refused(fly: dict[str, Path], shares: list[str]) -> None:
    result = run(fly, "--image", IMAGE, "mirror", *shares)

    assert result.returncode != 0
    assert calls(fly) == []


def test_the_national_build_gets_16_gb_and_room_on_disk(fly: dict[str, Path]) -> None:
    run(fly, "--image", IMAGE, "national")

    call = started(fly)
    assert flag(call, "--vm-size") == ["performance-8x"]
    assert flag(call, "--vm-memory") == []
    assert flag(call, "--rootfs-size") == ["20"]
    assert job_command(call) == ["fieldclub-terrain", "national", "build", "--skip-sources"]


def test_any_other_command_keeps_its_own_flags(fly: dict[str, Path]) -> None:
    run(
        fly,
        "--image",
        IMAGE,
        "run",
        "fieldclub-jobs",
        "add-channel",
        "UCabcdefghijklmnopqrstuv",
        "--title",
        "X",
    )

    assert job_command(started(fly)) == [
        "fieldclub-jobs",
        "add-channel",
        "UCabcdefghijklmnopqrstuv",
        "--title",
        "X",
    ]


def test_a_source_key_that_is_not_one_is_refused(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "ingest", "--all; rm")

    assert result.returncode != 0
    assert calls(fly) == []


def test_schedule_makes_the_hourly_machine_with_the_volume_when_there_is_none(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "schedule")

    assert result.returncode == 0, result.stderr
    call = started(fly)
    assert call[:2] == ["machine", "run"]
    assert flag(call, "--name") == ["due"]
    assert flag(call, "--schedule") == ["hourly"]
    assert flag(call, "--restart") == ["no"]
    assert "--rm" not in call
    assert flag(call, "--volume") == [f"{SETTINGS['schedule']['volume']}:{SETTINGS['schedule']['mount']}"]
    assert f"FIELDCLUB_VAR_DIR={SETTINGS['schedule']['mount']}/var" in flag(call, "--env")
    assert job_command(call) == ["fieldclub-jobs", "due"]


def machines(*entries: dict[str, Any]) -> str:
    return json.dumps(list(entries))


def test_schedule_moves_the_machine_there_is_to_the_new_image(fly: dict[str, Path]) -> None:
    listing = machines(
        {"id": "e784079b449483", "name": "due"}, {"id": "148ed193b95e89", "name": "mirror-1-3"}
    )

    result = run(fly, "--image", IMAGE, "schedule", FAKE_FLY_MACHINES=listing)

    assert result.returncode == 0, result.stderr
    call = started(fly)
    assert call[:3] == ["machine", "update", "e784079b449483"]
    assert flag(call, "--image") == [IMAGE]
    assert flag(call, "--schedule") == ["hourly"]
    assert "--skip-start" in call
    assert "--yes" in call


def test_schedule_refuses_to_guess_between_two_hourly_machines(fly: dict[str, Path]) -> None:
    listing = machines({"ID": "e784079b449483", "Name": "due"}, {"ID": "148ed193b95e89", "Name": "due"})

    result = run(fly, "--image", IMAGE, "schedule", FAKE_FLY_MACHINES=listing)

    assert result.returncode != 0
    assert "2 machines named due" in result.stderr
    assert [call[:2] for call in calls(fly)] == [["machine", "list"]]


def test_the_image_is_the_web_app_s_image_of_head_by_default(fly: dict[str, Path]) -> None:
    head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    run(fly, "sources")

    call = started(fly)
    assert call[call.index("--") - 1] == f"{SETTINGS['image_repository']}:{head}"


def test_a_short_commit_is_refused(fly: dict[str, Path]) -> None:
    result = run(fly, "--commit", "abc1234", "sources")

    assert result.returncode != 0
    assert calls(fly) == []


def test_dry_run_prints_the_command_and_runs_nothing(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "--dry-run", "national")

    assert result.returncode == 0, result.stderr
    assert "fly machine run" in result.stdout
    assert "performance-8x" in result.stdout
    assert calls(fly) == []


def test_fly_s_exit_status_is_passed_on(fly: dict[str, Path]) -> None:
    result = run(fly, "--image", IMAGE, "sources", FAKE_FLY_STATUS="3")

    assert result.returncode == 3
