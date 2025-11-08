"""Dagster Jobs."""

from dagster import RetryPolicy, define_asset_job, multiprocess_executor

all_assets_job = define_asset_job("all_assets", op_retry_policy=RetryPolicy(delay=120))

backfill_job = define_asset_job(
    name="github_products",
    selection="github__products",
    executor_def=multiprocess_executor.configured({"max_concurrent": 1}),
    op_retry_policy=RetryPolicy(max_retries=3, delay=120),
)

__all__ = ["all_assets_job", "backfill_job"]
