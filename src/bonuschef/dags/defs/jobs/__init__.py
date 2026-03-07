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

daily_refresh_job = define_asset_job(
    name="daily_refresh",
    selection=AssetSelection.assets("ah__bonus_products")
    | (AssetSelection.all() - AssetSelection.groups("dlt")),
)

__all__ = ["all_assets_job", "backfill_job", "dbt_job", "daily_refresh_job"]
