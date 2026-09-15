"""Dagster Jobs."""

from dagster import (
    AssetObservation,
    AssetSelection,
    MetadataValue,
    OpExecutionContext,
    RetryPolicy,
    define_asset_job,
    job,
    multiprocess_executor,
    op,
)

from bonuschef.utils.ah_auth import manager_from_env

all_assets_job = define_asset_job("all_assets", op_retry_policy=RetryPolicy(delay=120))

backfill_job = define_asset_job(
    name="github_products",
    selection="github__products",
    executor_def=multiprocess_executor.configured({"max_concurrent": 1}),
    op_retry_policy=RetryPolicy(max_retries=3, delay=120),
)

dbt_job = define_asset_job(
    name="dbt_models",
    selection=AssetSelection.all() - AssetSelection.groups("dlt"),
)

# Rebuilds every dbt model, so it is a superset of markdowns_refresh. Runs are
# serialised instance-wide (see dagster.yaml), which means this job can find the
# warehouse busy; retry rather than silently skipping a day's bonus feed.
daily_refresh_job = define_asset_job(
    name="daily_refresh",
    selection=AssetSelection.assets("ah__bonus_products")
    | (AssetSelection.all() - AssetSelection.groups("dlt")),
    op_retry_policy=RetryPolicy(max_retries=2, delay=120),
)

# The portal triggers this when a recipe is adopted, so it can finish its own
# work instead of printing `dbt run` for the user to type. Deliberately an asset
# job over models that already exist: adoption is one human act on one recipe,
# and a new asset would be swept into daily_refresh and re-run nightly.
recipes_rebuild_job = define_asset_job(
    name="recipes_rebuild",
    selection=AssetSelection.assets("int_recipe_items_resolved").downstream(),
    op_retry_policy=RetryPolicy(max_retries=2, delay=30),
)


# Clearance ("laatste kans koopjes") deepens through the day and sells out fast,
# so it runs on its own intraday cadence: scrape the store markdowns, then
# rebuild only the downstream clearance dbt models. The portal's "Refresh now"
# button triggers this same job by name (see portal/dagster_client.py).
markdowns_refresh_job = define_asset_job(
    name="markdowns_refresh",
    selection=AssetSelection.assets("ah__store_markdowns").downstream(),
    op_retry_policy=RetryPolicy(max_retries=2, delay=60),
)


# The recipe pool refreshes weekly and is never urgent, so it gets its own job
# rather than riding the nightly rebuild. Selecting the asset and its downstream
# keeps the opportunity marts in step with the pool that feeds them.
recipe_pool_refresh_job = define_asset_job(
    name="recipe_pool_refresh",
    selection=AssetSelection.assets("ah__recipe_pool").downstream(),
    # One retry. The pool is never urgent and the AH credential is the scarce
    # thing; retrying a rejected credential is how it gets burned.
    op_retry_policy=RetryPolicy(max_retries=1, delay=120),
)


# The AH member refresh credential expired twice from disuse: the clearance
# scrape was the only thing that ever refreshed it, so whenever the stack sat
# idle - or the scrape broke for an unrelated reason - AH eventually rejected it
# and recovery needed an interactive browser login behind hCaptcha. This job
# exists purely to keep the credential in use, independently of any pipeline.
@op(description="Force an AH token refresh so the refresh credential stays in use.")
def refresh_ah_credential(context: OpExecutionContext) -> None:
    # refresh_now(), not get_access_token(force_refresh=True): the latter returns
    # a bare string and could not report rotation or age. An AHAuthError is
    # deliberately left to propagate - a dead credential must fail the run so the
    # failure sensor sees it.
    outcome = manager_from_env().refresh_now()
    age_days = (
        None if outcome.credential_age_s is None else outcome.credential_age_s / 86_400
    )
    # An observation rather than output metadata: it is indexed by asset key, so
    # `instance.fetch_observations` returns the whole series and the UI plots the
    # numeric values over time. That series is the evidence for whether AH's
    # refresh expiry is sliding or absolute.
    context.log_event(
        AssetObservation(
            asset_key="ah_refresh_credential",
            metadata={
                "rotated": outcome.rotated,
                "used_env_fallback": outcome.used_fallback,
                "credential_age_days": (
                    MetadataValue.null()
                    if age_days is None
                    else MetadataValue.float(round(age_days, 2))
                ),
            },
        )
    )
    context.log.info(
        "AH credential refreshed (rotated=%s, age_days=%s, env_fallback=%s)",
        outcome.rotated,
        "unknown" if age_days is None else round(age_days, 2),
        outcome.used_fallback,
    )


@job(
    name="token_heartbeat",
    description="Keeps the AH member refresh credential alive between scrapes.",
    # Op-level retries happen inside the run, so a transient AH 5xx costs one
    # extra minute and still emits exactly one RUN_FAILURE if it never recovers.
    op_retry_policy=RetryPolicy(max_retries=2, delay=60),
)
def token_heartbeat_job() -> None:
    refresh_ah_credential()


__all__ = [
    "all_assets_job",
    "backfill_job",
    "dbt_job",
    "daily_refresh_job",
    "markdowns_refresh_job",
    "recipe_pool_refresh_job",
    "recipes_rebuild_job",
    "refresh_ah_credential",
    "token_heartbeat_job",
]
