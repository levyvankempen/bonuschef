"""Dagster schedules."""

from dagster import DefaultScheduleStatus, ScheduleDefinition

from bonuschef.dags.defs.jobs import daily_refresh_job, markdowns_refresh_job

daily_refresh_schedule = ScheduleDefinition(
    job=daily_refresh_job,
    cron_schedule="0 6 * * *",  # Daily at 06:00 UTC
    default_status=DefaultScheduleStatus.RUNNING,
)

# Clearance discounts appear from midday and deepen toward closing; capture the
# curve by scraping hourly through the afternoon/evening (11:00–20:00 UTC).
markdowns_refresh_schedule = ScheduleDefinition(
    job=markdowns_refresh_job,
    cron_schedule="0 11-20 * * *",
    default_status=DefaultScheduleStatus.RUNNING,
)
