"""`infra/fly-secrets.sh` sets an app's secrets on Fly without showing them.

The script is run for real, against a stand-in `fly` that records what it was
called with and what it was sent on standard input.
"""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "infra" / "fly-secrets.sh"

HOST = "sftp.supply.invalid"
# Unquoted in the file, where python-dotenv would expand `${...}`.
USER = "supply-${HOME}-user-7"
# Characters a hand-written parser gets wrong: a hash, a dollar, quotes and spaces inside.
PASSWORD = "p#ss $HOME 'w' \"d\""
KNOWN_HOSTS = (
    "sftp.supply.invalid ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPinnedPinnedPinnedPinnedPinnedPinnedPinnedPin\n"
)
# python-dotenv would expand `${...}` in an unquoted or double-quoted value.
GOOGLE = "GOCSPX-${HOME}-not-real-41"
SMTP = "smtp-${FLY_SECRETS_TEST_UNSET}-93"
TIGRIS_SECRET = "tsec_not_a_real_secret_88"
VALUES = (HOST, USER, PASSWORD, "PinnedPinned", GOOGLE, SMTP, TIGRIS_SECRET)

FAKE_FLY = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
entry = {"args": args}
if args[:2] == ["secrets", "list"]:
    names = os.environ.get("FAKE_FLY_FILLED", "").split()
    key = os.environ.get("FAKE_FLY_NAME_KEY", "Name")
    print(json.dumps([{key: name, "Digest": "d1"} for name in names]))
elif args[:2] == ["secrets", "import"]:
    entry["sent"] = sys.stdin.read()
    print("Secrets have been staged")
else:
    sys.exit(f"unexpected fly call: {args}")
with open(os.environ["FAKE_FLY_LOG"], "a") as out:
    out.write(json.dumps(entry) + "\\n")
