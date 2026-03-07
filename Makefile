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

clean:
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
