"""`infra/refresh_issue.py` keeps one GitHub issue open while the nightly refresh is behind.

The script is run for real, against a stand-in site on this machine that
answers as `GET /api/v1/sources/refresh-state` does, and a stand-in `gh` that
records what it was called with and what it was sent on standard input.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from fieldclub.services.refresh import REFRESH_HOUR_UTC, REFRESH_OVER_AFTER

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "infra" / "refresh_issue.py"
LABEL = "refresh-failed"

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
sent = sys.stdin.read() if "--body-file" in args else None
with open(os.environ["FAKE_GH_LOG"], "a") as out:
    out.write(json.dumps({"args": args, "sent": sent}) + "\\n")
if args[:2] == ["issue", "list"]:
    print(os.environ.get("FAKE_GH_OPEN", "[]"))
if args[:2] == ["issue", "create"]:
    print("https://github.com/example/site/issues/7")
if " ".join(args[:2]) == os.environ.get("FAKE_GH_FAIL"):
    sys.exit(1)
"""

CURRENT = {
    "source_key": "a-source",
    "state": "current",
    "last_success_at": "2026-11-27T04:00:00Z",
    "last_run_at": "2026-11-27T04:00:00Z",
    "error": None,
}
NOT_LOADED = {
    "source_key": "unset-source",
    "state": "not_loaded",
    "last_success_at": None,
    "last_run_at": None,
    "error": None,
}
FAILED = {
    "source_key": "big-source",
    "state": "failed",
    "last_success_at": "2026-11-13T05:10:00Z",
    "last_run_at": "2026-11-27T03:42:00Z",
    "error": "DiskFullError",
}
OVERDUE = {
    "source_key": "late-source",
    "state": "overdue",
    "last_success_at": "2026-11-20T04:00:00Z",
    "last_run_at": "2026-11-20T04:00:00Z",
    "error": None,
}
# Last night's refresh, as the site gives it when it finished and when it didn't.
RAN = {
    "state": "current",
    "expected_at": "2026-11-27T03:00:00Z",
    "started_at": "2026-11-27T03:41:00Z",
    "finished_at": "2026-11-27T05:52:00Z",
}
STOPPED = {**RAN, "state": "overdue", "finished_at": None}
NOT_STARTED = {
    **RAN,
    "state": "overdue",
    "started_at": "2026-11-26T03:41:00Z",
    "finished_at": "2026-11-26T05:52:00Z",
}


def report(*sources: dict[str, Any], refresh: dict[str, Any] = RAN) -> dict[str, Any]:
    return {"refresh": refresh, "sources": list(sources)}


class Site:
    """What the stand-in site answers, and how often it was asked."""

    def __init__(self) -> None:
        self.status = 200
        self.body: Any = report(CURRENT)
        self.asked = 0
        self.agents: list[str] = []
        self.url = ""


