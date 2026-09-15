FROM ghcr.io/astral-sh/uv:python3.12-bookworm

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

LABEL org.opencontainers.image.version="${BONUSCHEF_VERSION}" \
      org.opencontainers.image.revision="${BONUSCHEF_COMMIT}" \
      org.opencontainers.image.source="https://github.com/levyvankempen/bonuschef"

CMD ["uv", "run", "dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "bonuschef.dags.definitions"]
