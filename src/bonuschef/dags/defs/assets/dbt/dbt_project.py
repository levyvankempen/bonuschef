"""DBT Project setup."""

from pathlib import Path

from dagster_dbt import DbtProject

from bonuschef.dags.constants import ENVIRONMENT

project = DbtProject(
    project_dir=Path(__file__).joinpath("..", "..", "..", "..", "..", "sql").resolve(),
    profiles_dir=Path(__file__).joinpath("..", "..", "..", "..", "..", "sql").resolve(),
    target=ENVIRONMENT,
)
project.prepare_if_dev()