@pytest.fixture
def site() -> Iterator[Site]:
    answer = Site()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            answer.asked += 1
            answer.agents.append(self.headers.get("User-Agent", ""))
            body = answer.body if isinstance(answer.body, bytes) else json.dumps(answer.body).encode()
            self.send_response(answer.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Say nothing: the default writes every request to the test's output."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    answer.url = f"http://127.0.0.1:{server.server_address[1]}/api/v1/sources/refresh-state"
    yield answer
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def stand_in_gh(folder: Path) -> dict[str, Path]:
    """A `gh` of our own in `folder`, and where it writes what it was called with."""
    bin_dir = folder / "bin"
    bin_dir.mkdir(parents=True)
    stand_in = bin_dir / "gh"
    stand_in.write_text(FAKE_GH)
    stand_in.chmod(stand_in.stat().st_mode | stat.S_IXUSR)
    return {"bin": bin_dir, "log": folder / "gh.jsonl"}


@pytest.fixture
def gh(tmp_path: Path) -> dict[str, Path]:
    return stand_in_gh(tmp_path)


def run(site: Site, gh: dict[str, Path], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    environ = {
        **os.environ,
        "PATH": f"{gh['bin']}{os.pathsep}{os.environ['PATH']}",
        "FAKE_GH_LOG": str(gh["log"]),
        **env,
    }
    command = [sys.executable, str(SCRIPT), "--url", site.url, "--attempts", "2", "--wait", "0", *args]
    return subprocess.run(command, env=environ, capture_output=True, text=True, timeout=60, check=False)


def calls(gh: dict[str, Path]) -> list[dict[str, Any]]:
    if not gh["log"].exists():
        return []
    return [json.loads(line) for line in gh["log"].read_text().splitlines()]


def called(gh: dict[str, Path]) -> list[list[str]]:
    """The first two words of each call, which name what was done."""
    return [call["args"][:2] for call in calls(gh)]


def the(gh: dict[str, Path], *words: str) -> dict[str, Any]:
    """The one call that began with these words."""
    made = [call for call in calls(gh) if call["args"][: len(words)] == list(words)]
    assert len(made) == 1, made
    return made[0]


def flag(call: dict[str, Any], name: str) -> list[str]:
    """Every value given to a flag, in order."""
    args = call["args"]
    return [args[i + 1] for i, arg in enumerate(args) if arg == name]


def body_raised_for(
    site: Site, tmp_path: Path, *sources: dict[str, Any], refresh: dict[str, Any] = RAN
) -> str:
    """The issue body the script writes for this report, from a run of its own."""
    stand_in = stand_in_gh(tmp_path / "first")
    site.body = report(*sources, refresh=refresh)
    assert run(site, stand_in).returncode == 0
    return the(stand_in, "issue", "create")["sent"]


def test_nothing_is_raised_when_nothing_is_behind(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(CURRENT, NOT_LOADED)
    result = run(site, gh)
    assert result.returncode == 0, result.stderr
    assert called(gh) == [["issue", "list"]]
    listed = the(gh, "issue", "list")
    assert flag(listed, "--label") == [LABEL]
    assert flag(listed, "--state") == ["open"]
    assert site.agents == ["openantiquity-refresh-check"]


def test_a_source_left_behind_raises_an_issue(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(CURRENT, FAILED, OVERDUE, NOT_LOADED)
    result = run(site, gh, "--assignee", "the-owner")
    assert result.returncode == 0, result.stderr
    assert called(gh) == [["issue", "list"], ["label", "create"], ["issue", "create"]]
    assert the(gh, "label", "create")["args"][2] == LABEL
    assert "--force" in the(gh, "label", "create")["args"]
    created = the(gh, "issue", "create")
    assert flag(created, "--label") == [LABEL]
    assert flag(created, "--assignee") == ["the-owner"]
    assert "2 sources" in flag(created, "--title")[0]
    body = created["sent"]
    assert "`big-source`" in body
    assert "`DiskFullError`" in body
    assert "`late-source`" in body
    # When each was last refreshed and last run, in a form a person reads.
    assert "2026-11-13 05:10 UTC" in body
    assert "2026-11-27 03:42 UTC" in body
    assert "a-source" not in body
    assert "unset-source" not in body
    assert "didn't finish" not in body, "last night's refresh finished"


def test_times_are_given_in_utc_whatever_zone_the_site_sends(site: Site, gh: dict[str, Path]) -> None:
    site.body = report({**FAILED, "last_run_at": "2026-11-27T04:42:00+01:00"})
    assert run(site, gh).returncode == 0
    assert "2026-11-27 03:42 UTC" in the(gh, "issue", "create")["sent"]


def test_one_source_is_counted_as_one(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(FAILED)
    assert run(site, gh).returncode == 0
    created = the(gh, "issue", "create")
    assert "1 source" in flag(created, "--title")[0]
    assert "1 sources" not in flag(created, "--title")[0]
    assert flag(created, "--assignee") == []


def test_an_issue_open_for_the_same_sources_is_left_alone(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    body = body_raised_for(site, tmp_path, FAILED, OVERDUE)
    # A night later the failed source has run and failed again.
    site.body = report(CURRENT, {**FAILED, "last_run_at": "2026-11-28T03:42:00Z"}, OVERDUE)
    result = run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}]))
    assert result.returncode == 0, result.stderr
    assert called(gh) == [["issue", "list"]]


def test_a_change_in_what_is_behind_updates_the_issue_and_says_what_changed(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    body = body_raised_for(site, tmp_path, FAILED)
    site.body = report({**FAILED, "state": "current", "error": None}, OVERDUE)
    result = run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}]))
    assert result.returncode == 0, result.stderr
    assert called(gh) == [["issue", "list"], ["issue", "edit"], ["issue", "comment"]]
    edited = the(gh, "issue", "edit")
    assert edited["args"][2] == "7"
    assert "1 source" in flag(edited, "--title")[0]
    assert "`late-source`" in edited["sent"]
    assert "big-source" not in edited["sent"]
    comment = the(gh, "issue", "comment")
    assert comment["args"][2] == "7"
    assert "`late-source`" in comment["sent"]
    assert "`big-source`" in comment["sent"]


