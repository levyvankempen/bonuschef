"""Dagster Jobs."""

from dagster import RetryPolicy, define_asset_job

all_assets_job = define_asset_job("all_assets", op_retry_policy=RetryPolicy(delay=120))

jobs = [all_assets_job]
