"""All defined assets."""

from dagster import load_assets_from_package_module

from bonuschef.dags.defs.assets import dlt

dlt_assets = load_assets_from_package_module(dlt)