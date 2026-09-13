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


def start_recipe_rebuild() -> bool:
    """Ask Dagster to recost the recipes. Never raises."""
    try:
        trigger_job(RECIPES_REBUILD_JOB)
    except DagsterTriggerError as exc:
        # A failed rebuild does not undo the recipe; say so rather than
        # implying the save went wrong.
        st.warning(
            f"Het recept is opgeslagen, maar de prijsberekening kon niet starten: {exc}"
        )
        return False
    return True
