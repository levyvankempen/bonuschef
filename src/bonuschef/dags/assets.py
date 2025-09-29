import dlt

from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets
from .supermarket_pipeline import github_source


@dlt_assets(
    dlt_source=github_source(),
    dlt_pipeline=dlt.pipeline(
        pipeline_name="supermarket_pipeline",
        dataset_name="public",
        destination="postgres",
        progress="log",
    ),
    name="github",
    group_name="github",
)
def dagster_github_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)