def test_a_different_kind_of_error_is_a_change(site: Site, gh: dict[str, Path], tmp_path: Path) -> None:
    body = body_raised_for(site, tmp_path, FAILED)
    site.body = report({**FAILED, "error": "UpstreamError"})
    assert run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}])).returncode == 0
    assert called(gh) == [["issue", "list"], ["issue", "edit"], ["issue", "comment"]]
    assert "`UpstreamError`" in the(gh, "issue", "comment")["sent"]


def test_the_issue_is_closed_when_nothing_is_behind_any_more(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    body = body_raised_for(site, tmp_path, FAILED)
    site.body = report(CURRENT, {**FAILED, "state": "current", "error": None})
    result = run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}]))
    assert result.returncode == 0, result.stderr
    assert called(gh) == [["issue", "list"], ["issue", "close"]]
    closed = the(gh, "issue", "close")
    assert closed["args"][2] == "7"
    assert flag(closed, "--comment")


def test_an_issue_someone_else_wrote_under_the_label_is_left_alone(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    """Their words aren't ours to rewrite or to close. The one this script wrote is the one it keeps."""
    theirs = {"number": 9, "body": "The refresh looks broken."}
    site.body = report(FAILED)
    assert run(site, gh, FAKE_GH_OPEN=json.dumps([theirs])).returncode == 0
    assert called(gh) == [["issue", "list"], ["label", "create"], ["issue", "create"]]

    ours = {"number": 7, "body": body_raised_for(site, tmp_path, FAILED)}
    site.body = report(CURRENT)
    later = stand_in_gh(tmp_path / "later")
    assert run(site, later, FAKE_GH_OPEN=json.dumps([theirs, ours])).returncode == 0
    assert called(later) == [["issue", "list"], ["issue", "close"]]
    assert the(later, "issue", "close")["args"][2] == "7"


def test_an_issue_whose_hidden_line_was_spoiled_is_written_afresh(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(FAILED)
    spoiled = {"number": 7, "body": "Edited by hand.\n\n<!-- refresh-check: {not json -->"}
    assert run(site, gh, FAKE_GH_OPEN=json.dumps([spoiled])).returncode == 0
    assert called(gh) == [["issue", "list"], ["issue", "edit"], ["issue", "comment"]]
    assert "`big-source` is failed with `DiskFullError`" in the(gh, "issue", "comment")["sent"]


def test_a_refresh_that_was_stopped_part_way_raises_an_issue(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(CURRENT, refresh=STOPPED)
    result = run(site, gh)
    assert result.returncode == 0, result.stderr
    created = the(gh, "issue", "create")
    assert flag(created, "--title") == ["The nightly refresh didn't run or didn't finish"]
    body = created["sent"]
    assert "2026-11-27 03:00 UTC" in body, "the hour it was due to start in"
    assert "started at 2026-11-27 03:41 UTC and didn't finish" in body
    assert "| Source |" not in body, "no source is behind, so there is no table"


def test_a_night_with_no_refresh_raises_an_issue_that_says_when_the_last_one_ran(
    site: Site, gh: dict[str, Path]
) -> None:
    site.body = report(CURRENT, OVERDUE, refresh=NOT_STARTED)
    assert run(site, gh).returncode == 0
    body = the(gh, "issue", "create")["sent"]
    assert "started at 2026-11-26 03:41 UTC and finished at 2026-11-26 05:52 UTC" in body
    assert "`late-source`" in body


def test_a_refresh_never_written_down_raises_an_issue(site: Site, gh: dict[str, Path]) -> None:
    site.body = report(CURRENT, refresh={**STOPPED, "started_at": None})
    assert run(site, gh).returncode == 0
    assert "No refresh has been written down at all" in the(gh, "issue", "create")["sent"]


def test_a_refresh_that_finishes_after_a_missed_night_is_said_in_a_comment(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    body = body_raised_for(site, tmp_path, FAILED, refresh=STOPPED)
    site.body = report(FAILED)
    assert run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}])).returncode == 0
    assert called(gh) == [["issue", "list"], ["issue", "edit"], ["issue", "comment"]]
    assert "1 source" in flag(the(gh, "issue", "edit"), "--title")[0]
    comment = the(gh, "issue", "comment")["sent"]
    assert "A refresh has finished since" in comment
    assert "big-source" not in comment, "nothing about it changed"


