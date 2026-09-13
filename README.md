# BonusChef

A data engineering pipeline that tracks Dutch supermarket (Albert Heijn) product prices and calculates recipe costs over time. Built with **dlt**, **Dagster**, **dbt**, and **Streamlit**.

## Architecture

```
GitHub (JSON snapshots)
        |
       dlt          ── extract & load ──>  PostgreSQL
        |
      Dagster       ── orchestration ──>   sensors, jobs, partitions
        |
       dbt          ── transform ──>       staging > intermediate > marts
        |
    Streamlit       ── visualise ──>       interactive portal
```

### Data flow

1. A GitHub repository stores daily JSON snapshots of Albert Heijn product data
2. **dlt** extracts commit history and loads product snapshots into PostgreSQL
3. **Dagster** orchestrates the pipeline with a sensor that discovers new commits and triggers backfill jobs via dynamic partitions
4. **dbt** transforms raw data through staging, intermediate, and mart layers into analytical models
5. **Streamlit** provides an interactive portal to explore recipe costs, ingredient breakdowns, and price trends

### dbt model layers

| Layer | Models |
|---|---|
| **Staging** | `stg_github__products`, `stg_ah__bonus_products`, `stg_ah__markdowns`, `stg_portal__recipes`, `stg_portal__recipe_ingredients`, `stg_portal__product_images` |
| **Intermediate** | `int_product_latest_price`, `int_recipe_items_resolved`, `int_recipe_items_priced` |
| **Marts** | `dim_product`, `dim_recipe`, `fct_products`, `fct_recipe_cost_history`, `fct_recipe_cost_latest`, `fct_recipe_cost_breakdown`, `fct_recipe_cost_breakdown_bonus`, `fct_product_price_changes`, `fct_bonus_price_comparison`, `fct_store_clearance`, `fct_store_clearance_history` |

Recipe ingredients use **SCD Type 2** (`valid_from` / `valid_to`) to track product renames and succession over time.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/levyvankempen/bonuschef.git
cd bonuschef
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Environment variables

Copy the committed template and fill it in:

```bash
cp .env.example .env
```

`.env.example` lists every variable the services read. `POSTGRES_PASSWORD`
initialises the database container, while `PG_PASSWORD` and
`DESTINATION__POSTGRES__CREDENTIALS__PASSWORD` are what clients authenticate
with - all three must match. Compose fails to start if `POSTGRES_PASSWORD` is
absent, rather than falling back to a well-known default.

For reference, the file looks like:

```
# PostgreSQL
POSTGRES_PASSWORD="postgres"

DESTINATION__POSTGRES__CREDENTIALS__HOST="localhost"
DESTINATION__POSTGRES__CREDENTIALS__PORT=5455
DESTINATION__POSTGRES__CREDENTIALS__USERNAME="postgres"
DESTINATION__POSTGRES__CREDENTIALS__PASSWORD="postgres"
DESTINATION__POSTGRES__CREDENTIALS__DATABASE="postgres"

PG_HOST="localhost"
PG_PORT=5455
PG_DB="postgres"
PG_USER="postgres"
PG_PASSWORD="postgres"
TARGET_SCHEMA="public_marts"

# Environment
ENVIRONMENT="default"

# GitHub source
GITHUB_TOKEN=""  # Optional, for higher API rate limits
GITHUB_OWNER="supermarkt"
GITHUB_REPO="checkjebon"
GITHUB_PATH="data/supermarkets.json"
GITHUB_MESSAGE_FILTER="Update supermarkets.json"
GITHUB_START_DATE="2025-01-01T00:00:00Z"
GITHUB_BRANCH="main"
GITHUB_MAX_PAGES="2"

# Albert Heijn store markdowns ("laatste kans koopjes")
AH_STORE_ID="1876"        # defaults to Eindhoven Torenallee
AH_REFRESH_TOKEN=""       # fallback only; `python -m bonuschef.utils.ah_login` (see below)
# AH_TOKEN_FILE=""        # optional; defaults to $DAGSTER_HOME/ah_tokens.json

# Dagster webserver, used by the portal's "Refresh now" button (defaults shown)
DAGSTER_HOST="localhost"
DAGSTER_PORT=3000
```

