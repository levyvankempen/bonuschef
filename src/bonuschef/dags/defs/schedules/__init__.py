"""Dagster schedules."""

from dagster import DefaultScheduleStatus, ScheduleDefinition

from bonuschef.dags.defs.jobs import (
    daily_refresh_job,
    markdowns_refresh_job,
    recipe_pool_refresh_job,
    token_heartbeat_job,
)

# Store hours are Dutch local time, so schedules are too (DST-aware).
LOCAL_TIMEZONE = "Europe/Amsterdam"

daily_refresh_schedule = ScheduleDefinition(
    job=daily_refresh_job,
    cron_schedule="30 17 * * *",  # Daily at 17:30 Amsterdam time
    execution_timezone=LOCAL_TIMEZONE,
    default_status=DefaultScheduleStatus.RUNNING,
)

# Clearance discounts appear from midday and deepen toward closing; capture the
# curve by scraping hourly through the afternoon/evening (11:00–20:00 local).
markdowns_refresh_schedule = ScheduleDefinition(
    job=markdowns_refresh_job,
    cron_schedule="0 11-20 * * *",
    execution_timezone=LOCAL_TIMEZONE,
    default_status=DefaultScheduleStatus.RUNNING,
)

# Twice daily, so one missed cycle still leaves margin against the 24h access
# token cap. 03:30/15:30 deliberately avoids the :00 clearance scrapes, the 17:30
# rebuild, and the 02:00-03:00 window that does not exist on the spring-forward
# day. Independent of the data schedules by design: retiming those must not stop
# the credential being exercised.
token_heartbeat_schedule = ScheduleDefinition(
    job=token_heartbeat_job,
    cron_schedule="30 3,15 * * *",
    execution_timezone=LOCAL_TIMEZONE,
    default_status=DefaultScheduleStatus.RUNNING,
)

# Weekly, at 04:00 on Monday. Three constraints pick that slot and each matters:
# it is after the 03:30 credential heartbeat has already proven the credential,
# so the crawl is never what discovers a dead one; it is outside the 11:00-20:00
# clearance window, which is unbackfillable and therefore has absolute priority;
# and runs are serialised instance-wide, so a long job here would otherwise hold
# the only slot while a clearance scrape was due.
recipe_pool_refresh_schedule = ScheduleDefinition(
    job=recipe_pool_refresh_job,
    cron_schedule="0 4 * * 1",
    execution_timezone=LOCAL_TIMEZONE,
    default_status=DefaultScheduleStatus.RUNNING,
)
