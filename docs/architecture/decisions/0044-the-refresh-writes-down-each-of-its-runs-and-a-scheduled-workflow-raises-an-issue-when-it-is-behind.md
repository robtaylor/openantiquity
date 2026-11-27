# Decision 0044 — The refresh writes down each of its runs, and a scheduled workflow raises an issue when it is behind

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Ingest"](../../ARCHITECTURE.md#ingest).

**TL;DR.** In the context of a nightly source refresh that had failed for four nights with nobody told, facing a second way to go wrong that leaves no failed run behind, we chose to have the refresh write down each of its runs, the site report whether last night's finished and where each source stands, and a scheduled GitHub workflow keep one issue open while anything is behind, to tell the owner the morning after without giving any machine a new key, accepting a new table, a public route that names each source's state, and a check that depends on GitHub's scheduler.

## Context

When this was written, `jobs.sources.refresh` wrote a `refresh_runs` row as it started and again as it ended, `GET /api/v1/sources/refresh-state` reported on the refresh and on each source it covers, and `.github/workflows/refresh-check.yml` ran `infra/refresh_issue.py` every morning.

Before that, nothing told anyone how a refresh had gone. Each source's run wrote an `ingest_runs` row, the job logged one summary line and exited non-zero when a source failed, and nobody was sent either. From 2026-11-21 to 2026-11-24 every night's refresh failed on a full volume (Decision 0043). It was found three days late, by asking the database.

A refresh can also go wrong with no failed run to show for it. On 2026-11-12 the hourly machine wasn't started by its schedule for two hours after it was moved to a new image, and a refresh that is never started writes no `ingest_runs` row. `timeout` stops the machine's command after six hours with a signal that nothing in the job catches, so the run it stops is left as `running` and the sources after it are never reached. A night when every source was current wrote no row either, so it looked the same as a night with no refresh.

The owner asked on 2026-11-27 for a GitHub issue to be raised when there are failures.

The jobs app holds Defra's SFTP login, and GitHub holds no token for it (`infra/README.md`, step 12). The repository is public, so its issues are too.

## Decision

1. The refresh writes down its own runs. `jobs.sources.refresh` adds a row to `refresh_runs` when it starts, and when it ends fills in the time and what it did with each source. A refresh that is stopped, or that raises, is left without an end.
2. The site reports how the refresh is going at `GET /api/v1/sources/refresh-state`, the same for everyone and with no sign-in (`services.refresh.report`).
   - The refresh itself is `current` when one that started at or after the last night that is over has finished, and `overdue` otherwise. A night is over seven and a quarter hours after the start of the refresh hour: the hour the machine may start in, the six hours its command is allowed, and a quarter of an hour for it to be stopped.
   - A source is `failed` when its last run of the whole source failed, or has been `running` for a quarter of an hour longer than a run is allowed. It is `overdue` when no run failed and its last completed full run is older than its `max_age` by 36 hours or more. It is `not_loaded` when it has never had a completed full run.
   - A run limited by area or count is left out. So that this holds for a run that is still going, or was killed, a run's `ingest_runs` row says from its start whether it is of the whole source.
   - The report gives the kind of error a failed run ended with, which is the exception's type name, and never the message.
3. A scheduled workflow raises the issue. `.github/workflows/refresh-check.yml` runs `infra/refresh_issue.py` at 10:23 UTC with the workflow's own token, which may write issues and read the repository and nothing else. The script keeps one issue open under the label `refresh-failed` while the refresh itself is overdue or any source is failed or overdue. It opens the issue and gives it to the repository's owner, rewrites its body and adds a comment when what is behind changes, does nothing when it hasn't changed, and closes it when nothing is behind.
4. What the issue was last told is kept in the issue's own body, in a comment line that a reader doesn't see. An open issue under the label without that line is left alone.
5. A check that can't read the site, or reads something that isn't the report, fails its run and raises nothing.
6. The rules of the refresh, which are what it covers and when a source is due, moved from `jobs/sources.py` to `services/refresh.py`, so that the job and the report read the same ones.

## Alternatives considered

- **The jobs machine opens the issue itself** — rejected because it needs a GitHub token on the machine that holds Defra's login, and because a refresh that is never started, or is stopped part way, can't report itself.
- **Judging the refresh by the age of each source's data alone, with no record of the refresh** — rejected after review. A source's data is overdue only once its `max_age` and a day and a half have passed, so a refresh that didn't run would have been raised on the third morning, which is how late the full volume was found.
- **A ping to an outside monitor at the end of each refresh** — not pursued. It would also catch a refresh that didn't finish, but it adds an outside service and an address to keep secret, and it can't say which source failed.
- **An email from the site** — rejected because the site has no mail relay yet (`docs/plans/owner-actions.md`, WS3).
- **Raising an issue when the site can't be read** — not pursued. Whether the site is up is another question with false alarms of its own, and GitHub already tells whoever last changed a scheduled workflow's schedule when a run of it fails.
- **Giving the error's message in the report** — rejected because a message can name a path on the volume or an address, and the route and the issue are public.

## Consequences

- A night when the refresh didn't run, didn't finish, or left a source failed is raised as an issue the same morning. A refresh that `timeout` stopped is raised as one that didn't finish, and the source it was on shows as failed only once its run is a quarter of an hour past the limit. A source that the refresh keeps passing over is raised a day and a half after it came due.
- Anyone can read which sources are behind and what kind of error stopped them.
- The schema gains `refresh_runs`, which grows by a row a night, and by one more for each refresh run by hand. The refresh can't run without it, so a release that brings it deploys the web app, whose release command makes the table, before the jobs app's image is moved.
- The report counts on the six-hour limit in `infra/fly_jobs.py` and on the time of day in the workflow. Tests hold `services.refresh.RUN_LIMIT` to the limit the machines are given, and the workflow's time to after the night is over.
- A source that has never loaded, as one that lacks a setting hasn't, is `not_loaded` and raises nothing.
- A source that fails one night and loads the next opens an issue that closes itself the morning after. One that fails on alternate nights opens a new issue each time.
- GitHub stops a scheduled workflow in a public repository after 60 days without a commit, and nothing checks until it is enabled again.
- The first morning after this is released, the report says the refresh is overdue unless a refresh has finished on the new image since the night before.

## Walk-back options

- **If the issues are noise** — remove the workflow. The report and the table cost nothing to keep.
- **If the refresh moves to another hour, or its limit changes** — change `REFRESH_HOUR_UTC` or `RUN_LIMIT` in `services/refresh.py`, and the workflow's time if the tests say so.
- **If the site gets a mail relay or an outside monitor** — have it read the same report.

## Links

- Decision 0043 — the full volume that went unseen for three days.
- Decision 0025 — the weekly look at spending, where failed runs were to be looked at until something alerted.
- Decision 0018 — the move to Fly.io, whose scheduler starts the refresh.
