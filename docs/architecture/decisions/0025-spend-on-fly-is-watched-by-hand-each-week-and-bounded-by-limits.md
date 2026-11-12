# Decision 0025 — Spend on Fly is watched by hand each week and bounded by limits

**Status:** Proposed.

**Current architecture:** [infra/README.md, "Spend"](../../../infra/README.md#spend).

**TL;DR.** In the context of a deployment on Fly.io, which had no billing alert, no spending cap and no documented way to ask what a month had cost, facing Decision 0018's promise of an automatic spend check that nothing on the platform could be built on, we chose a weekly look at the dashboard's bill and fixed limits on machines, their sizes and how long a job runs, to keep the bill inside a known range with no new code, accepting that data sent to visitors, object storage and the database's disk are watched only by a person.

## Context

When this was written nothing checked spend automatically. The runbook's "Spend" section described a weekly look at the dashboard and the limits below, and said the owner had to accept them or ask for more.

Decision 0018, point 9, said the deployment would supply its own check of the month's spend, because Fly had no billing alert. The Google deployment had an alert at £75 a month.

Fly's cost page said "We don't support billing alerts (yet)" and "there's no soft ceiling. If you go over, we'll bill you". The only place it named for the month so far was the dashboard's current month to date bill. Its billing page described no API or command for usage. Whether Fly's GraphQL API exposed the invoice wasn't looked into. Prepaid credit was no cap: the billing page didn't say what happens when the credit runs out.

The deployment already bounded most of what it could spend on machines.

- **Web machines.** Fly's proxy starts and suspends machines and never creates one. The web app had three, which cost $40.17 a month if all three ran all month, at US east prices.
- **Sizes.** `fly.toml` fixed the web machines' size, and `infra/fly_jobs.py` fixed each job's.
- **Job run times.** Every job ran under `timeout`. The dearest, the national overview build, stopped after six hours, about $2.20.

Three costs had no bound: data sent to visitors at $0.02 a gigabyte, Tigris storage and requests, and the database's disk, which grows by itself.

The owner was asked on 2026-11-12 and chose the weekly look and the limits.

## Decision

1. The owner reads the organisation's current month to date bill in Fly's dashboard once a week. A bill on course to pass £75, the figure Google's alert had, means something has changed.
2. The web app keeps three machines, and only a person changes that number.
3. Machine sizes stay fixed in `fly.toml` and `infra/fly_jobs.py`, and a test fails if the web machines' memory changes.
4. Every job runs under a time limit.
5. No automatic check of spend was built. This replaced point 9 of Decision 0018, and the rest of that decision stood.

## Alternatives considered

- **A scheduled job that adds up machine hours from Fly's API** — rejected because machines were the part already bounded. The three costs without a bound don't show in a list of machines, and the job would have needed a Fly token on the jobs app, the app that was to hold Defra's login.
- **Looking into Fly's GraphQL or metrics API for the invoice or the data sent out, before deciding** — not pursued. The owner preferred to accept the weekly look. It stays open as the walk-back.
- **Prepaid credit as a cap** — rejected because Fly's billing page didn't say that usage stops when the credit runs out.

## Consequences

- No new code runs, and no app holds a token that can read the organisation's machines or billing.
- A fault or abuse that raises data sent out, storage or the database's disk goes unseen for up to a week. At $0.02 a gigabyte, a terabyte sent in that week costs $20.
- The check depends on a person remembering it. Nothing reminds them.
- The £75 figure is a judgement carried over from Google, about 1.3 to 1.6 times the bill expected at light use.

## Walk-back options

- **If Fly adds billing alerts** — set one at £75 and drop the weekly look.
- **If a month's bill is a surprise, or the weekly look keeps being missed** — look into Fly's metrics API for data sent out and the database's disk, and have the hourly machine warn past a threshold.

## Links

- Decision 0018 — the move to Fly.io. This record replaced its point 9.
- [spikes/hosting-on-fly-io.md](spikes/hosting-on-fly-io.md) — Q6, where the missing billing alert was found.
