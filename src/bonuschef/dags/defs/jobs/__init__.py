"""Dagster Jobs."""

from dagster import AssetSelection, RetryPolicy, define_asset_job, multiprocess_executor

all_assets_job = define_asset_job("all_assets", op_retry_policy=RetryPolicy(delay=120))

backfill_job = define_asset_job(
    name="github_products",
    selection="github__products",
    executor_def=multiprocess_executor.configured({"max_concurrent": 1}),
    op_retry_policy=RetryPolicy(max_retries=3, delay=120),
)

dbt_job = define_asset_job(
    name="dbt_models",
    selection=AssetSelection.all() - AssetSelection.groups("dlt"),
)

# Rebuilds every dbt model, so it is a superset of markdowns_refresh. Runs are
# serialised instance-wide (see dagster.yaml), which means this job can find the
# warehouse busy; retry rather than silently skipping a day's bonus feed.
daily_refresh_job = define_asset_job(
    name="daily_refresh",
    selection=AssetSelection.assets("ah__bonus_products")
    | (AssetSelection.all() - AssetSelection.groups("dlt")),
    op_retry_policy=RetryPolicy(max_retries=2, delay=120),
)

# Clearance ("laatste kans koopjes") deepens through the day and sells out fast,
# so it runs on its own intraday cadence: scrape the store markdowns, then
# rebuild only the downstream clearance dbt models. The portal's "Refresh now"
# button triggers this same job by name (see portal/dagster_client.py).
markdowns_refresh_job = define_asset_job(
    name="markdowns_refresh",
    selection=AssetSelection.assets("ah__store_markdowns").downstream(),
    op_retry_policy=RetryPolicy(max_retries=2, delay=60),
)

__all__ = [
    "all_assets_job",
    "backfill_job",
    "dbt_job",
    "daily_refresh_job",
    "markdowns_refresh_job",
]