### 3a. Enable store markdowns (optional — "laatste kans koopjes")

Store-specific clearance data (reduced-to-clear stickers) lives behind Albert
Heijn's **member** GraphQL API, so it needs a one-time browser login:

```bash
# 1. Print the login URL + instructions
python -m bonuschef.utils.ah_login

# 2. Log in; capture the blocked appie://login-exit?code=... from the browser
#    console, then exchange it:
python -m bonuschef.utils.ah_login "appie://login-exit?code=PASTE_HERE"
```

This writes the access + refresh token to the **token file** (default
`$DAGSTER_HOME/ah_tokens.json`, or `~/.bonuschef/ah_tokens.json` when
`DAGSTER_HOME` is unset; override with `AH_TOKEN_FILE`) and prints an
`AH_REFRESH_TOKEN=` line to keep in `.env` as a fallback for fresh hosts.

From then on the pipeline manages tokens itself (`utils/ah_auth.AHTokenManager`):
the access token is cached and refreshed at most once a day, a rotated refresh
token is persisted, a 401 triggers one forced refresh and retry, and the `.env`
token is tried when the stored one is rejected. AH does expire refresh tokens
that sit **unused for weeks**, so keep the hourly job running; if every token is
rejected, re-run the login above. On docker compose run it inside the daemon
container so it lands on the shared volume:

```bash
docker compose exec dagster-daemon uv run python -m bonuschef.utils.ah_login "appie://login-exit?code=..."
```

Find your `AH_STORE_ID` by postal code via `storesSearch` (the default `1876`
is Eindhoven Torenallee).

The `daily_refresh` job runs once a day at **17:30 Amsterdam time**, pulling
the AH bonus feed and rebuilding every dbt model.

Because clearance discounts deepen through the day and sell out quickly, the
`markdowns_refresh` job runs hourly (11:00–20:00 **Amsterdam time**) and
**appends** each snapshot, so `fct_store_clearance_history` captures the
intraday markdown curve. `fct_store_clearance` shows only the items present in
the latest scrape, so sold-out items disappear as soon as a newer snapshot
lands. The portal's **Laatste kans** page has a **Refresh now** button that
launches the same job through the Dagster webserver (`DAGSTER_HOST`/`DAGSTER_PORT`)
and reloads the page when it finishes.

### 4. Start PostgreSQL

```bash
docker compose up -d
```

This starts a PostgreSQL 16 container on port **5455**.

All published ports - Postgres (5455), the Dagster UI (3000) and the portal
(8501) - bind to `127.0.0.1` only. Neither UI authenticates its callers and
the Dagster UI can launch and terminate jobs, so nothing answers on a
routable interface. To reach them from another machine, use Tailscale or an
SSH tunnel:

```bash
ssh -L 8501:127.0.0.1:8501 -L 3000:127.0.0.1:3000 user@your-host
```

Runs are serialised (`max_concurrent_runs: 1` in `dagster.yaml`): the daily
rebuild touches every dbt model, so an hourly clearance run that falls due
mid-rebuild queues rather than racing it.

## Usage

### Run the full pipeline via Dagster

```bash
dagster dev
```