def test_a_missed_night_after_a_failed_source_is_said_in_a_comment(
    site: Site, gh: dict[str, Path], tmp_path: Path
) -> None:
    body = body_raised_for(site, tmp_path, FAILED)
    site.body = report(FAILED, refresh=STOPPED)
    assert run(site, gh, FAKE_GH_OPEN=json.dumps([{"number": 7, "body": body}])).returncode == 0
    assert "didn't finish" in the(gh, "issue", "comment")["sent"]
    assert flag(the(gh, "issue", "edit"), "--title") == ["The nightly refresh didn't run or didn't finish"]


@pytest.mark.parametrize("status", [500, 404])
def test_a_site_that_answers_badly_fails_the_run_and_raises_nothing(
    site: Site, gh: dict[str, Path], status: int
) -> None:
    site.status = status
    result = run(site, gh)
    assert result.returncode != 0
    assert str(status) in result.stderr
    assert site.asked == 2, "it asks as often as it was told to, and no more"
    assert calls(gh) == []


def test_a_site_that_cannot_be_reached_fails_the_run(site: Site, gh: dict[str, Path]) -> None:
    site.url = "http://127.0.0.1:9/api/v1/sources/refresh-state"
    result = run(site, gh)
    assert result.returncode != 0
    assert calls(gh) == []


@pytest.mark.parametrize(
    "body",
    [
        report(),
        [CURRENT],
        {"detail": "Not Found"},
        {"sources": [CURRENT]},
        report(CURRENT, refresh={**RAN, "state": "resting"}),
        b"<html>starting</html>",
        report({**CURRENT, "state": "resting"}),
        report({"state": "failed"}),
        report({**FAILED, "last_run_at": "last night"}),
        report({**FAILED, "last_run_at": 1795750920}),
        report({**FAILED, "last_run_at": "2026-11-27T03:42:00"}),
        report(CURRENT, refresh={**STOPPED, "expected_at": None}),
    ],
    ids=[
        "no sources",
        "the sources alone",
        "another answer",
        "nothing of the refresh itself",
        "an unknown state of the refresh",
        "not JSON",
        "an unknown state of a source",
        "no source key",
        "a time that isn't one",
        "a time as a number",
        "a time with no zone",
        "no time the refresh was due",
    ],
)
def test_an_answer_that_is_not_the_report_is_a_fault(site: Site, gh: dict[str, Path], body: Any) -> None:
    """Silence must not pass for health: an empty or foreign answer raises nothing, so it fails the run."""
    site.body = body
    result = run(site, gh)
    assert result.returncode != 0
    assert result.stderr.strip()
    assert calls(gh) == []


@pytest.mark.parametrize("failing", ["issue list", "label create", "issue create"])
def test_a_gh_that_fails_fails_the_run(site: Site, gh: dict[str, Path], failing: str) -> None:
    site.body = report(FAILED)
    result = run(site, gh, FAKE_GH_FAIL=failing)
    assert result.returncode != 0
    assert f"gh {failing} failed" in result.stderr
    assert called(gh)[-1] == failing.split(), "it stops at the call that failed"


def test_the_check_runs_once_last_nights_refresh_is_over() -> None:
    """Asked any earlier, the site would answer for the night before."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "refresh-check.yml").read_text()
    [(minute, hour)] = re.findall(r'cron: "(\d+) (\d+) \* \* \*"', workflow)
    over = timedelta(hours=REFRESH_HOUR_UTC) + REFRESH_OVER_AFTER
    assert timedelta(hours=int(hour), minutes=int(minute)) > over
