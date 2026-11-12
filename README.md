# Open Antiquity

A shared map for finding and checking archaeological earthworks in UK LIDAR data.

You look at terrain drawn to show banks, ditches and mounds a few centimetres high. You mark what you think is there. Other people take a second look without seeing what you said, and a finding climbs from "Spotted" to "Seen by others" as people agree and add evidence. Designated sites and other heritage records sit on the same map, each credited to its publisher under its licence.

The site will be at [openantiquity.org](https://openantiquity.org). It isn't open yet. While it was being built it was called Field Club, and the code still uses `fieldclub` for its own names.

## What is here

| Path | What it is |
|---|---|
| `backend/` | The API, the terrain renderer, the connectors that load heritage records, and the jobs. Python, FastAPI and PostGIS |
| `frontend/` | The map and everything around it. TypeScript, React and MapLibre |
| `infra/` | The deployment on Fly.io, with its runbook in `infra/README.md` |
| `docs/` | What the product does and why, how it is built, each decision, and each source of data |

Start with [`docs/DESIGN.md`](docs/DESIGN.md) for what the product does, and [`docs/architecture/README.md`](docs/architecture/README.md) for how it is built and the decisions behind it. [`docs/sources/README.md`](docs/sources/README.md) lists every external source with its licence and attribution.

## Running it

You need Docker, [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/).

```
docker compose -f infra/docker-compose.yml up -d db     # PostGIS on localhost:54329
(cd backend && uv sync && uv run fieldclub-api)          # the API on :8000
(cd frontend && pnpm install && pnpm dev)                # the map on :5173, in a second terminal
```

The checks are `uv run pytest`, `uv run ruff check .` and `uv run pyright` in `backend/`, and `pnpm test`, `pnpm typecheck` and `pnpm lint` in `frontend/`. The backend's tests run against the PostGIS above. Checks against live third-party services are off unless asked for.

## Licence

The code is free software under the GNU Affero General Public License, version 3. The text is in [`LICENSE`](LICENSE). If you run a changed copy as a service, the licence asks you to offer its source to the people who use it.

Copyright © 2026 the Open Antiquity contributors.

Three things here are not the project's own code and keep their own terms:

- **What people add on the site** is published under CC BY 4.0.
- **Data from other publishers** keeps its publisher's licence. That covers the small samples recorded as test fixtures under `backend/tests/` and the catalogue in `docs/sources/`. Most are under the Open Government Licence or a Creative Commons licence. The lost villages sample is CC BY-NC-SA 4.0, so it may not be used commercially.
- **The terrain views** reimplement algorithms of the Relief Visualization Toolbox, which is under Apache-2.0. `backend/src/fieldclub/terrain/visualise.py` says which.
