#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ruff: noqa: T201 - a command-line tool: what it prints is its output
"""Keep one GitHub issue open while the nightly refresh is behind.

    uv run infra/refresh_issue.py [--url URL] [--assignee LOGIN] [--attempts N] [--wait SECONDS]

It asks the site how the refresh is going (`GET /api/v1/sources/refresh-state`).
The refresh is behind when last night's didn't run or didn't finish, or when a
source it covers is failed or overdue. Then it looks for the open issue it
keeps, labelled `refresh-failed`:

- Something is behind and no such issue is open: it opens one, with the label,
  that says what.
- One is open and what is behind has changed: it rewrites the issue's body and
  title and adds a comment that says what changed.
- One is open and nothing has changed: it does nothing, so a fault that lasts
  a week is one issue and not seven.
- One is open and nothing is behind: it closes it with a comment.

What the issue was last told is kept in its own body, in a comment line a
reader doesn't see. Only someone who may edit the issue can change that, where
anyone may comment on a public repository. An issue under the label without
that line is someone else's, and is left alone.

It runs `gh`, which reads `GH_TOKEN` and `GH_REPO`, and is run every morning by
`.github/workflows/refresh-check.yml` with the workflow's own token. It exits
non-zero when the site doesn't answer, or answers with anything but the report,
or `gh` fails: a check that can't see must not pass for a refresh in good
order.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

REPORT_URL = "https://openantiquity.org/api/v1/sources/refresh-state"
USER_AGENT = "openantiquity-refresh-check"
LABEL = "refresh-failed"
LABEL_DESCRIPTION = "The nightly refresh didn't finish, or left a source failed or overdue"
LABEL_COLOUR = "D93F0B"
# Every state the site may give a source (`fieldclub.vocab.RefreshState`), and the two that mean it is behind.
SOURCE_STATES = frozenset({"current", "failed", "overdue", "not_loaded"})
BEHIND_STATES = frozenset({"failed", "overdue"})
# The two it may give the refresh itself.
REFRESH_STATES = frozenset({"current", "overdue"})
# What the issue was last told, written into its body where a reader doesn't see it.
MARKER = re.compile(r"<!-- refresh-check: (.*?) -->")
# What the issue is told of the refresh itself is kept under this key, which no source can have.
THE_REFRESH = ""
TABLE_HEAD = ("| Source | State | Last refreshed | Last run | Kind of error |", "|---|---|---|---|---|")
# The paragraphs that close the issue's body.
EXPLANATION = (
    (
        "A failed source's last run failed. An overdue source has no failed run to show, and its data is "
        "older than the refresh lets it get: the refresh passed it over."
    ),
    (
        "The error's message is in the database, in `ingest_runs.error`. `infra/README.md`, "
        '"What to watch", says how to read it.'
    ),
    (
        'The "Refresh check" workflow keeps this issue up to date each morning and closes it when nothing '
        "is behind."
    ),
)


class CheckError(Exception):
    """The check couldn't be made, so nothing is known about the refresh."""


@dataclass(frozen=True)
class Source:
    """A source the refresh has left failed or overdue."""

    key: str
    state: str
    # When it last completed a full run, and when it last ran, as `when` gives them.
    refreshed: str | None
    ran: str | None
    error: str | None

    @property
    def told(self) -> str:
        """What the issue is told of this source. Another night's failure of the same kind is nothing new."""
        return self.state + (f":{self.error}" if self.error else "")

    def summary(self) -> str:
        return f"`{self.key}` is {self.state}" + (f" with `{self.error}`" if self.error else "")

    def row(self) -> str:
        """This source's line of the table in the issue's body."""
        cells = [
            f"`{self.key}`",
            self.state,
            self.refreshed or "never",
            self.ran or "never",
            f"`{self.error}`" if self.error else "",
        ]
        return "| " + " | ".join(cells) + " |"


