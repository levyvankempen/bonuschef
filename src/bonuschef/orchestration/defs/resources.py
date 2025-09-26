from dagster_duckdb import DuckDBResource
from pathlib import Path

import dagster as dg

db_path = Path(__file__).resolve().parents[0] / "bonuschef_platform.duckdb"
database_resource = DuckDBResource(database=str(db_path))

@dg.definitions
def resources():
    return dg.Definitions(
        resources={
            "duckdb": database_resource,
        },
    )