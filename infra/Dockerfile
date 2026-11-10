# syntax=docker/dockerfile:1.7
#
# Field Club: one image for the Cloud Run service and every Cloud Run job.
#
#   docker buildx build -f infra/Dockerfile --platform linux/amd64 -t fieldclub .
#
# Build from the repository root. Three stages:
#
#   frontend  builds the single-page app with pnpm from its lock file
#   backend   installs the backend with uv from its lock file into /app/.venv
#   runtime   a slim Python 3.12 image holding the virtualenv and the built app
#
# The runtime stage has no compiler, no uv, no pnpm or Node, no tests and no
# secrets. Settings come from FIELDCLUB_* variables at run time, and secrets
# from Secret Manager through Cloud Run (see infra/terraform). The default
# command serves the API and the frontend; a job runs the same image with
# another command, such as `fieldclub-ingest run <key>`.
#
# The base images are pinned by digest so a rebuild gets the same bytes.
# To move to a newer one, look up its digest with
#   docker buildx imagetools inspect python:3.12-slim-trixie
# and change both the tag and the digest.

ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ARG NODE_IMAGE=node:24-trixie-slim@sha256:0820eaa85e07d0490446dd01d14707e17e6108a36988cf374899cd057eb3812d
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490

FROM ${UV_IMAGE} AS uv

# --- Frontend ----------------------------------------------------------------
# The built files are the same on every platform, so this stage always runs on
# the machine doing the build, however many platforms the image is for.
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS frontend
ARG PNPM_VERSION=12.16.1
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=true
RUN npm install --global --no-fund --no-audit "pnpm@${PNPM_VERSION}"
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --frozen-lockfile
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig.json ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN pnpm build

# --- Backend -----------------------------------------------------------------
# Follows https://docs.astral.sh/uv/guides/integration/docker/: dependencies
# first, from the lock file alone, so a source change doesn't reinstall them;
# then the project itself, not editable, so the source tree isn't needed later.
FROM ${PYTHON_IMAGE} AS backend
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src/backend
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --no-editable
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Runtime -----------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# tini runs as process 1 and passes SIGTERM on. Without it a command-line job
# (process 1 with no signal handler of its own) would ignore SIGTERM and be
# killed ten seconds later instead of stopping at once. rasterio's wheel
# bundles GDAL but links the system's libexpat, which the slim image lacks.
RUN apt-get update && \
    apt-get install --yes --no-install-recommends tini libexpat1 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 10001 fieldclub && \
    useradd --system --uid 10001 --gid fieldclub --home-dir /home/fieldclub --create-home \
        --shell /usr/sbin/nologin fieldclub

COPY --from=backend --chown=root:root /app/.venv /app/.venv
COPY --from=frontend --chown=root:root /src/frontend/dist /app/frontend/dist
COPY --chown=root:root infra/jobs /app/jobs

# Paths are explicit because the package is installed into site-packages, so
# the settings' repository-relative defaults would point inside the virtualenv.
# Everything the process writes goes under /tmp, which on Cloud Run is memory:
# nothing written there needs to outlive the instance.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FIELDCLUB_HOST=0.0.0.0 \
    FIELDCLUB_FRONTEND_DIST=/app/frontend/dist \
    FIELDCLUB_VAR_DIR=/tmp/fieldclub/var \
    FIELDCLUB_TERRAIN_WORK_DIR=/tmp/fieldclub/terrain-work \
    FIELDCLUB_TERRAIN_SOURCE_DIR= \
    FIELDCLUB_ENV_FILE= \
    GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR \
    GDAL_HTTP_MAX_RETRY=3 \
    GDAL_HTTP_RETRY_DELAY=1

USER fieldclub:fieldclub
WORKDIR /home/fieldclub
# Cloud Run sends PORT (8080 by default), which the settings read when
# FIELDCLUB_PORT is unset.
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["fieldclub-api"]
