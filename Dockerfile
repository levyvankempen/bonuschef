# Pinned by digest, not by tag.
#
# `uv:python3.12-bookworm` is a floating tag: the same commit built a fortnight
# apart picks up different Debian and CPython patch levels. That was harmless
# while every host built its own image and nobody compared them. It stops being
# harmless once a version is built once and run in two environments, because
# then "the artifact I watched working" has to mean something, and a floating
# base is the one thing in this build that can differ without appearing in any
# diff. (uv.lock already pins the Python side exactly, via `uv sync --frozen`.)
#
# This is a multi-arch index, so amd64 (the deployment host) and arm64 (a
# developer's Mac) both still resolve. Bumping it is a deliberate commit:
#
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:python3.12-bookworm
#
FROM ghcr.io/astral-sh/uv:python3.12-bookworm@sha256:85d4cb1afa769a7338e095b927bee941cf5ec92266c7424b3f6c0f2748567248

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock .python-version README.md ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/

# The Streamlit theme. Without this the container falls back to the stock
# white-and-slate look and nothing reports it - the app just looks wrong.
COPY .streamlit/ .streamlit/

# Install the project itself
RUN uv sync --frozen --no-dev

# The operator scripts. These are run against production - creating an
# account, setting a password, pointing an account at a store, curating the
# catalogue - so they belong in the image rather than being copied in one at a
# time when needed.
#
# Deliberately after the dependency install and after the dbt parse below
# would be better still, but this sits where it does because the parse needs
# nothing from here: editing a script rebuilds this layer and the two `uv sync`
# layers above it are untouched.
COPY scripts/ scripts/

# Copy dagster instance config
RUN mkdir -p /app/dagster_home
COPY dagster.yaml /app/dagster_home/dagster.yaml

# Generate dbt manifest at build time (no DB connection needed)
RUN PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DB=postgres ENVIRONMENT=default \
    uv run dbt deps --project-dir src/bonuschef/sql --profiles-dir src/bonuschef/sql && \
    PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DB=postgres ENVIRONMENT=default \
    uv run dbt parse --project-dir src/bonuschef/sql --profiles-dir src/bonuschef/sql

# The version stamp goes last. It changes on every commit, so putting it
# higher would invalidate the dependency and manifest layers on each build
# and turn a redeploy into a full reinstall.
ARG BONUSCHEF_VERSION=unknown
ARG BONUSCHEF_COMMIT=unknown

# ENV for a running container and `docker compose exec`; LABEL for
# `docker inspect` without starting anything. Two audiences ask this
# question in two different situations.
ENV BONUSCHEF_VERSION=${BONUSCHEF_VERSION} \
    BONUSCHEF_COMMIT=${BONUSCHEF_COMMIT}

# title/description/url are overridden, not just set: without them the image
# inherits the uv base image's labels, so `docker inspect` answers "what is
# this image?" with "uv - an extremely fast Python package manager".
LABEL org.opencontainers.image.version="${BONUSCHEF_VERSION}" \
      org.opencontainers.image.revision="${BONUSCHEF_COMMIT}" \
      org.opencontainers.image.source="https://github.com/levyvankempen/bonuschef" \
      org.opencontainers.image.url="https://github.com/levyvankempen/bonuschef" \
      org.opencontainers.image.title="bonuschef" \
      org.opencontainers.image.description="Albert Heijn bonus and clearance tracking"

CMD ["uv", "run", "dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "bonuschef.dags.definitions"]
