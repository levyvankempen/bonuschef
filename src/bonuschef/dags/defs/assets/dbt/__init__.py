"""Dbt asset."""

from typing import Iterator

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

from bonuschef.dags.defs.assets.dbt.dbt_project import project


@dbt_assets(manifest=project.manifest_path)
def dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator:
    """All dbt assets."""
    yield from dbt.cli(
        ["build"],
        context=context,
    ).stream()
