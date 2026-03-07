"""Dagster schedules."""

from dagster import DefaultScheduleStatus, ScheduleDefinition

from bonuschef.dags.defs.jobs import daily_refresh_job

daily_refresh_schedule = ScheduleDefinition(
    job=daily_refresh_job,
    cron_schedule="0 6 * * *",  # Daily at 06:00 UTC
    default_status=DefaultScheduleStatus.RUNNING,
)