@dataclass(frozen=True)
class Missed:
    """A night whose refresh didn't run or didn't finish. Each time is as `when` gives it."""

    # The start of the hour it was due to start in.
    expected: str
    # When the last refresh of any night started and finished.
    started: str | None
    finished: str | None

    def summary(self) -> str:
        if self.started is None:
            last = "No refresh has been written down at all."
        elif self.finished is None:
            last = f"The last one started at {self.started} and didn't finish."
        else:
            last = f"The last one started at {self.started} and finished at {self.finished}."
        return f"No refresh has finished since the one due to start in the hour from {self.expected}. {last}"


@dataclass(frozen=True)
class Behind:
    """What the refresh is behind with."""

    # The refresh itself, when last night's didn't run or didn't finish.
    missed: Missed | None
    sources: list[Source]

    def __bool__(self) -> bool:
        return self.missed is not None or bool(self.sources)

    def told(self) -> dict[str, str]:
        """What the issue is told, by what it is told of: each source by its key, and the refresh itself."""
        told = {source.key: source.told for source in self.sources}
        return told | ({THE_REFRESH: "overdue"} if self.missed else {})

    def title(self) -> str:
        if self.missed:
            return "The nightly refresh didn't run or didn't finish"
        count = "1 source" if len(self.sources) == 1 else f"{len(self.sources)} sources"
        return f"The nightly refresh has left {count} behind"

    def body(self, url: str) -> str:
        paragraphs = [f"The site reports that the nightly refresh is behind ({url})."]
        if self.missed:
            paragraphs.append(self.missed.summary())
        if self.sources:
            paragraphs.append("\n".join([*TABLE_HEAD, *(source.row() for source in self.sources)]))
        # No `>` is written as itself, so nothing in the line can end the comment early.
        marker = json.dumps(self.told(), sort_keys=True).replace(">", "\\u003e")
        return "\n\n".join([*paragraphs, *EXPLANATION, f"<!-- refresh-check: {marker} -->"]) + "\n"

    def change(self, before: dict[str, str]) -> str:
        """What to say in a comment when what is behind has changed from `before`."""
        now = self.told()
        lines = []
        if self.missed and THE_REFRESH not in before:
            lines.append(f"- {self.missed.summary()}")
        lines += [
            f"- {source.summary()}." for source in self.sources if before.get(source.key) != source.told
        ]
        lines += [
            "- A refresh has finished since." if key == THE_REFRESH else f"- `{key}` is no longer behind."
            for key in before
            if key not in now
        ]
        return "What the nightly refresh is behind with changed:\n\n" + "\n".join(lines)


def fetch(url: str, attempts: int, wait_s: float) -> Any:
    """The site's answer as JSON. A machine that was stopped takes half a minute to start, so ask again."""
    assert attempts >= 1, "ask at least once"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    fault = ""
    for attempt in range(attempts):
        if attempt:
            time.sleep(wait_s)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            fault = f"it answered {exc.code}"
        except (OSError, http.client.HTTPException) as exc:
            fault = f"it couldn't be read ({type(exc).__name__}: {exc})"
        except ValueError:
            fault = "its answer wasn't JSON"
    raise CheckError(f"{url} was asked {attempts} times, and the last time {fault}.")


def behind(report: Any) -> Behind:
    """What the report says is behind. Raises when it isn't the report: silence must not pass for health."""
    refresh = report.get("refresh") if isinstance(report, dict) else None
    entries = report.get("sources") if isinstance(report, dict) else None
    if not isinstance(refresh, dict) or refresh.get("state") not in REFRESH_STATES:
        raise CheckError(
            "The site's answer doesn't say how the refresh itself stands, so it isn't the report."
        )
    if not isinstance(entries, list) or not entries:
        raise CheckError("The site's answer names no sources, so it isn't the refresh's report.")
    found = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_key"), str):
            raise CheckError(f"The site's answer has an entry with no source key: {entry!r}")
        if entry.get("state") not in SOURCE_STATES:
            raise CheckError(
                f"{entry['source_key']} has a state this script doesn't know: {entry.get('state')!r}"
            )
        if entry["state"] in BEHIND_STATES:
            found.append(
                Source(
                    key=entry["source_key"],
                    state=entry["state"],
                    refreshed=when(entry.get("last_success_at")),
                    ran=when(entry.get("last_run_at")),
                    error=entry.get("error"),
                )
            )
    missed = None
    if refresh["state"] == "overdue":
        expected = when(refresh.get("expected_at"))
        if expected is None:
            raise CheckError("The site's answer doesn't say when the refresh was due.")
        missed = Missed(expected, when(refresh.get("started_at")), when(refresh.get("finished_at")))
    return Behind(missed=missed, sources=found)