"""


@pytest.fixture
def stage(tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fly = bin_dir / "fly"
    fly.write_text(FAKE_FLY)
    fly.chmod(fly.stat().st_mode | stat.S_IXUSR)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DEFRA_SFTP_HOST={HOST}\nDEFRA_SFTP_USER={USER}\nDEFRA_SFTP_PASSWORD='{_quoted(PASSWORD)}'\n"
        "GANDI_DNS_SSL=pat-must-never-be-sent\n"
    )
    known_hosts = tmp_path / "defra_known_hosts"
    known_hosts.write_text(KNOWN_HOSTS)
    others = tmp_path / "web-secrets.env"
    others.write_text(
        f'FIELDCLUB_GOOGLE_CLIENT_SECRET={GOOGLE}\nFIELDCLUB_SMTP_PASSWORD="{SMTP}"\n'
        f"AWS_SECRET_ACCESS_KEY={TIGRIS_SECRET}\nAWS_ACCESS_KEY_ID=tid_web\n"
        f"DEFRA_SFTP_PASSWORD=smuggled\nGANDI_DNS_SSL=pat-must-never-be-sent\n"
    )
    return {
        "bin": bin_dir,
        "env": env_file,
        "known_hosts": known_hosts,
        "others": others,
        "log": tmp_path / "fly.jsonl",
    }


def _quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def run(stage: dict[str, Path], role: str, *extra: str, filled: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{stage['bin']}{os.pathsep}{os.environ['PATH']}",
        "FAKE_FLY_LOG": str(stage["log"]),
        "FAKE_FLY_FILLED": filled,
    }
    command = ["bash", str(SCRIPT), role, "--env-file", str(stage["env"])]
    command += ["--known-hosts", str(stage["known_hosts"]), *extra]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=120, check=False)


def calls(stage: dict[str, Path]) -> list[dict[str, Any]]:
    if not stage["log"].exists():
        return []
    return [json.loads(line) for line in stage["log"].read_text().splitlines()]


def sent(stage: dict[str, Path]) -> dict[str, str]:
    """NAME=VALUE pairs sent to `fly secrets import`, split as flyctl would: at the first '='."""
    imports = [call for call in calls(stage) if call["args"][:2] == ["secrets", "import"]]
    pairs: dict[str, str] = {}
    for call in imports:
        for line in call["sent"].splitlines():
            name, _, value = line.partition("=")
            pairs[name] = value
    return pairs


def test_defra_s_login_and_host_key_reach_the_jobs_app_exactly(stage: dict[str, Path]) -> None:
    result = run(stage, "jobs", "--defra")

    assert result.returncode == 0, result.stderr
    assert sent(stage) == {
        "DEFRA_SFTP_HOST": HOST,
        "DEFRA_SFTP_USER": USER,
        "DEFRA_SFTP_PASSWORD": PASSWORD,
        "DEFRA_KNOWN_HOSTS_B64": base64.b64encode(KNOWN_HOSTS.encode()).decode(),
    }
    imports = [call["args"] for call in calls(stage) if call["args"][:2] == ["secrets", "import"]]
    assert imports == [["secrets", "import", "--app", "openantiquity-jobs", "--stage"]]


def test_defra_s_login_is_refused_for_the_web_app(stage: dict[str, Path]) -> None:
    result = run(stage, "web", "--defra")

    assert result.returncode == 2
    assert "jobs app only" in result.stderr
    assert calls(stage) == []


def test_the_other_secrets_are_read_from_a_file_and_only_the_names_known_for_the_app(
    stage: dict[str, Path],
) -> None:
    result = run(stage, "web", "--from", str(stage["others"]))

    assert result.returncode == 0, result.stderr
    assert sent(stage) == {
        "FIELDCLUB_GOOGLE_CLIENT_SECRET": GOOGLE,
        "FIELDCLUB_SMTP_PASSWORD": SMTP,
        "AWS_SECRET_ACCESS_KEY": TIGRIS_SECRET,
        "AWS_ACCESS_KEY_ID": "tid_web",
    }


def test_the_jobs_app_takes_only_its_storage_key_from_a_file(stage: dict[str, Path]) -> None:
    result = run(stage, "jobs", "--from", str(stage["others"]))

    assert result.returncode == 0, result.stderr
    assert set(sent(stage)) == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}


def test_a_session_key_is_generated_long_and_different_each_time(stage: dict[str, Path]) -> None:
    assert run(stage, "web", "--session-key").returncode == 0
    first = sent(stage)["FIELDCLUB_SECRET_KEY"]
    stage["log"].unlink()
    assert run(stage, "jobs", "--session-key").returncode == 0
    second = sent(stage)["FIELDCLUB_SECRET_KEY"]

    assert len(first) >= 64
    assert first != second


def test_no_value_is_printed_or_passed_as_an_argument(stage: dict[str, Path]) -> None:
    results = [
        run(stage, "jobs", "--defra", "--session-key"),
        run(stage, "web", "--from", str(stage["others"]), "--session-key", "--replace"),
    ]

    shown = "".join(result.stdout + result.stderr for result in results)
    arguments = " ".join(arg for call in calls(stage) for arg in call["args"])
    generated = [value for name, value in sent(stage).items() if name == "FIELDCLUB_SECRET_KEY"]
    for value in (*VALUES, *generated):
        assert value not in shown
        assert value not in arguments
    assert "pat-must-never-be-sent" not in json.dumps(calls(stage))
    # The names are what it reports.
    assert "DEFRA_SFTP_PASSWORD set on openantiquity-jobs" in shown


def test_a_secret_the_app_has_is_left_alone(stage: dict[str, Path]) -> None:
    result = run(stage, "jobs", "--defra", filled="DEFRA_SFTP_HOST DEFRA_SFTP_PASSWORD")

    assert result.returncode == 0, result.stderr
    assert set(sent(stage)) == {"DEFRA_SFTP_USER", "DEFRA_KNOWN_HOSTS_B64"}
    assert "DEFRA_SFTP_HOST is already set on openantiquity-jobs: left alone" in result.stdout


def test_the_listing_is_read_whichever_case_flyctl_gives_its_field_names(
    stage: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_FLY_NAME_KEY", "name")

    result = run(stage, "jobs", "--defra", filled="DEFRA_SFTP_HOST")

    assert result.returncode == 0, result.stderr
    assert "DEFRA_SFTP_HOST" not in sent(stage)


def test_replace_sends_it_again_without_asking_what_is_there(stage: dict[str, Path]) -> None:
    result = run(stage, "jobs", "--defra", "--replace", filled="DEFRA_SFTP_HOST")

    assert result.returncode == 0, result.stderr
    assert sent(stage)["DEFRA_SFTP_HOST"] == HOST
    assert not [call for call in calls(stage) if call["args"][:2] == ["secrets", "list"]]


def test_nothing_is_sent_when_every_secret_is_there(stage: dict[str, Path]) -> None:
    result = run(stage, "web", "--session-key", filled="FIELDCLUB_SECRET_KEY")

    assert result.returncode == 0, result.stderr
    assert sent(stage) == {}


def test_a_missing_value_stops_it_before_anything_is_sent(stage: dict[str, Path]) -> None:
    stage["env"].write_text(f"DEFRA_SFTP_HOST={HOST}\nDEFRA_SFTP_USER={USER}\n")

    result = run(stage, "jobs", "--defra", "--session-key")

    assert result.returncode != 0
    assert "DEFRA_SFTP_PASSWORD" in result.stderr
    assert sent(stage) == {}
    assert HOST not in result.stdout + result.stderr


def test_a_missing_host_key_file_stops_it_before_anything_is_sent(stage: dict[str, Path]) -> None:
    stage["known_hosts"].unlink()

    result = run(stage, "jobs", "--defra")

    assert result.returncode != 0
    assert "known-hosts" in result.stderr
    assert sent(stage) == {}


@pytest.mark.parametrize("value", ["'-----BEGIN KEY-----\nabc\n-----END KEY-----'", "' padded '"])
def test_a_value_that_import_might_change_is_refused(stage: dict[str, Path], value: str) -> None:
    stage["others"].write_text(
        f"FIELDCLUB_GOOGLE_CLIENT_SECRET={GOOGLE}\nFIELDCLUB_APPLE_PRIVATE_KEY={value}\n"
    )

    result = run(stage, "web", "--from", str(stage["others"]))

    assert result.returncode != 0
    assert "FIELDCLUB_APPLE_PRIVATE_KEY" in result.stderr
    assert sent(stage) == {}


def test_a_file_with_none_of_the_app_s_names_is_refused(stage: dict[str, Path]) -> None:
    stage["others"].write_text("DEFRA_SFTP_PASSWORD=smuggled\n")

    result = run(stage, "web", "--from", str(stage["others"]))

    assert result.returncode != 0
    assert sent(stage) == {}


@pytest.mark.parametrize("argv", [[], ["staging"], ["web"], ["web", "jobs", "--session-key"]])
def test_bad_arguments_are_refused(stage: dict[str, Path], argv: list[str]) -> None:
    command = ["bash", str(SCRIPT), *argv]
    env = {
        **os.environ,
        "PATH": f"{stage['bin']}{os.pathsep}{os.environ['PATH']}",
        "FAKE_FLY_LOG": str(stage["log"]),
    }

    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60, check=False)

    assert result.returncode == 2
    assert calls(stage) == []