Open the Dagster UI at [http://localhost:3000](http://localhost:3000). From there you can:

- **Start the sensor** &mdash; `github_commit_sensor` discovers new GitHub commits and registers them as dynamic partitions, triggering backfill runs automatically
- **Run `github_products` job** &mdash; backfills product data for specific partitions (commits)
- **Run `dbt_models` job** &mdash; materialises all dbt models (staging, intermediate, marts)

### Run dbt standalone

```bash
cd src/bonuschef/sql
dbt seed            # load recipe seeds (use --full-refresh after schema changes)
dbt run             # run all models
dbt test            # run schema tests
dbt build           # seed + run + test in one command
```

### Launch the portal

```bash
uv run streamlit run src/bonuschef/portal/app.py
```

The portal provides:

- **Table viewer** &mdash; browse any dbt-created table
- **Recipe cost over time** &mdash; line chart of total recipe cost per snapshot
- **Ingredient cost breakdown** &mdash; horizontal bar chart showing each ingredient's cost and percentage
- **Product price history** &mdash; line chart with top movers pre-selected and a product multi-select
- **Laatste kans** &mdash; current store clearance items with a **Refresh now** button (needs the Dagster webserver running)

## Development

### Linting & formatting

Uses [nox](https://nox.thea.codes/) to run sessions with [Ruff](https://docs.astral.sh/ruff/) (Python) and [SQLFluff](https://sqlfluff.com/) (SQL):

```bash
uv run nox -rs lint_python      # ruff check + format --diff
uv run nox -rs lint_sql         # sqlfluff lint (requires dbt parse)
uv run nox -rs format_python    # ruff check --fix + format
uv run nox -rs format_sql       # sqlfluff fix
uv run nox -rs mypy             # type checking
```

### Tests

```bash
uv run nox -rs tests            # pytest with coverage
# or directly
uv run pytest                   # fast, no coverage
uv run pytest --cov             # with coverage report
```

The suite runs without a database or network. It covers:

- **config** — env parsing and validation for every config dataclass
- **AH auth** — token exchange/refresh/GraphQL calls, the token file, and the
  auto-refresh manager (caching, rotation, fallback to `.env`, 401 retry)
- **dlt sources** — bonus pricing rules, pagination, dedupe, and the markdown
  feed mapping, iterated in-process with stubbed HTTP
- **GitHub helpers** — weekly commit selection (Monday-first fallback) and the
  snapshot source
- **Dagster** — the commit sensor against an ephemeral instance, plus a smoke
  test that the code location loads and each job selects the intended assets
  (`markdowns_refresh` touches only the clearance lineage) and schedules run in
  Amsterdam time
- **portal** — every page through Streamlit's `AppTest` with stubbed queries,
  including the Refresh-now flow (success, trigger error, failed run, timeout),
  plus the db helpers and chart guards

dbt models keep their schema tests in the `*.yml` files (`dbt test`, needs a
database).

### CI

GitHub Actions runs `lint_python`, `lint_sql`, `mypy`, and `tests` on pull requests to `main` and `develop`.

## Project structure

```
bonuschef/
├── src/bonuschef/
│   ├── config.py                      # GitHubConfig & DatabaseConfig dataclasses
│   ├── dags/
│   │   ├── definitions.py             # Dagster entry point (jobs, schedules in Europe/Amsterdam)
│   │   ├── constants.py
│   │   └── defs/
│   │       ├── assets/
│   │       │   ├── dlt/github/        # dlt GitHub product extraction
│   │       │   └── dbt/               # dbt asset definitions
│   │       ├── jobs/                   # all_assets_job, backfill_job, dbt_job
│   │       ├── sensors/               # github_commit_sensor
│   │       └── resources/             # dbt + database resources
│   ├── portal/
│   │   ├── app.py                     # Streamlit entry point
│   │   ├── db.py                      # Database queries
│   │   ├── dagster_client.py          # Trigger/poll Dagster jobs (Refresh now)
│   │   └── ui.py                      # Charts and UI components
│   ├── utils/
│   │   ├── ah_auth.py                 # AH member auth + auto-refreshing token store
│   │   └── ah_login.py                # One-time AH login bootstrap CLI
│   └── sql/
│       ├── dbt_project.yml
│       ├── seeds/                     # recipes.csv, recipe_ingredients.csv
│       └── models/
│           ├── staging/               # stg_ models
│           ├── intermediate/          # int_ models
│           └── marts/                 # dim_ and fct_ models
├── tests/                             # pytest suite (conftest + unit/)
├── docker-compose.yml                 # PostgreSQL 16
├── noxfile.py                         # lint, format, test sessions
├── pyproject.toml                     # dependencies & tool config
└── .github/workflows/ci.yml          # CI pipeline
```
