"""Definition of dbt resources."""

from dagster_dbt import DbtCliResource
from bonuschef.dags.defs.assets.dbt.dbt_project import project

dbt = DbtCliResource(project_dir=project)