def when(stamp: object) -> str | None:
    """A time from the report as a person reads it, in UTC, or None where the report gives none."""
    if stamp is None:
        return None
    try:
        time = datetime.fromisoformat(stamp) if isinstance(stamp, str) else None
    except ValueError:
        time = None
    if time is None or time.tzinfo is None:
        raise CheckError(f"The site's answer gives a time that isn't one, or has no zone: {stamp!r}")
    return time.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def gh(*args: str, send: str | None = None) -> str:
    """Run `gh` and give what it printed. Raises when it fails."""
    done = subprocess.run(["gh", *args], input=send, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise CheckError(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout


def last_told(body: str) -> dict[str, str] | None:
    """What an issue's body says it was last told, or None when this script didn't write it."""
    marker = MARKER.search(body)
    if marker is None:
        return None
    try:
        told = json.loads(marker.group(1))
    except ValueError:
        told = None
    # A line someone has spoiled reads as nothing told, so the body is written afresh.
    return told if isinstance(told, dict) else {}


def kept_issue() -> tuple[str, dict[str, str]] | None:
    """The newest open issue under the label that this script wrote: its number, and what it was last told."""
    listed = gh(
        "issue", "list", "--label", LABEL, "--state", "open", "--limit", "20", "--json", "number,body"
    )
    for issue in json.loads(listed):
        told = last_told(issue.get("body") or "")
        if told is not None:
            return str(issue["number"]), told
    return None


def check(url: str, assignee: str | None, attempts: int, wait_s: float) -> str:
    """Bring the issue into line with the site's report, and say what was done."""
    found = behind(fetch(url, attempts, wait_s))
    kept = kept_issue()
    if not found:
        if kept is None:
            return "Nothing is behind, and no issue is open."
        gh("issue", "close", kept[0], "--comment", "Nothing is behind any more, so this is closed.")
        return f"Closed issue {kept[0]}: nothing is behind."
    if kept is None:
        gh("label", "create", LABEL, "--description", LABEL_DESCRIPTION, "--color", LABEL_COLOUR, "--force")
        to = ["--assignee", assignee] if assignee else []
        made = gh(
            "issue",
            "create",
            "--title",
            found.title(),
            "--label",
            LABEL,
            *to,
            "--body-file",
            "-",
            send=found.body(url),
        )
        return f"Opened {made.strip()}: {found.title()}."
    number, before = kept
    if before == found.told():
        return f"Issue {number} already says what is behind."
    gh("issue", "edit", number, "--title", found.title(), "--body-file", "-", send=found.body(url))
    gh("issue", "comment", number, "--body-file", "-", send=found.change(before))
    return f"Brought issue {number} up to date: {found.title()}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Keep one GitHub issue open while the nightly refresh is behind."
    )
    parser.add_argument("--url", default=REPORT_URL, help="where the site gives the refresh's report")
    parser.add_argument("--assignee", help="who a new issue is given to")
    parser.add_argument("--attempts", type=int, default=4, help="how many times to ask the site")
    parser.add_argument("--wait", type=float, default=20, help="seconds between one attempt and the next")
    args = parser.parse_args(argv)
    try:
        print(check(args.url, args.assignee, args.attempts, args.wait))
    except CheckError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
