# Plan — Report a problem: a button that captures what a fix needs

**Status:** Proposed.

## Goal

Someone who hits a fault can report it in under a minute, and the report carries enough for the fault to be found and reproduced: which build, what kind of page, what failed. The report opens as a prefilled issue on the project's public GitHub repository, with a second route for people who have no GitHub account. The owner asked for this on 2026-11-12 as a nice to have. It waited behind lines and curves, which landed on 2026-11-13.

## Prerequisites

- The repository is public and takes issues (Decision 0026).
- Nothing else. The first workstream stands alone and is worth doing without the button.

## Where things stand (2026-11-12)

Nothing is built. Three gaps were found by reading the code that day, and each would make any report less useful:

- `/api/v1/meta` gives the version as `0.1.0` and no commit, so a report can't say which build it came from.
- No request carries an identifier. A search of `backend/src` for a request, correlation or trace id found none, so a failure in the browser can't be matched to a line in the server's log.
- The interface links to neither the source nor the issue tracker. A search of `frontend/src` and `frontend/index.html` for `github` found nothing outside tests.

Fly keeps only a short log. On 2026-11-12, when the owner reported that "Save finding" did nothing, the buffer held about 90 seconds and the failed presses were gone, so the cause was found from the code alone.

## Workstreams

### WS1 — What a report needs from the app

**Status:** Not started.

The groundwork, useful to anyone debugging whether or not the button exists.

**Deliverables:**

- `/api/v1/meta` gives the commit the build was made from. The deploy already labels the image with it.
- Every response carries a request id, the server logs it on each line for that request, and an error response repeats it in its body.
- The browser keeps the last few failures in memory: failed requests with their status and request id, and uncaught errors with their message. Nothing is stored or sent until the person reports.
- The About page links to the source and to the issue tracker.

**Exit criteria:**

- A failed request seen in the browser can be found in the server's log by its id.
- A test shows the kept failures hold no request or response bodies.

### WS2 — The button and the prefilled issue

**Status:** Not started. Needs WS1.

"Report a problem" sits in the About page and in every error state. It opens a short form that shows exactly what will be sent, and two ways to send it.

**What is captured by default:** the commit, the kind of page as a route pattern with ids removed, phone or desktop layout, browser and window size, the layers shown and 2D or 3D, whether the person is signed in, and the kept failures from WS1.

**What is left out by default:** the map position, finding and investigation ids, the account, and the contents of drafts. The repository is public, and an address or a map position can say where a protected finding is.

**Position by choice.** A tick box adds where the person was looking, since position is often what reproduces a terrain fault. It is unavailable while the page shows a finding whose place is kept back from that person, and on any page of an investigation that holds one.

**Routes:**

- "Open a GitHub issue" opens the repository's new-issue page with the title and body prefilled. GitHub shows it all before anything is submitted. No key or backend is involved.
- "Copy the details" and an email link carry the same text, for people with no GitHub account.

**Exit criteria:**

- A report made on a page showing a protected finding, as someone who sees only its square, holds nothing that places the finding more closely than the square. A test proves it for each route.
- The prefilled address stays under GitHub's length limit with the most failures the browser keeps.
- Every control works by keyboard and has a visible focus ring, as `docs/UI.md` requires.

### WS3 — Finding duplicates

**Status:** Not started. Independent of WS1 and WS2.

A workflow on the repository reads each new issue, compares it with the open ones, comments with the likely matches and adds a label. It runs in GitHub, after the issue is filed. That keeps any key out of the web app, costs nothing while nobody reports, and covers issues filed by any route.

Issue text comes from strangers and would be read by a model, on a public repository. The workflow's token may comment on and label issues and nothing else, and the model is given no other tool.

**Exit criteria:**

- A new issue that restates an open one gets a comment naming it within a few minutes.
- The workflow file grants `issues: write` and no other permission, and `actionlint` passes.

## Decided by the owner

Asked on 2026-11-13 with a recommendation for each, the owner replied: "sounds good to me all round".

- **Logs.** Fly's own log search and nothing else for now. Fly's documentation says it keeps an app's logs for 7 days, searchable in its Grafana, free while the feature is in beta, and names no set-up ([Search logs](https://docs.fly.io/monitoring/search-logs)). It hasn't been tried on this account. The privacy notice says seven days. If that proves too short, or the beta ends, the next step is Fly's log shipper writing to a Tigris bucket that expires objects after 30 days, which needs one small machine running all the time.
- **The address for email reports.** One role address on the project's domain that forwards to the owner, used for reports, for the privacy notice's contact and for complaints, so that no personal address is published. Its name isn't chosen yet, and WS2's email link waits for it.
- **Security reports** go by GitHub's private vulnerability reporting, switched on for the repository on 2026-11-13, with [`SECURITY.md`](../../SECURITY.md) pointing to it.
- **No stored reports.** A prefilled issue and a copy-and-email route cover the need. A table of reports would add moderation and personal data to look after. Revisit if emailed reports become regular, or if reports about protected places need somewhere private.

## Open questions

- **The role address's name**, and where it forwards. The owner's to choose.
- **Whether GitHub's duplicate suggestions are on for this repository.** See below. If they are, WS3 is dropped.

**Checked on 2026-11-13:**

- **What GitHub does about duplicates.** Since June 2026, in public preview, GitHub's new-issue form shows up to three possible matches among the repository's issues while it is being filled in ([changelog](https://github.blog/changelog/2026-06-18-duplicate-detection-and-issue-fields-mcp-support-for-github-issues)). The announcement doesn't say which plans or repositories have it, and it wasn't tried on this one. If it is on here, WS3 isn't needed.
- **GitHub's limit on a prefilled address.** Measured signed out, with an unencoded body: 6,500 characters were accepted, 7,000 got an error page, and from about 8,150 the answer was 414. WS2 keeps the whole encoded address under 6,000 characters, and falls back to "Copy the details" with a short address when a report is longer.
- **How the build learns its commit.** A Fly machine has `FLY_IMAGE_REF` in its environment, and on a jobs machine it read `registry.fly.io/openantiquity-jobs:<commit>@sha256:…`, the label the deploy gives the image. `/meta` can read the commit from it, with no build argument.

## Phase exit criteria

When all of these are true, this plan closes:

- [ ] WS1 and WS2 shipped.
- [ ] WS3 shipped, or dropped because GitHub's own duplicate suggestions serve.
- [ ] Every open question above is answered here or in a decision record.

## References

- `architecture/decisions/0026-the-code-is-published-under-the-agpl-version-3.md` — the code is public, so the tracker is too.
- `architecture/decisions/0005-sensitive-findings-are-generalised-by-viewer.md` — who may see a protected finding's place, which binds what a report may carry.
- `UI.md` — the interface rules the form follows.
- `../infra/README.md` — the deploy that labels each image with its commit.
