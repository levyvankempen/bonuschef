from ..dags import assets

from dagster import Definitions, load_assets_from_modules
from dagster_dlt import DagsterDltResource

dlt_resource = DagsterDltResource()
all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={"dlt": dlt_resource},
)
