from dagster_duckdb import DuckDBResource

import dagster as dg

@dg.asset
def products(duckdb: DuckDBResource):
    url = "https://raw.githubusercontent.com/supermarkt/checkjebon/refs/heads/main/data/supermarkets.json"
    table_name = "products"
    
    with duckdb.get_connection() as conn:
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT *
            FROM read_json_auto('{url}')
        """)