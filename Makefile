.PHONY: build up up-build down restart logs logs-dagster logs-daemon logs-streamlit logs-postgres ps clean shell-dagster shell-streamlit dbt-run dbt-build

build:
	docker compose build

up:
	docker compose up -d

up-build:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-dagster:
	docker compose logs -f dagster-webserver

logs-daemon:
	docker compose logs -f dagster-daemon

logs-streamlit:
	docker compose logs -f streamlit

logs-postgres:
	docker compose logs -f postgres

ps:
	docker compose ps

# Reclaim disk without touching data. Each `up --build` orphans the previous
# image layers and BuildKit cache, and the deployment guide requires a rebuild
# after any dbt ref() change - so this is the routine one.
prune:
	docker image prune -af
	docker builder prune -f

# Named for what it does. `down -v` destroys pg_data and dagster_home: the
# append-only markdown curve that AH cannot re-serve, every hand-confirmed
# ingredient resolution, and ah_tokens.json - whose only other recovery is an
# interactive browser login behind hCaptcha. It used to be called `clean` and
# sat directly under `down`, one tab-completion from the worst outcome here.
destroy-everything:
	@printf 'This deletes the database and the AH credential. Type DESTROY to confirm: ' \
		&& read ans && [ "$$ans" = "DESTROY" ] || { echo "aborted"; exit 1; }
	docker compose down -v
	docker image prune -f

shell-dagster:
	docker compose exec dagster-webserver bash

shell-streamlit:
	docker compose exec streamlit bash

dbt-run:
	docker compose exec dagster-webserver uv run dbt run --project-dir src/bonuschef/sql --profiles-dir src/bonuschef/sql

dbt-build:
	docker compose exec dagster-webserver uv run dbt build --project-dir src/bonuschef/sql --profiles-dir src/bonuschef/sql
