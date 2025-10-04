"""All configured Dagster resources."""

from dagster_dlt import DagsterDltResource
from bonuschef.dags.defs.resources.dbt import dbt

resources = {
    "dlt": DagsterDltResource(),
    "dbt": dbt,
}
