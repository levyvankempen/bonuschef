"""Entry point for Dagster."""

from dagster import Definitions, load_assets_from_modules

from bonuschef.dags.defs.assets import all_assets
from bonuschef.dags.defs.jobs import (
    all_assets_job,
    backfill_job,
    daily_refresh_job,
    dbt_job,
    markdowns_refresh_job,
    token_heartbeat_job,
)
from bonuschef.dags.defs.resources.configured_resources import resources
from bonuschef.dags.defs.schedules import (
    daily_refresh_schedule,
    markdowns_refresh_schedule,
    token_heartbeat_schedule,
)
from bonuschef.dags.defs.sensors import (
    dbt_after_backfill_sensor,
    github_commit_sensor,
    run_failure_alert_sensor,
)

defs = Definitions(
    assets=load_assets_from_modules([all_assets]),
    resources=resources,
    jobs=[
        all_assets_job,
        backfill_job,
        dbt_job,
        daily_refresh_job,
        markdowns_refresh_job,
        token_heartbeat_job,
    ],
    schedules=[
        daily_refresh_schedule,
        markdowns_refresh_schedule,
        token_heartbeat_schedule,
    ],
    sensors=[
        github_commit_sensor,
        dbt_after_backfill_sensor,
        run_failure_alert_sensor,
    ],
)
