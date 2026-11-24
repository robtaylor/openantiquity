# Decision 0043 — A download removes the copy it replaces before it fetches, and its partial file when the disk fills

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Ingest"](../../ARCHITECTURE.md#ingest).

**TL;DR.** In the context of bulk sources whose files the hourly machine keeps on a 10 GB volume between refreshes, facing a nightly refresh that had failed for four nights because one source's old and new files didn't fit together, we chose to have a download remove the copy it is about to replace before it fetches, and remove what it had fetched when the disk fills, to make a refresh need room for one copy of each file at no cost, accepting that a fetch that fails leaves no copy of that file on disk.

## Context

When this was written, `download()` in `backend/src/fieldclub/ingest/adapters/download.py` removed a copy it wasn't going to reuse before fetching its replacement, and removed what it had fetched and raised `DiskFullError` when the disk filled.

Before that, `download()` wrote the new file to `<name>.part` beside the old one and replaced the old one only when the new one was complete, so refreshing a file needed room for two copies. A failure left the partial file where it was, to be resumed.

The hourly machine of the jobs app kept `var/ingest/` on a 10 GB volume. `he-aim-detailed-mapping` is one GeoPackage of 4.73 GB, refreshed weekly. Its first weekly refresh on Fly, on 2026-11-21, filled the volume when the new file had reached 4.40 GB. That partial file then left no room for any other source, and on 2026-11-22, 23 and 24 all 14 sources due each night failed with "No space left on device". Measured on 2026-11-24, the volume held 9,437 MB of 9,964. That source's two files were 8,708 MB of it, and every other source's folder together about 730 MB.

The old copy was dead weight once a new download started. A copy past its `max_age` was never read again: a download that failed raised, and none of the eight callers of `download()` fell back to the old file. The records stored by a source's last completed run stayed in the database whatever was on disk.

Nothing told anyone that a refresh had failed. The fault was found three days late, by asking the `ingest_runs` table.

The owner was given three remedies on 2026-11-24 and chose the change in code.

## Decision

1. `download()` removes the file at its destination, and the note kept beside it, once it has decided not to reuse it and before it asks the publisher for anything. That covers a copy older than `max_age`, a copy with no note of when it was fetched, and a call that gives no `max_age`.
2. When a write fails because the disk is full, `download()` removes what it had fetched and raises `DiskFullError`, which names the file, the bytes written and the bytes promised. That is the partial file and its note, or the whole file when the disk fills as the note beside it is written, since a file without that note is thrown away by the next run. Any other fault in writing leaves the partial file to be resumed, as before.
3. The volume stayed at 10 GB.

## Alternatives considered

- **Extending the volume to 20 GB** — rejected because it left the cause in place. It cost $1.50 more a month, a Fly volume can't be made smaller again, and a refresh would still have needed twice the room of its largest file.
- **Deleting the old file from the volume by hand** — rejected because the fault would have come back at that source's next weekly refresh.
- **Removing the old copy only once the publisher had begun to send the new one** — not pursued. It would have kept the old file through a night when the publisher was down, and nothing read that file. It would matter if a download ever asked the publisher whether a file had changed, and kept the old one when told it hadn't.

## Consequences

- A refresh needs room for one copy of each file. With one copy of each, the files measured on 2026-11-24 came to about 5.4 GB of the 10.
- The volume as it stood was expected to mend at the next refresh with no work by hand: the old copy would go first, and the partial file would be resumed, or begun again if the publisher's file had changed.
- After a fetch that fails, the source has no file on disk until a later fetch succeeds. A developer who reads `var/ingest/` by hand finds nothing there for that source.
- A disk that fills costs the failing source the bytes it had fetched, and its next run starts that file again.
- Paged answers kept by the `rest` reader don't go through `download()`. A page that fails on a full disk can leave a partial file of at most one page, which the next write replaces.

## Walk-back options

- **If a download learns to ask whether a file changed** — keep the old copy until the publisher answers, and remove it when a new body starts to arrive.
- **If the files outgrow the volume with one copy each** — `fly volumes extend`. `DiskFullError` in `ingest_runs.error` is the sign.

## Links

- Decision 0018 — the move to Fly.io, which put ingest downloads on a volume.
- Decision 0025 — the weekly look at spending, which is where failed runs are looked at until something alerts.
