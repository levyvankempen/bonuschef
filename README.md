# 🍋 BonusChef Data Pipeline

This project builds a modern data stack around **Dagster**, **dlt**, and **dbt** to ingest and analyze supermarket product data.  
It extracts weekly JSON data from GitHub, loads it into PostgreSQL, and transforms it into analytical models (e.g., recipe cost tracking and historical price trends).

---

## Setup

### Clone the repository

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

## Environment Variables
Create a `.env` file in the project root and set the following variables:

```
# Postgres destination
DESTINATION__POSTGRES__CREDENTIALS__HOST="localhost"
DESTINATION__POSTGRES__CREDENTIALS__PORT=5455
DESTINATION__POSTGRES__CREDENTIALS__USERNAME="postgres"
DESTINATION__POSTGRES__CREDENTIALS__PASSWORD="postgres"
DESTINATION__POSTGRES__CREDENTIALS__DATABASE="postgres"

# Environment
ENVIRONMENT="default"

# GitHub source
GITHUB_TOKEN=""  # Optional, for higher API limits
GITHUB_OWNER="supermarkt"
GITHUB_REPO="checkjebon"
GITHUB_MESSAGE_FILTER="Update supermarkets.json"
GITHUB_START_DATE="2025-01-01T00:00:00Z"
GITHUB_BRANCH="main"
GITHUB_MAX_PAGES="2"
```

## Run the pipeline
Run the pipeline by first spinning up the requiered docker container and then running dagster dev.