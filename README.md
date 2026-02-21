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
| **Staging** | `stg_github__products`, `stg_seeds__recipes`, `stg_seeds__recipe_ingredients` |
| **Intermediate** | `int_product_latest_price`, `int_recipe_items_resolved`, `int_recipe_items_priced` |
| **Marts** | `dim_product`, `dim_recipe`, `fct_products`, `fct_recipe_cost_history`, `fct_recipe_cost_latest`, `fct_recipe_cost_breakdown`, `fct_product_price_changes` |

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

Create a `.env` file in the project root:

```
# PostgreSQL
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
```

### 4. Start PostgreSQL

```bash
docker compose up -d
```

This starts a PostgreSQL 16 container on port **5455**.

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
uv run nox -rs tests
# or directly
pytest tests/
```

### CI

GitHub Actions runs `lint_python`, `lint_sql`, and `tests` on pull requests to `main` and `develop`.

## Project structure

```
bonuschef/
├── src/bonuschef/
│   ├── config.py                      # GitHubConfig & DatabaseConfig dataclasses
│   ├── dags/
│   │   ├── definitions.py             # Dagster entry point
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
│   │   └── ui.py                      # Charts and UI components
│   └── sql/
│       ├── dbt_project.yml
│       ├── seeds/                     # recipes.csv, recipe_ingredients.csv
│       └── models/
│           ├── staging/               # stg_ models
│           ├── intermediate/          # int_ models
│           └── marts/                 # dim_ and fct_ models
├── tests/unit/                        # pytest unit tests
├── docker-compose.yml                 # PostgreSQL 16
├── noxfile.py                         # lint, format, test sessions
├── pyproject.toml                     # dependencies & tool config
└── .github/workflows/ci.yml          # CI pipeline
```
