FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock .python-version README.md ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/

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

CMD ["uv", "run", "dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "bonuschef.dags.definitions"]
