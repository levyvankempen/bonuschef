"""Starting a recipe cost rebuild from the portal.

Deliberately fire-and-forget. The clearance page blocks on its refresh and that
is right there — you pressed the button *to see today's list*, and the wait is
the task. Adopting a recipe is the opposite: the recipe exists the moment it is
written, and the cost is derived. Blocking for a minute per recipe would make
adding twenty of them a half-hour vigil, which is the `dbt run` failure again
with better typography.
"""

from __future__ import annotations

import streamlit as st

from bonuschef.portal.dagster_client import DagsterTriggerError, trigger_job

RECIPES_REBUILD_JOB = "recipes_rebuild"
MARKDOWNS_JOB = "markdowns_refresh"


def start_recipe_rebuild() -> str | None:
    """Ask Dagster to recost the recipes. Never raises.

    Returns the run id so a caller can tell someone how it is getting on.
    Fire-and-forget does not mean say-nothing: the work is asynchronous, but a
    person who has just corrected six ingredients needs to know that a
    recalculation is running and that the page will change when it finishes.
    """
    try:
        return trigger_job(RECIPES_REBUILD_JOB)
    except DagsterTriggerError as exc:
        # A failed rebuild does not undo the recipe; say so rather than
        # implying the save went wrong.
        st.warning(
            f"Het recept is opgeslagen, maar de prijsberekening kon niet starten: {exc}"
        )
        return None


def start_store_first_scrape() -> str | None:
    """Ask Dagster to scrape clearance now, for a shop it has never seen.

    markdowns_refresh reads the shops to scrape from the accounts, so a new one
    needs no configuration - only a run. Without this, somebody who signs up and
    picks a shop nobody else uses sees an empty Laatste kans until the next
    hourly scrape happens to come round, which is the first visit and the one
    that decides whether they come back.

    Fire-and-forget, like the recipe rebuild above, and for the same reason: the
    shop is saved the moment it is chosen and the koopjes are derived. Blocking
    the profile page for a minute would be worse than an explained wait.
    """
    try:
        return trigger_job(MARKDOWNS_JOB)
    except DagsterTriggerError:
        # The shop is the person's choice and is saved either way. Only the
        # promise about when data arrives changes, so that is what is said -
        # not that something went wrong with the save.
        st.info(
            "Je winkel is opgeslagen. De koopjes van deze winkel verschijnen "
            "bij de volgende ronde, binnen het uur."
        )
        return None
