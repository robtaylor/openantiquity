# Decision 0026 — The code is published under the AGPL version 3

**Status:** Proposed.

**Current architecture:** [README.md, "Licence"](../../../README.md#licence).

**TL;DR.** In the context of a non-commercial heritage service whose code was about to be made public for the first time, facing a repository with no licence, which gives nobody the right to reuse anything, we chose the GNU Affero General Public License, version 3 only, to let anyone use, change and host the code while any hosted copy that is changed has to offer its source, accepting that some companies and public bodies won't take code under it.

## Context

When this was written the repository had no `LICENSE` file, no licence field in `backend/pyproject.toml` or `frontend/package.json`, and no `README.md`. It had been pushed to a public GitHub repository on 2026-11-12, `robtaylor/openantiquity`, so the code could be read but not reused.

OpenAntiquity is a hosted service, and its value is the map people share. Decision 0004 made the project non-commercial. What people add on the site was already published under CC BY 4.0 (`CONTRIBUTION_LICENCE` in `vocab.py`), and each external source keeps its publisher's licence (Decision 0007).

The owner was asked on 2026-11-12, with the AGPL recommended and Apache-2.0 named as the permissive alternative, and chose the AGPL version 3.

The licences of what the code depends on were read that day from the installed packages. The 104 Python packages in the backend's environment were under MIT, BSD, Apache-2.0, ISC, PSF-2.0, MPL-2.0, the Unlicense and, for `psycopg` and `paramiko`, the LGPL. The 35 packages in the frontend's shipped bundle were under MIT, ISC and BSD. None forbids combining with AGPL code.

## Decision

1. The project's own code is under the GNU Affero General Public License, version 3 and no later version: `AGPL-3.0-only`. The text is in `LICENSE` at the root, and both packages name it.
2. The copyright line names "the OpenAntiquity contributors". No operating entity had been chosen when this was written.
3. The licence covers the project's own code and documents. What people add on the site stays under CC BY 4.0, and data from other publishers, the test fixtures included, keeps its publisher's licence. The `README.md` says so.
4. The terrain views stay credited to the Relief Visualization Toolbox, whose algorithms they reimplement and which is under Apache-2.0.

## Alternatives considered

- **Apache-2.0 or MIT** — rejected because a changed copy could be run as a closed service, and the shared map is what the project is for. Either would have allowed the widest reuse.
- **GPL version 3** — rejected because its duty to share source is triggered by handing out copies, not by running a service, so it wouldn't reach a hosted fork.
- **"Version 3 or any later version"** — not taken. The owner said version 3. A sole copyright holder can widen the grant later, and can't narrow one already given.
- **A non-commercial source licence** — rejected because it isn't open source, and nothing in Decision 0004 needs the code to be non-commercial: that decision is about the data the project may hold.
- **Leaving the repository without a licence** — rejected because nobody could then run, change or contribute to it lawfully.

## Consequences

- Anyone may use, change and host the code. Whoever hosts a changed copy has to offer that copy's source to the people who use it.
- Some organisations have a rule against AGPL code and won't reuse it.
- Contributions from other people come in under the same licence. With no contributor agreement, the licence can't be changed later without each contributor's consent.
- The copyright line will want changing once an operating entity is named (`owner-actions.md`, WS14).
- The lost villages fixture is CC BY-NC-SA 4.0, so the repository as a whole can't be reused commercially without leaving that file out.
- A new dependency has to be under a licence that can be combined with the AGPL.

## Walk-back options

- **If the AGPL keeps away a partner the project wants** — while the owner holds all the copyright, publish under a second licence as well, or move to Apache-2.0. After outside contributions arrive this needs their authors' consent.
- **If a later version of the AGPL is wanted** — add "or any later version" to the grant.

## Links

- Decision 0004 — the project is non-commercial, which governs the data it may hold.
- Decision 0007 — the record index stores only what each source's licence allows.
- Decision 0006 — the terrain views and the Relief Visualization Toolbox.
