"""All defined assets."""

from dagster import load_assets_from_package_module, load_assets_from_modules

from bonuschef.dags.defs.assets import dlt, dbt

dlt_assets = load_assets_from_package_module(dlt)
other_assets = load_assets_from_modules([dbt])
